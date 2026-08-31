# 01 — Why Distillation Exists
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Frontier models are expensive to serve: hundreds of billions of parameters, multi-GPU
or multi-node footprints, high latency and power draw — and impossible to deploy at the
edge. Knowledge distillation asks one question: *how much of that capability can a much
smaller model inherit, and at what cost?* This page frames the problem, places
distillation in the LLM-efficiency landscape, and defines the teacher/student vocabulary
used by the rest of this section.

## The core problem

```
        Frontier Model  (671B / 400B / 70B / 32B)
                │
                ├─ expensive $/1M tokens
                ├─ high VRAM (multi-GPU or multi-node)
                ├─ high latency (memory-bound decode)
                ├─ high power (J/token)
                └─ infeasible at the edge
                ▼
     Can we transfer much of its capability
     into a much smaller model?
                ▼
        Knowledge Distillation
```

**The professor analogy.** An expert professor (the teacher) has spent years building
deep, connected understanding. A motivated student cannot simply copy the professor's
brain; the student learns from what the professor *emits* — answers, explanations,
corrections, judgments of the student's own attempts. Distillation formalizes that
transfer: the student trains on some representation of the teacher's knowledge rather
than rediscovering everything from scratch.

What a teacher can emit (and the student can learn from) — this list is effectively the
taxonomy of the whole field (→ `04-distillation-taxonomy.md`):

| Teacher exposes | Student learns from | Section |
|---|---|---|
| final outputs / responses | imitation (SFT) | 06 |
| full probability distributions | soft targets / KL | 02, 05 |
| reasoning traces | reasoning distillation | 07, 08 |
| hidden features / attention | feature & attention KD | 05 |
| preferences / pairwise judgments | preference distillation | 12 |
| scores of *student* attempts | on-policy distillation | 10, 11 |
| tool-call trajectories | agentic distillation | 13 |

## The critical misconception (read this first)

> **Distillation is not quantization.**

- **Quantization** changes *numerical precision* of an existing model's weights
  (BF16 → FP8 → INT4). Parameter count, architecture and behavior are (approximately)
  preserved. No new model is trained. → `Quantization/README.md`
- **Distillation** produces/trains a *different, smaller model* that approximates the
  teacher's behavior. New weights, new architecture (possibly), new failure modes.

They are complementary, not competing — 70B BF16 → distill → 7B BF16 → quantize → 7B
NVFP4 is a standard deployment stack (→ `16-distillation-vs-compression.md`).

## The LLM efficiency landscape

Distillation is one leaf of a four-branch optimization tree. Every branch composes with
the others:

```
LLM EFFICIENCY
├── Model Compression            ← what the model IS
│   ├── Knowledge Distillation   ← this section
│   ├── Quantization             → Quantization/README.md
│   ├── Pruning                  → Inference/Inference-Optimization.md
│   ├── Sparsity                 → Inference/Inference-Optimization.md
│   └── Low-rank techniques      → Quantization/README.md (LoRA family)
├── Runtime Optimization         ← how requests are scheduled
│   ├── Continuous Batching      → Inference/Continuous-Batching.md
│   ├── PagedAttention           → KV-Cache/Paged-KV-Cache.md
│   ├── Prefix Caching           → KV-Cache/Prompt-and-Prefix-Caching.md
│   ├── Speculative Decoding     → Speculative-Decoding/README.md
│   └── KV-cache optimization    → KV-Cache/README.md
├── Kernel Optimization          ← how math executes
│   ├── FlashAttention           → GPU-Systems/FlashAttention.md
│   ├── TensorRT-LLM             → Serving-Engines/TensorRT-LLM.md
│   └── Fused kernels            → GPU-Systems/Fused-Kernels.md
└── Architecture Optimization    ← how the model is shaped
    ├── GQA / MQA                → Model-Architectures/Attention-Head-Designs.md
    ├── MoE                      → Model-Architectures/Mixture-of-Experts.md
    └── MTP                      → Speculative-Decoding/README.md
```

**Composition is the norm.** A production stack might be: distilled 7B student
(compression) + NVFP4 quantization (compression) + speculative decoding with a 1.5B
draft (runtime) + continuous batching (runtime) on vLLM (serving). Distillation is
unique among these in that it changes *what model runs*; everything else changes *how
the same (or a paired) model runs*.

## Teacher, student, distillation — precise definitions

- **Teacher:** a large or otherwise more capable model. It can be a frontier API model
  (black-box) or an open-weight checkpoint (white-box). Access level determines which
  KD techniques are available (→ `04-distillation-taxonomy.md`).
- **Student:** the smaller/cheaper model being trained. It inherits *selected*
  capabilities within its own capacity — it is not "the teacher, smaller"
  (→ `04` §capacity gap).
- **Distillation:** any training procedure that transfers teacher behavior or knowledge
  into the student through some teacher-derived signal.

```
                 Teacher LLM
                      │
                      │ knowledge signal
                      ▼
 Training data ─▶ Distillation ─▶ Student LLM
                                      │
                                      ▼
                             cheaper inference
```

## Why not just train a small model from scratch?

You can — but a small model trained only on the same data as a big model is worse than a
small model trained on a big model's *outputs*, because the teacher's outputs encode
what the teacher learned from all its data — the "dark knowledge" of relative
similarities and plausible-but-wrong alternatives (→ `02-classical-knowledge-distillation.md`).
DeepSeek-R1's distill study states the empirical finding directly: models trained on
high-quality teacher outputs consistently outperform those trained directly on
human-generated data [F: arXiv:2501.12948 §4]. Distillation is also usually far cheaper
than RL for the same capability gain (→ `10`, `12`).

## The capacity gap (why a 1.5B student ≠ 671B teacher)

A student can only represent what fits in its capacity. Two consequences:

1. **Extreme compression loses capabilities unevenly.** Factual recall and long-tail
   knowledge typically degrade before procedural skills like arithmetic-from-CoT or
   coding-from-traces (→ `14-data-generation-and-verification.md` §what degrades first).
2. **Intermediate teachers can help.** The chain 671B → 70B → 14B → 7B can outperform a
   direct 671B → 7B jump, an idea present since the earliest BERT-era KD work
   [F: arXiv:1908.09355 patient KD; research result: effect size varies by task].
   → `09-self-and-multi-teacher-distillation.md`.

How small is too small is an open, benchmark-dependent question — see
`17-benchmarking.md` §retention ratio and `20-future-research.md` §distillation scaling
laws [F: arXiv:2502.08606].

## Capability retained per parameter (conceptual plot)

```
Model quality
   ▲
   │                              Teacher ●
   │
   │                     ● Student (distilled)
   │        ● Student (smaller)
   │   ● Student (too small — capabilities collapse)
   └──────────────────────────────────────────▶ Parameters
```

The goal of a good distillation project is to move the student curve *up and left*:
maximum quality per parameter. Benchmarks that operationalize this:
`17-benchmarking.md` (retention ratio, accuracy/GB, accuracy/$, Pareto frontier).

## Where the economics live (preview)

The full unit-economics treatment is `17-benchmarking.md` §cost and break-even, with the
platform-level view in `Platform-Economics/10-model-economics.md`. The one-line summary:
distillation converts a **recurring inference-cost difference** into a **one-time
training cost** — and the break-even request volume is often surprisingly small for
high-traffic workloads [I: worked example in 17].

## Related
- `04-distillation-taxonomy.md` — every technique on one map
- `Quantization/README.md` — the precision axis this page's misconception box guards against
- `Speculative-Decoding/README.md` — the *other* way to make a big model cheaper (and 16 for the comparison)
- `Model-Architectures/Mixture-of-Experts.md` — MoE teachers (why they're cheap to *train*, hard to *serve*)
- `Inference/Roofline.md` — why decode latency scales with weight bytes
- `Platform-Economics/10-model-economics.md` — the money view of model size

## Key Takeaways
- Distillation exists because frontier capability is real and frontier serving is expensive;
  it converts capability into a smaller model rather than shaving the big one.
- **Distillation trains a different model; quantization changes precision.** They compose.
- The student learns from a *representation* of teacher knowledge — outputs, probabilities,
  traces, features, preferences, or judgments of its own attempts.
- The capacity gap means transfer is lossy and uneven; intermediate teachers and
  task-focused datasets are the practical mitigations.
- Everything in this section optimizes one curve: capability retained per parameter,
  per GB, per watt, per dollar.
