# 11 — GKD: Generalized Knowledge Distillation
`LAST_UPDATED: 2026-08-27` · Status: first-class page · Primary source: arXiv:2306.13649 (Agarwal et al., verified this session)

## 30-Second Explanation
Generalized Knowledge Distillation (GKD) is the 2023 Google DeepMind method that
prescribed the cure for distribution mismatch two years before "on-policy distillation"
became a buzzword: train the student on **its own self-generated output sequences**
while the teacher provides feedback on those sequences, with the freedom to choose the
divergence (forward KL, reverse KL, JS) that fits the student's capacity. GKD also
showed distillation and RL fine-tuning compose cleanly — the property every 2025–26
on-policy pipeline inherits.

## The architecture

```
Student generates Y_student            (on-policy contexts)
        ↓
Teacher computes feedback on Y_student contexts
(per-token distributions under student prefix)
        ↓
Distribution matching loss
(fKL / rKL / JSD — chosen per capacity)
        ↓
Student update
        ↓
(repeat; optionally interleave with RL fine-tuning)
```

## The three problems GKD attacked

1. **Distribution mismatch (the core):** classical KD evaluates teacher and student on
   *data/teacher* sequences; inference runs on *student* sequences. GKD trains on the
   student's own rollouts, so training states = inference states [F: abstract].
2. **Capacity-expressivity mismatch:** a small student often *cannot* mimic the
   teacher's distribution. GKD's answer: pick a divergence that suits limited
   expressivity (e.g. reverse KL's mode-seeking behavior) instead of being locked to
   forward KL [F: abstract — "flexibility to employ alternative loss functions"].
3. **KD + RL composition:** GKD integrates with RLHF fine-tuning — distillation during
   RL or as its warm start [F: abstract — "facilitates the seamless integration of
   distillation with RL fine-tuning (RLHF)"].

Verified in the paper on summarization (CNN/DailyMail, XSum), translation (WMT), and
arithmetic reasoning (GSM8K), plus task-agnostic instruction-following distillation
[F: abstract + paper §5].

## GKD's design knobs (all ablated in the paper)

| Knob | Options | Effect |
|---|---|---|
| Data policy | on-policy / mixed / off-policy (teacher data) | on-policy or mixed beat pure off-policy on the mismatch-sensitive tasks [F: paper ablations; effect strongest on arithmetic reasoning] |
| Divergence | fwd KL / rev KL / JSD | reverse KL wins when student underfits the teacher's multimodality [F: ablations] |
| Teacher feedback granularity | per-token distributions (white-box) | requires teacher logits on student prefixes |
| Init | start from SFT checkpoint vs base | SFT-init + GKD is the practical default [I: paper's best configs] |

The "mixed" data policy — some on-policy batches + some fixed data — is the practical
answer to the brittleness of full on-policy training (self-reinforcing drift) and is
the direct ancestor of 2025–26 production recipes [I: lineage reading].

## Relationship with MiniLLM

| | MiniLLM (2023, arXiv:2306.08543) | GKD (2023, arXiv:2306.13649) |
|---|---|---|
| Core idea | reverse-KL KD for LMs | on-policy data + flexible divergences |
| Optimization | policy gradient on student-sampled sequences | supervised-style on student rollouts with teacher scoring |
| Data | teacher/reference contexts (PG makes it on-policy-ish) | explicitly student-generated |
| Claim to fame | objective-side fix | data-side fix + KD↔RL bridge |

They compose: modern on-policy distillation (→ `10`) is essentially
"GKD-style data + MiniLLM-style reverse KL, implemented in an RL trainer."

## Implementation reality (TRL, 2026)

Hugging Face TRL ships a `GKDTrainer` (and `GKDConfig`) implementing this recipe:
student generation + teacher scoring + chosen divergence, SFT-loss mixing, and
Neftune-style noise options [F: TRL docs, gkd_trainer module — verified against TRL
source this session; exact option names live in `TRL/examples` — check your installed
version]. Typical use:

```python
from trl import GKDConfig, GKDTrainer
# teacher & student loaded as causal LMs; student generates,
# teacher scores per-token distributions on student sequences
cfg = GKDConfig(
    beta=0.1,                # SFT-loss mixing (0 = pure KD)
    temp=0.9,                # KD temperature
    alpha=0.5,               # on-policy vs off-policy data mix
    seq_length=1024,
    # lora / gradient-checking knobs per your hardware
)
trainer = GKDTrainer(model=student, teacher_model=teacher, args=cfg, ...)
trainer.train()
```
[F: TRL documentation structure; parameter names per TRL's `GKDConfig` — verify against
your TRL version before running. Lab wiring in `18-practical-labs.md`.]

## The 80/20 of GKD
1. Train on the student's own states — the single biggest fix (data axis).
2. Choose the divergence by student capacity: reverse KL when the student narrows, JSD
   as the stable middle, forward KL when the student can truly mimic (→ `03`).
3. Mix in some off-policy data for stability; go full on-policy only with monitoring.
4. GKD + RL compose — distill to seed, RL to refine (→ `12`).
5. TRL makes the baseline reproducible in an afternoon on 2–4 GPUs.

## Related
- `10-on-policy-distillation.md` — the 2025–26 generalization and its economics
- `03-distillation-losses.md` — the divergence mathematics
- `12-distillation-and-rl.md` — the RL composition GKD enabled
- `18-practical-labs.md` — a GKD lab on home hardware
- `Post-Training/Alignment-RLHF.md` — the RLHF machinery GKD plugs into

## Key Takeaways
- GKD = on-policy data + divergence choice + KD↔RL composition — every modern
  on-policy distillation method is this recipe with new clothes.
- The data axis (whose sequences?) mattered more than the objective axis (which KL?) in
  the paper's own ablations.
- TRL's `GKDTrainer` makes it a standard engineering component, not a paper artifact.
