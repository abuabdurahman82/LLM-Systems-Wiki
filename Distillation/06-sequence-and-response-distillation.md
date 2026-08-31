# 06 — Sequence-Level and Response Distillation (What Most "Distillation" Actually Is)
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
The workhorse of 2026 distillation is embarrassingly simple: ask a teacher to generate
high-quality responses, then SFT the student on (prompt, response) pairs. This is
*response distillation* — the modern descendant of sequence-level KD (Kim & Rush 2016).
It requires nothing but teacher access to text, it crosses tokenizers and architectures
freely, and — when the data is verified and curated — it is what produced the R1-Distill
family. The honest framing: most things marketed as "LLM distillation" are **synthetic
teacher-data generation + supervised fine-tuning**.

## Response distillation: the pipeline

```
Prompt
  ↓
Teacher LLM
  ↓
High-quality response
  ↓
(prompt, response) pairs        ← the "distilled dataset"
  ↓
Student SFT (standard CE on teacher tokens)
  ↓
Student model
```

The training step is plain SFT — cross-entropy on the teacher's tokens, exactly as in
`Post-Training/README.md`. Nothing in the loss knows a teacher exists. **All the
distillation-ness lives in the data.**

Why this counts as distillation at all: the student's capability source is the teacher's
behavior rather than human annotations or the base model's own distribution. The
empirical claim — teacher data beats human data for the same student — is supported by
the R1 study's direct comparison [F: arXiv:2501.12948 §4: "models distilled from
high-quality teacher outputs consistently outperform those trained directly on
human-generated data"] and by Distillation-vs-SFT scaling-law analysis
[F: arXiv:2502.08606 — distillation can beat supervised pretraining per FLOP in the
student-size regimes studied].

## How this differs from classical logit KD

| Dimension | Classical logit KD (`02`, `05`) | Response distillation (this page) |
|---|---|---|
| Teacher signal | full distribution per token | one sampled sequence |
| Info per position | O(V) | O(1) |
| Loss | KL divergence | cross-entropy (SFT) |
| Teacher access | white-box | black-box suffices |
| Exposure of teacher uncertainty | yes (soft targets) | no — flattened into one sample |
| Infra cost | teacher forward pass per training token, storage/bandwidth | one-off generation |
| Cross-tokenizer | hard | trivial |

The last-but-one row is the real difference: a sampled response *hides* the teacher's
uncertainty. Two teacher outputs that would be soft-target-identical are identical
datasets; but a 0.60/0.40 fork in the teacher's head becomes a single hard path in the
data — the student never sees the plausible alternatives. Best-of-N and multi-sample
datasets partially recover this (→ `07` §best-of-N).

## Sequence-level KD (the 2016 ancestor)

Kim & Rush [F: arXiv:1606.07947] defined KD for seq2seq two ways:
1. **Token-level (per-position distribution matching)** — teacher distribution at each
   position of the *reference* sequence (works because teacher and student share the
   parallel-data context).
2. **Sequence-level KD — train the student on teacher-GENERATED sequences** rather than
   on reference data. For an autoregressive LM this is simply SFT on teacher outputs.

| | Token-level KD | Sequence-level KD |
|---|---|---|
| Signal | per-position distributions | full teacher-chosen continuation |
| Handles teacher≠student tokenizers | no | yes |
| Data cost | store V-dim dists | store text |
| Modern form | logit/top-K KD (`05`) | response/reasoning KD (this page, `07`) |
| Weakness | storage/bandwidth | exposure bias (→`10`); quality = teacher's one sample |

Sequence-level KD won in practice because of its simplicity and portability — the same
reason response distillation dominates the LLM era.

## The "distillation" naming problem (say it precisely)

Because SFT-on-teacher-data *is* the training mechanism, the field's terminology is
loose. A usage guide [I: house convention for this section]:

- **Response distillation / sequence KD:** student learns from teacher-generated text.
  The teacher's *identity* is the point.
- **Synthetic data + SFT:** same mechanics, but the emphasis is dataset construction;
  whether the generator is "a teacher" or just "a data source" is a framing choice.
- **Logit/feature KD:** distribution/geometry matching — "real" KD in the 2015 sense.
- **On-policy KD:** teacher scores the student's own rollouts (→`10`).

When reading vendor posts ("our model is distilled from GPT-5-class outputs"), the
honest translation is usually: *we generated SFT data with a strong model, then
fine-tuned*. That is not a scam — R1-Distill did exactly this — but it says nothing
about logit/feature transfer, and its quality ceiling is set by data curation, not by
the KL machinery (→ `07`, `14`).

## Why response distillation is the 80% answer

1. **Zero teacher hosting** if API-accessible; trivially parallel generation.
2. **Portable** across tokenizers/architectures/licenses-with-permission.
3. **Debuggable** — you can read the dataset. Quality problems are visible; bad data can
   be filtered before training (→ `14`).
4. **Composable** — the same student can then be improved by logit KD (same family) or
   on-policy KD (long-horizon behavior) in later phases (→ `18` §iterative).

Limitations to say out loud:
- **Exposure bias debt:** the student trains on teacher-clean prefixes but lives on its
  own (→ `10`).
- **One sample ≠ distribution:** uncertainty is lost (partially recoverable via
  multi-sample datasets).
- **Teacher hallucinations propagate:** no loss-term protection — filtering is the only
  defense (→ `14`).
- **No dense credit assignment:** the student sees only the sampled path, not the
  teacher's near-misses — the gap on-policy KD closes (→ `10`).

## Related
- `07-reasoning-distillation.md` — the same pipeline with reasoning traces as the payload
- `14-data-generation-and-verification.md` — the pipeline engineering (filtering, dedup, contamination)
- `10-on-policy-distillation.md` — fixing exposure bias and one-sample blindness
- `05-logit-and-feature-distillation.md` — when you can afford the dense signal
- `Post-Training/README.md` — the SFT mechanics this method uses
- `18-practical-labs.md` — this pipeline as Lab A

## Key Takeaways
- Response distillation = teacher data + SFT; the loss is vanilla CE — the "distillation"
  is entirely in the data provenance.
- Sequence-level KD (2016) already contained the idea; LLMs made it the default because
  it is portable, cheap, and debuggable.
- It is *not* logit KD: no distributions, no uncertainty transfer, no dense supervision —
  and cross-tokenizer portable because of it.
- Quality lives and dies by curation and verification, which is why `07` and `14` exist.
