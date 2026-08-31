# 17 — Benchmarking Distillation: Retention, Pareto, Cost and Break-Even
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
A distillation project is judged on one curve — capability per cost — which needs
honest benchmarks, efficiency normalization, and a cost model. This page assembles the
evaluation suite, the efficiency metrics (accuracy/param, /GB, /watt, /$), the retention
and compression ratios, the Pareto-frontier view, the total cost of distillation, and
the break-even analysis that answers "when is distillation financially worthwhile?"

## Evaluation benchmarks (2026, contamination-aware)

| Domain | Primary | Notes |
|---|---|---|
| General knowledge | MMLU-Pro | prefer current variants; classic MMLU is saturated/contaminated [→ `Benchmarks/README.md`] |
| Math | MATH-500, AIME (2024/2025 editions) | AIME-2025+ less training-adjacent; use cons@64 or pass@1 consistently |
| Coding | LiveCodeBench (time-windowed), MBPP/HumanEval+ | HumanEval/MBPP legacy — near-saturated [→ `Evaluation-Engineering/Coding-Evaluation.md`] |
| Reasoning | GPQA Diamond | graduate-level science |
| Instruction following | IFEval | constraint-checkable |
| Agentic (if applicable) | task success in harness (`13`) | `Evaluation-Engineering/Agent-Tool-Use-Evaluation.md` |

Rules [I: house evaluation discipline]:
1. **Fresh variants when available** — contamination inflates distilled students just as
   it inflates teachers (`14` §contamination).
2. **Pin generation settings** — temperature, thinking budget, max tokens, template;
   reasoning models swing tens of points on these.
3. **Same harness for teacher, student, baselines** — cross-paper number comparison is
   how myths are born.
4. Report **pass@1 and cons@k** where relevant; statistical gaps →
   `Evaluation-Engineering/Statistical-Evaluation.md`.

## Baseline ladder (always run, in this order)

```
Base student  →  Standard SFT (human data)  →  Response distillation
   →  Reasoning distillation  →  On-policy KD  →  Teacher (ceiling)
```
Each rung isolates one ingredient; skipping rungs makes attribution impossible [I].
This ladder is exactly Lab-A's measurement plan (`18`).

## Efficiency metrics

Definitions (with the [E] arithmetic conventions from `15` §memory):

| Metric | Definition | Why it matters |
|---|---|---|
| Accuracy / parameter | bench ÷ B params | capability density |
| Accuracy / GB VRAM | bench ÷ deployed weight GiB | footprint-adjusted quality |
| Accuracy / watt | bench ÷ measured J/token | energy view (`Platform-Economics/44-energy-and-sustainability.md`) |
| Accuracy / dollar | bench ÷ $/1M tokens | the procurement metric |
| tok/s, tok/s/watt | throughput at fixed hw | serving capacity |
| **Capability-per-Dollar** | (benchmark composite) ÷ ($/1M tok) | this section's headline metric |

Worked example [E, using `15` tables + R1 numbers]: R1-Distill-Qwen-32B @NVFP4
(14.9 GiB) scoring 72.6 AIME vs the 671B teacher @BF16 (1,249.8 GiB) scoring 79.8:
- accuracy/GB: 32B = 4.9/GiB, teacher = 0.064/GiB → **~76× density advantage** [E]
- retention: 91% (`08`) for 1.2% of the deployed memory [E].

## Retention ratio (use with care)

```
Retention = Student score / Teacher score
Example: 81/90 = 90%
```
- Benchmark scales are **not** ratio-valid (a 90→81 drop is not "10% less capability");
  retention is an *educational shorthand*, not a measurement [I: say so in every deck].
- Report it per-benchmark, with generation settings, alongside the raw numbers
  (`08` §economics demonstrates the full honesty pattern).
- Compression ratio is cleaner: teacher params ÷ student params — 70B/7B = **10×**,
  671B/32B = **21×**, 671B/7B = **96×** [E].

## The Pareto frontier

```
Quality
 ▲
 │                        Teacher ●
 │
 │                                  ● Student C (bigger)
 │           ● Student B (Pareto-optimal)
 │
 │     ● Student A  ← dominated by B (worse AND costlier)
 └────────────────────────────────▶ Inference cost ($/1M tok)
```
- Pareto-optimal = no measured alternative is both cheaper AND better.
- Plot students (sizes × quantizations) + teacher; the frontier is your deployment menu.
- Points below the frontier exist only to teach you something (that's fine — label them).
- Frontier shifts with traffic mix (reasoning-heavy vs chatty) — measure on *your*
  distribution [I].

## The total cost of distillation (don't forget these)

```
C_distill = C_teacher_gen          (teacher tokens: generation × N samples)
          + C_verification         (tests/checkers/judge calls)
          + C_training             (student GPU-hours × $/GPU-h)
          + C_evaluation           (benchmarks, seeds, harness runs)
          + C_engineering          (pipeline build & debugging — the real cost)
```
Reference points [F: arXiv:2501.12948 Table 7 — the *R1 project's* full costs:
R1-Zero RL 101K H800-h, SFT-data creation 5K H800-h, R1 RL 41K H800-h; the
*distillation* of the six students is a small fraction of the SFT-data line — the
teacher was already built]. A home-lab mini-R1 (`18`) runs 3–4 orders of magnitude
cheaper [E: lab budgets].

## Break-even analysis

Model the decision as replacing teacher-service with student-service:

```
C_distill  = one-time total cost (above)
C_teacher  = cost per request on teacher
C_student  = cost per request on student

Break-even requests  N*  =  C_distill / (C_teacher − C_student)
```

Worked example [E: arithmetic; parameters are [A]]:
- C_teacher = $0.60 / 1M tok effective; C_student = $0.06 / 1M tok (10× serving-cost
  ratio, consistent with the `15` memory/throughput tables at equal hardware)
- a distillation project at C_distill = $5,400 (data + verification + training + eval)
- **N* = 5,400 / (0.60 − 0.06) = 10,000 M tokens = 10B tokens** of lifetime demand.
- At 2B tokens/month traffic → break-even in ~5 months; every month after saves
  2,000 × $0.54 ≈ **$1,080/mo (~$13K/yr)** at the same hardware pricing
  [A: same pricing assumptions] — small traffic is why C_distill discipline matters;
  a 100× larger deployment multiplies the same ratio.

Sensitivity [I]: the answer is dominated by (a) the serving-cost ratio (hardware class
difference → bigger ratio → smaller N*) and (b) the lifetime-token estimate. Do the
arithmetic with *your* prices; a template lives in
`Platform-Economics/29-local-vs-api-economics.md` (the same break-even shape).

## Energy view

- J/token ≈ (weight-bytes-read/token × TDP-adjusted effective energy/byte) + activation
  overhead — decode is bandwidth-bound, so the distillation memory cut translates
  nearly linearly into energy per token [I: roofline argument; measurement template in
  `Production-Operations` labs].
- Lifecycle: training energy (teacher gen + student train) vs inference energy saved —
  for high-volume serving the inference side dominates within months [I: same
  break-even shape as $; verify per deployment].

## Related
- `15-systems-and-infrastructure.md` — the hardware/memory facts this page monetizes
- `08-deepseek-r1-distillation.md` — the worked retention example
- `Evaluation-Engineering/Model-Evaluation.md` — general eval discipline
- `Benchmarks/README.md` — benchmark families and saturation
- `Platform-Economics/03-llm-inference-unit-economics.md` — the unit-economics toolkit
- `18-practical-labs.md` — the labs that generate these numbers at home

## Key Takeaways
- Always run the six-rung baseline ladder in one harness with pinned settings.
- Retention ratio is a shorthand, not a metric — pair it with compression ratio and raw
  scores.
- Capability-per-dollar (or /GB, /watt) is the metric that moves decisions; the 32B
  example shows ~76× density advantage [E].
- Break-even: N* = C_distill / (C_teacher − C_student) — compute it before the project,
  not after.
- Distillation is an *investment*: front-loaded cost against lifetime inference savings.
