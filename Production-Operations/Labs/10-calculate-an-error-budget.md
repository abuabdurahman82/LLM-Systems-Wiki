# Lab 10 — Calculate an Error Budget

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [02-sli-slo-sla-for-llms](../02-sli-slo-sla-for-llms.md), [06-error-budgets-for-ai-systems](../06-error-budgets-for-ai-systems.md)

## Goal
Turn an SLO into a concrete **error budget** and learn when a release is safe.

## Why
The error budget is the planned-for failure that makes change safe
([06](../06-error-budgets-for-ai-systems.md)).

## Method
```python
def error_budget(slo_pct, window_days=30):
    budget = 1 - slo_pct/100
    total_s = window_days*24*3600
    return {"slo":slo_pct,"allowed_unreliability":budget,
            "allowed_seconds":budget*total_s,
            "allowed_pct_per_day": (budget/total_s)*86400*100}

print(error_budget(99.9))   # 0.1%  -> ~2,592 s/mo (~43 min)
print(error_budget(99.95))  # 0.05% -> ~1,296 s/mo (~21.6 min)
```
`0.1% of a 30-day (2,592,000 s) window = 2,592 s ≈ 43 min` (`[E]` arithmetic —
your python output is ground truth).

## Burn-rate practice
Track actual unreliability over the window. If burn is consuming the budget too
fast for your multi-day rating (e.g. would exhaust it in 2 days), **halt risky
releases** and page ([22](../22-alerting-strategy.md)). For LLMs also keep a
**quality error budget** — a bounded Δ on eval-set quality that a latency/quant
win may consume ([06](../06-error-budgets-for-ai-systems.md), [28](../28-llm-regression-testing.md)).

## Interpretation
- A 99.9% SLO allows only ~43 min of failure per month — decide what is truly
  worth promising.
- Every release that risks availability/quality spends this budget; spend it
  deliberately or halt.

## Safety
Pure computation; no services touched.
