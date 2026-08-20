# Model Evaluation: benchmark families and score hygiene
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Model evaluation organizes into benchmark *families*, each measuring a
different construct: multi-task knowledge, math reasoning, instruction
following, open-ended preference, and long-horizon coding. No family is the
"model score"; a model card that leads with one family number is making a
selective claim. Score hygiene means reading every number as *benchmark +
protocol + contamination status + CI*, and discounting leaderboard figures
when any of those is missing. The two structural failure modes are
**contamination** (the benchmark leaked into training data, so the score
measures memorization) and **saturation** (the ceiling is reached, so the
benchmark no longer discriminates between models). Live and rolling
benchmarks exist specifically to defeat both. The statistical floor: a
benchmark of 300 items has a standard error around 2.4–2.7 points, so a
4-point gap between two models is not a winner — it is noise.

## Benchmark families
The families below are the backbone of model cards; per-benchmark reference
material lives in `../Benchmarks/README.md`, and model lineages in
`../Frontier-Models/README.md`.

**Knowledge / multi-task.** MMLU (arXiv:2009.03300 [F]) — 57 subjects,
multiple-choice, single- or few-shot; the default "knowledge" proxy since
2020. MMLU-Pro (arXiv:2406.01574 [F]) — harder 10-option items and a reduced
subset, built because MMLU saturated. GPQA (arXiv:2311.12022 [F]) —
graduate-level questions in biology/chemistry/physics written to be
"Google-proof," with a high school/grad/majority-of-experts split that exposes
when a model is pattern-matching versus reasoning. All three are
multiple-choice, so exact-match scoring is clean but *format-gaming* (position
bias, length bias of distractors) is a standing concern [I].

**Math.** GSM8K (arXiv:2110.14168 [F]) — grade-school word problems; long
saturated, useful now mostly as a regression canary. MATH (arXiv:2103.03874 [F])
— competition math, harder, still saturating at the frontier. AIME —
annual, *live* by construction: new problems each year, so any model
released in year Y cannot have seen year Y+1's problems [I: the live-set
property is definitional, not verified per release]. The GSM8K → MATH → AIME
lineage is the canonical "freeze, saturate, replace" lifecycle
(`Benchmark-Design.md` § lifecycle).

**Instruction following.** IFEval (arXiv:2311.07911 [F]) — verifiable
constraints (word counts, formatting, keyword inclusion) scored by
programmatic checkers, so it measures *instruction adherence* without a judge.
Distinct from the other families: the "answer" is the constraint satisfaction,
not content quality.

**Open-ended / preference.** WildBench (arXiv:2406.04770 [F]) — real user
prompts with a rubric-based judge scoring; measures what users actually ask,
at the cost of judge noise. HELM (arXiv:2211.09110 [F]) — not a benchmark but
an evaluation *framework*: many scenarios × many metrics, explicitly reporting
accuracy *and* calibration, robustness, fairness, bias, efficiency. HELM is
the template for the multi-axis reporting this section demands
[ I: the framework role is from its design; arXiv:2211.09110 [F] ].

**Contamination-resistant / live.** LiveBench (arXiv:2406.19314 [F]) —
quarterly-updated, contamination-limited questions across science, reasoning,
math, coding; the model of the rolling benchmark. LongBench v2
(arXiv:2412.15204 [F]) — long-context with realistic multi-hop reasoning,
harder than v1 (arXiv:2308.14508 [F]). Humanity's Last Exam (arXiv:2501.14249 [F])
— cross-disciplinary expert-written exam, positioned as a long-horizon
"last exam" for current frontier models; scores on it move with each
frontier release, which is the signature of a non-saturated set [I].

**Live coding.** LiveCodeBench (arXiv:2403.07974 [F]) — time-stamped problem
collection (LeetCode/AtCoder/Codeforces windows) so evaluation can be
contamination-controlled by release date; BigCodeBench (arXiv:2406.15877 [F])
— diverse function-call and real-world library tasks; SWE-bench
(arXiv:2310.06770 [F]) — real GitHub issues with test-based scoring. See
`Coding-Evaluation.md` and `../Benchmarks/README.md`.

## Effort level / thinking budget
Reasoning-capable vendor models expose *effort levels* (short/medium/long
thinking budgets) [F: vendor — vendor documentation exposes configurable
reasoning effort; specific level names and token budgets are
vendor-specific and change between releases]. This makes "the model's
score" doubly ill-posed: model + effort level + task. The minimum
discipline: state the effort level in every reported number, and when
comparing models, either fix effort or report the full effort curve
(score vs budget), because the *shape* of that curve (how fast the model
saturates in thinking tokens) is itself a capability signal [I]. A number
reported at max effort against a competitor's default effort is not a
comparison; it is a confound with a leaderboard attached.

## How to read a model card / system card
Demand, in order of importance [I: editorial checklist]:
1. **Full protocol** — dataset version, prompt, sampling, scorer, effort
   level, harness (`Evaluation-Fundamentals.md` § minimum spec).
2. **CI or SE** — without it, treat the number as a point estimate with
   unknown error bars of at least ±2–5 points on typical set sizes.
3. **Percentiles, not just means** — P50/P95/P99 of latency and cost
   (`Statistical-Evaluation.md`, `../Inference/Inference-Metrics.md`).
4. **Cost** — tokens and $ per benchmark item and per success.
5. **Contamination statement** — release date vs problem release dates;
   known-leak audit results (`Benchmark-Contamination.md`).
6. **Negative results** — which benchmarks it did *not* run; absence is
   information.

A model card that reports a single MMLU-style number with no protocol is
publishing a rumor.

## When to discount a leaderboard number
- **Contamination**: problem release date predates the model's training cutoff
  by a long margin, or the set is a known training-data source; discount
  heavily (`Benchmark-Contamination.md`).
- **Saturation**: the family ceiling is near 100%; the number no longer
  discriminates, and small protocol differences dominate.
- **Vendor-reported**: the vendor ran its own eval on its own infra with its
  own harness; independent replication usually lands lower or higher — both
  are informative, and the *gap* is a harness/harness effect [I].
- **No CI**: a 300-item set gives SE ≈ 2.4–2.7 points; gaps smaller than
  ~2 SEs are not claims.
- **Single-shot**: one run of a stochastic protocol, no seed reporting.

## Worked example: a 4-point gap is not a winner [E]
Two models are evaluated on the same 300-item multiple-choice set. Model A:
`p1 = 0.70` (210/300). Model B: `p2 = 0.74` (222/300).

Standard error of a proportion: `SE(p) = sqrt(p(1−p)/n)`.
- Model A: `sqrt(0.70 × 0.30 / 300) = sqrt(0.21/300) = sqrt(0.0007) ≈ 0.0265`.
- Model B: `sqrt(0.74 × 0.26 / 300) = sqrt(0.1924/300) = sqrt(0.000641) ≈ 0.0253`.
- SE of the *difference*: `sqrt(0.0007 + 0.000641) = sqrt(0.001341) ≈ 0.0366`.

The observed gap is `0.74 − 0.70 = 0.04`. In units of the SE of the
difference: `0.04 / 0.0366 ≈ 1.09`. That is just over one sigma — a two-sided
p-value of about 0.28 [E: `2 × (1 − Φ(1.09)) ≈ 2 × 0.138 ≈ 0.276`]. The
probability of seeing a gap this large when the models are *identical* is
roughly 1 in 4. You cannot claim a winner.

**How big must the set be?** Solve for `n` where a true 4-point gap is
significant at 95% confidence. Using a pooled `p ≈ 0.72`, the two-sided
margin is `1.96 × sqrt(2 · 0.72 · 0.28 / n)`; we need this below `0.04`:

`1.96 × sqrt(0.4032/n) < 0.04`
→ `sqrt(0.4032/n) < 0.0204`
→ `0.4032/n < 0.000416`
→ `n > 0.4032 / 0.000416 ≈ 969`.

So roughly **n ≈ 970 items per model**. (Using `p = 0.5`, the worst case for
`p(1−p)`, gives `n ≈ 1200`, so ~1000–1200 items is the safe rule of thumb.)
At 300 items, the 4-point gap is inside the
noise; at ~1000 items it would clear 95% confidence. This is why
"Model B beats Model A by 4 points on SetX" headlines on small sets should
be read as "the two models are statistically indistinguishable on SetX."

## Related
- `Evaluation-Fundamentals.md` — the protocol behind every number.
- `Benchmark-Design.md` — why families saturate and get replaced.
- `Benchmark-Contamination.md` — when a number measures memory, not ability.
- `Statistical-Evaluation.md` — CIs and sample-size math in depth.
- `../Benchmarks/README.md` — per-benchmark reference.
- `../Frontier-Models/README.md` — model families and release context.

## Key Takeaways
Benchmark families measure different constructs, so a model card's headline
number is a selective claim; demand the full protocol, CI, percentiles, cost,
and contamination statement. A 4-point gap on a 300-item set is about one
sigma and not a winner — the set needs roughly 970 items for that gap to be
significant at 95%. Effort level is a free variable on reasoning models, and
any comparison that doesn't fix it (or report the curve) is confounded.
