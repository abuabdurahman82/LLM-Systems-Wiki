# 04 — The LLM Distillation Taxonomy: Black-Box vs White-Box and the Full Map
`LAST_UPDATED: 2026-08-27` · Status: first-class page

## 30-Second Explanation
Every distillation method answers three questions: *what does the teacher expose*
(outputs, logits, hidden states, preferences, judgments), *what does the student train
on*, and *at what cost*. This page is the master map: the taxonomy tree, the mandatory
black-box/white-box split, the per-technique tables, a decision tree for choosing, and
the flagship comparison matrix. The other pages deep-dive one branch each.

## The taxonomy tree

```
LLM DISTILLATION
├── Output / Response Distillation ........ teacher answers → student SFT (06)
├── Logit Distillation .................... token distributions → KL (05)
│   ├── Token-Level KD
│   └── Top-K Logit KD
├── Sequence-Level Distillation ........... teacher-generated sequences (06)
├── Feature Distillation .................. hidden states (05)
├── Hidden-State Distillation ............. layer-mapped matching (05)
├── Attention Distillation ................ attention matrices/heads (05)
├── Representation Distillation ........... embedding-space alignment (05)
├── Reasoning / CoT Distillation .......... traces → student (07, 08)
├── Preference Distillation ............... pairwise judgments → DPO-style (12)
├── Reward Distillation ................... RM/judge behavior → cheap RM (12)
├── On-Policy Distillation ................ student rollouts + teacher scores (10, 11)
├── Self-Distillation ..................... model → same/different-size self (09)
├── Multi-Teacher Distillation ............ ensemble/domain teachers (09)
├── Cross-Architecture Distillation ....... MoE→dense, family→family (05, 16)
├── Agent / Tool-Use Distillation ......... trajectories: plan/tool/observe (13)
└── Dataset Distillation .................. NOT model KD — see 14 §terminology
```

## Black-box vs white-box (the mandatory split)

Everything practical flows from *what you can access*:

```
                    Teacher
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
    Logits        Hidden states     Attention
       │               │                │
       └───────────────┼────────────────┘
                       ▼
                    Student            ← WHITE-BOX only

   Prompt ─▶ Teacher API ─▶ response text ─▶ Student     ← BLACK-BOX always available
```

| Dimension | Black-box teacher | White-box teacher |
|---|---|---|
| Access | prompt → response (maybe logprobs, scores) | + logits, hidden states, attention, intermediates |
| Techniques available | response/reasoning distillation, best-of-N, (limited) preference distillation | + logit KD, feature/attention KD, on-policy logit feedback |
| Perfomance ceiling | high — surprisingly close when data is verified & diverse (R1-Distill ≈ [F: arXiv:2501.12948]) | highest *per token of supervision* (denser signal) |
| Teacher cost | pay-per-token; no GPU hosting | must host teacher (often multi-GPU; MoE = multi-node) |
| Storage | small (text) | large unless top-K compressed (→ 05 §storage math) |
| Legal/ToS | output-use terms vary by provider — verify before designing (→ 15 §API) | model license governs; open-weight licenses differ (→ 15 §open-weight) |
| Reproducibility | API drift risk | checkpoint pinning |
| Cross-tokenizer/family | easy (text-level) | hard unless tokenizers align (→ 05 §cross-tokenizer) |

**Practical consequence:** the LLM era's most famous distillation (R1-Distill) is
*black-box-style* — teacher text only — and it worked because the data was verified and
the behavior was in the text. White-box methods buy sample efficiency, not a different
ceiling, when the student is large enough [I: synthesis; see 07 for the data-quality
argument].

## Per-technique reference table

Legend: Teacher access = what the pipeline needs; Cost = training-time compute; Storage =
extra data kept around.

| Technique | Teacher exposes | Student receives | Access | Cost | Storage | Typical loss | Best for | Watch out for |
|---|---|---|---|---|---|---|---|---|
| Response KD | answers | (prompt, answer) pairs | black-box | low | low | SFT CE | the 80% case | quality unverified → 14 |
| Sequence KD | sampled sequences | sequences | black-box | low-med | low | CE on teacher tokens | cross-family transfer | exposure bias → 10 |
| Logit KD | full next-token dists | per-token targets | white-box | high | high (→05) | fwd/rev KL | same-family, dense signal | vocab mismatch, bandwidth |
| Top-K logit KD | top-K tokens+probs | sparse targets | white-box | med | med | KL over support ∪ truth | practical logit KD | tail loss |
| Feature/hidden-state | layer activations | mapped targets | white-box | high | med | MSE/cosine | same-arch compression | layer-mapping choice |
| Attention KD | attention maps | maps | white-box | high | high | MSE over heads | early Transformer KD | mostly superseded by 05-era results [I] |
| Reasoning/CoT KD | traces | (prompt, trace, answer) | black-box | med | low | SFT CE + filters | reasoning students | unfaithful traces → 07 |
| Preference KD | A>B judgments | pairs | black-box | med | low | DPO/ranking | alignment transfer | judge bias → 12 |
| Reward-model KD | RM scores | (prompt, resp, score) | black/white | high | med | MSE/ranking/KL | cheap verifiers/RMs | RM fidelity → 12 |
| On-policy KD | scores of student rollouts | rollouts + per-token scores | white-box (typ.) | high | — | per-token rKL | long generations, agents | teacher serving cost → 10 |
| Self-distill | own outputs | own outputs | white-box | med | low | SFT/KL | bootstrapping | self-training ≠ KD → 09 |
| Multi-teacher | N teacher signals | mixture/consensus | any | N× | varies | weighted KD | domain coverage | conflicts → 09 |
| Agent/tool-use KD | full trajectories | plans+calls+obs | black-box | high | med | SFT on trajectory | agent models | env fidelity → 13 |

## The flagship comparison (the table to memorize)

| Technique | Teacher access | Student generates training states? | Knowledge signal | Compute cost | Best for |
|---|---|---|---|---|---|
| Response KD | outputs | no | text | $ | fastest win |
| Logit KD | logits | no | distributions | $$$ | same-family compression |
| Feature KD | activations | no | geometry | $$$ | architecture-aware transfer |
| Sequence KD | sequences | no | text | $$ | cross-tokenizer |
| Reasoning KD | traces | no | process+answer | $$ | reasoning students |
| Self-distillation | self | no/loop | text+iter. | $$ | data lifting |
| Multi-teacher KD | N teachers | no | mixture | $N$ | breadth |
| GKD | logits/teacher | yes | dists on own states | $$$$ | exposure bias |
| On-policy KD | teacher | yes | per-token rKL | $$$$ | long-horizon behavior |
| Agent distillation | trajectories | no (env does) | behavior | $$$ | tool-using students |

## Decision tree (expanded)

```
Need cheaper inference?
    │
   YES
    │
Can a smaller EXISTING model meet requirements? ─── YES ──▶ Use it. Done.
    │
   NO
    ▶ Consider KD
         │
   Do you own/have teacher access?
    │                       │
   YES                     NO
    │                       ▶ Check API ToS / license FIRST (→15)
    ▼                       ▶ else: buy responses or skip
What access?
    ├── logits/weights (white-box)
    │        │
    │    Same tokenizer/arch family?
    │        YES ─▶ logit + feature KD (dense, sample-efficient)
    │        NO  ─▶ response/reasoning KD (text is universal)
    │
    └── outputs only (black-box)
             ▼
      Need reasoning?
        YES ─▶ verified reasoning-trace distillation (→07, 08)
        NO  ─▶ response KD + quality filter (→14)
             ▼
      Long autoregressive / agentic tasks?
        YES ─▶ add on-policy KD (GKD-style) (→10, 11)
        NO  ─▶ done
             ▼
      Then: quantize the student + consider it as speculative
      drafter for the teacher (→16)
```

## Which technique should I use? (recommendations)

| Situation | Recommendation |
|---|---|
| Cheapest possible implementation | teacher response generation + SFT (→06) |
| Better generative matching | logit/KL KD (→05) |
| Reasoning student | verified reasoning-trace distillation (→07) |
| Long-sequence behavior / agents | on-policy / GKD-style methods (→10, 11) |
| Cross-model-family transfer | response/sequence KD (→06) |
| Same family, dense budget | hidden-state/logit KD (→05) |
| Edge / local AI | reasoning KD + quantization; small dense students (→16, 18) |
| Cheap verifier for RL or BoN | reward-model distillation (→12) |
| Many domains, one student | multi-teacher with routing (→09) |

## Non-duplication note
This page is the map. Math lives in `03`/`05`; the modern flagship methods in
`07`–`11`; systems in `15`–`16`; measurement in `17`. The post-training mechanics the
students use (SFT, DPO, GRPO) are owned by `Post-Training/README.md` and
`Post-Training/Alignment-RLHF.md`.

## Related
- `01-why-distillation.md` — the why and the efficiency landscape
- `03-distillation-losses.md` / `05-logit-and-feature-distillation.md` — the white-box toolbox
- `06-sequence-and-response-distillation.md` — the black-box workhorse
- `10-on-policy-distillation.md` — the 2025–26 frontier
- `Post-Training/README.md` — SFT/RLHF/DPO/GRPO mechanics
- `Agents/Tool-Use.md` — agent runtime behavior (pairs with 13)

## Key Takeaways
- Classify every method by: teacher access → signal → contexts → loss. That four-tuple
  pins down the technique.
- Black-box vs white-box is the first fork: it determines cost, storage, legality, and
  the available toolbox.
- Response/reasoning KD carries most real-world distillation in 2026; logit/feature and
  on-policy methods are the deeper layers.
- The decision tree ends the same way in most deployments: distilled student →
  quantized → (optionally) a speculative drafter for the teacher.
