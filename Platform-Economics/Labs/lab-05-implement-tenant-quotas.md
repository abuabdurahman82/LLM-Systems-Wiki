# Lab 5 — Implement Tenant Quotas

`LAST_UPDATED: 2026-08-24` · Concept: quotas · Builds on
[../20-quota-engineering](../20-quota-engineering.md).

## Goal
Implement a **token + concurrency** quota with **baseline / burst / soft**
semantics for a tenant and enforce it on an admission path.

## Approach (simulation)
Model a proactive token-bucket + concurrency limiter:

```python
class TenantQuota:
    def __init__(self, tok_per_min, concurrency_max, burst_mult=3):
        self.bucket = tok_per_min          # tokens available now
        self.rate = tok_per_min / 60       # refill per second
        self.max_tok = tok_per_min * burst_mult
        self.conc = 0; self.conc_max = concurrency_max
    def tick(self, dt): self.bucket = min(self.max_tok, self.bucket + self.rate*dt)
    def admit(self, tokens):
        if self.conc >= self.conc_max: return False
        if tokens > self.bucket: return False
        self.bucket -= tokens; self.conc += 1; return True
```

Feed a synthetic arrival stream; count admitted vs rejected; show that a short
burst (≤ burst_mult × rate) rides through while sustained overload is capped.

## Interpretation
Token+concurrency quotas stop the two expensive abuse shapes — token-heavy
requests and parallel floods — and the burst window gives elasticity without a
permanent over-consumption loophole ([20](../20-quota-engineering.md),
[18](../18-tenant-fairness.md)).

## Verify
With rate=1000 tok/s and a 2000-token request every 0.5s (needs 4000 tok/s), show
admission falls to ~50% while concurrency stays ≤ cap.
