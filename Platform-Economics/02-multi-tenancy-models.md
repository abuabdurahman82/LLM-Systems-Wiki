# 02 — Multi-Tenancy Models

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

There is no single "multi-tenant" design — there is a **spectrum of isolation**,
from *many tenants sharing one model on one GPU* to *a dedicated cluster per
tenant*. The spectrum is a set of engineering trade-offs, not a quality ladder:
**more isolation costs money and utilization, buys predictability and security**.
Choosing where to sit on the spectrum per workload is a core platform-design
decision, and most mature platforms run *several* models at once (shared pool
for cost, dedicated for the premium and the regulated).

## The isolation spectrum

| Model | Isolation | Utilization | Cost | Ops complexity | Security | Perf predictability | Best use |
|---|---|---|---|---|---|---|---|
| **1. Shared model + shared GPU** | None (soft) | Highest (pooled) | Lowest $/token | Low | Weakest | Low (noisy neighbor) | Internal best-effort, low sensitivity |
| **2. Shared model + dedicated GPU quota** | Soft, quota-enforced | High | Low | Medium | Medium | Medium | Internal tenants with budget/priority tiers |
| **3. Dedicated model replica** | Model/endpoint isolated, GPU shared | Medium | Medium | Medium | Medium-High | Medium-High | Tenants needing isolation of the *model*, not the hardware |
| **4. Dedicated GPU** | Hardware isolated per tenant | Low-Med (per-tenant bursts waste) | Medium-High | Low | High | High | A tenant with spiky-but-critical load |
| **5. Dedicated node** | Node isolated | Low | High | Low | High | High | Compliance/anti-noise requirements |
| **6. Dedicated cluster** | Cluster isolated | Low | Highest | High | Highest | Highest | Regulated tenants, strict data separation |
| **7. Dedicated region** | Geo/datacenter isolated | Lowest | Very high | Very high | Very high | Very high | Sovereign data residency mandates |
| **8. Cloud API isolation** | Provider boundary | n/a (metered) | Variable | Low | Provider-dependent | Provider-controlled | Burst, geos without local GPUs |
| **9. Hybrid local/cloud tenant** | Mixed; local + controlled burst | Medium | Medium | High | Depends on routing policy | Medium | Bursty tenants, elastic demand |

> The table is a conceptual ordering, not an industry standard or a universal
> recommendation. Where you land depends on **data sensitivity, SLO, volume,
> and budget** — see [53-platform-governance-decision-framework](53-platform-governance-decision-framework.md).

## Soft vs hard multi-tenancy

- **Soft multi-tenancy** — tenants share resources (GPU, model, cache, memory)
  with *logical* limits (quotas, priority, admission). Cheap, high utilization,
  but isolation is behavioral: a misbehaving tenant degrades others unless
  controls hold ([19-noisy-neighbor](19-noisy-neighbor.md)).
- **Hard multi-tenancy** — tenants get *physical* separation at some layer
  (dedicated GPU/node/cluster/region, separate caches, separate model replicas).
  Predictable and secure, but each walled-off pool dilutes pooling gains and
  lowers utilization ([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).

>[I] The economic insight: **soft tenancy captures pooling, hard tenancy buys
> peace of mind.** A sound platform default is *soft media with hard edges* —
> share aggressively for cost, but give hard isolation to the regulated,
> the premium, and the noise-prone. See [46-gpuaas-pricing](46-gpuaas-pricing.md)
> for how the "dedicated GPU" model maps to charging.

## When isolation genuinely pays

Isolation is worth its cost when it protects something real:

- A **regulated/confidential** tenant that must not co-reside ([24-data-governance](24-data-governance.md)).
- A **premium** tenant buying a strict SLO (dedicated capacity removes the noisy-neighbor term) ([17-slo-economics](17-slo-economics.md)).
- A **noise generator** that would otherwise need aggressive throttling — isolating it may be *cheaper* than policing it ([34-ai-cost-waste](34-ai-cost-waste.md)).

## Related

[01-multi-tenant-llm-platform-overview](01-multi-tenant-llm-platform-overview.md) ·
[19-noisy-neighbor](19-noisy-neighbor.md) · [46-gpuaas-pricing](46-gpuaas-pricing.md) ·
[47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md) ·
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)

## Key takeaways

1. Multi-tenancy is a *spectrum* of isolation/cost/security trade-offs, not a binary.
2. Soft tenancy = pooling + behavioral limits; hard tenancy = physical separation.
3. Cost per token falls with sharing; predictability and security rise with isolation.
4. Run several tenancy models at once; "share, but with hard edges" is a sane default.
