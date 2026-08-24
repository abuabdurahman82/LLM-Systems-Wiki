# Lab 4 — Build Token Metering

`LAST_UPDATED: 2026-08-24` · Concept: metering · Builds on
[../13-tenant-metering](../13-tenant-metering.md).

## Goal
Build a minimal per-request metering record that feeds showback/quota/finops —
specifically that captures the dimensions in
[../13-tenant-metering](../13-tenant-metering.md).

## Approach (pure Python — no services)
1. Define a `MeterEvent` with the minimum dimensions: tenant_id, user_id,
   project, application, model, endpoint, pool, region, tokens (in/out/cached/
   reasoning), ttft, tpot, latency, gpu_time, status, timestamp.
2. Emit events; aggregate per tenant/day and per model.
3. Check **cardinality**: how many series does 100 tenants × 5 models × 4
   pools × 24h produce?

```python
dims = dict(tenants=100, models=5, pools=4, hours=24)
print("metric series ≈", dims["tenants"]*dims["models"]*dims["pools"]*dims["hours"])
```
_≈ 48,000 series from a small platform — the reason you bucket into rollups._

## Interpretation
Metering must come **before** billing: without these fields you can't allocate,
quote, or audit. High cardinality drives the storage design
([13](../13-tenant-metering.md), [42](../42-multi-tenant-observability.md)).

## Verify
Emit 5 synthetic events and aggregate one tenant's daily output tokens by hand.
