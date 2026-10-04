# How strong is the novelty? An honest assessment

> **Research update (2026-09-23):** See
> [`NOVELTY_RESEARCH_2026-09-23.md`](NOVELTY_RESEARCH_2026-09-23.md) before
> using the claims below. The broad “first real-machine measurement” wording
> is too strong: EdgeShard used a physical prototype, and other systems have
> implemented live inference migration. EdgeFlow (ICDCS 2026) also studies
> transfer and recomputation of KV state on a real edge platform. The 77.9 s
> break-even value is a model prediction from measured components, not an
> observed distributed crossover. The updated memo narrows the candidate
> contribution and sets out the experiments needed to establish it.

Written 2026-09-23, before the Azure VM experiments. Everything below is based
on what is built and verified in this repo, and on the prior work we have
actually read. Nothing here is a result we have not measured.

---

## Short answer

**The novelty is real, but it is empirical rather than algorithmic.** It is
enough for a paper at a good workshop or conference **if the VM experiments
produce clear results**, whether those results are positive or negative. Without
those experiments it is not enough, because the idea by itself is not new.

| Question | Answer |
|---|---|
| Is the *idea* (online repartitioning that accounts for migration cost) new? | **No.** arXiv 2505.02533 already does this, including KV cache in the migration cost. |
| Is *measuring it on real machines* new? | **Yes, as far as we know.** 2505.02533 is simulation only, and it names real testbeds as its own future work. |
| Is there a publishable paper here? | **Yes, if Phase 6 produces clean data.** A measured answer to "when does repartitioning pay?" is the contribution. |
| What is the biggest risk? | The effect is smaller than the noise with 2 VMs and a 0.6B model, which gives inconclusive results. |

**Overall novelty: moderate (about 6/10).** Strong measured results would raise
it to about 7/10. A weak or ambiguous dataset would drop it to workshop level.

---

## 1. What is NOT novel (do not claim these)

| Claim | Why not |
|---|---|
| "First online / dynamic repartitioning of LLM layers" | 2505.02533 and Petals |
| "First migration-cost-aware repartitioning" | 2505.02533 (migration size includes K/V cache) |
| "First to use DP for layer placement" | EdgeShard, PipeEdge, Galaxy |
| "Context length makes transitions costlier, and nobody models it" | 2505.02533's migration size grows with K/V cache |
| "Runs without Kubernetes" | Engineering convenience, not a research contribution |
| "No prior system does X" | Not allowed without a full literature check |

A reviewer who knows 2505.02533 would reject the paper if it made any of these
claims.

---

## 2. What IS novel (the actual contributions)

### C1. Measured break-even horizon on real machines. **Primary contribution**
- **What it is:** a measurement, not a prediction, of when moving layers pays
  off, as a function of context length. The break-even horizon is
  H* = T · current / (current − optimal).
- **Why it is new:** the closest work, 2505.02533, samples its parameters
  (compute from a log-normal distribution, bandwidth uniformly between 1 and
  10 Gbps) and simulates. We measure real reload time, real KV reconstruction
  time and real throughput.
- **What we already have:** for a 0.7× slowdown at ctx 2048, the break-even is
  **77.9 s**. The naive estimate is 26.4 s, because it ignores that
  reconstruction replays the whole chain.
- **Strength: moderate to strong**, depending on Phase 6. This is the headline.

### C2. A cost-modelling finding: endpoint modules are large
- The LM head plus the final norm cost **33–49 % of a 14-layer stage**.
- A layer-proportional model therefore picks the wrong split by **10.7–15 %**.
- Per-layer decode cost rises **+71 %** from ctx 128 to ctx 2048.
- **Strength: moderate.** It is a solid and useful measurement, but a finding
  about modelling, not a new idea. We must not claim that others omit it.

### C3. A transition gate evaluated against its counterfactual
- There are three policy arms: no hysteresis, hysteresis, and hysteresis plus
  the gate.
- The **`gate-force`** arm makes the same decisions as the gate but always
  moves, so we can observe what would have happened after the moves the gate
  rejected.
- Most papers never show whether their "don't move" decisions were right.
- **Strength: moderate.** The design is careful. How much it is worth depends on
  whether the gate actually beats plain hysteresis (H2b).

### C4. Does kernel (eBPF) telemetry help? (H3)
- **Early observation:** on RPC traffic, kernel sRTT read ~11 ms while
  application transport time read 4.5–8.2 ms. A likely cause is that the kernel
  RTT sample absorbs server compute time through the delayed/piggybacked ACK.
- If this is confirmed on the VMs, it is an **interesting, non-obvious finding**:
  "kernel RTT on an inference pipeline does not measure the network".
- **Strength: uncertain, but potentially the most surprising result.** A null
  result is still reportable, because the criterion is pre-registered.

### C5. Correctness under repartitioning
- Logits match HuggingFace to max |Δ| **2.2e-5** across 12 configurations.
- A repartition in the middle of a request produces **identical tokens**.
- **Strength: low as novelty, high as credibility.** Simulation papers cannot
  show this. It makes reviewers trust the other results.

---

## 3. Side by side (short version)

| | EdgeShard | 2505.02533 | **Ours** |
|---|---|---|---|
| Repartitions online | no | yes | yes |
| Models migration cost | no | yes (transfer, incl. KV) | yes (reload + full-chain replay, **measured**) |
| Parameters | profiled | **sampled** | **measured live** |
| Evaluated on | real devices | **simulator** | **real machines** |
| Faults tested | — | background load | compute cap, contention, network delay, device loss |
| Checks whether "don't move" was right | — | — | **yes (gate-force)** |
| Output correctness verified | — | n/a | **yes, token-identical** |

(EdgeShard cells still need to be re-checked against the paper before
submission; see `docs/NOVELTY_AND_ABLATIONS.md`.)

---

## 4. What decides whether the paper is accepted

The novelty is in the **answer**, so the paper stands or falls on the data.

| Phase 6 outcome | Paper strength |
|---|---|
| Clear crossover: adaptation helps above some horizon or fault size and hurts below it, and the model predicts where | **Strong.** A clean "when does it pay" story. |
| Adaptation never pays at this scale, and the cost model explains why | **Still publishable** as a negative result with an explanation. This was stated before running, so it is not spin. |
| eBPF sRTT confound is confirmed | A strong extra finding, whatever H1 shows. |
| Results are inconclusive because the effect is below the noise | **Weak.** At best a workshop paper. §2 of the research plan (fault-magnitude gate) exists to catch this early. |

---

## 5. Honest weaknesses a reviewer will raise

1. **Scale:** 2–3 VMs and a 0.6B model. Answer: the question is about the
   ratio of transition cost to degradation, and we can report the fault
   magnitude needed. Ideally, add one larger model or physical laptops later.
2. **VMs are not consumer devices:** they have no thermal throttling, no Wi-Fi
   and no real hardware heterogeneity. The title says "consumer devices", so
   either add laptop runs or soften the title for the VM-only version.
3. **Coarse granularity:** we move whole layers, while 2505.02533 moves heads.
   This is acceptable, but say it openly.
4. **Transfer vs recompute:** we only do recompute (replay). "Which one is
   better when" is not established, so don't claim it.

---

## 6. Where it fits

- **Good fit:** edge and ML-systems workshops, plus measurement-focused edge
  computing conferences (e.g. EdgeSys, EuroMLSys, ACM/IEEE SEC). Check the
  current calls for papers for dates and page limits.
- **Reach:** a top systems or mobile venue needs physical devices, a larger
  model and a sharper headline result than we can promise before Phase 6.
- **Journal:** feasible, with the full ablation matrix (A1–A13) plus laptop runs.

---

## Bottom line

We are **not** the first to repartition LLMs adaptively. We would be the first,
as far as we have checked, to **measure on real machines when it is worth
doing**, with verified correctness and a counterfactual for rejected moves.
That is a legitimate and defensible contribution. Its strength now depends
entirely on running the Azure experiments carefully and reporting whatever they
show.
