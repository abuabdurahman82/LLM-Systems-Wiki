# 20 — Quota Engineering

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

A **quota** is a ceiling enforced on a tenant's consumption — the technical
backbone of fairness ([18](18-tenant-fairness.md)), budget control
([22](22-budget-aware-routing.md)), and noise protection ([19](19-noisy-neighbor.md)).
Quotas come in many resource dimensions (requests, tokens, GPU-hours, memory,
concurrency, money), and in **hard / soft / burst** flavors. The art is choosing
the *right dimensions* (token + concurrency, not just request count) and the
*right flavor* (a burst quota lets tenants ride short spikes without breaking
their allowance or the neighbors' SLO).

## Quota dimensions compared

| Quota | Enforces | Weakness if used alone |
|---|---|---|
| **Request quota** | requests / period | gameable by token-heavy requests |
| **Token quota** | tokens / period | shape-aware; better |
| **GPU quota** | GPU-hours / period | capacity-based; ignores efficiency |
| **Memory quota** | peak/concurrent memory | protects KV but not total compute |
| **Concurrency quota** | in-flight requests | protects latency, not total volume |
| **Cost quota** | currency / period | needs a price model ([15](15-llm-platform-pricing-models.md)) |
| **Daily budget** | currency / day | catches runaway within a day |
| **Monthly budget** | currency / month | the accounting-level control ([22](22-budget-aware-routing.md)) |

>[I] Use **token + concurrency** as the primary enforcement pair (they're the
> dimensions that actually hurt the platform, per [07](07-prefill-decode-economics.md)
> and [19](19-noisy-neighbor.md)), plus **daily/monthly budgets** for economics.

## Hard / soft / burst quotas

- **Hard quota** — an absolute ceiling; requests beyond it are **rejected**.
  Protects the platform unconditionally, but a hard cap on a legitimate burst
  is a UX and business hit.
- **Soft quota** — a *warning* threshold; over it, requests still flow but are
  flagged / deprioritized. Preserves availability but doesn't bound cost.
- **Burst quota** — allows a short, bounded overage *above* the baseline for a
  limited window, then returns to baseline. Provides elasticity without
  allowing permanent over-consumption.

## Example policy (illustrative)

A tenant is configured:
- **baseline** = 10 concurrent requests,
- **burst** = 30 (for up to, say, 5 minutes),
- **monthly token budget** = 500M tokens,
- **monthly cost budget** = $2,000.

Consequences:
- The tenant gets short bursts (good for spiky marketing traffic) but cannot
  sustain 30-way concurrency (protects the pool, [19](19-noisy-neighbor.md)).
- 500M tokens and $2,000 bound total consumption; when either exhausts, the
  router shifts to budget-aware behavior ([22](22-budget-aware-routing.md)) and
  admission starts downgrading/rejecting ([21](21-admission-control-governance.md)).

## Multi-dimensional policy is the norm

A real tenant has a **policy object**, not a single number:

```
{
  "tenant": "acme/eng",
  "concurrency": {"baseline": 10, "burst": 30, "burst_window_ms": 300000},
  "tokens":      {"daily": 25_000_000, "monthly": 500_000_000},
  "cost":        {"monthly_usd": 2000},
  "rate":        {"requests_per_min": 600, "tokens_per_min": 1_000_000},
  "models":      ["small-approved", "standard"],   // [26]
  "cloud_allowed": false,                           // [24]
  "tier": "SILVER",                                 // [16]
}
```

Enforced at gateway (rate), admission (concurrency/tokens), and router (budget +
model + cloud policy). See [21-admission-control-governance](21-admission-control-governance.md)
and [47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md) (union with
Kubernetes `ResourceQuota`/`LimitRange`).

## Related

[18-tenant-fairness](18-tenant-fairness.md) · [19-noisy-neighbor](19-noisy-neighbor.md) ·
[21-admission-control-governance](21-admission-control-governance.md) ·
[22-budget-aware-routing](22-budget-aware-routing.md) · [47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md)

## Key takeaways

1. Quotas are the technical enforcement of fairness, budget, and noise control.
2. Prefer token + concurrency quotas; add daily/monthly cost budgets.
3. Combine hard caps with soft thresholds and burst windows for elasticity.
4. A tenant's quota is a multi-dimensional policy object, not one number.
