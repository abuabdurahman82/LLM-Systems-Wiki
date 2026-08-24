# Lab 14 — Simulate Service Tiers

`LAST_UPDATED: 2026-08-24` · Concept: service tiers · Builds on
[../16-llm-service-tiers](../16-llm-service-tiers.md).

## Goal
Model BRONZE / SILVER / GOLD / PLATINUM tiers with different **priority,
capacity, and price**, and see how tiering protects premium SLOs while letting
bronze fill idle capacity.

## Approach (simulation)
Assign each tier: priority weight, a reserved capacity share, and a price
multiple. Feed mixed-tier arrivals into a scheduler that honors priority and
reserved shares; compute per-tier SLO attainment and platform revenue.

```python
tiers = {"bronze":{"pri":1,"reserved":0.10,"price":1.0},
         "silver":{"pri":2,"reserved":0.25,"price":1.5},
         "gold":  {"pri":3,"reserved":0.35,"price":2.5},
         "platinum":{"pri":4,"reserved":0.30,"price":4.0}}
```

Saturate the pool; observe: bronze SLO degrades first, gold/platinum hold.
Revenue = Σ workload × tier price.

## Expected result
Under overload, **premium tiers keep their SLO** while bronze absorbs the
misses — exactly the intent. Bronze also *fills idle* capacity off-peak, raising
overall utilization ([05](../05-gpu-utilization-economics.md)).

## Interpretation
Tiers segment demand so strict-SLO tenants **pay for their headroom** (their
price covers reserved capacity) instead of socializing it
([16](../16-llm-service-tiers.md), [17](../17-slo-economics.md)). Names are
illustrative — set your own ([53](../53-platform-governance-decision-framework.md)).

## Verify
Shrink platinum's reserved share to 0.1 and show its SLO starts breaching —
proving reservation is what buys the guarantee.
