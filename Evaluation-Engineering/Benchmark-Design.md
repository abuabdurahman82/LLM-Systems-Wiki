# Benchmark Design: from task to dataset to scorer
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A benchmark is a claim that items, a scoring function, and an aggregation
rule jointly measure a named *construct*. Design failures are almost
always construct failures: the benchmark measures the protocol, not the
capability it names. The pipeline is task definition → item design →
scoring design → aggregation → anti-gaming, and each stage has a named
failure mode (ambiguity, oracle mismatch, credit misassignment, gaming).
Construct validity is the master question — what is the construct, and who
validates that items instantiate it? Difficulty is calibrated with item
response theory; the lifecycle is freeze → saturate → successor; live
benchmarks trade update cost for contamination resistance. At agentic
scale, task count dominates score variance, and the cost of "statistically
clean" designs is so high that practice settles on small held-out sets
plus variance control.

## Design checklist
Working checklist, in build order [I: synthesis of practice; each item
names the failure it prevents]:
1. **Construct validity.** Name the construct in one sentence ("the ability
   to resolve a real GitHub issue with a passing test suite") and who
   validates it: expert reviewers, human performance data, or time (does
   the set stay hard as models improve?). "General intelligence" is not a
   construct; it is a hope [I].
2. **Item design.** Unambiguous (one defensible reading), a single ground
   truth *or* an explicit rubric, difficulty spread. Duplicate or
   near-duplicate answers let models interpolate [I].
3. **Scoring design.** Choose the oracle: exact answer, program (unit
   tests), execution, reference diff, or judge; decide credit assignment:
   all-or-nothing per item, or partial credit (test-pass fraction,
   step-level credit). For agents, cross-step credit is the hard part — a
   task failing at step 80 of 100 has *almost* succeeded, and all-or-
   nothing scoring throws that signal away [I].
4. **Aggregation.** Mean masks a bimodal item set; median is robust to
   outliers but discards the tails; report P10/P50/P90 of per-item success
   across a model pool when the goal is discrimination [I].
5. **Anti-gaming.** Held-out rotation (public split for research, private
   split for final claims), canary strings (marker items whose appearance
   in outputs reveals contamination), and answer uniqueness (no two items
   share an answer string, defeating lookup-style gaming)
   [I: `Benchmark-Contamination.md`].

## Construct validity and its failure modes
The central claim of a benchmark: *the score is a valid proxy for the
construct.* Failure modes, in increasing subtlety [I]:
- **Protocol capture**: the benchmark measures the prompt template, not
  the capability; a prompt tuned to a particular option style lifts scores
  without any capability change.
- **Surface-feature capture**: scorers reward formatting, verbosity, or
  boilerplate ("Therefore, the answer is C") rather than reasoning;
  judge-based scorers are especially exposed (`LLM-as-a-Judge.md`).
- **Population mismatch**: items reflect one domain's style; the score
  generalizes poorly elsewhere [I].
- **Time decay**: the construct moves — "solve a GitHub issue" in 2023 and
  2026 are different constructs once models can read the whole repo; the
  set did not fail, the construct shifted.

The key reframe: **saturation means the construct moved, not that models
stopped improving** [I]. A saturated benchmark is evidence that the items
no longer instantiate the intended difficulty for current models, not
evidence of an intelligence ceiling. The response is a successor set
(harder, newer, or live), not a conclusion about the models. "The
benchmark hit 100%, so we're done" is the most expensive error a research
program can make.

## Difficulty calibration: item response theory
IRT models the probability that a model of ability θ solves an item of
difficulty b and discrimination a [I: standard IRT content, applied by
analogy]:
- **2PL form**: `P(θ) = 1 / (1 + exp(−a(θ − b)))`. `b` is the difficulty
  (θ at which P = 0.5); `a` is the discrimination (steepness at θ = b).
- **Hand example** [E]: item with `a = 1.5`, `b = −0.5`.
  - At `θ = 0`: `P = 1/(1 + exp(−0.75)) = 1/(1+0.4724) ≈ 0.680`.
  - At `θ = 1`: `P = 1/(1 + exp(−2.25)) = 1/(1+0.1054) ≈ 0.905`.
  - At `θ = −2`: `P = 1/(1 + exp(2.25)) ≈ 0.095`.
  One item moves a model from 9% to 90% success as θ goes from −2 to +1:
  a *discriminating* item, centered below average ability — useful for
  separating weak from mid models, useless for separating the frontier.
- **Practice**: fit IRT (or even a per-item success-rate histogram across
  a model pool) to find items that separate your target model band, and
  drop or down-weight items everyone passes or fails — variance without
  information [I].

## Benchmark lifecycle: freeze → saturate → successor
The observed lineage across families [F: each link is a verified arXiv
paper; the lifecycle *pattern* is [I]]:

| Family | Frozen | Successor | Why |
|---|---|---|---|
| Knowledge | MMLU (arXiv:2009.03300 [F]) | MMLU-Pro (arXiv:2406.01574 [F]) | Saturation + 10-option robustness |
| Math | GSM8K (arXiv:2110.14168 [F]) | MATH (arXiv:2103.03874 [F]), then AIME (annual, live [I]) | Saturation, then live-by-construction |
| Code | HumanEval (arXiv:2107.03374 [F]) | LiveCodeBench (arXiv:2403.07974 [F]), BigCodeBench (arXiv:2406.15877 [F]) | Saturation + contamination |
| Agentic SWE | SWE-bench (arXiv:2310.06770 [F]) | SWE-bench Pro (arXiv:2509.16941 [F]) | Long-horizon, harder tasks |

Each successor re-litigates the construct (harder, newer, longer horizon)
and re-runs calibration. The frozen set stays for *regression* (canaries)
even after it stops being a *discriminator* — conflating the two uses is
how stale numbers get published as current capability [I].

## Live-benchmark economics
A live set buys contamination resistance at three costs [I: cost model]:
- **Update cost**: refresh cadence (quarterly for LiveBench-style sets,
  arXiv:2406.19314 [F]) implies a standing pipeline: curation,
  verification, release-date stamping.
- **Annotation cost**: expert-written items (GPQA-style, arXiv:2311.12022 [F])
  cost orders of magnitude more per item than scraped-and-filtered ones.
- **Contamination half-life**: even a live set decays — once items ship,
  they enter the world (forums, datasets, training mixes). The half-life of
  contamination resistance depends on release cadence plus the ecosystem's
  scraping speed [I: no published constant; plan in months, not years].

Design consequence: a live benchmark is a *service*, not a dataset. Teams
that treat it as a one-shot download re-contaminate it by the second
frontier release [I].

## Dataset construction at scale
When items must be generated, the pipeline is **synthesis + filtering**
[I: standard pattern]:
- **Synthesis**: generate candidate tasks from seeds — real repos, issue
  templates, task grammars. SWE-smith (arXiv:2504.21798 [F]) scales SWE
  training data by synthetically *injecting bugs* into real code and
  deriving task pairs: the generator is a bug-injection program, not a
  human annotator.
- **Filtering**: a reference agent must *solve* the generated task at a
  target rate, and a weaker model must *not*; the dual filter keeps items
  in the informative difficulty band (the IRT argument, industrialized).
- **Split discipline**: SWE-Gym (arXiv:2412.21139 [F]) is explicit about
  train/eval separation — the same repo/issue family must not appear on
  both sides, and the split is declared, not implicit. Cross-family
  leakage (same library, same bug class) is the harder failure mode and
  only partially addressable [I].

## Rigorous agentic benchmarks: what "rigorous" means
For agent environments (not just question-answer items), the
best-practices literature (arXiv:2507.02825 [F]) names three
load-bearing requirements [F: the paper's stated practices]:
1. **State isolation** — each run starts from a deterministically reset
   environment (fresh container, fixed filesystem image); no shared state
   between runs or between models.
2. **Seed control** — model sampling seeds and environment randomization
   are fixed and logged, so "same task, same model" is a real rerun.
3. **Deterministic reset** — the reset is itself verified (checksums,
   fixture snapshots), not assumed; a silently drifted fixture changes
   every run that touches it.

Without these, agent scores have an *uncontrolled confound* — the
environment — and the CI you compute is wrong by construction
(`Statistical-Evaluation.md` § bootstrap). HAL (arXiv:2510.11977 [F])
argues for cross-harness, cross-task leaderboards precisely because
single-environment numbers are harness-specific.

## How many tasks are enough
Replay analyses of public agent benchmarks (arXiv:2607.12338 [F]) find
that **task count, not run count, is the dominant driver of score
variance** [F: the paper's finding] — 50 tasks × 10 runs is noisier than
500 tasks × 2 runs, because task-sampling variance dominates. Implications
[I: interpretation]:
- Buy tasks before buying runs; more distinct environments beat more
  repeats of the same environments.
- A decision-grade benchmark (go/no-go between two systems) needs enough
  tasks that the task-sampling SE of the mean is below the effect size you
  care about — the worked example shows how far that is from practice
  budgets.
- Leaderboard positions are only as stable as the task set: with few
  tasks, systems flip ranking under resampling even when the true ordering
  is fixed [I: direct consequence of the variance result].

## Contamination-resistant design
Design-level defenses, beyond the operational ones in
`Benchmark-Contamination.md` [I: design framing; arXiv:2505.08389 [F]
studies contamination resistance as a benchmark property]:
- **Temporal stamping**: every item carries a creation/release date; claims
  for models released after date X use only items newer than X
  (LiveCodeBench's time-windowing, arXiv:2403.07974 [F]).
- **Private core**: a never-published fraction of items; public items for
  research, private items for final claims.
- **Answer obfuscation / re-encoding**: periodically restate items in new
  surface form (new variables, wording, repos) so memorized patterns stop
  transferring while the construct stays fixed [I: re-encoding must not
  move the construct — re-validate the IRT band].
- **Canary items**: a few items with known unique answers, whose
  appearance in outputs or corpus probes is the contamination alarm [I].

## Worked example: the cost of a statistically clean agent benchmark [E]
Design a 1000-task agent benchmark; per-task outcome is Bernoulli with
`p = 0.5` (variance `p(1−p) = 0.25`).

**Per-task precision.** With `r` runs of the same task, the SE of that
task's success rate is `0.5/sqrt(r)`: `r = 1` → `0.5` (one coin flip, no
information); `r = 5` → `0.5/sqrt(5) = 0.5/2.236 ≈ 0.224`.

**Benchmark-level precision (the reported number).** The benchmark score
is the mean over 1000 tasks; the SE of that mean is `0.5/sqrt(1000·r)`:
`r = 1` → `0.5/sqrt(1000) ≈ 0.0158` (1.6 points); `r = 5` →
`0.5/sqrt(5000) ≈ 0.0071` (0.7 points). (The spec-of-record "SE 0.05 at 1
run / 0.0224 at 5 runs" refers to a *per-task* estimate on a much smaller
task set; at 1000 tasks, task-averaging already buys most of the
precision.)

**Detecting a 3-point improvement.** The strict requirement is
per-task-level: if each task's estimate is noisy, no aggregation rescues
it. Require `1.96·0.5/sqrt(r) < 0.03`: `sqrt(r) > 1.96·0.5/0.03 = 32.67`
→ `r > (32.67)² = 1067.1`, i.e. **≈ 107 runs per task** [E: check
`1.96·0.5/sqrt(1070) ≈ 0.0300`]. (If instead you rely on the 1000-task
mean, `r = 2` already gives a difference-SE of `sqrt(2)·0.5/sqrt(2000) ≈
0.0158`, well under 3 points — task count and run count trade off, and
arXiv:2607.12338 [F] says spend on the task dimension first.)

**Cost math** (per-task level, the conservative reading): 1000 tasks ×
107 runs × 2,000 tokens/run × $0.50/M tokens
= `1000 × 107 × 2000 × 0.5 / 10⁶ = $107,000` [E]; the full 1070-runs-per-
task reading is `1000 × 1070 × 2000 × 0.5 / 10⁶ = $1,070,000` [E]. Against
typical internal benchmark budgets, this is the arithmetic that explains
the field's actual practice: **small held-out sets (tens to low hundreds
of tasks) plus variance control** — seeds, state isolation, task-count
maximization, and *paired* comparisons of two systems on the *same* tasks,
which remove the task-variance term entirely [I: practice inference;
paired designs in `Statistical-Evaluation.md`].

## Related
- `Evaluation-Fundamentals.md` — the protocol the design instantiates.
- `Benchmark-Contamination.md` — operational defenses to the design-level ones.
- `Statistical-Evaluation.md` — sample-size and paired-test machinery.
- `Agent-Tool-Use-Evaluation.md` — agentic item design in depth.
- `../Benchmarks/README.md` — per-benchmark reference.

## Key Takeaways
A benchmark's score is a property of its construct, items, scorer, and
aggregation — and its most common failure is measuring the protocol, not
the capability. Saturation means the construct moved; the answer is a
successor or a live set, not a ceiling claim. IRT (even just a per-item
success histogram) tells you which items carry information. At agentic
scale, task count dominates score variance, and fully clean statistics
cost six figures — so practice is small held-out sets, seeds, isolated
state, and paired comparisons.
