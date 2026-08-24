# 28 — Cloud Bursting Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

When the **private GPU pool saturates**, a platform with a cloud path can *burst*
the overflow to a cloud GPU/API instead of queueing or rejecting. This trades
**cost, latency, privacy, and data-residency constraints** for **elasticity and
SLO protection**. Bursting is *not* always profitable: the cloud premium plus
data risk must be weighed against the cost of *not* bursting (queue delay,
SLO breach, lost work). The decision rule below makes that trade explicit.

## Architecture

```
Private GPU Pool
      │
capacity available?   YES → local (cheapest)
      ↓ NO
Cloud GPU / API    (policy-permitted? data class OK? -> [24])
```

## What bursting reverses

| Factor | Direction when you burst |
|---|---|
| **Cost** | higher (cloud premium + egress) |
| **Latency** | higher (network RTT, cold start, provider queueing) |
| **Privacy** | higher risk (data leaves the boundary) |
| **Data residency** | harder (region/compliance) |
| **Egress** | extra cost moving data out |
| **Rate limits** | provider caps on burst volume |
| **Provider availability** | new dependency / possible provider outage |

## Decision rule (conceptual/illustrative)

$$\text{Cloud Burst Value} = \underbrace{\text{Avoided Queue Cost}}_{\text{what not bursting costs}} + \underbrace{\text{SLO Protection Value}}_{\text{avoided SLO breach}} - \underbrace{\text{Cloud Premium}}_{\text{extra $/token}} - \underbrace{\text{Data Risk}}_{\text{privacy/residency penalty}}$$

Burst **only if** `Cloud Burst Value > 0`. In practice this means: burst when
the local queue would breach a premium tenant's SLO **and** the data class
permits cloud **and** the extra cost is affordable within budget
([22-budget-aware-routing](22-budget-aware-routing.md)).

## Policy gating

Bursting is conditional on governance, not just economics:

- **Data class** — confidential/regulated → never burst
  ([24-data-governance](24-data-governance.md)).
- **Provider approval** — which cloud providers are approved at all
  ([40-llm-platform-governance-model](40-llm-platform-governance-model.md)).
- **Budget** — burst spend counts against tenant budget ([22](22-budget-aware-routing.md)).
- **Tenant entitlement** — does the tenant's tier allow cloud?

These gates are policy-as-code ([27-policy-as-code](27-policy-as-code.md)).

## Related

[29-local-vs-api-economics](29-local-vs-api-economics.md) ·
[24-data-governance](24-data-governance.md) ·
[21-admission-control-governance](21-admission-control-governance.md) ·
[32-demand-forecasting](32-demand-forecasting.md) ·
[30-capacity-reservation](30-capacity-reservation.md)

## Key takeaways

1. Bursting trades elasticity for cost, latency, privacy, and residency.
2. Burst Value = avoided queue cost + SLO protection − cloud premium − data risk.
3. Burst only when value > 0 AND data/compliance/budget policy permits.
4. Provider approval and data class are governance gates on top of economics.
