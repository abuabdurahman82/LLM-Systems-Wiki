# LLM-as-a-Judge: the workhorse, its biases, and its calibration

`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation

For open-ended outputs — summaries, plans, refusals, RAG answers — human rating is the
gold standard but it is expensive, slow, and inconsistent across raters. An LLM judge is
the workhorse substitute: a judge model scores or ranks candidate outputs, and MT-Bench /
Chatbot Arena demonstrated that a strong judge reaches high agreement with human
preferences at a fraction of the cost [F: arXiv:2306.05685]. But the judge is itself a
model: it has a bias taxonomy (position, verbosity, self-enhancement, style-over-substance,
language) [I; F: arXiv:2305.17926; arXiv:2411.15594], pairwise comparison is a trap that
*amplifies* those biases [F: arXiv:2406.12319], and judges are overconfident — confident
even when wrong [F: arXiv:2508.06225]. The discipline is therefore: pick a paradigm,
mitigate known biases, calibrate against a human-labeled set, track judge drift across
versions, and know when *not* to use a judge at all. The meta-problem: evaluating the
judge is itself an evaluation, and the loop terminates at humans [I].

## Why judges, and the three paradigms

Humans are expensive (tens of dollars per hundred judgments at market rates [I]), slow
(hours of annotation for thousands of outputs), and inconsistent (inter-rater agreement
is never 1.0 — see `Human-Evaluation.md`). A judge model scales to any number of outputs
with one API call each, is available at 2 a.m., and — if calibrated — reproduces human
preferences with high agreement [F: arXiv:2306.05685].

The three paradigms [I]:

| Paradigm | Input to judge | Output | Strength | Weakness |
|---|---|---|---|---|
| Pointwise scoring | single output + rubric | score (e.g. 1–10) | absolute scale, comparable across time | rubric drift, verbosity bias |
| Pairwise comparison | two outputs | which is better | matches how humans actually decide | position bias, the comparative trap |
| Reference-guided | output + reference answer | score vs reference | grounds the judgment, less free-floating | reference quality caps the ceiling |

MT-Bench used pointwise scoring (1–10 with a rubric) over multi-turn conversations
[F: arXiv:2306.05685]; Chatbot Arena used live pairwise human preference, which is why the
comparative-trap literature matters for both. [I]

## The bias taxonomy

- **Position bias** — in pairwise comparisons, the order of the options changes the
  verdict; LLMs are not fair evaluators, and the effect is measurable, not anecdotal
  [F: arXiv:2305.17926].
- **Verbosity bias** — longer answers get higher scores even when the extra length is
  filler [I].
- **Self-enhancement / self-preference** — judges favor outputs from their own model
  family; a GPT judge grades GPT-like text more leniently. Surveys of the judge
  literature catalog this and the other biases [F: arXiv:2411.15594; I: mechanism].
- **Style over substance** — fluent, well-formatted answers beat correct-but-clumsy ones
  [I].
- **Language bias** — non-English or low-resource-language outputs are systematically
  scored lower [I].

**The comparative trap**: pairwise comparison does not just inherit these biases — it
*amplifies* them. When forced to choose between two similar answers, the judge latches
onto surface cues (position, length, formatting) and the resulting ranking can diverge
sharply from true quality [F: arXiv:2406.12319]. Pairwise is the most natural protocol
and one of the least reliable. [I]

## Mitigation playbook [I]

1. **Swap positions and require consistency.** Run each pair both orders (A,B) and (B,A);
   if the verdict flips, discard the pair as a tie or mark it low-confidence. This is the
   direct counter to position bias.
2. **Reference-guided rubrics.** Give the judge a reference answer or an expected-answer
   sketch so the score is anchored, not free-floating.
3. **Decompose the rubric into binary checks.** "Contains a citation?", "Numbers are
   correct?", "Answers the actual question?" — binary sub-scores are more reliable and
   more debuggable than a holistic 1–10.
4. **Different judge model than the evaluated model.** Breaks the self-preference loop
   (or at least moves it out of the direct diagonal).
5. **Calibration set with human labels.** A fixed set of outputs with human scores; the
   judge's job includes reproducing it. Track judge-human agreement (Cohen's kappa or
   Spearman, see `Statistical-Evaluation.md`) and treat a judge whose calibration
   regresses as a broken instrument.
6. **Bias-aware scoring** — mitigation methods from the literature: de-biasing the
   scoring prompt and aggregating across orderings [F: arXiv:2409.16788].
7. **Calibrate confidence** — judges are overconfident, so use confidence-driven
   solutions: weight or gate judgments by calibrated confidence rather than raw scores
   [F: arXiv:2508.06225].

## Calibration and drift tracking

The judge is an instrument, and instruments drift. Protocol [I]:

- **Frozen gold set.** A fixed set of outputs with stable human labels. Re-run it every
  time the judge model version changes (or its prompt changes). A judge-version bump that
  moves gold-set agreement by more than your tolerance is a red flag, not a minor
  upgrade.
- **Agreement metrics.** Kappa for categorical judgments, Spearman for rankings
  [I; `Statistical-Evaluation.md`]. Report both the level of agreement and the trend.
- **Version the judge prompt** as carefully as the judge model: prompt drift is a model
  change wearing a different label. [I]

## When NOT to use a judge

- **High-stakes safety decisions** — the tail case goes to a human, always. A judge's
  95% accuracy means 5% of the safety tail is machine-signed, which is not acceptable
  at the boundary. See `Safety-Red-Teaming.md`. [I]
- **Numeric / exact answers** — use exact match or programmatic checks; a judge adds
  bias with no information gain. [I]
- **The safety tail** — specialized moderation classifiers (e.g. WildGuard
  [F: arXiv:2406.18495]) are purpose-built for risk labeling and outperform a general
  judge on that task. [I]

## The meta-problem

Evaluating the judge is itself an evaluation: you need a better judge, or humans. There is
no escaping the loop — judge-of-judges recursion terminates at human labels, which is
why a frozen, human-labeled gold set is not a nicety but the base of the whole edifice
[I]. If you cannot afford the human labels for the gold set, you do not have a calibrated
judge; you have a second opinion, and those are worth stating as such. [I]

## Cost and throughput: the hand example

Judges are LLM calls: batchable, parallelizable, and — for a deterministic judge
(model + prompt + temperature 0) — cacheable. A cache key is (prompt_hash,
model_version, temperature, item_id); any change invalidates. [I]

Hand example [E]:

- 10,000 outputs to judge, one judge call each, ~1.5k tokens per call (prompt + output
  + verdict).
- Total tokens: 10,000 × 1.5k = 15M tokens.
- At $2 per million tokens [I: assumed blended pricing]: 15 × $2 = **$30**.

That is the full cost of a 10k-output judge pass — roughly the cost of one human
annotator-hour at market rates [I], which is the entire argument for judges: not
*cheaper*, but *thousands of times more throughput* at acceptable (calibrated)
accuracy. The pairwise protocol doubles the call count (both orders), and image items
add vision tokens on top (see `Multimodal-Evaluation.md`). [I]

## Judge ensembles

A common defense: run 3 judges and take a majority vote. This cuts **idiosyncratic**
error — one judge's quirk — but not **correlated** error: if all three share the same
training lineage, the same bias (they all favor verbosity, say), the ensemble's
agreement is high and its error is high too. Ensemble diversity must be real (different
families, not three checkpoints of one model) to buy anything [I]. And ensembles triple
the cost, so they are for high-stakes or release-gating runs, not routine triage. [I]

## Interlock

LLM-as-a-judge is the scoring layer under three other disciplines in this section:

- `RAG-Evaluation.md` — RAG answer quality is judge-scored (faithfulness, relevance);
  judge bias directly contaminates RAG numbers.
- `Human-Evaluation.md` — the hybrid pipeline: judge pre-screens, humans audit a sample;
  the calibration set is the bridge between the two.
- This wiki's own pipeline uses an independent evaluator (judge) over generated content,
  following the same discipline: calibration set, versioned prompt, disagreement goes to
  humans. See `../Agents/Agent-Evaluation.md` for the agent-eval instance of the pattern.

## Related

- `Human-Evaluation.md` — gold labels, raters, and the hybrid pipeline
- `Statistical-Evaluation.md` — agreement metrics (kappa, confidence intervals)
- `RAG-Evaluation.md` — the most common judge workload
- `Safety-Red-Teaming.md` — where the judge is NOT the answer
- `../Agents/Agent-Evaluation.md` — judge-of-agents and the same calibration discipline

## Key Takeaways

An LLM judge scales evaluation to a fraction of human cost [F: arXiv:2306.05685], but it
is a biased instrument: position, verbosity, self-preference, and style biases are
measurable [F: arXiv:2305.17926; arXiv:2411.15594], and pairwise comparison amplifies
them [F: arXiv:2406.12319]. The mitigation playbook — position swaps, binary rubric
checks, reference guidance, a different judge family, a frozen human-labeled gold set —
is not optional decoration; it is what separates a calibrated judge from a second opinion.
And know the escape hatch: high-stakes safety and exact-match cases do not use a judge at
all.
