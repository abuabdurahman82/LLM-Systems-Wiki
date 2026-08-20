# Contamination and Saturation: when a benchmark stops measuring
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A benchmark stops measuring in two distinct ways. **Contamination**: the
test items (or their patterns) entered the training data, so the score
partially measures *memorization*, not capability — a model that saw the
question at training time can retrieve the answer without reasoning.
**Saturation**: the ceiling is reached (scores near 100%), so the benchmark
no longer *discriminates* between models, and protocol differences and
noise dominate the remaining spread. Contamination is a *validity* failure
(the construct moved to "has this been seen?"); saturation is an
*information* failure (variance and protocol artifacts now carry the
signal). Detection tools overlap but target different failures: n-gram
overheaps and probe sets catch memorization; temporal analysis (new model
families scoring far above the frontier on a frozen set) is the telltale
signature of contamination; score compression at the top signals
saturation. Mitigation is the same direction from both sides: live/rolling
sets, private held-out cores, and canary strings. The 2026 landscape favors
live sets, especially for agentic benchmarks, where the task space is large
enough to keep rotating.

## Definitions: the two failure modes
- **Direct contamination (memorization)**: train/test overlap — the item,
  its phrasing, or its answer was in training data. The model's score on
  that item measures retrieval. Detection: exact or near-duplicate overlap
  between test items and corpus samples [I: standard n-gram/substring
  heuristics].
- **Indirect contamination (pattern leakage)**: the item was not seen, but
  the *format, style, or problem class* was seen extensively — the model
  learned the solution *template* (e.g., "this MCQ style has the answer in
  option C 60% of the time"). Harder to detect, equally damaging [I].
- **Saturation (ceiling)**: the population being measured all scores near
  the maximum. The benchmark still measures something, but not
  *differences between the models you care about* — discrimination dies
  before the scale does. `Benchmark-Design.md` § lifecycle treats
  saturation as the trigger for successor sets.
- **The interaction**: contamination *causes* apparent saturation. A
  contaminated set looks saturated even to models that are not actually
  strong, because the score is partly memorization. Distinguishing the two
  is the whole game — the mitigations differ (rotate vs. harden).

## Detection methods
No single detector is sufficient; practice stacks several [I: the stack is
author synthesis; individual techniques are standard]:

- **Probe sets / canaries**: a small set of items never disclosed, whose
  items and answers are tracked. If probe items appear in training-data
  audits, in model memorization outputs, or in the training corpora of
  suspected models, the audit fires [I: canary practice]. Canary strings in
  the *items themselves* (marker text that should never be reproduced) are
  the cheaper variant.
- **N-gram / overlap heuristics**: substring or n-gram match rates between
  test items and sampled training corpora; a rate far above the random-text
  background is evidence of overlap [I: threshold is corpus-dependent; no
  universal constant].
- **Perplexity gap**: models assign anomalously low perplexity to
  contaminated test items relative to held-out control items of matched
  difficulty. A large test-vs-control gap, *conditioned on the model being
  strong enough to parse the items*, is a memorization signal [I: the
  conditioning matters — a weak model has high perplexity everywhere].
- **Temporal analysis**: plot frontier scores on a *frozen* set against
  model release date. A frozen set whose top score climbs sharply as each
  new family ships (while a contemporaneous *live* set climbs slowly) has
  a contamination gradient — newer models "remember" more of the frozen
  set. This is the most practical field signal, because it needs only
  public leaderboards [I: method-level claim; the pattern is well
  documented across frozen math/code sets].
- **Watermarks for contamination detection**: embed detectable
  statistical structure (token-level watermarks, stylized phrasing) in
  benchmark items so that memorization is *detectable in model outputs* —
  if a model reproduces the watermark, the item was seen [I: research
  direction; adoption in public benchmarks is limited].
- **Memorization studies on specific sets**: the SWE-bench Verified
  memorization study (arXiv:2512.10218 [F]) asks whether top SWE-bench
  scores measure agent ability or model *memory* of the issue set, and
  finds meaningful memorization signatures on popular issue instances
  [F: paper's claim; specific magnitudes are in the paper]. The method —
  contrast performance on known-seen vs. known-unseen issue slices — is a
  template for auditing any agentic set.

## Mitigation
- **Live / rolling sets**: refresh items on a cadence so the set is
  perpetually "newer than most training cutoffs." LiveBench
  (arXiv:2406.19314 [F]) updates quarterly with contamination-limited
  curation; LiveCodeBench (arXiv:2403.07974 [F]) time-stamps problems and
  scores only on the post-cutoff window. Economics in
  `Benchmark-Design.md` § live-benchmark economics.
- **Private held-out core**: publish the research split, keep a private
  final split; publish aggregate claims only against the private core,
  released after the model's training cutoff [I: practice standard].
- **Canary strings**: marker content inside items or item IDs that any
  reproduction in model output or corpus audits flags [I: practice].
- **Adversarial re-encoding**: restating saturated/leaked items in new
  surface form (new variable names, repos, phrasing) to *revive* them
  while holding the construct fixed; then re-validate the difficulty band
  (an item re-encoded to be easier is now a different item) [I: the
  revival operation and its construct-preservation caveat].
- **Answer uniqueness + obfuscation**: no shared answer strings across
  items; rotation of distractor sets for MCQ [I: defeats lookup-style
  gaming, see `Benchmark-Design.md` § anti-gaming].

## Saturation as an information problem
Once the ceiling is reached, the *absolute* standard error shrinks — for
`p` near 1, `SE = sqrt(p(1−p)/n)` is small — but the *discrimination
problem* gets harder, not easier, because the gap you must resolve shrinks
faster than the SE [I: the core argument]. A benchmark where the best
models sit at 0.95–0.99 must resolve a 4-point gap; a benchmark where they
sit at 0.60–0.80 must resolve a 10–20 point gap. The first is
statistically much more expensive.

**Hand example: how many items to separate 0.95 from 0.99?** [E] Two
models, true success rates `p1 = 0.95` and `p2 = 0.99`, evaluated on the
same `n` items each. We want the two-sample test to distinguish them with
95% confidence (α = 0.05, two-sided) and 80% power. The standard
two-proportion sample size is:

`n = (z_{α/2} + z_β)² · (p1(1−p1) + p2(1−p2)) / (p1 − p2)²`

Step by step:
- `z_{α/2} = 1.96`, `z_β = 0.84` (for 80% power).
- `p1(1−p1) = 0.95 × 0.05 = 0.0475`; `p2(1−p2) = 0.99 × 0.01 = 0.0099`; sum = `0.0574`.
- `(p1 − p2)² = 0.04² = 0.0016`.
- `n = (1.96 + 0.84)² × 0.0574 / 0.0016 = (2.80)² × 35.875 = 7.84 × 35.875 ≈ 281`.

So roughly **n ≈ 282 items per model** — just to tell 0.95 from 0.99 with
decent power [E: verified; with exact z-values 1.959964/0.841621 the solve
gives 281.6, i.e., 282]. Sanity check in the other direction: at `n = 100`
per model, the 95% margin for the difference is
`1.96 × sqrt(0.0475/100 + 0.0099/100) = 1.96 × sqrt(0.000574) = 1.96 × 0.0240 ≈ 0.047`,
which is *larger* than the 0.04 gap — the test cannot separate the models
at 100 items [E: `sqrt(0.000574) ≈ 0.02396`; `1.96 × 0.02396 ≈ 0.0470`].
The operational lesson: a "saturated" benchmark is not merely boring — it
is *statistically expensive*, and a 300-item set at the top of the scale
still cannot cleanly separate the two best systems. This is the arithmetic
behind "rotate the set, don't argue with it" (`Statistical-Evaluation.md`
for the full two-sample machinery).

## When to retire a benchmark
Retire (or demote to canary-only) when any of these hold [I: editorial
criteria, not a single source]:
1. **Discrimination is gone**: the frontier band scores within ~1 SE of
   each other on the set, persistently across releases.
2. **Contamination is confirmed**: an audit (probe, overlap, or
   temporal-gradient method) shows test items in training data; the
   construct is now "memorization + capability" and the decomposition is
   unrecoverable.
3. **The construct moved**: the task style no longer represents the
   capability of interest (e.g., one-shot MCQ knowledge vs. agentic
   retrieval) — the set is *valid but obsolete*.
4. **Cost of staying current exceeds value**: the live-update pipeline
   costs more than the decisions the number supports.

Retirement is not deletion: the frozen set stays as a regression canary
(stability check across model revisions), and its historical scores stay
in the record with the protocol attached. `../Evaluation/README.md` keeps
the status-of-sets overview; `../Benchmarks/README.md` the per-set
reference.

## The 2026 landscape
Agentic sets (SWE, terminal, web, tool-use) are where the action is, and
they are the hardest to keep clean: the task space is large enough to
rotate (`Benchmark-Design.md` § how many tasks are enough — arXiv:2607.12338
[F] shows task count drives variance, which argues *for* large rotating
sets), but each task is expensive to run, which argues for small sets.
The field's compromise in 2026 is live sets for *claim-grade* evaluation
(private cores, temporal stamping, canaries) plus large public sets for
research and regression, with the SWE-bench Pro line (arXiv:2509.16941 [F])
as the current hard end of the software-engineering spectrum
[ I: landscape judgment; the per-set statuses are in
`../Benchmarks/README.md` ]. Contamination-resistant benchmark design as a
research topic (arXiv:2505.08389 [F]) and the verified-set memorization
audit (arXiv:2512.10218 [F]) mark the shift from "release a set" to
"operate a set" [I: interpretation of the 2025-26 literature mix].

## Related
- `Benchmark-Design.md` — design-level defenses and the lifecycle.
- `Statistical-Evaluation.md` — sample-size math and CIs behind the numbers above.
- `Model-Evaluation.md` — reading leaderboard numbers with contamination discount.
- `../Benchmarks/README.md` — per-benchmark reference and status.
- `../Evaluation/README.md` — set-status overview.

## Key Takeaways
Contamination measures memory, not capability; saturation measures noise,
not a ceiling — the mitigations differ but both point at live/rolling sets
with private cores and canaries. Temporal analysis (frozen-set scores
climbing with each release while live sets lag) is the cheapest field
signal of a contamination gradient. At the top of the scale, separating
0.95 from 0.99 needs ~282 items per model at 80% power — saturation is a
statistical cost problem, not just a boredom problem. Retire sets when
discrimination dies or contamination is confirmed; keep them as canaries,
never as current-capability claims.
