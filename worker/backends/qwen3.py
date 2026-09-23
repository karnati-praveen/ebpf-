"""Qwen3 pipeline backend: this worker holds decoder layers [start, end) of a
Qwen3 causal LM. The first stage embeds token ids; the last stage applies the
final RMSNorm and LM head and returns the greedy next token.

Two execution modes, selected by KV_CACHE (must match the router's setting):

  KV_CACHE=0 (default)  Stateless. Every step recomputes the full accumulated
                        context. Token-identical to single-process decoding and
                        the correctness reference -- but decode cost grows with
                        context, and a repartition costs nothing extra because
                        everything is recomputed anyway.

  KV_CACHE=1            Cached. Step 0 prefills the full context and builds a
                        per-request KV cache for this shard's layers; later
                        steps process one new position. A repartition makes the
                        router replay from step 0 under a new request id, which
                        rebuilds the cache -- that replay IS the reconstruction
                        cost the study measures.

A router/worker mode mismatch is detected and rejected rather than silently
producing wrong tokens: a cached worker refuses a multi-position decode step,
and a stateless worker refuses a step shorter than the context must be.

Rotary position embeddings are computed per shard from absolute positions --
the session's processed-token count in cached mode, 0..n-1 in stateless mode --
never from the local tensor's shape. That is what keeps positions correct
across a shard boundary.

Attention runs under SDPA with no explicit mask: SDPA applies a causal mask
whenever there is more than one query position and no mask, which is correct
for prefill from an empty cache (the only multi-position case here) and for
stateless full-context steps. A single decode position attends to the whole
cache, which needs no mask. Eager attention would ignore causality without a
mask, so SDPA is enforced at load time.
"""

import gc
import logging
import os
import threading
import time
import urllib.request

import numpy as np
import pipeline_pb2 as pb

log = logging.getLogger("qwen3")


def _kv_cache_enabled():
    return os.environ.get("KV_CACHE", "0") == "1"


class _ShardCache:
    """Minimal per-request KV cache for this shard's layers.

    Duck-types the one method Qwen3Attention calls, update(k, v, layer_idx),
    and concatenates along the sequence axis exactly as transformers'
    DynamicCache does, so per-token cost matches the single-process baseline.
    Keys are GLOBAL layer indices, which is what each attention module holds.
    """

    def __init__(self):
        self.k = {}
        self.v = {}

    def update(self, key_states, value_states, layer_idx, *args, **kwargs):
        import torch

        if layer_idx in self.k:
            self.k[layer_idx] = torch.cat([self.k[layer_idx], key_states], dim=-2)
            self.v[layer_idx] = torch.cat([self.v[layer_idx], value_states], dim=-2)
        else:
            self.k[layer_idx] = key_states
            self.v[layer_idx] = value_states
        return self.k[layer_idx], self.v[layer_idx]

    def nbytes(self):
        return sum(t.element_size() * t.nelement() for t in self.k.values()) + sum(
            t.element_size() * t.nelement() for t in self.v.values()
        )


class _Session:
    def __init__(self):
        self.cache = _ShardCache()
        self.past_len = 0      # positions already in the cache
        self.next_step = 0     # step number expected on the next forward
        self.last_used = time.monotonic()


class _SpeedProbe:
    """Measures this shard's compute speed relative to a reference profile.

    For each cached decode step the per-layer time is compared with what the
    reference profile predicts at that context length:

        sample = expected_ms_per_layer(ctx) / observed_ms_per_layer

    so 1.0 means "as fast as the profiled machine", 0.5 means half as fast.
    Samples are smoothed (EWMA) and pushed to the co-located node agent, which
    reports them as the speed factor the controller partitions with. Only the
    decoder-layer loop is timed; endpoint modules have their own cost terms.

    Configure with PER_LAYER_PROFILE="ctx:ms,ctx:ms,..." (the measured decode
    table) and NODE_AGENT_ADDR=host:port. Without a profile nothing is
    measured and the controller sees speed 1.
    """

    ALPHA = 0.2
    # Push only while samples are fresh, and restart the average after a gap.
    # Otherwise an idle worker would keep re-sending the speed it measured
    # under a fault that has since been cleared, and the next experiment run
    # would start by partitioning around a fault that no longer exists. Once
    # pushes stop, the node agent's own staleness returns speed to 1.
    PUSH_FRESH_S = 5.0
    RESET_AFTER_S = 10.0

    def __init__(self):
        self.table = []
        raw = os.environ.get("PER_LAYER_PROFILE", "")
        for part in filter(None, raw.split(",")):
            ctx, ms = part.split(":")
            self.table.append((int(ctx), float(ms)))
        self.table.sort()
        self.agent = os.environ.get("NODE_AGENT_ADDR", "")
        self.ewma = None
        self.last_sample = 0.0
        self.lock = threading.Lock()
        if self.table and self.agent:
            threading.Thread(target=self._push_loop, daemon=True).start()
            log.info("speed probe on: profile=%s agent=%s", self.table, self.agent)

    def enabled(self):
        return bool(self.table)

    def expected(self, ctx):
        t = self.table
        if ctx <= t[0][0]:
            return t[0][1]
        if ctx >= t[-1][0]:
            return t[-1][1]
        for (c0, m0), (c1, m1) in zip(t, t[1:]):
            if ctx <= c1:
                return m0 + (m1 - m0) * (ctx - c0) / (c1 - c0)
        return t[-1][1]

    def observe(self, ctx, elapsed_ms, n_layers):
        if not self.table or n_layers <= 0 or elapsed_ms <= 0:
            return
        sample = self.expected(ctx) / (elapsed_ms / n_layers)
        now = time.monotonic()
        with self.lock:
            if self.ewma is None or now - self.last_sample > self.RESET_AFTER_S:
                self.ewma = sample
            else:
                self.ewma = self.ALPHA * sample + (1 - self.ALPHA) * self.ewma
            self.last_sample = now

    def _push_loop(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                v = self.ewma
                fresh = time.monotonic() - self.last_sample < self.PUSH_FRESH_S
            if v is None or not fresh:
                continue
            try:
                url = f"http://{self.agent}/gpu?measured_speed={v:.4f}"
                with urllib.request.urlopen(url, timeout=0.3) as r:
                    r.read()
            except Exception:
                pass  # telemetry is best-effort; never disturb inference


def _pick_device():
    import torch

    want = os.environ.get("WORKER_DEVICE", "auto").lower()
    if want == "cpu":
        return "cpu"
    if want == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("WORKER_DEVICE=cuda but torch.cuda.is_available() is False")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


class Qwen3Backend:
    def __init__(self, model_name):
        self.model_name = model_name
        self.start = self.end = self.total = -1
        self.layers = None
        self.device = "cpu"
        self.cached = _kv_cache_enabled()
        self.max_sessions = int(os.environ.get("KV_MAX_SESSIONS", "16"))
        self.session_ttl_s = float(os.environ.get("KV_SESSION_TTL_S", "300"))
        self.sessions = {}
        self.sessions_lock = threading.Lock()
        self.probe = _SpeedProbe()

    def load(self, start, end, total):
        if (start, end, total) == (self.start, self.end, self.total):
            return
        import torch
        from transformers import AutoModelForCausalLM

        self.device = _pick_device()
        if os.environ.get("TORCH_THREADS"):
            torch.set_num_threads(int(os.environ["TORCH_THREADS"]))
        log.info("loading %s layers [%d, %d) of %d on device=%s kv_cache=%s threads=%d",
                  self.model_name, start, end, total, self.device, self.cached,
                  torch.get_num_threads())
        dtype = torch.float16 if self.device == "cuda" else torch.float32
        # Free the previous shard BEFORE loading, so a relayout's peak memory
        # is one full model rather than one full model plus the old shard.
        # Every cached session is invalid for the new layers anyway.
        self.layers = self.embed = self.norm = self.lm_head = self.rotary = None
        with self.sessions_lock:
            self.sessions.clear()
        gc.collect()
        # Loads the full model, keeps this shard's modules, and frees the rest.
        # Peak memory is therefore the full model during load. Acceptable for
        # Qwen3-0.6B (~2.4 GB FP32); a larger tier would need per-tensor
        # loading of only the assigned weights.
        model = AutoModelForCausalLM.from_pretrained(
            self.model_name, dtype=dtype, attn_implementation="sdpa"
        )
        model.eval()
        model.to(self.device)
        if model.config._attn_implementation != "sdpa":
            raise RuntimeError("Qwen3 backend requires SDPA attention for implicit causal masking")
        inner = model.model
        if total != len(inner.layers):
            raise ValueError(f"model has {len(inner.layers)} layers, pipeline says {total}")

        self.is_first = start == 0
        self.is_last = end >= total
        self.layers = [inner.layers[i] for i in range(start, end)]
        self.rotary = inner.rotary_emb  # buffers only; every stage needs its own
        self.embed = inner.embed_tokens if self.is_first else None
        self.norm = inner.norm if self.is_last else None
        # Qwen3-0.6B ties lm_head to embed_tokens: they are the same Parameter.
        # Holding the module keeps the shared tensor alive after `model` is
        # dropped; a stage that is both first and last holds it once.
        self.lm_head = model.lm_head if self.is_last else None
        self.dtype = dtype
        self.start, self.end, self.total = start, end, total

        # A cache is only valid for the layers that built it.
        with self.sessions_lock:
            self.sessions.clear()

        del model, inner
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()

    # ---- session management (cached mode) --------------------------------

    def _evict_locked(self, now):
        for rid in [r for r, s in self.sessions.items() if now - s.last_used > self.session_ttl_s]:
            del self.sessions[rid]
        while len(self.sessions) > self.max_sessions:
            oldest = min(self.sessions, key=lambda r: self.sessions[r].last_used)
            del self.sessions[oldest]

    def _session_for(self, req, n_new):
        """Return (session, error). Enforces the step protocol so duplicate or
        out-of-order forwards are rejected instead of corrupting the cache."""
        now = time.monotonic()
        with self.sessions_lock:
            self._evict_locked(now)
            if req.step == 0:
                # Prefill always starts a fresh cache. A repeated step 0 for the
                # same id replaces the session rather than appending to it.
                sess = _Session()
                self.sessions[req.request_id] = sess
            else:
                sess = self.sessions.get(req.request_id)
                if sess is None:
                    return None, "kv cache miss: no session for request (evicted, restarted or relaid out)"
                if req.step != sess.next_step:
                    return None, f"kv cache step mismatch: expected step {sess.next_step}, got {req.step}"
                if n_new != 1:
                    return None, (f"kv cache protocol error: decode step {req.step} carried {n_new} "
                                  "positions, expected 1 (is the router running with KV_CACHE=0?)")
            sess.last_used = now
            return sess, None

    def cache_stats(self):
        with self.sessions_lock:
            return len(self.sessions), sum(s.cache.nbytes() for s in self.sessions.values())

    # ---- forward ----------------------------------------------------------

    def forward(self, req):
        import torch

        with torch.no_grad():
            if self.is_first:
                if not req.input_ids:
                    return pb.ForwardReply(error="first stage requires input_ids")
                ids = torch.tensor([list(req.input_ids)], dtype=torch.long, device=self.device)
                h = self.embed(ids)
            else:
                if not req.hidden:
                    return pb.ForwardReply(error="non-first stage requires hidden")
                arr = np.frombuffer(req.hidden, dtype=np.float32).reshape(tuple(req.shape))
                h = torch.from_numpy(arr.copy()).to(self.device)
            h = h.to(self.dtype)  # activations travel as fp32 on the wire
            n_new = h.shape[1]

            if self.cached:
                sess, err = self._session_for(req, n_new)
                if err:
                    return pb.ForwardReply(error=err)
                past = sess.past_len
                cache = sess.cache
            else:
                # Stateless: the request must carry the whole context. Step s
                # of a prompt of length p has p + s >= s + 1 positions.
                if req.step > 0 and n_new < req.step + 1:
                    return pb.ForwardReply(error=(
                        f"stateless worker got {n_new} positions at step {req.step}; "
                        "is the router running with KV_CACHE=1?"))
                past = 0
                cache = None

            if n_new > 1 and past != 0:
                return pb.ForwardReply(error="multi-position step with a non-empty cache is unsupported")

            position_ids = torch.arange(past, past + n_new, dtype=torch.long,
                                        device=self.device).unsqueeze(0)
            position_embeddings = self.rotary(h, position_ids)

            t_layers = time.perf_counter()
            for layer in self.layers:
                out = layer(
                    h,
                    attention_mask=None,
                    position_ids=position_ids,
                    past_key_values=cache,
                    use_cache=cache is not None,
                    position_embeddings=position_embeddings,
                )
                # transformers >=5 returns a tensor, <5 a tuple
                h = out[0] if isinstance(out, tuple) else out

            if self.cached:
                # Only single-position decode steps are comparable to the
                # decode profile; prefill has a different per-token cost.
                if n_new == 1 and self.probe.enabled():
                    if self.device == "cuda":
                        torch.cuda.synchronize()  # kernels are async; time real work
                    self.probe.observe(past + 1, (time.perf_counter() - t_layers) * 1000.0,
                                       len(self.layers))
                sess.past_len = past + n_new
                sess.next_step = req.step + 1

            if self.is_last:
                h = self.norm(h[:, -1:, :])
                logits = self.lm_head(h[:, -1, :])
                return pb.ForwardReply(next_token=int(logits.argmax().cpu()), is_last=True)

        out = h.float().cpu().numpy().astype(np.float32)
        return pb.ForwardReply(hidden=out.tobytes(), shape=list(out.shape))
