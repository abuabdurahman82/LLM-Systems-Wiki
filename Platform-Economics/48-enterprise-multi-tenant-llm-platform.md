# 48 — Enterprise Multi-Tenant LLM Platform (Reference Architecture)

`LAST_UPDATED: 2026-08-24` · Status: reference page

## 30-Second Explanation

This page ties the whole section into **one end-to-end reference architecture**:
identity → policy → admission → model routing → scheduling → GPU pools →
serving → metering → chargeback, plus the supporting systems (model registry,
evaluation, secrets, RAG, audit logs, policy database). Each block references
the page(s) that detail it. It is a *reference* — adapt to your size and risk,
but the data and control flows shown are the ones that must exist for a
governed, economical shared LLM platform.

## Reference architecture

```
                            USERS
                              │
                           SSO/IAM
                              │
                          API Gateway
                              │
                    Tenant / Project Resolver
                              │
                 ┌────────────┴────────────┐
                 │                         │
             Policy Engine             FinOps
                 │                         │
           Admission Control           Budget DB
                 │
              LLM Router
       ┌─────────┼─────────┐
       ▼         ▼         ▼
   Local Small  Local Big  Cloud
       │         │         │
     Scheduler / Placement
       │
   ┌───┴───────────────┐
   ▼                   ▼
Shared GPU          Dedicated GPU
Pool                Pool
   │
vLLM / SGLang / TensorRT-LLM
   │
GPU Infrastructure
   │
Metering / Observability
   │
Chargeback / Showback
```

## Supporting systems

| System | Purpose | Detail |
|---|---|---|
| **Model registry** | catalog + entitlements + version pinning | [25-model-governance](25-model-governance.md) |
| **Evaluation service** | quality/safety/cost gating + ongoing evals | [25](25-model-governance.md), [Evaluation-Engineering/](../Evaluation-Engineering/README.md) |
| **Secrets management** | per-tenant/scoped secrets | [23-tenant-security-isolation](23-tenant-security-isolation.md) |
| **RAG** (vector DB + retrieval) | tenant-scoped retrieval | [37-rag-economics](37-rag-economics.md) |
| **Audit logs** | accountability for access/routing/overrides | [42-multi-tenant-observability](42-multi-tenant-observability.md), [23](23-tenant-security-isolation.md) |
| **Policy database** | versioned policy-as-code | [27-policy-as-code](27-policy-as-code.md) |

## Data flow vs control flow

- **Data flow (request):** Users → SSO → Gateway → Resolver → Policy → Admission
  → Router → Scheduler → GPU/Serving → response. Metered at the serving layer.
- **Control flow (governance):** Policy DB + Budget DB + Model Registry + FinOps
  feed the Router/Admission; audit logs and metering feed back into the policy
  and cost models. This closed loop ([57-economics-governance-big-picture](57-economics-governance-big-picture.md))
  is what makes the platform self-governing rather than rule-bound.

## How each page maps in

- **Quotas/budget** feed Admission + Router ([20](20-quota-engineering.md), [22](22-budget-aware-routing.md)).
- **Fairness/priority** live in Scheduler + Admission ([18](18-tenant-fairness.md), [16](16-llm-service-tiers.md)).
- **Security/data class** gate Router (which model/cloud) ([23](23-tenant-security-isolation.md), [24](24-data-governance.md)).
- **Capacity** is the GPU pools beneath ([31](31-capacity-planning.md), [30](30-capacity-reservation.md)).
- **Metering → Chargeback** is the bottom of the diagram ([13](13-tenant-metering.md), [14](14-showback-chargeback.md)).

## Related

[01-multi-tenant-llm-platform-overview](01-multi-tenant-llm-platform-overview.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md) ·
[27-policy-as-code](27-policy-as-code.md) ·
[Production-Operations/38-production-reliability-reference-architecture](../Production-Operations/38-production-reliability-reference-architecture.md)

## Key takeaways

1. The reference architecture runs identity → policy → admission → routing → scheduling → GPU → metering → chargeback.
2. Add model registry, evaluation, secrets, RAG, audit logs, policy DB.
3. Keep the control loop: metering/audit feed policy + FinOps closing the loop.
4. Data-residency and isolation choices live in the pool/region layers.
