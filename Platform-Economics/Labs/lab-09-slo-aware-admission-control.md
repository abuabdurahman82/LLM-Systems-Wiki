# Lab 9 — SLO-Aware Admission Control

`LAST_UPDATED: 2026-08-24` · Concept: admission control · Builds on
[../21-admission-control-governance](../21-admission-control-governance.md).

## Goal
Implement the **accept / queue / downgrade / reject** decision given queue
depth, budget, and priority, so premium SLOs hold under overload.

## Approach (simulation)
A controller reads (queue_depth, remaining_budget, priority) and maps to an action:

```python
def admit(req, state):
    if state.budget <= 0:            return "reject"       # out of money
    if state.queue < state.slo_depth:
        return "accept"                                     # headroom
    if req.priority == "interactive":
        return "accept"                                     # protect interactive
    if req.can_downgrade:            return "downgrade"     # cheaper model
    if state.up_tier:                return "queue"         # defer
    return "reject"
```

Generate overloaded arrivals (batch flood + a few interactive) and count
interactive SLO attainment under admission vs without.

## Expected result
Without admission, interactive P99 blows past SLO once the batch flood arrives.
With admission, batch gets queued/downgraded/rejected first, and **interactive
SLO attainment stays flat** even during the flood.

## Interpretation
Admission control is how the platform protects premium SLOs and enforces
budgets ([21](../21-admission-control-governance.md),
[17](../17-slo-economics.md)). "Reject" for batch is usually cheaper than
breaking an interactive SLO ([43](../43-goodput-economics.md)).

## Verify
Vary the batch flood size; show interactive SLO attainment is flat once
admission is on.
