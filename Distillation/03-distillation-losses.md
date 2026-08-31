# 03 — Distillation Loss Functions: Forward KL, Reverse KL, and the Divergence Zoo
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
A KD loss measures "how far" the student's distribution is from the teacher's — and *the
direction you measure that distance changes what the student learns*. Forward KL
(KL(teacher∥student)) drags the student to cover every mode the teacher has; reverse KL
(KL(student∥teacher)) lets the student pick modes it can represent and match them well.
For classifiers the choice is minor; for autoregressive LLMs it is the difference
between a student that averages and a student that acts — which is why MiniLLM
(abandoning forward KL) and GKD/Tinker (reverse KL per token) matter.

## Setup and notation
Teacher distribution P (frozen), student distribution Q_θ (trainable). At a token
position (or a class), the divergence options are:

| Divergence | Formula | As a loss (minimize) |
|---|---|---|
| Cross-entropy | H(P, Q) = −Σ p log q | = H(P) + KL(P∥Q), so same optimum |
| Forward KL | KL(P∥Q) = Σ p log(p/q) | mean-inclusive; standard KD term |
| Reverse KL | KL(Q∥P) = Σ q log(q/p) | MiniLLM / on-policy KD choice |
| Jensen–Shannon | ½KL(P∥M) + ½KL(Q∥M), M=(P+Q)/2 | symmetric, bounded; DistiLLM variants |
| Total variation | ½·Σ\|p−q\| | DistiLLM's "adaptive" family [F: arXiv:2402.03898] |

All are f-divergences; all are zero iff P=Q; they differ in *where the gradient pressure
is strongest*.

## Forward KL — mode covering

```
KL(P∥Q):  cost of missing a teacher mode is huge
          → student spreads mass to cover ALL teacher modes
          → "mean-seeking" behavior: if the teacher is bimodal,
             the (underpowered) student puts mass BETWEEN the modes
```

Concretely: teacher = {0.5, 0, 0.5} over three tokens; a student restricted to near-deterministic
predictions cannot represent it. Forward KL pushes toward {0.5, 0, 0.5}-shaped blur or,
if capacity forces a choice, toward a mixture — for *sequences* this manifests as
incoherent averages: text that hedges, blends styles, or produces "gray soup"
[I: behavioral description; the sequence-level consequence is a well-reported
phenomenon in KD-for-generation literature].

Properties that matter for LLM KD:
- Forward KL's penalty includes the **low-probability regions of the student** where the
  teacher has mass — the student is punished for *any* mode it drops.
- With a **limited-capacity student**, forward KL spends capacity on the teacher's whole
  support, including regions irrelevant to generation quality (→ capacity gap,
  `01-why-distillation.md`).
- Numerically, forward KL is a **fixed-dataset** loss: samples come from the teacher/data,
  gradients are simple expectations — stable, no sampling from the student needed.

## Reverse KL — mode seeking

```
KL(Q∥P):  cost of student mass where the teacher has none
          → student concentrates on modes it can reproduce WELL
          → "mode-seeking": it picks (some) modes and matches them sharply
```

Properties:
- The student is punished for *inventing* support, not for dropping teacher modes →
  it narrows to what it can do; quality per mode goes up, coverage goes down.
- For **generation** this is usually the right trade: text is sampled greedily/ancestrally
  from the student, so what matters is that *the sampled region* is high quality, not
  that the student's tails match the teacher's tails.
- **Policy-gradient form:** KL(Q∥P) is intractable directly when P is only known up to a
  softmax over huge vocabularies in the student's own trajectory states; MiniLLM
  optimizes it with policy gradients (student samples sequences; teacher log-probs give
  rewards) [F: arXiv:2306.08543].

## The two KLs side by side

```
Teacher (P)          Forward KL (P∥Q)           Reverse KL (Q∥P)
   ██                  student must cover          student keeps best
  ████                 EVERY mode →                modes → sharp but
   ██                  blurs under low             possibly narrow
                       capacity
```

| Property | Forward KL | Reverse KL |
|---|---|---|
| Optimizer's nickname | mode covering | mode seeking |
| Low-probability student regions w/ teacher mass | heavily penalized | ignored |
| Student mass where teacher ≈ 0 | penalized weakly (log q term) | heavily penalized |
| Under-capacity behavior | averaged/blurry | selective/sharp |
| Training scheme | expectation over data/teacher samples | needs student samples (policy gradient) or student-generated contexts |
| Generation quality role | good for density matching | good for sampling quality |
| Canonical LLM-era use | classical KD, DistilBERT-era, logit KD | MiniLLM, GKD options, on-policy distillation |

[F: arXiv:2306.08543 §3 shows the zero-forcing/mode-covering analysis for LMs;
the behavioral summaries are I: standard reading of the same math.]

## The third axis: where the sequences come from

The divergence choice interacts with a *second* choice the classical picture hides:
**which contexts the distributions are evaluated on.** Teacher-only (off-policy, static
dataset) vs student-generated (on-policy) contexts is the exposure-bias axis:

```
        off-policy (teacher contexts)     on-policy (student contexts)
fKL     classical KD                      "forward GKD"
rKL     MiniLLM (PG on teacher data)      on-policy distillation (GKD, Tinker)
```
→ `10-on-policy-distillation.md`, `11-gkd.md`.

## JS, TV and the f-divergence zoo

- **Jensen–Shannon:** symmetric, bounded by log 2; no mode-selection pathology in
  either direction; a safe middle ground when you fear both blurring and narrowing.
- **Total variation / skewed KL:** DistiLLM introduced *skew KL*
  (KL((1−λ)P + λQ ∥ Q)-style linear interpolations) to stabilize optimization and
  reported faster/better streaming distillation than plain KL [F: arXiv:2402.03898;
  research result].
- **Practical guidance [I]:** start with forward KL at T≈1–4 for logit KD on fixed data;
  switch to reverse KL when the student *generates* and quality-per-mode matters more
  than coverage; reach for JS/skew variants when training is unstable or the student is
  much smaller than the teacher.

## Worked micro-example (computed)

Teacher over a 4-token continuation: {0.70, 0.20, 0.08, 0.02}.
Student (underpowered) must place *one* mode sharply, rest near zero:

- Forward-KL optimum under hard one-hot restriction: pick the argmax → {1,0,0,0};
  KL(P∥Q) = −log(1/0.7) ≈ **0.357 nats** — computed this session [E].
- Reverse KL is undefined/infinite for zeroed teacher-mass positions → the optimum
  spreads a little mass everywhere, trading sharpness for finiteness [I: analytic
  consequence].

The asymmetry in one sentence: **forward KL hates missing modes; reverse KL hates
inventing modes.**

## Related
- `02-classical-knowledge-distillation.md` — temperature scaling and the T² trick
- `05-logit-and-feature-distillation.md` — applying these losses over 100K+ token vocabularies
- `10-on-policy-distillation.md` — reverse KL per token as a dense reward
- `11-gkd.md` — GKD's divergence menu and on-policy data
- `Post-Training/Alignment-RLHF.md` — where the same divergences appear in RL objectives (KL penalties to reference policies)
- `12-distillation-and-rl.md` — the KD↔RL dictionary

## Key Takeaways
- KD loss = divergence + direction + *contexts*. All three choices shape the student.
- Forward KL covers modes (blurs under low capacity); reverse KL matches modes (narrows).
- Generation-time quality usually favors reverse KL; density matching favors forward KL.
- JS and skew/TV variants are the stabilization middle ground.
- The context question (teacher data vs student rollouts) is as consequential as the
  divergence question — that is the on-policy turn (→ `10`).
