# 13 — Tenant Metering

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Metering must be designed before billing, because you cannot govern,
allocate, or charge for what you never measured.** Every consumption event on a
multi-tenant platform must be recorded with enough **cardinality** to answer
"who consumed what, on which model/pool, toward which budget" — and the
dimensions you choose up front determine every downstream capability:
showback, chargeback, quota enforcement, waste detection, and SLO reporting.

## Minimum metering dimensions

A single metering event ("one request finished") should carry at least:

| Dimension | Why it matters |
|---|---|
| `tenant_id` | who owns the cost (the accounting unit) |
| `user_id` | who acted within the tenant |
| `project_id` / `namespace` | scoped workload / quota target |
| `application_id` | which product generated the traffic |
| `model_id` | which model (pricing + governance) |
| `endpoint_id` | which serving address / endpoint |
| `gpu_pool` | which hardware/isolation pool |
| `region` | geo + data-residency accounting |
| `input_tokens` | prefill cost basis |
| `output_tokens` | decode cost basis |
| `cached_tokens` | cache economics ([08](08-kv-cache-economics.md)) |
| `reasoning_tokens` | hidden thinking output ([35](35-agent-economics.md)) |
| `request_latency` | E2E + SLO compliance |
| `TTFT` | first-token latency |
| `TPOT` | per-output-token latency |
| `gpu_time` | actual GPU-seconds consumed (for GPU-time quotas/chargeback) |
| `request_status` | ok / error / timeout / rejected / downgraded |
| `timestamp` | time + seasonality / burst analysis |

## Design for the billing/Governance that follows

Metering feeds a stack:

```
Metering (raw events)
   ↓
Aggregation (per tenant · per model · per hour/day)
   ↓
Showback / Chargeback        Quota/Budget enforcement
   ↓
Forecasting / FinOps         SLO reporting
```

Getting it wrong upstream breaks everything downstream: you can't enforce a
monthly token budget ([20-quota-engineering](20-quota-engineering.md)) without
counting tokens; you can't chargeback ([14](14-showback-chargeback.md)) without
an allocation key; you can't detect waste ([34](34-ai-cost-waste.md)) without
per-unit GPU-time.

## Cardinality & observability implications

- **High cardinality**: tens of thousands of tenants × models × endpoints ×
  regions is a *metrics/events* problem, not a side-table — push raw events to a
  scalable event store and keep pre-aggregated rollups for queries
  ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
- **Label hygiene**: dimension names must be consistent (tenant=BU, project,
  etc.) or allocation logic breaks; standardize the label taxonomy in the schema
  before rollout.
- **Sampling is dangerous for billing** — never sample the metering you charge
  from; sample only the *observability* feed.
- **Idempotency**: retries must not double-count; record a request `id` and
  dedupe ([Production-Operations/23-llm-tracing](../Production-Operations/23-llm-tracing.md)).
- **Right-to-erase**: retention/delete policies for telemetry with PII
  ([24-data-governance](24-data-governance.md)).

## Worked example (illustrative labels)

A tenant `acme/eng` sends a request to endpoint `gpt-class-70b` on `pool-prod-a`
in `us-east-1`: 1,500 in / 500 out / 200 cached / 40 reasoning, TTFT 320 ms,
TPOT 28 ms, latency 14 s, status ok, timestamp 2026-08-24T10:00:00Z. That one
line is the atomic unit from which showback, budgets, and SLO reports are all
derived.

## Related

[14-showback-chargeback](14-showback-chargeback.md) ·
[20-quota-engineering](20-quota-engineering.md) ·
[42-multi-tenant-observability](42-multi-tenant-observability.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md) ·
[Production-Operations/23-llm-tracing](../Production-Operations/23-llm-tracing.md)

## Key takeaways

1. You cannot govern what you don't measure — metering comes before billing.
2. Record a rich, consistent set of dimensions per request (tenant/model/GPU/
   region/tokens/latency/gpu_time/status/timestamp).
3. High cardinality means scalable event storage + pre-aggregated rollups.
4. Never sample billing-grade metering; keep it idempotent and retention-governed.
