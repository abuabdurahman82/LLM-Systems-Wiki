# Lab 8 — Budget-Aware Model Router

`LAST_UPDATED: 2026-08-24` · Concept: budget-aware routing · Builds on
[../22-budget-aware-routing](../22-budget-aware-routing.md).

## Goal
Build a router that picks a model per request from cost/quality/latency **and a
remaining budget**, and shifts to cheaper options as the budget drains.

## Approach (simulation)
Options (illustrative): local-small $0.01, local-large $0.07, cloud-reasoning $0.40.
Router: score `Quality − cost_penalty − latency_penalty − risk_penalty`, where
`cost_penalty` grows as remaining budget fraction shrinks.

```python
def pick(budget_left, options):
    p = budget_left / budget_total           # 1.0 .. 0.0
    cost_weight = 1.0 - 0.8*p                # higher when budget tight
    return min(options, key=lambda o: o.cost*cost_weight - o.quality + o.latency)
```

Feed a synthetic request mix; watch the modal choice drift small as budget runs
low; at budget=0, admission (lab 9) rejects.

## Expected result
Early in the month the router may afford cloud-reasoning on hard asks; as the
budget drains it converges to local-small. End-to-end spend stays at/under budget.

## Interpretation
Budget pressure is a smooth steering signal, better than a hard cliff
([22](../22-budget-aware-routing.md), [11](../11-economic-model-routing.md)). The
weights are illustrative — tune with real evals.

## Verify
Track cumulative spend over 1000 requests; confirm it never exceeds the budget cap.
