# Human Evaluation: gold labels, raters, and hybrid pipelines

`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation

For open-ended quality — preference, helpfulness, the safety tail — humans remain the
ground truth; no judge model gets to define "helpful" on its own authority. The craft is
annotation engineering: task instructions, a binary rubric where possible (binary beats
5-point Likert for inter-rater reliability [I]), worked examples, and item-level ground
truth (an exact answer is worth a preference) [I]. The quality gate is **rater
reliability**, measured by inter-rater agreement and Cohen's kappa [I], and it is only
achievable with trained raters — calibration rounds on gold items before production
labeling starts [I]. Preference data (Chatbot Arena's anonymous pairwise collection
[F: arXiv:2306.05685], scored via Elo/Bradley-Terry [I]) and fine-grained multi-turn
benchmarks (MT-Bench-101 [F: arXiv:2402.14762]) show the two ends of human eval: mass
casual preference vs. small carefully labeled set. The modern pipeline is hybrid: an LLM
judge pre-screens, humans sample-audit 10–20% [I]. Humans win on trust and lose on
speed: a 1000-item × 3-annotator pass costs ~$500 and 25 annotator-hours [E], which is
why the eval design question is *which* items get human attention, and the answer is:
hard cases first [I].

## Why humans are still the ground truth

- **Open-ended quality has no reference.** "Helpfulness," "tone," "does this plan make
  sense" are not properties of the text alone; they are judgments a person makes in
  context. A judge model's notion of helpfulness is a learned proxy, and the proxy is
  exactly what you are trying to validate. [I]
- **The safety tail is high-stakes.** Rare, consequential failures (a jailbreak that
  works, a refusal that should not have happened) are precisely where a judge's error
  rate matters most and human review is the only defensible gate. See
  `Safety-Red-Teaming.md`. [I]
- **Novel capability frontiers.** When the model is doing something no training-time
  label distribution covers, the only yardstick is a person who understands the task.
  [I]
- **Data selection as an eval product.** Human (or judge-proxy-of-human) preference
  signals are used to *select training data*: AlpaGasus showed that a small set selected
  by judge-scored quality beats random selection cheaply — the preference labels are
  the product, not just the measurement [F: arXiv:2307.08701].

## Annotation design

The annotation spec is an engineering artifact, not a form. Required fields [I]:

1. **Task instructions** — the exact question the rater answers, unambiguous, with the
   decision rule ("refused = model declined the request; partial refusal counts as
   refused"). Ambiguity here is the biggest source of rater disagreement.
2. **Rubric.** Binary where possible: "helpful / not helpful" is far more reliable than
   "rate 1–5" — 5-point scales have midpoint clustering and rater-scale-shift artifacts,
   and their inter-rater agreement is typically much lower than a well-specified binary
   [I]. If a scale is unavoidable, anchor every point with an example.
3. **Worked examples** — 3–5 labeled items covering the edge cases (the obvious good,
   the obvious bad, and the *hard* one), so raters converge on the interpretation before
   touching production items.
4. **Item-level ground truth where possible** — if the item has an exact answer
   (a number, a code patch that passes, a factual claim with a source), use exact match;
   "is the answer correct" is cheaper to label reliably and more informative to report
   than "is this answer better than that one." Preference labels are the last resort,
   not the default. [I]

## Rater reliability: kappa and the hand example [E]

Two raters label 200 binary items ("yes = refusal observed"). They agree on 172 items.
Rater 1 says "yes" on 130 of 200; rater 2 on 120 of 200.

- Observed agreement: 172/200 = **0.86**.
- Chance agreement: P(both yes) + P(both no) = (130/200)(120/200) + (70/200)(80/200)
  = (0.65)(0.60) + (0.35)(0.40) = 0.39 + 0.14 = **0.53**.
- Cohen's kappa: (0.86 − 0.53) / (1 − 0.53) = 0.33 / 0.47 = **0.70** — "good" agreement
  [I: standard interpretive banding: <0.4 poor, 0.4–0.6 moderate, 0.6–0.8 good, >0.8
  excellent].

The 86% raw agreement looks fine; the 0.70 kappa is the honest number, because the raters
share base rates (both say "yes" most of the time), which inflates raw agreement.
Always report kappa (or a family of agreement statistics — see
`Statistical-Evaluation.md`), never raw agreement alone. [I]

Practical floors [I]: kappa below ~0.6 means the rubric or the instructions are broken —
fix the spec, don't add raters. Kappa is a property of the (item, rubric, rater)
triple; changing any leg changes the number.

### Training raters

Raters are trained, not just briefed [I]: a calibration round on labeled gold items
(with the correct answers revealed and discussed), a second calibration round to verify
convergence, and only then production labeling. Gold items double as ongoing monitoring:
mix unlabeled gold items into production batches to detect rater drift mid-study.
[I]

## Preference collection: the two ends

**Mass casual preference** — Chatbot Arena's method: users see two anonymous model
responses, pick a winner; votes aggregate into a global ranking via Elo / Bradley-Terry
models [F: arXiv:2306.05685; I: ranking model choice]. Strength: scale, and it measures
what real users prefer. Weakness: user populations are biased (technical users,
English-dominant), prompt distributions are uncontrolled, and Elo is noisy on small vote
counts — a ranking without its vote count and population description is a rumor. [I]

**Fine-grained small-N** — MT-Bench-101: a fixed set of 101 multi-turn dialogue
benchmarks with explicit capability rubrics, designed for controlled human (or judge)
evaluation where every rubric dimension is labeled per turn [F: arXiv:2402.14762].
This is the opposite end: small, controlled, per-dimension. Most eval programs need
both: Arena-style data for the aggregate picture, MT-Bench-101-style data for the
mechanistic one. [I]

## Hybrid pipelines: judge pre-screens, humans audit

The production-standard pipeline [I]:

1. **LLM judge pass** over 100% of outputs — cheap, fast, catches the obvious.
2. **Human sample audit** over 10–20% of items, oversampled from: judge-flagged
   disagreements, low-confidence judge calls, and the safety-relevant tail.
3. **Calibration feedback** — where the sample disagrees with the judge, update the
   judge's calibration set and prompt; the audit *maintains* the judge rather than
   replacing it. [I]

This is the same structure as this wiki's own independent-evaluator pipeline: the judge
covers volume, humans cover validity, and the disagreement channel is the quality
signal. See `LLM-as-a-Judge.md` for the judge side and `../Agents/Agent-Evaluation.md`
for the pattern applied to agent outputs. [I]

When is human eval the *only* option? Judge disagreement (two strong judges split — the
item is genuinely hard), the safety tail (a machine signature is not defensible), and the
novel capability frontier (nothing in the judge's training distribution matches the
construct) [I].

## Cost math [E]

- 1000 items × 3 annotators × 30 s per item = 90,000 s = **1,500 min = 25 h** of
  annotation time.
- At $20/h [I: assumed market rate]: 25 × $20 = **$500**.
- LLM judge over the same 1000 items, ~1.5k tokens/call: 1.5M tokens × $2–4/M
  [I: pricing assumption] ≈ **$3–6**.

The speed gap is 3 orders of magnitude; the trust gap is qualitative. Humans win on
trust (a human signature is defensible; a judge's is calibrated, not trusted), and lose
on speed and scale. The design question is not "human or judge" but *which items*
justify the human hour. [I]

### Sampling strategy: which items get labeled

Labeling budget is scarce, so allocate it to signal [I]:

- **Hard cases first** — judge-disagreement items, low-confidence calls, long or
  unusual inputs; the information content per labeled item is highest there.
- **The tail** — safety-relevant items always get human eyes regardless of difficulty.
- **Stratified random baseline** — keep a stratified random sample (by domain, length,
  outcome class) so the audit has a known, unbiased base rate to compare the
  hard-case-enriched sample against; otherwise you are measuring the difficulty
  distribution, not the error distribution. [I]

## The crowdsourcing reality

Marketplace annotation is a supply chain, not a button [I]:

- **Variance across marketplaces and worker pools** — the same rubric produces different
  kappa on different platforms; treat platform as a covariate, not a constant.
- **Gold-item monitoring** — embedded gold items with known answers are the only way to
  measure rater quality in production; without them, "we checked 5 items and they look
  fine" is not a measurement.
- **Payment structure affects quality** — per-item payment rewards speed; per-batch
  quality bonuses reward care. The annotation economics are part of the protocol. [I]
- **Adjudication** — when 3 raters disagree, a 4th (trained) adjudicator decides; the
  adjudication rule must be written down before labeling starts, not after. [I]

## Interlock

- `LLM-as-a-Judge.md` — the other half of the hybrid pipeline; calibration sets are
  shared between the two.
- `Statistical-Evaluation.md` — agreement statistics, confidence intervals, sample-size
  reasoning for "is this difference real."
- `Safety-Red-Teaming.md` — the domain where human eval is not optional: the tail.
- `RAG-Evaluation.md` — hybrid judge+human pipelines for retrieval answer quality.

## Related

- `LLM-as-a-Judge.md`
- `Statistical-Evaluation.md`
- `Safety-Red-Teaming.md`
- `RAG-Evaluation.md`
- `../Agents/Agent-Evaluation.md`

## Key Takeaways

Humans remain the ground truth for open-ended quality, the safety tail, and novel
frontiers — and the craft that makes them usable is annotation engineering: binary
rubrics, worked examples, trained raters, and kappa-measured reliability (the 0.70
hand example shows why raw agreement misleads). The modern pipeline is hybrid: judge
pre-screens, humans audit 10–20% with hard cases and the tail oversampled, and the
disagreement channel feeds the judge's calibration set. And because a 1000-item pass
costs ~$500 of human time against ~$3–6 of judge time [E], the core design question is
which items earn the human hour — the answer is hard cases, the tail, and a stratified
random baseline, in that order of priority. [I]
