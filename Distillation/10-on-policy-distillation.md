# 10 — On-Policy Distillation: The 2025–26 Frontier
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Off-policy distillation trains the student on the teacher's data; on-policy distillation
(ODP) trains the student on **its own** trajectories, scored by the teacher. The student
generates, the teacher grades each token (typically per-token reverse KL against the
teacher's distribution), and the student learns from mistakes made in *states it will
actually visit*. This fixes the exposure bias that all static-data methods suffer, and
it does so with dense per-token supervision — combining RL's realism with distillation's
signal density at a fraction of RL's cost.

## The problem that motivates it: exposure bias

Static (offline/off-policy) distillation trains on teacher-perfect prefixes but deploys
on student-imperfect ones:

```
Training:    teacher → perfect state → perfect state → perfect state
Inference:   student → small error → unfamiliar state → larger error → ...
```

During training the student never *visits* its own error states, so it never learns to
recover from them; small errors compound at inference (the autoregressive cousin of
scheduled sampling's diagnosis [F: arXiv:2306.13649 §1 frames exactly this
distribution mismatch]). GKD named the fix — train on the student's own generated
sequences with teacher feedback [F: arXiv:2306.13649]; MiniLLM attacked the same
mismatch from the objective side with reverse-KL policy gradients [F:
arXiv:2306.08543].

## On-policy distillation: the loop

```
Student generates trajectory
        ↓
Teacher evaluates that trajectory
(per-token reverse KL, or rewards)
        ↓
Learning signal (dense, per token)
        ↓
Student update  →  (loop)
        ↓
Student improves in its OWN states
```

Contrast with static distillation, where the loop is: teacher → dataset → student
(one-shot, student never in the loop).

The Tinker/Thinking-Machines formulation made this practical and popularized it
[F: thinkingmachines.ai/blog/on-policy-distillation, Oct 2025]:
- **Loss:** per-token reverse KL between student and teacher *on the student's
  trajectory*, discount = 0 (myopic per-token matching).
- **Implementation:** a one-line change on top of an RL trainer — swap the reward/ KL
  regularizer for teacher reverse-KL.
- **Results (their replication of the Qwen3 method):** Qwen3-8B AIME'24 60→70 in ~150
  steps; **≈9–30× cheaper than RL** for equivalent reasoning-benchmark gains; also used
  for personalization with a few hundred prompts.
- **Context:** extends Agarwal et al. (GKD), MiniLLM, and the Qwen3 team's use of
  strong-model logit distillation to build small models [F: arXiv:2505.09388 reports
  using ~1T tokens of logit distillation from flagship models for small ones].

## Off-policy vs on-policy: the table

| Dimension | Off-policy KD | On-policy KD |
|---|---|---|
| Training sequences | teacher/fixed dataset | student-generated rollouts |
| Who generates trajectories | teacher | student |
| Teacher calls | one pass (dataset creation) | every step/batch (live) |
| Compute cost | low–medium | high (teacher serving + student training interleaved) |
| Exposure bias | present — student never sees own states | addressed — trains in student states |
| Training stability | very stable (fixed data) | RL-trainer-like; needs care (LR, KL scale, replay) |
| Long reasoning | degrades off student-distribution | strong suit |
| Online interaction | no | natural (tools, environments) |
| Scalability | embarrassingly parallel | teacher is the bottleneck |
| Best use case | cheap broad capability transfer | long-horizon behaviors, agents, style/persona matching |

## The 2026 on-policy taxonomy

**Feedback type**
- *Logit feedback:* per-token distributions → reverse/forward KL (GKD, Tinker OD).
- *Outcome feedback:* verifier/reward on the final answer only (RLVR-flavored; sparse).
- *Reward feedback:* a (distilled) reward model scores trajectories (→ `12`).
- *Self-play feedback:* student generations graded by an improved self or a rival
  (self-play lineage; early-stage [Experimental]).

**Teacher access**
- *White-box:* teacher logits on student states — the dense default.
- *Black-box:* teacher/judge scores text only (weaker; pairs with reward distillation).
- *Teacher-free:* verifier or self-play replaces the teacher (→ `09`).

**Loss granularity**
- *Token:* per-token KL — densest, default.
- *Sequence:* whole-sequence score (outcome/reward) — sparse but simple.
- *Trajectory:* multi-turn episode-level signal (agents).
- *Hybrid:* token KL + sequence verifier bonus — common production compromise [I].

## Cost and infrastructure reality

- The teacher must serve *during training*: either colocated (GPU-rich) or a fast
  inference service (API-grade latency requirements).
- Typical loop [I: engineering estimate from the Tinker/TRL references]: student
  rollout batch → teacher scoring pass → student update; teacher FLOPs per step are
  comparable to one extra forward-only "critic" per rollout token — hence the 9–30×
  savings claim *vs RL* (no value model, no full rollouts-per-update ratio, dense
  signal) but still ≥ several × the cost of one-off SFT distillation.
- Replay buffers of student trajectories amortize teacher calls (score once, train
  several epochs) at the price of slight staleness (→ `19` §OPD production).

## When to reach for it

| Situation | Choose |
|---|---|
| Broad capability transfer on a budget | off-policy (→ `06`/`07`) |
| Student drifts/derails on long generations | on-policy |
| Agent/tool behavior where states depend on student actions | on-policy (→ `13`) |
| Style/persona with few demonstrations | on-policy (Tinker's personalization case) |
| Teacher only available as text API | on-policy with reward/verifier feedback (weaker) |

## Related
- `11-gkd.md` — the GKD method: divergences, on/off-policy mixing, TRL trainer
- `12-distillation-and-rl.md` — the full KD↔RL dictionary
- `06-sequence-and-response-distillation.md` — the off-policy baseline
- `13-agentic-distillation.md` — on-policy in multi-turn tool environments
- `19-production-design.md` — the production OPD loop (buffers, staleness, sync)
- `Speculative-Decoding/README.md` — unrelated "on-policy" name collision: none; but note both fields say "draft"

## Key Takeaways
- Exposure bias is the defining weakness of static distillation; on-policy KD is the fix
  with the strongest 2025–26 evidence.
- Mechanically it is "RL with a dense reward": swap the sparse outcome for per-token
  teacher reverse-KL on student rollouts.
- Evidence: AIME 60→70 on Qwen3-8B in ~150 steps at 9–30× less compute than RL
  [F: Thinking Machines 2025], on top of GKD/MiniLLM [F: arXiv:2306.13649/2306.08543].
- Cost moves from data storage to live teacher serving — a systems trade, not a free win.
- Pair it: off-policy verified traces to seed competence, on-policy to sharpen behavior
  in the student's own distribution.
