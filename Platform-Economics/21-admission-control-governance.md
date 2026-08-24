# 21 — Admission Control & Governance

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Sometimes the **economically rational response to a request is not "yes."** A
well-governed platform decides per request whether to **accept, queue, defer,
downgrade, route elsewhere, or reject** — based on queue capacity, memory
pressure, budget exhaustion, priority, SLO protection, and rate limits. This
*admission policy* is where quotas ([20](20-quota-engineering.md)), fairness
([18](18-tenant-fairness.md)), and economics ([15](15-llm-platform-pricing-models.md))
all get enforced mechanically. (The queuing/latency side is developed in
[Production-Operations/13-overload-protection](../Production-Operations/13-overload-protection.md)
and [Inference/Production-Serving/10-admission-control-and-overload](../Inference/Production-Serving/10-admission-control-and-overload.md).)

## The decision space

| Action | When | Economic/governance meaning |
|---|---|---|
| **Accept** | within quota + capacity + budget | normal service |
| **Queue** | capacity available later, latency allows | defer work; keeps utilization high ([05](05-gpu-utilization-economics.md)) |
| **Defer** | e.g. shift batch to off-peak | arbitrage cheaper/less-busy window |
| **Downgrade model** | budget/SLO allows a cheaper model | capture cost on the frontier ([11](11-economic-model-routing.md)) |
| **Cloud burst** | local saturated, policy allows cloud | elastic out ([28](28-cloud-bursting-economics.md)) |
| **Reject** | hard quota/budget/policy | protect platform + other tenants |

The art is *ordering* the actions: **downgrade and defer are kinder than reject**,
and for many tenants a soft mitigation beats a hard "no" ([20](20-quota-engineering.md)).

## Architecture

```
Request
   ↓
Policy Engine            (tenant entitlements, data class, model, cloud rules)
   ↓
Admission Controller
   ├── Accept
   ├── Queue
   ├── Downgrade model
   ├── Cloud burst
   └── Reject
```

The **policy engine** is the governance brain (often OPA/Kyverno — see
[27-policy-as-code](27-policy-as-code.md)); the **admission controller** is the
executor that maps policy verdicts to the five actions.

## Signals the controller reads

- **Queue capacity** — headroom before latency SLO breaks ([17](17-slo-economics.md)).
- **Memory pressure** — KV cache exhaustion ([08](08-kv-cache-economics.md)).
- **Budget exhaustion** — tenant at/over budget (`[22](22-budget-aware-routing.md)`).
- **Priority / tier** — premium tenants admitted ahead ([16](16-llm-service-tiers.md)).
- **SLO protection** — refuse work that would breach the pool's SLO ([17](17-slo-economics.md)).
- **Rate limits** — burst boundaries ([20](20-quota-engineering.md)).

## Governance framing

Admission control is where *policy-as-code* meets *economics*: the controller
should apply **fair, transparent, published** rules (no silent per-tenant
favoritism beyond declared tiers) and **meter the outcome** (was it accepted,
queued, downgraded, rejected?) for observability and dispute resolution
([13-tenant-metering](13-tenant-metering.md), [42-multi-tenant-observability](42-multi-tenant-observability.md)).

## Related

[20-quota-engineering](20-quota-engineering.md) · [18-tenant-fairness](18-tenant-fairness.md) ·
[27-policy-as-code](27-policy-as-code.md) · [28-cloud-bursting-economics](28-cloud-bursting-economics.md) ·
[Production-Operations/13-overload-protection](../Production-Operations/13-overload-protection.md)

## Key takeaways

1. "Reject" is one of five legitimate governance actions — not always a failure.
2. Prefer soft mitigations (queue/defer/downgrade/burst) before hard "no".
3. Separate the policy engine (what's allowed) from the admission controller (execute).
4. Read queue/memory/budget/priority/SLO/rate signals; meter the decision.
