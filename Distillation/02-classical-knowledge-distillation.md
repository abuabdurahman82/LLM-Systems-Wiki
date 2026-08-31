# 02 — Classical Knowledge Distillation: Soft Targets, Temperature, Dark Knowledge
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Classical KD (Hinton, Vinyals, Dean 2015) trains a small student to match a large
teacher's *soft* probability distribution instead of hard one-hot labels. The soft
distribution carries "dark knowledge": *how similar* the wrong classes are to the right
one. Temperature T controls how much of that secondary structure survives the softmax;
the loss is typically KL(teacher ∥ student) scaled by T². Everything in modern LLM
distillation — logit KD, on-policy reverse-KL, even reasoning distillation — is a
variation on this 2015 core.

## Historical timeline (dates verified against primary sources)

| Year | Milestone | What it added | Source |
|---|---|---|---|
| 2006 | Model compression (Buciluǎ et al.) | train small model on big model's outputs — pre-"KD" name | [F: SIGKD-06, "Model Compression"] |
| 2015 | **Hinton, Vinyals, Dean — "Distilling the Knowledge in a Neural Network"** | the name, soft targets, temperature, T² scaling | [F: arXiv:1503.02531] |
| 2016 | Sequence-level KD (Kim & Rush) | KD for seq2seq: train on teacher *generated sequences* | [F: arXiv:1606.07947] |
| 2019 | DistilBERT | task-agnostic Transformer compression, 40% smaller / 60% faster, ~97% of BERT GLUE | [F: arXiv:1910.01108] |
| 2019 | TinyBERT | two-stage *feature + attention + logit* KD for Transformers | [F: arXiv:1909.10351] |
| 2020 | MiniLM | deep self-attention distillation + hidden-state matching | [F: arXiv:2002.10957] |
| 2020 | MobileBERT | bottleneck-wide design trained via feature transfer | [F: arXiv:2004.02984] |
| 2018 | Born-Again Networks | self-distillation: teacher and student share architecture | [F: arXiv:1805.04770] |
| 2019 | Patient KD for BERT | patient intermediate-layer matching (first/last + middle layers) | [F: arXiv:1908.09355] |
| 2021 | "Does KD Really Work?" / "Good teacher is patient & consistent" | KD skepticism + robustness of patient/consistent teachers | [F: arXiv:2106.05945, arXiv:2106.05237] |
| 2023 | **MiniLLM** | reverse-KL, policy-gradient KD for *generative* LMs | [F: arXiv:2306.08543] |
| 2023 | GKD | on-policy student-generated sequences + flexible divergences; KD+RLHF integration | [F: arXiv:2306.13649] |
| 2024 | DistiLLM | skewed KL + adaptive loss for streaming LLM distillation | [F: arXiv:2402.03898] |
| 2024 | LLM KD survey | taxonomy consolidation | [F: arXiv:2402.13116] |
| 2025 | **DeepSeek-R1 distillation** | reasoning-trace distillation at scale; 6 open students | [F: arXiv:2501.12948] |
| 2025 | Distillation scaling laws | compute-optimal teacher/student allocation | [F: arXiv:2502.08606] |
| 2025 | DistiLLM-2 | contrastive (IN- vs OUT-of-distribution) weighting | [F: arXiv:2503.07067] |
| 2025 | On-policy distillation (Tinker/TML) | per-token reverse-KL as dense reward ≈ 9–30× cheaper than RL | [F: thinkingmachines.ai/blog/on-policy-distillation] |
| 2026 | Agent/multi-teacher OPD era | domain-specialist RL teachers distilling on student rollouts | [Research Result: see 13, 20] |

The evolution in one line — each stage *changes what is transferred*:

```
Classical KD → Transformer KD → Sequence KD → Instruction Distillation
   → LLM Response Distillation → Reasoning Distillation → On-Policy Distillation
   → Agent / Interactive Distillation
```

## Hard labels vs soft targets

Teacher prediction on an image classifier (the original example, but the idea is
identical for token distributions):

```
Teacher softmax:   Cat 0.70   Dog 0.20   Fox 0.08   Car 0.02

Hard label:        Cat 1.0    Dog 0.0    Fox 0.0    Car 0.0
```

The hard label says *what*. The soft distribution says *what, and what it resembles*:
Dog ≈ 0.20 tells the student "this input is also dog-like"; Fox ≈ 0.08 "and a little
fox-like"; Car ≈ 0.02 "but nothing like a car." Two training signals in one example.

**Dark knowledge** = the information encoded in the teacher's probabilities over
*incorrect* classes/tokens. It is a similarity metric the teacher learned from all its
data — the "map" of the input space. A student trained only on hard labels gets the
boundaries but not the map; regularization and generalization suffer accordingly
[F: arXiv:1503.02531 reports the ImageNet-era effect: distillation matched a 100×
smaller network's baseline while transferring inductive knowledge; magnitudes are
task-specific — treat particular numbers as per-benchmark].

For LLMs this is even more natural: at each token position the teacher's next-token
distribution over a 100K+ vocabulary is a rich description of *all* plausible
continuations — exactly the same structure, one softmax over tokens instead of classes
(→ `05-logit-and-feature-distillation.md`).

## Temperature scaling

Softmax with temperature reshapes the teacher distribution before the student sees it:

```
Teacher logits z_i
      ↓
  softmax(z_i / T)  =  exp(z_i/T) / Σ_j exp(z_j/T)
      ↓
soft probability distribution
```

| T | Effect on the distribution | Use |
|---|---|---|
| 1 | native teacher confidence | final inference; often too peaked to teach secondary structure |
| 2 | mildly smoothed | classical KD default region |
| 4 | clearly smoothed — wrong-class mass becomes visible | common for large-vocabulary KD |
| 8 | very flat — near-uniform risk | rarely useful: **overly smooth targets** destroy the signal |

- **Low T (→ 0):** distribution collapses toward argmax — you reconstruct hard labels and
  throw away dark knowledge.
- **High T (→ ∞):** distribution flattens toward uniform — every token equally likely,
  no signal.
- **Gradient behavior:** gradients of the KD term scale like 1/T² per position, which is
  why the classical loss multiplies the KD term by **T²** to keep its magnitude
  comparable to the hard-label CE term when T changes [F: arXiv:1503.02531].

```
L_KD  =  α · T² · KL( softmax(z_teacher/T) ∥ softmax(z_student/T) )
L_total  =  (1−α) · CE(y_true, student)  +  L_KD
```

**Intuition:** T is a *contrast knob* on how much of the teacher's ranking tail the
student must reproduce. Pick it the way you'd pick any signal-to-noise knob: high enough
that secondary structure is visible, low enough that it isn't noise.

## What transfers and what doesn't (preview)

Classical KD transfers the teacher's *input→distribution mapping*. It does not transfer
parameters, and it does not automatically transfer:

- **calibration** — see `14-data-generation-and-verification.md` §calibration
- **hidden features** unless you add feature/attention losses (→ `05`)
- **process behaviors** (tool calls, self-correction) unless the training data contains
  them (→ `13`)

## The 80/20 of classical KD
1. Soft targets beat hard labels because they contain similarity structure (dark knowledge).
2. T controls the visibility of that structure; T² keeps losses comparable.
3. The KL direction matters for *generative* students — forward KL covers modes,
   reverse KL matches modes; this single choice separates classical KD from MiniLLM/GKD
   (→ `03-distillation-losses.md`).
4. Classical KD assumed teacher and student see the *same inputs and labels*. LLM
   generation breaks that assumption — the student's own outputs become the inputs —
   which is exactly the exposure-bias problem (→ `10-on-policy-distillation.md`).

## Related
- `03-distillation-losses.md` — the loss functions on this page, derived properly
- `05-logit-and-feature-distillation.md` — what happens when "classes" become a 150K-token vocabulary
- `06-sequence-and-response-distillation.md` — sequence-level KD (Kim & Rush) as the ancestor of modern response distillation
- `10-on-policy-distillation.md` — what breaks when the student's own generations enter the loop
- `Inference/The-Life-of-a-Token.md` — where logits/softmax live in the forward pass
- `Transformer/` — the softmax/CE foundation

## Key Takeaways
- Classical KD = match the teacher's soft distribution; T and T² are the only two knobs
  you must understand to read 2015-style papers.
- Dark knowledge is similarity structure over wrong answers — free supervision that hard
  labels discard.
- The 2015 core (soft targets + temperature + KL) recurs at every scale of the field,
  including 2025's on-policy distillation (per-token reverse KL, → `10`).
- For LLMs the vocabulary replaces the class list, and the student's own generation
  distribution replaces the fixed dataset — motivating everything that follows.
