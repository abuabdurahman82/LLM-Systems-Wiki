# 27 — Canary Deployments

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

A **canary** sends a small, growing share of live traffic to the new version
while the old version serves the rest, checking **SLO, quality, cost, GPU
utilization and errors** at every ramp step and **rolling back automatically**
if anything breaks. It turns risk into a measured, gated ramp.

## The ramp

```
1%  →  5%  →  10%  →  25%  →  50%  →  100%
```

At each stage, validate before promoting further:

- **SLO** — latency/error/goodput inside budget ([02](02-sli-slo-sla-for-llms.md))
- **quality** — golden/eval pass rate, judge scores ([24](24-quality-observability.md))
- **cost** — $/request, token spend ([33](33-cost-as-an-sre-signal.md))
- **GPU utilization** — the new version isn't eating more capacity than planned
- **errors** — no new failure class, no retry/GPU spikes

## Automated rollback criteria (`[I]`)

Define explicitly before release, e.g.:
- P95 TTFT exceeds target, or
- error rate exceeds X, or
- quality/golden pass-rate drops below Δ (the quality error budget, [06](06-error-budgets-for-ai-systems.md)), or
- cost per request exceeds Y.

If any criterion trips at 1–25%, **automatically divert traffic back to the old
version** (no on-call needed to stop a broken ramp).

## Operational practice

1. **Version pair in parallel** — canary and control run simultaneously under the
   same router so metrics are directly comparable.
2. **Route by canary%, with sticky-ish sampling** for comparable cohorts.
3. **Watch correlated signals** — latency without KV/GPU context is noise
   ([04](04-llm-golden-signals.md)).
4. **Nudge, don't jump** — hold at a step if signals are ambiguous; a bad canary
   that's allowed to grow is an incident.
5. **Record provenance** — canary responses tagged `model_id`/`canary:true`
   ([23](23-llm-tracing.md), [25](25-model-release-engineering.md)).

## Related

`02-sli-slo-sla-for-llms.md` · `06-error-budgets-for-ai-systems.md` ·
`24-quality-observability.md` · `25-model-release-engineering.md` ·
`26-shadow-testing.md` · `Labs/11-canary-a-configuration-change.md`

## Key takeaways

1. Ramp 1%→5%→10%→25%→50%→100%, checking SLO/quality/cost/GPU/errors each step.
2. Define automated rollback criteria up front.
3. Run canary and control in parallel for clean comparison.
4. Nudge, don't jump — a bad canary allowed to grow becomes an incident.
