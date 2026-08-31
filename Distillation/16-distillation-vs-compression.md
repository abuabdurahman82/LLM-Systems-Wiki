# 16 — Distillation vs Quantization vs Pruning vs Speculative Decoding (+ the Combined Stack)
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Four optimization axes get confused constantly because all four "make LLMs cheaper."
They operate at different levels: distillation changes *which model* runs; quantization
changes *numerical precision*; pruning changes *which parameters exist*; speculative
decoding changes *how a big model is executed* using a small draft. This page gives the
deep comparisons, the distilled-drafter combination (where distillation and speculation
reinforce each other), and the full 2026 deployment stack.

## The flagship comparison: distillation vs quantization

| Dimension | Distillation | Quantization |
|---|---|---|
| Changes parameter count | **yes** (new model) | no |
| Changes architecture | can | no |
| Training required | full training run | calibration or light QAT |
| VRAM reduction | structural (smaller model) | precision-driven (2–8×) |
| Latency benefit | structural (fewer weight reads) | bandwidth-driven |
| Accuracy risk | capability loss (uneven — `14`) | precision loss (mostly uniform; outliers → smoothquant etc.) |
| Hardware dependency | none (model is smaller everywhere) | format support (INT4/NVFP4/FP8 kernels) |
| Knowledge ceiling | student capacity | teacher's (minus precision) |

**Complementary, not competing** — the standard stack:

```
70B BF16 teacher
      ↓ distill (months → days of training, `17` §cost)
7B BF16 student
      ↓ quantize
7B NVFP4 student
```
Both steps shrink cost; the first shrinks *what is deployed*, the second shrinks *how
precisely it is deployed*. Together: 70B BF16 = 130.4 GiB → 7B NVFP4 = 3.3 GiB [E:
`15` §memory] — a ~40× deployment-memory cut for ~70% AIME retention in the R1-style
case (`08`).

## Distillation vs pruning

| | Distillation | Structured pruning | Unstructured pruning |
|---|---|---|---|
| Mechanism | train new smaller model | remove heads/channels/layers | zero weights (sparsity) |
| Hardware efficiency | full benefit (dense small model) | real but kernel-dependent | needs sparse-kernel support to pay |
| Retraining | the whole method | recovery fine-tuning | recovery fine-tuning |
| Capability loss | selectable (via data) | structural damage, hard to target | fine-grained, scattered |
| Combined with KD | — | KD as the recovery loss (prune → distill-recover) | same pattern |

The classic synergy: prune-then-distill or distill-then-prune — pruning defines the
architecture, distillation restores capability into it [Research Result: standard
pattern in the compression literature; see also `Inference/Inference-Optimization.md`
for the runtime side].

## Distillation vs speculative decoding (the conceptual pair people mix up)

```
DISTILLATION                              SPECULATIVE DECODING
70B                                       8B draft  +  70B target
  ↓                                           ↓
8B student   → only student runs          draft proposes → target verifies
                                          → faster 70B generation
«Distillation replaces the large model»   «Speculation still uses the large model»
```

| | Distillation | Speculative decoding |
|---|---|---|
| Output quality | student's ceiling | **identical to target** (verification guarantees the target distribution [F: arXiv:2302.01318 lineage]) |
| Deployment cost | small only | small **+ large** (both in memory) |
| Latency | small-model | target-model minus acceptance speedup |
| When target quality matters at peak | falls short | exact |
| Cross-link | this section | `Speculative-Decoding/README.md` |

## Distilled models as speculative drafters

The interesting combination: distill the teacher into a small student, then run the
student as the *draft model* for the original teacher.

```
Large Teacher
      ↓ distillation
Small Student (behaviorally similar to teacher!)
      ↓ used as
Draft Model → Speculative Decoding → Original Teacher as target
```

**Does behavioral similarity raise acceptance rates?** Plausibility: speculative
decoding accepts drafts the target agrees with; a student distilled from the target
 mimics its distribution, so drafts should be "on-distribution" more often than a
generic model's [I: mechanism argument].

Honest evidence status [Research Result + I]:
- It is established that *self-distilled* or family-aligned draft/target pairs work
  well; Medusa/EAGLE-style self-drafting heads and distilled draft-head methods show
  large speedups in the literature [F: `Speculative-Decoding/README.md` lineage].
- The specific claim "KD-trained cross-model drafters beat same-size undistilled
  drafters on acceptance rate" is supported in some settings but is not a universal
  law — acceptance depends on alignment of the *conditional distributions*, temperature
  match, and task; measure acceptance rate on your traffic before committing [I].
- Practical note: the drafter is a *different* optimization target than a deployment
  student — the best drafter is the one closest to the target's distribution, not the
  most capable small model [I].

## The full combined stack (2026 production pattern)

```
Large Teacher (BF16, multi-GPU, one-time)
      ↓ 1. distill
Small Student (dense, same family for white-box if possible)
      ↓ 2. quantize
NVFP4/INT4 student weights
      ↓ 3. deploy
vLLM/SGLang/TRT-LLM with continuous batching + paged KV + prefix caching
      ↓ 4. (optionally) keep teacher hot
student as speculative drafter for the teacher on hard requests
      ↓ 5. route
quality/cost router: student-first, teacher-escalation (→ Production-Serving)
```

| Layer | Axis | Page |
|---|---|---|
| 1 | model compression (KD) | this section |
| 2 | precision (`Quantization/README.md`) | — |
| 3 | runtime (`Inference/Continuous-Batching.md`, `KV-Cache/`) | — |
| 4 | execution (`Speculative-Decoding/README.md`) | — |
| 5 | routing (`Inference/Production-Serving/`) | — |

## Which axis when (decision hints)

- Peak quality non-negotiable, cost pressure on latency → **speculation** (keep the target).
- Cost/footprint pressure, some quality loss acceptable → **distill** (+ quantize).
- Model already chosen, hardware fixed → **quantize** first (cheapest), then reconsider.
- Architecture outgrown the workload → **prune/distill** into right-sized architecture.
- Doing several → the stack order above is the proven sequence [I].

## Related
- `01-why-distillation.md` — the full efficiency landscape
- `Quantization/README.md` — the precision axis deep dive
- `Speculative-Decoding/README.md` — draft/target mechanics and acceptance math
- `Inference/Inference-Optimization.md` — the measured optimization ladder
- `17-benchmarking.md` — how to measure each axis's contribution fairly

## Key Takeaways
- Distillation changes *the model*; quantization changes *precision*; pruning changes
  *structure*; speculation changes *execution* — the comparisons in this page follow
  from that one sentence.
- Distill → quantize → serve is the canonical 70B→7B→NVFP4 stack (~40× memory [E]).
- Distilled drafters are a real, promising combination — but acceptance-rate gains are
  measurable-per-deployment, not a theorem.
- The axes compose in a proven order; skipping straight to speculation is often the
  cheapest first win when quality must be exact.
