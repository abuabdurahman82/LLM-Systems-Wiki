# Lab 7 — Weighted Fair Scheduling

`LAST_UPDATED: 2026-08-24` · Concept: fairness · Builds on
[../18-tenant-fairness](../18-tenant-fairness.md).

## Goal
Implement **weighted fair queueing (WFQ)** over tenant queues and show that
service share converges to the weight ratio — not to arrival volume.

## Approach (simulation)
Two tenants, A weight 3, B weight 1. A floods 1000 jobs, B sends 50. Serve a
round-robin where each round gives A 3 credits and B 1 credit for whatever's
queued (credit-based WFQ).

```python
def wfq(pending, weights):
    served={k:0 for k in pending}; q={k:list(v) for k,v in pending.items()}
    while any(q.values()):
        for t,w in weights.items():
            for _ in range(w):
                if q[t]: q[t].pop(0); served[t]+=1
    return served
# pending={"A":1000[0], "B":50[0]} weights={"A":3,"B":1}
```

Compare A:B service ratio vs 3:1 over time.

## Expected result
Despite A having 20× B's jobs, delivered work stays ≈ **3:1** (their weight
share), so B isn't starved — B finishes promptly relative to its own demand.

## Interpretation
FIFO would serve ~A-only; WFQ guarantees each tenant a *share*
([18](../18-tenant-fairness.md), [16](../16-llm-service-tiers.md)). This is the
queue-position half of fairness; admission (lab 9) is the other half.

## Verify
Count completed jobs per tenant per round; confirm ratio ≈ weights after warm-up.
