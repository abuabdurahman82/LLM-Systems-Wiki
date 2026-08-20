# Evaluation Fundamentals: the discipline of measuring LLMs
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Evaluating an LLM means fixing a *protocol* — task, dataset, prompt
template, scorer, aggregation rule — and reporting what that protocol
produces, not what it *claims* to measure. The unit of measurement ranges
from a single output (one prompt, one completion) to a trajectory
(multi-step tool use) to a full system (model + harness + serving), and
the unit changes what the number means. Capability, reliability, and cost
are three orthogonal axes: a model can be capable but unreliable, or
reliable but expensive, and no single scalar collapses them. Scorers split
into deterministic ones (exact match, regex, unit tests, execution) and
stochastic ones (LLM judges), and the scorer choice moves the number more
than the model choice sometimes does. The same model on the same task gives different scores under different
protocols — sampling, context limit, effort level, retries, harness — so a
number without its full protocol is a rumor. Core discipline: version
protocols, report them in full, treat any headline as a property of
*model + dataset + scorer + protocol*, not of the model alone.

## The eval stack: task to report
A complete evaluation is a pipeline, and every stage carries degrees of
freedom that leak into the final number [I: structural decomposition]:

| Stage | What it fixes | Degrees of freedom |
|---|---|---|
| Task | What the model must do (solve, classify, act) | Construct definition, ambiguity |
| Dataset item | Concrete input + reference (answer, rubric, env state) | Difficulty, uniqueness, contamination risk |
| Prompt template | How the item is presented (system prompt, formatting, few-shot) | Wording, shot count, role framing |
| Scoring function | How one output maps to a score | Exact match vs judge vs execution; partial credit |
| Aggregation | How per-item scores become a number | Mean, median, percentile; weighting |
| Report | What is published | Protocol, CI, cost, percentiles |

Each stage is a hidden confounder: changing the prompt template
(system-prompt wording, few-shot examples) can shift scores by more than a
model release [I: observed across suites; treat as an empirical rule]. The
report stage is where most public evals fail — they publish the number
without the pipeline. `../Evaluation/README.md` surveys benchmark families.

## Unit of measurement
The unit determines everything downstream [I]:
- **Single output**: one prompt, one completion; per-item correctness,
  i.i.d. assumptions roughly hold, standard proportion CI math applies
  (`Statistical-Evaluation.md`).
- **Trajectory**: a sequence of model steps interacting with an
  environment (tools, web, repo, terminal). The unit is *task success
  rate*, horizon-dependent; trajectories share environment state, so
  independence assumptions break (`../Agents/Agent-Evaluation.md`).
- **System**: model + harness + serving config. The number is a *system*
  property, not a model property; harness differences (retries, memory,
  tools) routinely move agentic scores by 10+ points [I].

Common error: reporting a system-level number as if it were model-level.
The unit must be declared in the protocol.

## Capability, reliability, cost: three axes
- **Capability**: *can* it do the task, at best effort? Success rate on
  hard items, often at high sampling budget or reasoning effort [I].
- **Reliability**: *how consistently*? Variance across seeds,
  self-consistency, pass@k vs pass@1 gaps. A model at 80% with
  temperature 0 but 60% at temperature 1 is less reliable than one flat
  at 75% [I: definition-level claim].
- **Cost**: tokens, latency, money per success. Capability per dollar is
  the production number and the one almost never reported.

These are orthogonal: a strong, high-variance, high-cost model is a
different product from a weaker one that is cheap and stable [I].
Reporting only capability while silently varying effort or retries is the
most common leaderboard-misleading pattern [I].

## Deterministic vs stochastic scorers
| Scorer | Type | Properties |
|---|---|---|
| Exact match | Deterministic | Cheapest, zero scoring variance, brittle to formatting |
| Regex / normalized | Deterministic | Handles whitespace, case, units; still brittle |
| Unit tests / execution | Deterministic | Tests behavior, not string; gameable by special-casing |
| Reference-diff (code) | Deterministic | Partial credit via test-pass fraction |
| LLM judge | Stochastic | Open-ended quality; adds its own bias and variance |
| Self-consistency sampling | Stochastic | Uses the model's own distribution; cost multiplies |

Deterministic scorers give *reproducible* scores for a fixed model output;
stochastic scorers add a second noise layer on top of the model's sampling
noise. When a judge scores 100 items, its own inter-run variance
contributes to the CI — the effective n is smaller than the item count
[I]. See `LLM-as-a-Judge.md` for judge bias (position, verbosity,
self-preference) and `Statistical-Evaluation.md` for the CIs.

## Protocol sensitivity: same model, different numbers
The same model + task produces materially different aggregate scores when
any of these protocol knobs moves [I: mechanism, each independently
observable]:
- **Sampling**: temperature, top-p, seed; stochastic sampling alone moves
  a 40-item mean by a few points (`Statistical-Evaluation.md`).
- **Context limit**: truncation policy (drop oldest vs newest) changes
  long-context scores (`../Context-Engineering/README.md`).
- **Effort / thinking budget**: reasoning models expose effort levels; low
  vs high effort differs by tens of points on hard math [F: vendor —
  vendor models expose configurable effort/reasoning budgets; the magnitude
  is model- and task-specific and must be measured, not assumed].
- **Retries / self-repair**: allowing a retry of a failed tool call or a
  regenerated test adds a fixed offset easily confused with capability.
- **Harness**: tool definitions, memory, agent loop; different scaffolds on
  the same model differ widely (`../Agents/Agent-Evaluation.md`).

**Minimum protocol spec** — fields a report must include for its number to
be meaningful [I: editorial standard; mirrors HELM's multi-metric
discipline, arXiv:2211.09110 [F]]:
1. Model identifier + revision + serving config (context, max tokens).
2. Dataset + split + revision (commit or version tag); 3. prompt template
   (or a stable reference to it); 4. scorer (deterministic vs judge, judge
   model + version); 5. sampling parameters (temperature, top-p, seeds,
   run count); 6. aggregation (mean/median/percentile, per-item vs
   per-task); 7. cost (tokens and $ per run and per success); 8. CI or SE
   for the headline number.

## Evaluation vs verification vs monitoring
- **Evaluation**: one-shot measurement of capability on a benchmark — "how
  good is this model at X?" Offline, expensive, low frequency.
- **Verification**: checking that a *specific output* meets a spec — unit
  tests, execution, schema checks, judge rubric — "did this output do the
  thing?" Online, cheap per check, high frequency.
- **Monitoring**: continuous drift detection on a *canary set* — a small
  fixed set run on every deploy, with SLOs (success rate, P95 latency, cost
  per success) — "did the deploy regress?" SLO vocabulary in
  `../Inference/Inference-Metrics.md`.

A canary set is deliberately small (tens of items) and *frozen* — its value
is stability of the reference, not difficulty. Drift is detected against
the canary's own history with a control chart, not against a leaderboard
[I].

## The reproducibility crisis as a case study
Public AI evaluations have long suffered a reproducibility problem: results
published in papers frequently do not reproduce under the evaluator's own
setup, because the protocol (prompt, sampling, harness) is underspecified
[I: author inference from repeated field observation; the weakness of
AI-research reproducibility is a standing discussion, not a single citable
study]. The failure mode is structural: a benchmark number without its
protocol is underdetermined, so two competent labs running "the same eval"
can differ by more than the noise they report. Versioned protocols —
dataset commits, pinned prompt templates, pinned scorer code, declared
sampling — are the fix, and they are cheap relative to the cost of a wrong
model choice. This wiki's claim-tag discipline ([F], [E], [I], UNVERIFIED)
applies the same principle at document level: every number must trace to a
verified source or be explicitly flagged as inference.

## Worked example: three scorers, one sample, three numbers [E]
Evaluate one model on a 40-item open-numeric QA sample; run three scorers
on the *same* 40 raw outputs:
1. **Exact match** (string equality vs reference): 30 of 40 correct.
   `30 ÷ 40 = 0.75` → **75.0%**.
2. **Regex-normalized** (strip units, whitespace, case; parse numeric):
   35 of 40. `35 ÷ 40 = 0.875` → **87.5%**.
3. **LLM judge** (seems-correct rubric, one pass): 33 of 40.
   `33 ÷ 40 = 0.825` → **82.5%**.

The spread (75% to 87.5%, a 12.5-point range) exceeds the sampling noise of
a 40-item estimate: SE of a proportion at p = 0.8, n = 40 is
`sqrt(0.8·0.2/40) = sqrt(0.16/40) = sqrt(0.004) ≈ 0.063`, so the 95% CI is
roughly ±12 points [E]. The scorer choice, not the model, is the dominant
source of variation.

**Why "which score is the model's score?" is ill-posed**: the question
presupposes a single true number the protocol recovers. But the scorers
measure *different constructs*: exact match measures "does the output
string match the reference," regex measures "does the parsed value
match," the judge measures "does an LLM find the answer acceptable." Each
is a valid measurement of its own construct; none is "the" model quality.
The honest report is all three, construct named per scorer, with the gap
between them (12.5 points here) reported as *scorer sensitivity* — a
first-order feature of the evaluation, not an error to hide. This is the
concrete instance of the stack argument: the scorer stage is a degree of
freedom, and the report stage must disclose it.

## Related
- `Model-Evaluation.md` — benchmark families and score hygiene.
- `Benchmark-Design.md` — building tasks, items, and scorers.
- `Statistical-Evaluation.md` — CIs, paired tests, judge agreement.
- `LLM-as-a-Judge.md` — the stochastic scorer in depth.
- `../Agents/Agent-Evaluation.md` — trajectory-level evaluation.
- `../Evaluation/README.md` — benchmark survey.

## Key Takeaways
A benchmark number is a property of *model + dataset + prompt + scorer +
aggregation + sampling*, not of the model alone; report the full protocol
or the number is a rumor. The unit of measurement (output vs trajectory vs
system) and the scorer family (deterministic vs stochastic) are the two
decisions that usually move a score more than the model choice does.
Capability, reliability, and cost are orthogonal axes, and conflating them
— or silently varying effort and retries — is the standard way leaderboards
mislead. Version your protocols; the reproducibility crisis is the failure
mode of not doing so.
