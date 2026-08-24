# 46 — Pricing a GPU-as-a-Service Platform

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Some platforms don't just serve tokens — they expose **raw/dedicated GPU
capacity** to tenants as a product (GPU VMs, bare-metal GPU, shared GPU, MIG,
time-slicing, Kubernetes GPU quotas, managed inference). Pricing these is
**pricing capacity**, which has a different economic shape than pricing tokens
([15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)): you must
decide **what unit to charge** (GPU-hour, reserved GPU, namespace quota, token,
managed endpoint) and — delicately — **how much oversubscription to allow**,
because oversubscription is where GPUaaS providers make margins *and* where they
blow up SLOs.

## Product forms to price

| Form | Isolation | Pricing unit |
|---|---|---|
| **GPU VM** | virtualized, shared host | GPU-hour |
| **Bare-metal GPU** | dedicated node ([02](02-multi-tenancy-models.md)) | reserved GPU / node-hour |
| **Shared GPU** | soft (pooled) | GPU-hour, or token ([46↔15](15-llm-platform-pricing-models.md)) |
| **MIG** (Multi-Instance GPU) | hard slices of one GPU | MIG-slice-hour |
| **Time-slicing** | shared, sequential | GPU-hour (fractional) |
| **Kubernetes GPU quota** | namespace quota | quota/unit, then GPU-hour |
| **Managed inference** | managed endpoint | per token |

## Charging models compared

| Charge by | Strength | Distortion |
|---|---|---|
| **GPU-hour** | matches capacity cost | penalizes idle, ignores work done |
| **Reserved GPU** | predictable; SLO ([30](30-capacity-reservation.md)) | idle cost for tenant; under/over provision |
| **Namespace quota** | governance-friendly ([47](47-kubernetes-multi-tenancy.md)) | needs hindsight to price well |
| **Token usage** | usage-based; user-friendly | decouples from *capacity* cost |
| **Managed endpoint** | simple for app owners | hides shape ([06](06-token-economics.md)) |

A healthy GPUaaS often **charges capacity (reserved/GPU-hour) plus consumption
(tokens)** — the hybrid from [15](15-llm-platform-pricing-models.md), so tenants
pay for the capacity they hold *and* the work they do.

## Margins & oversubscription — carefully

- **Margin** = collected price − fully-loaded cost ([03](03-llm-inference-unit-economics.md)).
  With commodity GPUs, margin comes from **oversubscription** (selling more
  nominal capacity than physical GPUs) and **utilization** ([05](05-gpu-utilization-economics.md)).
- **Oversubscription** lets a shared pool serve more than its nominal cores by
  betting tenants don't all peak at once. Done modestly, high utilization and
  low prices. **Done blindly, it's a noisy-neighbor / SLO failure** ([19](19-noisy-neighbor.md)) —
  tenants' jobs slow or fail, and the platform eats the trust + support cost
  ([45-cost-of-failure](45-cost-of-failure.md)).
- **[I] Rule:** oversubscribe **only** what the SLO tolerates; make the
  oversubscription ratio **explicit and audited**, and price premium tiers into
  *unshared* capacity ([16-llm-service-tiers](16-llm-service-tiers.md),
  [17-slo-economics](17-slo-economics.md)).

## Related

[15-llm-platform-pricing-models](15-llm-platform-pricing-models.md) ·
[02-multi-tenancy-models](02-multi-tenancy-models.md) ·
[47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md) ·
[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[30-capacity-reservation](30-capacity-reservation.md)

## Key takeaways

1. GPUaaS prices *capacity*: GPU-hour, reserved, quota, token, or endpoint.
2. Add capacity + consumption pricing so tenants pay for held *and* used.
3. Margin comes from utilization and modest oversubscription.
4. Oversubscription beyond the SLO tolerance = noisy-neighbor disaster.
