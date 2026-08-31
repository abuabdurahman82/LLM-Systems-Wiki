# 12 — Distillation and Reinforcement Learning: Preference & Reward Transfer
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Distillation and RL are the two great post-training engines, and they keep converging:
RL needs dense rewards (distillation supplies them — teacher probabilities as reward),
and distillation wants to transfer alignment behavior, not just capability (preference
distillation, reward-model distillation). This page gives the KD↔RL dictionary, covers
transferring preferences (DPO-style) and reward models, and states clearly when each
engine — or the combination — is the right tool.

## The dictionary

| RL concept | Distillation counterpart | Bridge |
|---|---|---|
| reward (sparse, outcome) | verified answer (→ `07`) | verifier as teacher |
| dense per-token reward | teacher log-prob / per-token reverse KL | on-policy KD = RL with dense reward [F: Thinking Machines 2025] |
| policy | student | — |
| reference policy KL penalty | teacher-matching term | both penalize drift, different anchors |
| reward model | distilled RM | → this page |
| RLHF pipeline | KD pipeline + RL stage | R1: distill → (community adds) RL |

Two framings that are exactly equivalent mechanically [I]:
- **On-policy KD = RL** where the reward is −KL(student_token ∥ teacher_token) per token.
- **RL = on-policy distillation** against a *verifier-judged teacher-free signal*.

The practical difference is the signal's source and density: teacher distributions
(dense, learnable) vs verifier outcomes (sparse, truthful).

## Distillation vs RL — when each wins

| Question | Distillation | RL |
|---|---|---|
| Is there a strong teacher? | required | not required |
| Is the capability easy to verify? | not necessary | strongly preferred (RLVR) |
| Compute budget | lower per capability point (9–30× for reasoning gains [F: Tinker 2025]) | higher; but discovers behaviors the teacher lacks |
| Stability | SFT-stable (off-policy) | reward hacking, KL tuning, value-model pain (PPO) or group-noise (GRPO) |
| Ceiling | teacher's behavior within student capacity | open-ended (R1-Zero-style emergent reasoning) |
| Reproducibility | high (data-centered) | harder (reward+rollout variance) |

R1's own evidence: distill-only beat from-scratch RL at 32B on math benchmarks
[F: arXiv:2501.12948 Table 16], while RL remains the path to *beyond-teacher*
capability (R1-Zero) [F: §2]. **The 2026 default: distill first, RL second**
(→ `18` §iterative).

## Preference distillation

Transfer alignment *behavior* — what the teacher prefers, not just what it produces:

```
Prompt
 │
 ├── Response A
 └── Response B          (student or teacher generations)
        ↓
Teacher preference (or teacher RM/judge)
        ↓
Student preference training (DPO / ranking loss)
```

- **Teacher as preference oracle:** sample pairs from the student (on-policy pairs are
  better for DPO-style training — see the off-policy caveat in
  `Post-Training/Alignment-RLHF.md`), ask the teacher (or its RM) which is better,
  train the student with DPO/ranking on those labels.
- **Zephyr precedent:** "distillation of LM alignment" — DPO on GPT-4-generated
  preference data — beat its base's RLHF teacher on MT-Bench-era evals
  [F: arXiv:2310.16944].
- **Relation to reward-model distillation:** preference distillation trains the *policy*
  from teacher preferences; RM distillation (next section) compresses the *judge*
  itself. Same data, different artifact.
- **Failure modes:** teacher-preference noise becomes student policy noise; off-policy
  pairs weaken DPO (the β/counterfactual issue); judge-format bias transfers.

## Reward-model distillation

Can a big reward model / judge be compressed into a cheap one? Yes — it is an ordinary
distillation target [I: category; F for instances below]:

```
Large RM / LLM-judge
   ↓ scores (prompt, response) pairs  — teacher signatures
Distilled RM (small)
   ↓ used for
   ├─ RL training reward (cheap RLVR/RLHF loops)
   ├─ inference-time verification (best-of-N selection)
   ├─ content ranking
   └─ reasoning verification filters (→ 14)
```

- **Training signal:** RM scores are continuous → regression (MSE on score, or
  ranking losses on pairs). A judge-LLM can be distilled response-level (its verdicts
  as labels) or logit-level (same family) (→ `05`).
- **Where it pays:** RL loops consume millions of reward evals — a 10–100× cheaper RM
  changes RL economics directly [I: arithmetic in `17`]; best-of-N selection and
  data-verification filters (→ `07`) are the same lever.
- **Fidelity risk:** the distilled RM inherits the judge's biases *and* adds
  approximation error; keep an audit channel — periodically evaluate the distilled RM
  against held-out human preferences and against the big judge's disagreements
  [I: engineering guidance].
- **Known instance class:** process-reward and outcome-reward models distilled to
  1–7B for verification duty are standard in 2025–26 reasoning pipelines
  [Research Result: see `Reasoning/README.md` verification lineage].

## Teacher probability as reward signal (the unifying trick)

Three ways the same teacher signal enters training:

```
1. SFT on teacher samples        → imitation (→ 06)
2. KL to teacher distributions   → distribution matching (→ 05 / on-policy KD → 10)
3. Teacher-scored preferences    → alignment transfer (this page)
```

All three are "the teacher's belief about tokens, converted into gradient signal."
Once seen this way, KD vs RLHF is a *signal-density and truthfulness* trade:
dense-but-imitative vs sparse-but-truthful. Hybrid curricula (dense seed + sparse
refinement) dominate because they get both [I].

## Related
- `10-on-policy-distillation.md` — the dense-reward formalization
- `Post-Training/Alignment-RLHF.md` — PPO/DPO/GRPO mechanics and the alignment lineage
- `Reasoning/README.md` — RLVR and verifiable rewards (the teacher-free end of this axis)
- `07-reasoning-distillation.md` — verification as the truthful signal
- `Evaluation-Engineering/LLM-as-a-Judge.md` — judge calibration (the RM-distillation source)

## Key Takeaways
- KD and RL are two ends of a signal-density spectrum; on-policy KD literally is RL with
  teacher-KL reward.
- Preference distillation transfers alignment cheaply (Zephyr lineage); pairs should be
  student-generated to keep DPO healthy.
- Reward-model distillation compresses the judge — the key enabler of cheap RL loops,
  best-of-N, and verification filters.
- Distill-then-RL is the 2026 default: imitation for breadth, RL for the last mile.
