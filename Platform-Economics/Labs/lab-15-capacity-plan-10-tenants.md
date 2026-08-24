# Lab 15 — Capacity-Plan a 10-Tenant Platform

`LAST_UPDATED: 2026-08-24` · Concept: capacity planning · Builds on
[../31-capacity-planning](../31-capacity-planning.md) and
[../32-demand-forecasting](../32-demand-forecasting.md).

## Goal
Size the GPU fleet for **10 tenants** with heterogeneous demand + SLOs, using
peak (not mean) demand and a safe utilization — then sanity-check with the
simulator.

## Approach (computation)
1. For each tenant: peak tokens/s (in+out), model class, SLO tier.
2. Aggregate peak demand per model class.
3. `GPUs = (peak tok/s) / (tok/s per GPU × target_util) × replication`.
4. Run the section simulator with your totals for $/month.

```python
# illustrative
demand = {"interactive": 30_000, "batch": 60_000, "reasoning": 10_000}  # peak tok/s
by_gpu = {"interactive": 25_000, "batch": 25_000, "reasoning": 5_000}   # tok/s/GPU
util = {"interactive":0.6, "batch":0.85, "reasoning":0.5}               # SLO-driven
rep   = {"interactive":2, "batch":1, "reasoning":2}                     # N+1 etc.
gpus  = {k: (demand[k]/(by_gpu[k]*util[k]))*rep[k] for k in demand}
print(gpus)   # interactive ~4, batch ~2.8, reasoning ~8 -> ~15 GPUs total
```

## Expected result
A concrete GPU count per class plus the **headroom note**: interactive is
capped at ρ≈0.6 (SLO), batch runs hotter at 0.85, reasoning needs more GPUs for
its slow decode. Provision to **P90/P99**, not mean ([32](../32-demand-forecasting.md)).

## Interpretation
This is the planning method — measure throughput per GPU, choose target util
from the SLO, multiply by replication, provision to the peak percentile
([31](../31-capacity-planning.md), [17](../17-slo-economics.md),
[47](../47-kubernetes-multi-tenancy.md) for scheduling the result).

## Verify
Double one tenant's demand and re-derive its GPU count by hand; confirm the method scales.
