# 36 — Evaluator Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

A **critic / evaluator model** checks or improves a generator's output. It costs
an extra LLM call (or several) per task — and can *more than pay for itself* if
it prevents expensive errors, retries, or downstream failures. The economic test
is **Evaluator ROI = Value of Prevented Errors − Evaluation Cost**. The art is
**selective evaluation**: spend the evaluator where errors are costly, and skip
it where they're not.

## Generator + Critic + Revision

```
Generator  ──► draft
                 │
              Critic (evaluator LLM)
                 │
          acceptable?   YES → ship
                 │ NO
              Revision (generator re-writes)  → re-check
```

Each critic call and each revision is extra cost ([35-agent-economics](35-agent-economics.md) —
evaluators are part of the amplification).

## Options compared

| Option | Cost/task | Quality benefit | When |
|---|---|---|---|
| **No evaluator** | 0 calls | baseline | routine, low-cost-of-error work |
| **Local evaluator** | 1 cheap call | catches common errors | technical/internal answers |
| **Premium cloud evaluator** | 1 expensive call | strongest | high-impact decisions |

## Evaluator ROI

$$\text{Evaluator ROI} = \underbrace{\text{Value of Prevented Errors}}_{\text{cost of a bad answer × probability prevented}} - \underbrace{\text{Evaluation Cost}}_{\text{critic + revision calls}}$$

An evaluator is worth running when the *prevented-error value* exceeds its cost.
Because prevented error value scales with the *impact of being wrong*, the same
evaluator can be negative-ROI on routine queries and hugely positive-ROI on
high-stakes ones — hence **selective evaluation**.

## Selective evaluation (example policy)

| Workload | Evaluation strategy |
|---|---|
| **Routine query** | no critic (accept generator output) |
| **Technical answer** | local critic (cheap check) |
| **High-impact decision** | premium independent critic (strong, independent) |

This is a *routing* decision in the same family as
[11-economic-model-routing](11-economic-model-routing.md) and
[22-budget-aware-routing](22-budget-aware-routing.md) — spend the expensive
evaluator only where its prevented-error value justifies it
([43-goodput-economics](43-goodput-economics.md)).

## Cautions [I]

- **Evaluator cost is hidden amplification** — budget it like agent calls
  ([35](35-agent-economics.md)); unbounded critic loops are a waste pattern
  ([34-ai-cost-waste](34-ai-cost-waste.md)).
- **A weak evaluator can be net-negative** (false positives force useless
  revisions; false negatives give false confidence) — validate the evaluator
  itself ([Evaluation-Engineering/LLM-as-a-Judge](../Evaluation-Engineering/LLM-as-a-Judge.md)).
- Meter evaluation calls separately so their cost is visible and can be tuned
  ([13-tenant-metering](13-tenant-metering.md)).

## Related

[35-agent-economics](35-agent-economics.md) ·
[43-goodput-economics](43-goodput-economics.md) · [34-ai-cost-waste](34-ai-cost-waste.md) ·
[Evaluation-Engineering/LLM-as-a-Judge](../Evaluation-Engineering/LLM-as-a-Judge.md) ·
[11-economic-model-routing](11-economic-model-routing.md)

## Key takeaways

1. Evaluators add per-task cost but can prevent costlier errors — judge by ROI.
2. Evaluator ROI = value of prevented errors − evaluation cost.
3. Use selective evaluation: no critic for routine, cheap critic for technical, premium critic for high-impact.
4. Validate the evaluator itself; budget critic/revision loops.
