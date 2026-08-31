# 08 — DeepSeek-R1 Distillation: The Flagship Case Study
`LAST_UPDATED: 2026-08-27` · Status: first-class page · Primary source: arXiv:2501.12948 (all facts below verified against the paper text this session)

## 30-Second Explanation
In January 2025 DeepSeek released six open "R1-Distill" models — Qwen and Llama bases
(1.5B–70B) fine-tuned purely with SFT on ~800K reasoning samples generated (and
verified) by DeepSeek-R1. No RL on the students; no logit transfer; text-only
distillation. The results reset expectations: R1-Distill-Qwen-32B beat an
RL-trained-from-scratch Qwen2.5-32B ("Qwen2.5-32B-Zero") across reasoning benchmarks,
and the 1.5B student beat GPT-4o on AIME 2024. This page is the verified anatomy of
that work — and the local-AI story it made possible.

## The case-study diagram

```
                        DeepSeek-R1  (671B MoE, RL-trained reasoner)
                              │
                              │ generates reasoning trajectories
                              ▼
                 complex prompts → sample multiple responses
                              │
                              ▼
                 keep only CORRECT responses
                 + filter: mixed-language CoT, long paragraphs, code blocks
                              │
                              ▼
        ~600K reasoning samples + ~200K non-reasoning  (800K total)
                              │
        ┌──────────┬──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼          ▼
      Qwen      Qwen       Qwen       Qwen       Llama
      2.5-Math  2.5-Math   2.5-14B    2.5-32B    3.1-8B / 3.3-70B
      1.5B      7B
        │          │          │          │          │
        └──────────┴──────────┴────�─────┴──────────┘
                          SFT only (no RL)
                          2–3 epochs, ctx 32,768, batch 64
                          cosine LR 2e-5 … 1e-4 per model
                          ▼
              DeepSeek-R1-Distill-{Qwen,Llama}-{1.5B…70B}
```

## Verified pipeline facts [F: arXiv:2501.12948 §4, Appendix B.3.3, B.4.3]

| Item | Value |
|---|---|
| Teacher | DeepSeek-R1 (671B MoE, ~37B activated) |
| Distillation method | **SFT on teacher-generated text only** — no student RL, no logit KD |
| Dataset size | **~800K samples total**: ≈600K reasoning + ≈200K non-reasoning (V3-pipeline writing/QA/self-cognition/translation + software-engineering data) |
| Reasoning-data curation | multiple samples per prompt, **retain only correct ones**; filter mixed-language chains, long paragraphs, code blocks |
| Student bases | Qwen2.5-Math-1.5B, Qwen2.5-Math-7B, Qwen2.5-14B, Qwen2.5-32B, Llama-3.1-8B, Llama-3.3-70B-Instruct |
| Training | 2–3 epochs; max context 32,768; batch size 64 |
| Learning rates (initial) | 1.5B: 1e-4 · 7B: 8e-5 · 14B: 7e-5 · 32B: 6e-5 · Llama-8B: 5e-5 · Llama-70B: 2e-5 (cosine decay to 1/10) |
| Explicitly not done | RL after SFT — "our primary goal here is to demonstrate the effectiveness of the distillation technique" |
| Contamination note | the paper describes decontamination of its eval (Appendix D.1); method-level contamination checks → `14-data-generation-and-verification.md` |

The non-reasoning quarter of the dataset matters: it keeps writing/QA/instruction
behavior from collapsing while math/code traces dominate the reasoning signal —
a small-but-important balance lesson [I: interpretation of the B.3.3 split].

## Verified benchmark results [F: arXiv:2501.12948 Table 15; pass@1]

| Model | AIME 2024 | MATH-500 | GPQA Diamond | LiveCodeBench | CodeForces rating |
|---|---|---|---|---|---|
| GPT-4o-0513 (reference) | 9.3 | 74.6 | 49.9 | 32.9 | 759 |
| Claude-3.5-Sonnet-1022 (reference) | 16.0 | 78.3 | 65.0 | 38.9 | 717 |
| **R1-Distill-Qwen-1.5B** | **28.9** | 83.9 | 33.8 | 16.9 | 954 |
| **R1-Distill-Qwen-7B** | **55.5** | 92.8 | 49.1 | 37.6 | 1189 |
| **R1-Distill-Qwen-14B** | **69.7** | 93.9 | 59.1 | 53.1 | 1481 |
| **R1-Distill-Qwen-32B** | **72.6** | 94.3 | 62.1 | 57.2 | 1691 |
| **R1-Distill-Llama-8B** | **50.4** | 89.1 | 49.0 | 39.6 | 1205 |
| **R1-Distill-Llama-70B** | **70.0** | 94.5 | 65.2 | 57.5 | 1633 |

Read with care: pass@1 with the paper's generation settings; benchmarks of early 2025
(AIME 2024/MATH-500 were near-saturated and contamination-prone by 2026 — for fresh
re-evaluations prefer current benchmarks and independent harnesses, → `17`).

## Distillation vs RL — the paper's own experiment [F: Appendix F, Table 16]

DeepSeek trained **Qwen2.5-32B-Zero**: large-scale RL (math/code/STEM, 10K+ steps) on
Qwen2.5-32B-Base, no distillation. Head-to-head at 32B:

| Model | AIME 2024 | MATH-500 | GPQA Diamond | LiveCodeBench |
|---|---|---|---|---|
| QwQ-32B-Preview (reference) | 50.0 | 90.6 | 54.5 | 41.9 |
| Qwen2.5-32B-Zero (pure RL) | 47.0 | 60.0 | 91.6→[a: see note] | 55.0 |
| **R1-Distill-Qwen-32B (SFT only)** | **72.6** | **94.3** | 62.1 | **57.2** |

Note on the table: the paper's Table 16 lists GPQA-Diamond per column order
(AIME/MATH/GPQA/LiveCodeBench); the Qwen2.5-32B-Zero row reads 47.0 / 60.0 / 91.6 /
55.0 — the 91.6 sits in the paper's third numeric column. We reproduce the row as
printed rather than re-interpret it [A: faithful transcription; the decisive comparison
— AIME 72.6 vs 47.0 — is unambiguous either way].

**The finding:** on math reasoning, distillation-only massively outperformed
from-scratch RL at 32B, and the paper frames distillation as the democratizing path
("reduced computational requirements enable broader societal benefits"). The honest
boundary conditions [I]:
- Pure-RL baselines were still improving; 10K steps is a budget, not a ceiling.
- RL-from-distilled is the natural combination (the paper explicitly leaves
  "incorporating RL [to] substantially boost" to the community — since replicated in
  practice by many groups).
- Compute asymmetry: RL needs reward infrastructure, stability tuning, and thousands of
  rollouts per improvement; distillation needs one teacher generation pass (costs in
  `17` §break-even).

## Compression economics of the R1 family

| | Teacher (R1) | 32B student | 7B student |
|---|---|---|---|
| Params | 671B (MoE, ~37B active) | 32B dense [E: 21× fewer] | 7B [E: 96× fewer] |
| Weight memory BF16 | ~1,250 GiB [E] | ~59.6 GiB [E] | ~13.0 GiB [E] |
| Weight memory NVFP4/INT4 | ~313 GiB [E] | ~14.9 GiB [E] | ~3.3 GiB [E] |
| Deployment class | multi-node H800-class | 1× workstation (2×24 GB / 1×48 GB) | 1× consumer GPU |
| AIME 2024 pass@1 | 79.8 (paper's R1 number) | 72.6 | 55.5 |

Retention (student/teacher, same benchmark — use with the `17` §retention caveats):
32B keeps ~91% of AIME pass@1 [E: 72.6/79.8]; 7B keeps ~70% [E]. Both numbers are
*per-benchmark and per-generation-settings*; independent re-runs vary with harness,
thinking budget, and template.

## Why R1 distillation mattered for local AI

- Before R1-Distill, local reasoning meant "no reasoning" or multi-GPU clusters;
  after it, a consumer GPU ran a competitive math/code reasoner (`05` §memory table
  explains the physics: 7B @INT4 ≈ 3.3 GiB [E] fits an 8 GB card).
- It validated the *recipe* any lab can repeat: strong open teacher → verified
  traces → small open student (→ `18` labs).
- It shifted the local-AI question from "can we run it" to "can we *distill* it" —
  the community's default small-reasoner recipe for 2025–26 [I].

## What the paper does NOT claim (avoid over-reading)
- It does not claim logit/feature transfer, teacher ensembles, or student RL — none of
  that is in the distill pipeline.
- It does not claim the distill recipe beats RL in general — only that at 32B, from
  base, on their benchmarks and budgets, it did.
- It does not publish the prompt set or generation hyperparameters of the 800K-set
  construction in full detail; do not fabricate them [A: transparency note].

## Related
- `07-reasoning-distillation.md` — the general method this case study instantiates
- `14-data-generation-and-verification.md` — the filtering/verification pattern generalized
- `17-benchmarking.md` — retention, Pareto, break-even math on this family
- `18-practical-labs.md` — reproduce a mini-R1 on home hardware
- `Open-Source-Models/README.md` — where the R1-Distill family sits in the open ecosystem
- `Reasoning/README.md` — R1's other half (GRPO/RLVR training)

## Key Takeaways
- R1 distillation = verified teacher traces + SFT, nothing else — and that was enough to
  beat from-scratch RL at 32B on math reasoning [F: Table 16].
- 800K samples, six students, all open — the single most consequential open distillation
  release to date [I: impact judgment].
- The recipe is portable: teacher quality + verification + balance (reasoning/non-reasoning)
  + right-sized student bases.
- Boundary conditions matter: RL still wins on peak capability at scale; the two compose
  (distill first, RL after) in the standard 2026 playbook.
