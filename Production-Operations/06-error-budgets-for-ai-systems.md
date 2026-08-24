# 06 — Error Budgets for AI Systems

`LAST_UPDATED: 2026-08-23` · Status: foundational page

## 30-Second Explanation

An **error budget** is the planned-for amount of failure your SLO permits. If
your SLO is 99.9%, your error budget is 0.1% — i.e. a bounded amount of
"unreliability" you can *spend* on change. It turns "is it safe to ship this
risky change?" into a *measurable* question.

## Classic error budget

```
SLO           = 99.9%
Error budget  = 100% − 99.9% = 0.1% over the SLO window
```

`[F]` Google SRE Book (error-budget-based release). Interpretation: as long as
your recent error rate has *not already consumed* the budget, you are allowed to
ship a risky change; if the budget is burnt, you **halt** risky changes and focus
on reliability.

## How to use an error budget as a gate

A release is "safe to ship" only while there is budget left. This applies to **every
kind of change**, not just code:

| Change | What it risks | How the budget gates it |
|---|---|---|
| Model release | quality regressions, new latencies | ship if budget available; halt if burnt |
| Inference-engine upgrade | throughput/behaviour change | gated on latency/error budget |
| Quantization change | accuracy loss | gated on quality AND latency budget |
| Prompt / system-prompt change | output behaviour shift | gated on quality budget |
| RAG change (index, embeddings, reranker) | grounding, freshness | gated on retrieval/quality budget |
| Routing change | placement, herding, cache affinity | gated on latency/error budget |
| Kernel / CUDA change | crashes, perf regression | gated on error + GPU budget |

## Quality error budget

Availability budgets don't capture *silent quality loss* — a model can regress
with zero HTTP errors. So LLM platforms need a **quality error budget**: a
bounded allowance for quality degradation.

> **Conceptual example ([I], with illustrative `[A]` numbers):**
> baseline answer quality = X (a score on a fixed eval set). A latency
> optimization is acceptable only if the quality loss it introduces stays inside
> an **explicitly defined tolerance**, e.g. "quality score may drop at most Δ
> within the 30-day eval window." This Δ is the *quality error budget*.

The exact Δ and window are **your call** — there is **no single universal
formula**. The point is that a quality-degrading change is treated like any
other error-budget-spending change: it needs an allowance, is measured, and can
be rolled back when the allowance is spent.

**Measurement cadence (`[I]`, practical):** the quality budget is only
actionable if you can actually observe quality continuously enough to gate a
release. In practice run the **golden set** at least per-release and on a
schedule (e.g. nightly), and feed **sampled production traffic** through judges/
classifiers on a tight cadence (minutes-to-hourly) so a release can't sail
through a week before its quality regression is seen. Between eval runs the
budget is estimated by interpolation/roll-up over the last complete scores —
less precise, but enough to decide "safe to ship or not."

## Practical mechanics

1. Compute the availability error budget over the SLO window.
2. Maintain a *quality error budget* over your eval set (fixed golden set +
   sampled production traffic — see [28](28-llm-regression-testing.md)).
3. Before any of the changes above, check **both** budgets.
4. When a budget is exhausted: **freeze risky changes**, prioritize reliability,
   and only resume when the budget recovers.

## Related

`02-sli-slo-sla-for-llms.md` · `25-model-release-engineering.md` ·
`27-canary-deployment.md` · `Google SRE Book (release acceptance)`

## Key takeaways

1. Error budget = 100% − SLO; it is failure you've planned for.
2. Use it as a **gate** on model/engine/quant/prompt/RAG/routing/kernel changes.
3. LLMs need a separate **quality error budget** — silent quality loss has no
   HTTP status.
4. There is no universal Δ/formula; define your own tolerance and window.
