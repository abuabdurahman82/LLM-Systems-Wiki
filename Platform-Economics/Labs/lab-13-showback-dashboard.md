# Lab 13 — Create a Showback Dashboard

`LAST_UPDATED: 2026-08-24` · Concept: showback / FinOps · Builds on
[../14-showback-chargeback](../14-showback-chargeback.md) and
[../42-multi-tenant-observability](../42-multi-tenant-observability.md).

## Goal
Turn raw meter events (lab 4) into a **tenant showback report**: consumption +
attributed cost per tenant/model, so tenants see their spend before any
chargeback.

## Approach (computation)
```python
# price table (illustrative)
price = {"in":2.00/1e6, "cached":0.50/1e6, "out":8.00/1e6}
def cost(ev): return (ev["in"]*price["in"] + ev["cached"]*price["cached"]
                      + ev["out"]*price["out"])
# aggregate a list of meter events by (tenant, model); sum cost + tokens
```

Produce:
- Per tenant: total tokens (in/out/cached), total $, top model.
- Per model: total $ across tenants.
- Sort tenants by spend (the FinOps attention list).

## Expected result
A table like `acme/eng | 42M in / 9M out | $1,104 | gpt-class-70B 87%`.
This is *showback* (no money moves). Add a budget column and you're at
Level 3 ([14](../14-showback-chargeback.md)).

## Interpretation
Showback is the cheapest governor — tenants right-size when they *see* cost.
It must precede chargeback so the cost model is trusted
([14](../14-showback-chargeback.md), [33](../33-ai-finops.md)).

## Verify
Recount one tenant's $ by hand from your price table; confirm the report matches.
