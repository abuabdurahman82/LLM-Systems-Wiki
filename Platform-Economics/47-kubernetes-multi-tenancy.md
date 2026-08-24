# 47 — Multi-Tenant Kubernetes Architecture

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Kubernetes is a multi-tenant *container* platform, not automatically a
multi-tenant *LLM-service* platform.** K8s gives you the primitives
(Namespaces, ResourceQuota, LimitRange, PriorityClass, NetworkPolicy, RBAC,
PSA, OPA/Kyverno) and the GPU scheduling mechanisms (Device Plugin, GPU
Operator, MIG, time-slicing, Kueue, Volcano, Run:ai), but a namespace boundary
in K8s **does not** by itself enforce *token/request/budget* tenancy or
prevent noisy-neighbor *inference* interference. LLM-service tenancy (the quotas,
fairness, admission, and economics in the rest of this section) must be layered
**on top of** K8s tenancy.

## Kubernetes tenancy primitives

| Primitive | What it enforces |
|---|---|
| **Namespaces** | logical grouping + scope |
| **ResourceQuota** | aggregate resource caps per namespace (CPU/mem/GPU) |
| **LimitRange** | per-pod min/max resources |
| **PriorityClass** | scheduling/eviction priority (a K8s analog of tiers, [16](16-llm-service-tiers.md)) |
| **NetworkPolicy** | network segmentation ([23](23-tenant-security-isolation.md)) |
| **RBAC** | who can do what (identity) |
| **PSA** (Pod Security Admission) | pod security constraints |
| **OPA/Gatekeeper / Kyverno** | policy-as-code admission control ([27-policy-as-code](27-policy-as-code.md)) |

## GPU scheduling & partitioning

| Mechanism | What it does |
|---|---|
| **NVIDIA Device Plugin** | exposes GPUs as a schedulable resource |
| **GPU Operator** | automates driver/toolkit/MIG setup |
| **MIG** (Multi-Instance GPU) | hard partitioning of one GPU ([02](02-multi-tenancy-models.md), [46](46-gpuaas-pricing.md)) |
| **Time-slicing** | sharing a GPU over time (soft) |
| **Kueue** | quota-based batch job queueing for K8s |
| **Volcano** | batch/gang scheduling |
| **Run:ai** | GPU orchestration + fractional allocation (vendor) |

## The gap: container tenancy ≠ inference tenancy

A tenant isolated at the **namespace/GPU** layer can still:
- **consume the shared KV/prefix cache** of a co-located inference engine and
  evict another tenant ([08-kv-cache-economics](08-kv-cache-economics.md));
- **saturate the engine's batch** and destroy neighbor latency despite holding
  "their own" namespace ([09-batching-and-economics](09-batching-and-economics.md),
  [19-noisy-neighbor](19-noisy-neighbor.md));
- **blow a request/token/budget** that no K8s quota tracks
  ([20-quota-engineering](20-quota-engineering.md)).

So the platform must layer **LLM-service tenancy** — router/admission quotas,
per-tenant token+concurrency limits, cache namespaces, budget enforcement — on
top of the K8s primitives ([21](21-admission-control-governance.md),
[48-enterprise-multi-tenant-llm-platform](48-enterprise-multi-tenant-llm-platform.md)).

>[I] Pattern: **K8s gives you hard resource isolation; the LLM layer gives you
> economic + behavioral isolation.** Both are required for a sound shared LLM
> platform ([02-multi-tenancy-models](02-multi-tenancy-models.md)).

## Related

[21-admission-control-governance](21-admission-control-governance.md) ·
[02-multi-tenancy-models](02-multi-tenancy-models.md) ·
[27-policy-as-code](27-policy-as-code.md) ·
[Production-Operations/18-kubernetes-for-llm-sre](../Production-Operations/18-kubernetes-for-llm-sre.md) ·
[Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)

## Key takeaways

1. K8s gives container/resource tenancy primitives — namespaces, quotas, priority, RBAC, PSA, policy.
2. GPU scheduling: Device Plugin, GPU Operator, MIG, time-slicing, Kueue, Volcano, Run:ai.
3. K8s namespace isolation ≠ LLM-service isolation (cache, batch, tokens, budgets cross namespaces).
4. Layer economic + behavioral tenancy on top of the K8s primitives.
