"""GPT-2 pipeline backend: this worker holds transformer blocks
[start, end) of the model. The first stage embeds token ids; the last stage
applies the final layer norm and LM head and returns the greedy next token.

Workers are stateless (full-context recompute each step): output is
token-identical to single-process greedy decoding, and a mid-request
repartition needs no KV-cache migration — the router simply resends the
accumulated context to the new chain.
"""

import gc
import logging
import os

import numpy as np
import pipeline_pb2 as pb

log = logging.getLogger("gpt2")


def _pick_device():
    """WORKER_DEVICE=cuda|cpu|auto (default auto: use a GPU if the runtime
    can see one, e.g. via nvidia-container-toolkit passthrough on a real
    machine; falls back to cpu silently on kind/codespace where there is
    none). Explicit values fail loudly instead of silently falling back, so
    a misconfigured GPU node doesn't quietly benchmark on CPU."""
    import torch

    want = os.environ.get("WORKER_DEVICE", "auto").lower()
    if want == "cpu":
        return "cpu"
    if want == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("WORKER_DEVICE=cuda but torch.cuda.is_available() is False "
                                "(missing NVIDIA driver passthrough or a CPU-only torch wheel?)")
        return "cuda"
    return "cuda" if torch.cuda.is_available() else "cpu"


class GPT2Backend:
    def __init__(self, model_name):
        self.model_name = model_name
        self.start = self.end = self.total = -1
        self.blocks = None
        self.device = "cpu"

    def load(self, start, end, total):
        if (start, end, total) == (self.start, self.end, self.total):
            return
        import torch
        from transformers import GPT2LMHeadModel

        self.device = _pick_device()
        if self.device == "cpu":
            torch.set_num_threads(1)
        log.info("loading %s blocks [%d, %d) of %d on device=%s",
                  self.model_name, start, end, total, self.device)
        model = GPT2LMHeadModel.from_pretrained(self.model_name)
        model.eval()
        model.to(self.device)
        t = model.transformer
        if total != len(t.h):
            raise ValueError(f"model has {len(t.h)} blocks, pipeline says {total}")

        self.is_first = start == 0
        self.is_last = end >= total
        self.blocks = [t.h[i] for i in range(start, end)]
        self.wte = t.wte if self.is_first else None
        self.wpe = t.wpe if self.is_first else None
        self.ln_f = t.ln_f if self.is_last else None
        self.lm_head = model.lm_head if self.is_last else None
        self.start, self.end, self.total = start, end, total

        del model, t
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()

    def forward(self, req):
        import torch

        with torch.no_grad():
            if self.is_first:
                if not req.input_ids:
                    return pb.ForwardReply(error="first stage requires input_ids")
                ids = torch.tensor([list(req.input_ids)], dtype=torch.long, device=self.device)
                pos = torch.arange(ids.shape[1], dtype=torch.long, device=self.device)
                h = self.wte(ids) + self.wpe(pos)
            else:
                if not req.hidden:
                    return pb.ForwardReply(error="non-first stage requires hidden")
                arr = np.frombuffer(req.hidden, dtype=np.float32).reshape(tuple(req.shape))
                h = torch.from_numpy(arr.copy()).to(self.device)

            for block in self.blocks:
                out = block(h)
                # transformers <5 returns a tuple, >=5 a plain tensor
                h = out[0] if isinstance(out, tuple) else out

            if self.is_last:
                h = self.ln_f(h)
                logits = self.lm_head(h[:, -1, :])
                return pb.ForwardReply(next_token=int(logits.argmax().cpu()), is_last=True)

        out = h.cpu().numpy().astype(np.float32)
        return pb.ForwardReply(hidden=out.tobytes(), shape=list(out.shape))
