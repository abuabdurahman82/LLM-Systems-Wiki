# Statistical Evaluation: confidence intervals, paired tests, judge agreement
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Most published LLM evaluation numbers are point estimates with invisible
error bars; the statistical layer makes them honest. Averages lie in agent
evaluation specifically: n is small (tens of tasks), per-task variance is
high (Bernoulli-ish success), and cost is skewed (a few trajectories run
to 100k tokens) — so report percentiles (P50/P95/P99 of latency and cost),
not just means. For proportions, use the Wilson interval, not Wald, when
n is small or p is near 0 or 1. For comparing two systems on the *same*
tasks, use paired tests (McNemar for binary outcomes), which cancel
task-difficulty variance and buy enormous effective sample size. For
arbitrary metrics, bootstrap CIs are the default, and they fail quietly
when trajectories are non-i.i.d. (shared environment state). Judge-based
scores need agreement statistics (Cohen's kappa) before they can be
treated as measurements. And when you run 20 benchmarks, one "significant"
result is the null hypothesis — multiple-comparison correction is not
optional decoration.

## Why averages lie (and what to report instead)
Agent benchmarks have a distribution shape that breaks the average [I:
mechanism; each factor is independently observable]:
- **Small n**: a "clean" agent eval is often 20–100 tasks; the SE of a
  mean success rate at n = 50, p = 0.5 is `0.5/sqrt(50) ≈ 0.07` — a 7-point
  error bar on every headline.
- **High per-task variance**: Bernoulli outcomes at p ≈ 0.5 maximize
  variance; almost-succeeds-on tasks (p = 0.4–0.6) dominate the noise
  budget.
- **Skewed cost**: latency and cost are log-normal-ish; the mean is
  dominated by the few long trajectories. Inference SLO work reports
  percentiles for exactly this reason — P50/P95/P99 latency is standard in
  the serving literature, e.g. DistServe's goodput-latency objectives
  (arXiv:2401.09670 [F]); see `../Inference/Inference-Metrics.md`
  [I: percentile SLO practice extends to agent evals; no single source
  standardizes P50/P95/P99 for agent benchmarks specifically].

**Practice**: report the success-rate mean *and* its SE, plus P50/P95/P99
of per-task latency and cost, plus $/success. A single mean success rate
with no variance statement is a rumor with a decimal point
(`Evaluation-Fundamentals.md`).

## Confidence intervals for proportions
Two standard intervals for a binary outcome (`k` of `n` successes) [I:
standard formulas, textbook content applied to evals]:
- **Wald**: `p̂ ± z·sqrt(p̂(1−p̂)/n)`. Simple, but badly miscalibrated for
  small n or extreme p — it can produce CIs outside [0,1] and is
  anti-conservative near the boundaries [I].
- **Wilson** (score interval): the endpoints are
  `[k + z²/2 ± z·sqrt(k(n−k)/n + z²/4)] / (n + z²)` [I: formula as
  standard; applied below as [E]].

**Hand example [E]**: 7 of 10 tasks succeeded (small agent eval).
Wald: `p̂ = 0.7`, `SE = sqrt(0.7·0.3/10) = sqrt(0.021) ≈ 0.145`,
95% CI `0.7 ± 1.96·0.145` → `[0.416, 0.984]` — nearly the full range, and
the upper edge barely stays inside [0,1]. Wilson:
- `z = 1.96`, `z² = 3.84`, so `n + z² = 13.84`.
- `k + z²/2 = 7 + 1.92 = 8.92`.
- Inside the sqrt: `k(n−k)/n + z²/4 = 7·3/10 + 0.96 = 2.1 + 0.96 = 3.06`;
  `sqrt(3.06) ≈ 1.749`; `z·1.749 ≈ 3.431`.
- Lower: `(8.92 − 3.431)/13.84 = 5.489/13.84 ≈ 0.397`.
- Upper: `(8.92 + 3.431)/13.84 = 12.351/13.84 ≈ 0.892`.

Wilson 95% CI: **[0.397, 0.892]** [E: verified numerically] — narrower,
better-calibrated, and inside [0,1] by construction. Seven out of ten is
*not* evidence of 70% reliability; it is compatible with anywhere between
40% and 89%. Any claim built on a 10-task eval should carry this CI or
stronger.

## Paired comparisons: the McNemar test
The highest-leverage statistical move in model comparison is **pairing**:
run both systems on the *same* tasks (same seeds, same environments) and
compare per-task outcomes. Pairing cancels task-difficulty variance — the
biggest noise source in evals (task count drives variance:
arXiv:2607.12338 [F]) — so a paired test on 80 tasks beats two unpaired
tests of 80 tasks each.

For binary paired outcomes, tabulate the 2×2 of disagreements [I: standard
McNemar setup]:

|            | B succeeds | B fails |
|------------|------------|---------|
| **A succeeds** | both win (ignore) | A-only: `n10` |
| **A fails** | B-only: `n01` | both fail (ignore) |

McNemar statistic (no continuity correction):
`χ² = (n10 − n01)² / (n10 + n01)`, χ²₁ under the null; with continuity
correction: `(|n10 − n01| − 1)² / (n10 + n01)` for small tables [I: both
forms standard].

**Hand example [E]**: 80 paired task runs; 12 tasks only A wins
(`n10 = 12`), 7 tasks only B wins (`n01 = 7`).
- `χ² = (12 − 7)² / (12 + 7) = 25/19 ≈ 1.316`.
- Two-sided p (χ²₁): `p ≈ 0.25` [E: verified — the χ²₁ CDF at 1.316 gives
  p ≈ 0.251].
Not significant. A wins 12 to 7, and the honest report is "no detectable
difference on these 80 tasks." With the continuity correction:
`(5 − 1)²/19 = 16/19 ≈ 0.842`, p ≈ 0.36 — same conclusion. The paired
design did its job: with 80 tasks and *these* disagreement counts, the
test refuses to overclaim. (If A had won 30 to 7: `χ² = 529/37 ≈ 14.3`,
p < 0.001 — the same design would have been decisive the other way [E:
(30−7)²/37 = 529/37 ≈ 14.30, p ≈ 0.0015].)

## Bootstrap CIs for arbitrary metrics
For metrics with no closed-form distribution (F1, BLEU, judge rubric
scores, $/success, P95 latency), the bootstrap is the default [I:
procedure is standard]:
1. Take the observed per-task scores `x₁…xₙ`.
2. Resample `n` items *with replacement*; compute the metric on the sample.
3. Repeat `B = 1000` (or more) times; the CI is the 2.5th and 97.5th
   percentiles of the B metric values.

Caveats [I: failure modes]:
- **Non-i.i.d. trajectories**: if tasks share environment state (the same
  repo mutated across runs), the "independent items" assumption is false
  and bootstrap CIs come out *too narrow*. Isolate state per run
  (`Benchmark-Design.md` § rigorous agentic benchmarks,
  arXiv:2507.02825 [F]) before trusting any resampling CI.
- **Small n**: with n < 30 the bootstrap is unstable; report the CI only
  with the n attached, and prefer exact intervals (Wilson, McNemar) where
  they exist.
- **Skewed metrics**: $/success and P95 are skewed; the bootstrap CI is
  asymmetric (correct behavior — do not symmetrize it).
- **Judge noise**: if the metric is a judge score, the bootstrap treats
  judge variation as task variation; the CI undercovers unless judge runs
  are themselves replicated (`LLM-as-a-Judge.md`).

## Judge agreement: Cohen's kappa
When two systems (or a judge and a human) label the same items, raw
agreement overstates reliability because some agreement is chance [I].
Cohen's kappa [I: formula standard]:
`κ = (p_o − p_e) / (1 − p_e)`, where `p_o` is observed agreement and `p_e`
is the agreement expected by chance (from the marginals).

**Hand example [E]**: two judges score 100 items; they agree on 80
(`p_o = 0.80`); marginal agreement expected by chance is `p_e = 0.64`.
- `κ = (0.80 − 0.64) / (1 − 0.64) = 0.16 / 0.36 ≈ 0.44` [E: verified].
- 0.44 is conventionally "moderate" agreement (the 0.4–0.6 band [I: the
  convention bands are the standard Landis-Koch-style heuristics]).

Interpretation: the judges share a real but limited common signal; a
benchmark built on *one* judge pass at this agreement level should report
the judge's agreement statistics, or its CI is understated. Judge
agreement interacts with known judge biases — position, verbosity,
self-preference (arXiv:2306.05685 [F] documents MT-Bench/Chatbot Arena
judge properties; arXiv:2305.17926 [F] on position/fairness bias;
arXiv:2411.15594 [F] surveys the area) — which `LLM-as-a-Judge.md` covers
in depth [F: bias literature cited; the kappa workflow above is [I]].

## Multiple comparisons
Running 20 benchmarks and calling the one that "significantly" favors your
model is a textbook false-positive: under the null, each benchmark has a
5% chance of a p < 0.05, so with 20 tests you expect
`20 × 0.05 = 1` significant result *by chance alone* [E: trivially, the
expected false-positive count is α × number of tests]. Corrections
[I: standard]:
- **Bonferroni**: require `p < 0.05/20 = 0.0025` — simple, conservative,
  fine for a fixed short list.
- **Benjamini-Hochberg**: controls the false-*discovery* rate; more power
  when the test family is large and some tests are expected to be true.

The cheaper alternative is to *pre-register the claim*: name the one or
two benchmarks that decide the comparison before running, and report the
rest as descriptive. Pre-registration is the discipline; the correction
math is the fallback.

## When to trust a headline number (checklist)
Before acting on a benchmark number, check [I: editorial checklist]:
1. n and CI attached? (no CI → assume ±2 SEs, usually fatal).
2. Protocol complete? (`Evaluation-Fundamentals.md` minimum spec: model
   revision, dataset version, prompt, scorer, sampling, aggregation, cost).
3. Contamination status stated? (`Benchmark-Contamination.md`).
4. Saturation check: is the set still discriminating in the model's band?
5. Paired or unpaired? Unpaired agent comparisons are task-variance-
   limited (arXiv:2607.12338 [F]).
6. Judge-based? Judge agreement/kappa reported?
7. Effort level fixed? (reasoning models: `Model-Evaluation.md` § effort).
8. Multiple benchmarks? Pre-registered or corrected?

A number that passes this checklist is an evidence-grade measurement; one
that fails most of it is a marketing figure.

## Cost-aware statistics
Cost is a first-class metric with its own statistics [I: practice
positioning]:
- **Variance of cost across tasks** is usually far higher than the
  variance of success: report per-task cost P50/P95/P99, and total budget
  at P95, not at the mean.
- **$/success** (total spend / tasks solved) is the production metric; it
  is a ratio of two noisy quantities, so report it with a bootstrap CI,
  not a point estimate.
- **Effort-curve reporting**: for reasoning models, report
  success-vs-thinking-budget (the full effort curve, not one operating
  point [I: practice; effort levels are vendor-exposed —
  `Model-Evaluation.md` § effort]) because a single operating point hides
  whether the capability is cheap-attainable or only at maximal spend.

## The independent-evaluator pattern, applied to evaluation
The same pattern used to audit agent trajectories — a second, independent
evaluator re-derives the score from artifacts — applies to the evaluation
pipeline itself [I: pattern transfer from
`../Agents/Agent-Evaluation.md`'s agent-as-judge discussion
(arXiv:2410.10934 [F] on agent-as-judge as a method)]:
- **Artifact re-scoring**: dump raw outputs + scoring logs; an independent
  scorer (different judge model, or a human sample) re-scores a random
  slice; the agreement statistics (kappa, above) bound the scorer's
  contribution to the score.
- **Protocol re-execution**: a second team re-runs the protocol from the
  published spec; the reproducibility gap *is* the protocol-completeness
  diagnostic (`Evaluation-Fundamentals.md` § reproducibility crisis).
- **This wiki's own pipeline** is an instance of the pattern: every
  non-trivial claim carries a claim tag ([F] verified source, [E]
  machine-verified arithmetic, [I] inference, UNVERIFIED), and the
  citations registry is audited against arXiv before publication [I:
  description of this wiki's discipline as an application of the pattern].
  An evaluator that cannot be independently re-derived is not, by this
  standard, a measurement.

## Related
- `Evaluation-Fundamentals.md` — what a number is (and its protocol).
- `Benchmark-Contamination.md` — the validity failures statistics can't fix.
- `LLM-as-a-Judge.md` — the stochastic scorer and its biases.
- `../Agents/Agent-Evaluation.md` — trajectory-level evaluation and the independent-evaluator pattern.

## Key Takeaways
A proportion CI on small n is a Wilson interval, not a Wald one — 7/10 is
compatible with 40–89%, and that changes every downstream claim. Pairing
two systems on the same tasks cancels task variance and is the highest-
leverage design choice in model comparison; McNemar on the disagreements
is the test that goes with it. Bootstrap CIs are the default for arbitrary
metrics, and they come out wrong when environment state is shared —
isolate first. Judge scores need kappa before they are measurements, and
any multi-benchmark claim needs pre-registration or correction: of 20
tests, one "significant" result is the null hypothesis.
