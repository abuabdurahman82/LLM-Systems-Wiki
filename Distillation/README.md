# LLM Distillation — Compressing Frontier Intelligence into Smaller Models
`LAST_UPDATED: 2026-08-27` · Status: FIRST-CLASS section (2026-08-27)

## 30-Second Explanation
Knowledge distillation transfers useful capability from a large/capable **teacher**
into a smaller, cheaper **student**. The student does not copy the teacher's weights —
it learns from some representation of the teacher's behavior: its outputs, its
probabilities over tokens, its reasoning traces, its hidden features, or its
preferences. In 2015 this meant soft targets on a classifier; in 2026 it is the workhorse
that puts frontier-grade *reasoning* on a laptop (DeepSeek-R1-Distill-Qwen-7B
[F: arXiv:2501.12948]) and the cheapest post-training per capability point
(on-policy distillation ≈ an order of magnitude cheaper than RL [F: Thinking Machines,
2025]). This section covers the full arc: classical KD math → the LLM distillation
taxonomy → reasoning distillation → the R1 case study → on-policy/GKD methods →
data pipelines → infrastructure → benchmarking → production design → labs.

## How to read this section (Zero-to-Hero path)
| Level | Pages | You can then… |
|---|---|---|
| 0–2 Why & classical | [01 Why Distillation](01-why-distillation.md), [02 Classical KD](02-classical-knowledge-distillation.md) | explain KD, temperature, dark knowledge to a colleague |
| 3–5 Math & taxonomy | [03 Losses](03-distillation-losses.md), [04 Taxonomy](04-distillation-taxonomy.md), [05 Logit/Feature](05-logit-and-feature-distillation.md) | pick a KD signal and loss for a real project |
| 6 LLM practice | [06 Sequence/Response](06-sequence-and-response-distillation.md), [07 Reasoning](07-reasoning-distillation.md), [08 R1 case study](08-deepseek-r1-distillation.md) | design a response- or reasoning-distillation pipeline |
| 7 Frontier | [09 Self/Multi-teacher](09-self-and-multi-teacher-distillation.md), [10 On-Policy](10-on-policy-distillation.md), [11 GKD](11-gkd.md), [12 KD & RL](12-distillation-and-rl.md), [13 Agentic](13-agentic-distillation.md) | reason about GKD, OPD, reward and agent distillation |
| 8 Systems | [14 Data](14-data-generation-and-verification.md), [15 Systems/Infra](15-systems-and-infrastructure.md), [16 vs Compression](16-distillation-vs-compression.md), [17 Benchmarking](17-benchmarking.md), [18 Labs](18-practical-labs.md), [19 Production](19-production-design.md), [20 Future](20-future-research.md) | build, deploy, benchmark and cost a distilled LLM |

## Evidence labels (mapping to the house tags)
The house claim-tag system ([F]/[E]/[I]/[A], see root README) maps to this section's
needs as follows: **[Established]** → `[F]` with primary source, multiple independent
replications; **[Research Result]** → `[F]` (single paper or group, arXiv-preprint-grade);
**[Vendor Reported]** → `[F: vendor claim]`; **[Independent Benchmark]** → `[F]` from a
non-producer + `[E]` where measured here; **[Experimental]** / **[Open Question]** →
`[I]` / `[A]` / explicit `UNVERIFIED`. All arithmetic tagged `[E]` was computed in code
this session (see `15-systems-and-infrastructure.md` §Memory and `05` §Storage).

## What this section is NOT
- **Not a replacement for the post-training pillar.** SFT/RLHF/DPO/GRPO mechanics live in
  `Post-Training/README.md` and `Post-Training/Alignment-RLHF.md`; this section
  cross-links them and treats them as building blocks.
- **Not a quantization/pruning/speculative-decoding page.** Those are *different*
  compression axes — see `16-distillation-vs-compression.md` for the exact comparison and
  `Quantization/README.md`, `Speculative-Decoding/README.md` for the deep dives.
- **Not a reasoning-models page.** `Reasoning/README.md` owns test-time compute and RLVR;
  this section owns how reasoning *transfers* between models.

## The one-page mental model (the whole section in one screen)

```
                WHAT?  Transfer useful capability: teacher → smaller student
                WHY?   Frontier capability is real but serving it is expensive
                       (VRAM, latency, power, $/1M tokens, edge feasibility)

   SIMPLEST (2026 meaning of "distillation" in most product posts):
        Teacher ─▶ generate high-quality data ─▶ student SFT      [F: R1 §4]

   DEEPER (classical KD):
        Teacher logits ─▶ distribution matching (KL, T-scaled) ─▶ student
        [F: Hinton et al., arXiv:1503.02531]

   REASONING KD:
        Teacher reasoning traces ─▶ verify/filter ─▶ student SFT  [F: arXiv:2501.12948]

   ON-POLICY KD (2025–26):
        student generates ─▶ teacher scores per-token (rev-KL) ─▶ dense reward
        [F: arXiv:2306.13649 (GKD); Thinking Machines 2025]

   PRIMARY GOAL:   teacher-like capability  +  student-like inference cost
```

The engineering frame this section keeps returning to — every technique in every page is
a variation of these eight inputs:

```
   teacher quality + data quality + teacher signal + loss function
   + student capacity + curriculum + verification + evaluation
        ↓
   DISTILLED STUDENT  →  { quality ↑, speed ↑, cost ↓ }
```

## Page map (cross-linked, non-duplicating)
| Page | Owns | Deliberately does NOT cover (→ link) |
|---|---|---|
| [01 Why](01-why-distillation.md) | the cost problem, compression landscape, capacity gap, retention/compression metrics | quantization detail → `Quantization/README.md` |
| [02 Classical KD](02-classical-knowledge-distillation.md) | history 2006→2026, soft targets, temperature, dark knowledge | loss math → 03 |
| [03 Losses](03-distillation-losses.md) | CE, forward/reverse KL, JS, f-divergences, MiniLLM | RL comparison → 12 |
| [04 Taxonomy](04-distillation-taxonomy.md) | the full technique taxonomy, black/white-box, decision tree, mega-tables | per-technique math → 03/05 |
| [05 Logit/Feature](05-logit-and-feature-distillation.md) | logit/top-K/feature/attention/patient KD, storage math, cross-tokenizer, MoE→dense | serving infra → 15 |
| [06 Sequence/Response](06-sequence-and-response-distillation.md) | response KD, sequence KD, KD-vs-SFT confusion | data quality → 14 |
| [07 Reasoning](07-reasoning-distillation.md) | answer-vs-reasoning, data quality, verification, best-of-N, active/curriculum | R1 specifics → 08 |
| [08 R1 Case Study](08-deepseek-r1-distillation.md) | the verified R1 pipeline, benchmarks, distill-vs-RL, local-AI impact | general reasoning KD → 07 |
| [09 Self & Multi-teacher](09-self-and-multi-teacher-distillation.md) | born-again/self-distillation, ensemble/domain teachers | OPD → 10 |
| [10 On-Policy](10-on-policy-distillation.md) | exposure bias, OPD, off-vs-on-policy table, 2026 OPD taxonomy | GKD details → 11 |
| [11 GKD](11-gkd.md) | Generalized Knowledge Distillation deep dive, TRL `GKDTrainer` | — |
| [12 KD & RL](12-distillation-and-rl.md) | KD↔RLHF/GRPO/DPO, preference & reward-model distillation | alignment pipeline → `Post-Training/Alignment-RLHF.md` |
| [13 Agentic](13-agentic-distillation.md) | tool-use/plan/function-calling distillation, trajectory data | agent runtime → `Agents/Tool-Use.md` |
| [14 Data](14-data-generation-and-verification.md) | synthetic pipeline, cleaning, contamination, safety/calibration/knowledge-loss, lineage, failure modes, myths | benchmark design → `Evaluation-Engineering/Benchmark-Contamination.md` |
| [15 Systems](15-systems-and-infrastructure.md) | inference impact, memory tables, distributed KD, logit transfer, API/open-weight/enterprise/sovereign | engine internals → `Serving-Engines/README.md` |
| [16 vs Compression](16-distillation-vs-compression.md) | KD vs quantization/pruning/speculative decoding; distilled drafters; the combined stack | — |
| [17 Benchmarking](17-benchmarking.md) | eval suites, efficiency metrics, retention ratio, Pareto, cost/break-even, energy | stats → `Evaluation-Engineering/Statistical-Evaluation.md` |
| [18 Labs](18-practical-labs.md) | home-lab, 2×DGX-Spark, RTX PRO 6000 labs; hands-on project; error mining; iteration | — |
| [19 Production](19-production-design.md) | production KD architecture, OPD production loop, framework matrix, model lineage | ops → `Production-Operations/README.md` |
| [20 Future](20-future-research.md) | 2026 research frontier, glossary, references | — |

## Related
- `Post-Training/README.md` — SFT/RLHF/DPO/GRPO pipeline this section builds on
- `Post-Training/Alignment-RLHF.md` — the alignment lineage + DPO math
- `Reasoning/README.md` — test-time compute & RLVR (the teacher's home turf)
- `Quantization/README.md` — the numerical-precision compression axis
- `Speculative-Decoding/README.md` — draft/target acceleration (pairs with 16)
- `Inference/Inference-Optimization.md` — the optimization ladder
- `Open-Source-Models/README.md` — where distilled models live (Qwen/Llama/DeepSeek families)
- `Evaluation-Engineering/Benchmark-Contamination.md` — contamination detection method
- `Platform-Economics/10-model-economics.md` — model-size economics (complementary view)
- `GPU-Systems/MoE-Expert-Parallelism.md` — why MoE teachers are hard to serve (pairs with 05)

## Key Takeaways
- Distillation = **capability transfer**, not weight copying, not precision reduction.
- The 2026 default recipe is response/reasoning distillation via SFT; logit/feature KD and
  on-policy methods are the deeper layers of the same idea.
- DeepSeek-R1's distill family is the canonical open case study: 800k verified samples,
  SFT-only, six released students [F: arXiv:2501.12948].
- On-policy distillation (GKD lineage) fixes exposure bias and is ~an order of magnitude
  cheaper than RL — the most consequential 2025–26 shift in this field [F: arXiv:2306.13649;
  Thinking Machines 2025].
- Everything is judged by one engineering question: **how much capability per dollar/watt
  can we keep, at what training cost, with what quality loss?** → `17-benchmarking.md`.
