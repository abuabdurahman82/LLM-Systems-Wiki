# 09 — Self-Distillation and Multi-Teacher Distillation
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Not all distillation needs a *bigger* teacher. Self-distillation trains a model on
outputs of the same architecture or the same model at an earlier stage — Born-Again
Networks showed a same-size student can beat its teacher — and multi-teacher
distillation blends several specialists (or domains) into one student. Both directions
answer the same question: **what is the best *dataset* we can manufacture?** — with
teacher count and identity as free parameters.

## Self-distillation

```
Model
  ↓ generates (better-than-human or cheaper-than-redo data)
same architecture (or family)
  ↓ retrain
better model
```

**Distinct from ordinary self-training** [I: definitional, house convention]:
- *Self-training* (pseudo-labeling): model labels unlabeled data; student = same model
  fine-tuned on its own pseudo-labels. One round, same weights lineage, no claim of
  teacher→student *transfer*.
- *Self-distillation:* a deliberate teacher→student protocol where the "teacher" is an
  earlier/bigger/more-trained instance of the same family and the student is a new
  training run that inherits behavior. Iterated, it becomes a lineage.

### Born-Again Networks
Furlanello et al. showed the student (identical architecture to teacher) trained on
teacher soft targets improves over the teacher and that iterating keeps helping
[F: arXiv:1805.04770]. The mechanism usually credited [I: synthesis]: the student
re-uses the teacher's knowledge but re-randomizes the optimization, escaping bad
minima and implicitly ensembling across the lineage.

### Self-distillation patterns in LLMs (2023–26)

| Pattern | What happens | Example/lineage |
|---|---|---|
| **Same-size born-again** | model → own outputs → retrain | BAN lineage [F: arXiv:1805.04770] |
| **Large→small same-family** | 70B → 7B within a family; tokenizer/arch aligns so white-box KD also works | Qwen family practice [I] |
| **Self-generated reasoning** | model's own verified CoT improves itself (STaR-style) | STaR [F: arXiv:2203.14465]; R1-Zero's self-evolution [F: arXiv:2501.12948 §2] |
| **Teacher-free distillation** | structural priors (labels/augmentation) replace the teacher | [F: arXiv:2106.05945 discussion] |
| **Iterative distillation** | repeat: studentₙ becomes teacherₙ₊₁ | BAN iterations; distinct from RL self-improvement loops [I] |

The reasoning-flavored version blurs into RL: generate → verify → train on what passes
is both "self-distillation with a verifier" and "poor-man's RLVR" (→
`12-distillation-and-rl.md`).

### Why same-size or smaller teachers sometimes help
1. **Re-optimization effect** (BAN): fresh init + soft targets > original training.
2. **Data lifting:** teacher *generations* on new prompts extend the training
   distribution beyond the original corpus.
3. **Matched capacity:** a same-size student can fully represent the teacher — no
   capacity gap [→ `01`].

## Multi-teacher distillation

```
Teacher A — Coding
             \
Teacher B — Math ─────▶ Student
             /
Teacher C — General
```

### The design space

| Design | How it works | Failure mode |
|---|---|---|
| **Ensemble averaging** | average teacher distributions (where tokenizers align) | smooths out specialist sharpness; needs same vocab |
| **Domain teachers + routing** | route each prompt to its specialist; student sees best-of-domain data | router errors inject wrong-teacher data |
| **Weighted mixing** | per-domain loss weights (confidence/quality-weighted) | weight tuning cost |
| **Consensus filtering** | keep samples where teachers agree | loses hard/contested knowledge |
| **Sequential (cascade) KD** | teacher A → student → teacher B | catastrophic forgetting risk between stages |

### Can specialists make a generalist?
Yes, with caveats [I: synthesis of the multi-teacher literature and 2025–26 practice]:
- **Coverage yes, synergy hard:** a student trained on well-verified per-domain data
  from different teachers behaves like a generalist; what it does *not* get is
  cross-domain *integration* behavior (a coding-math-bridging strategy) unless the data
  contains it.
- **Style conflicts are real:** teachers with different formats/verbosity produce a
  student that oscillates; normalize formats (→ `14`) or use one teacher per stage.
- **2026 frontier:** multi-teacher *on-policy* distillation — several domain RL teachers
  scoring the student's rollouts — reports specialist→generalist transfer with
  parameter-efficient students [Research Result: e.g. Xiaomi/PKI MOPD-style work
  reported matching much larger models with 309B/15B-active MoE; single-source,
  treat as vendor-adjacent until independently replicated].
- **Practical default:** one strong generalist teacher + verified data usually beats
  fragile multi-teacher plumbing [I]; reach for multi-teacher when domain coverage
  genuinely exceeds one teacher's competence.

## The capacity-gap bridge (intermediate teachers)

```
671B
  ↓ distill
70B   (intermediate teacher)
  ↓ distill
14B
  ↓ distill
7B
```

Patient-KD-era evidence [F: arXiv:1908.09355] plus the capacity-gap argument (→ `01`)
motivate intermediate teachers when the direct gap is extreme. Honest status [I]:
results are task-dependent; the *data-side* version — use the 70B to generate/verify
data for the 7B — is more robust than logit-level chaining, because each stage is just
a distillation run with a well-matched student.

## Related
- `08-deepseek-r1-distillation.md` — the flagship single-teacher case
- `10-on-policy-distillation.md` — where multi-teacher met student rollouts (2026)
- `14-data-generation-and-verification.md` — format/style normalization across teachers
- `17-benchmarking.md` — how to A/B teacher choices fairly
- `Training-Engineering/Pretraining-Recipe.md` — where self-distillation sits vs pretraining

## Key Takeaways
- Self-distillation is a *protocol* (teacher = earlier/same-family instance), not
  self-training; Born-Again showed same-size students can win.
- Multi-teacher = dataset engineering: routing, weighting, and consensus are data
  decisions, not loss decisions.
- Specialists → generalist works through verified, normalized data; synergy behavior
  must exist in the data to be learned.
- Intermediate teachers bridge extreme capacity gaps — most robustly at the data level.
