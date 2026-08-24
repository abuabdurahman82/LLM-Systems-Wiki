# 01 — What Is a Multi-Tenant LLM Platform?

`LAST_UPDATED: 2026-08-24` · Status: core page — the definitional anchor of the
**Platform Economics & Governance** section.

## 30-Second Explanation

A multi-tenant LLM platform is **shared AI infrastructure that many independent
consumers (users, teams, business units, customers) use at the same time,
with the platform responsible for keeping that sharing fair, secure, measurable,
and economically sustainable.** The central question this section answers is:

> *How do you turn expensive shared AI infrastructure into a fair, secure,
> measurable, economically sustainable platform?*

The naive mental model — *a GPU cluster plus a vLLM endpoint* — is the source of
most failures. When multiple tenants share one service, every operational
decision (scheduling, routing, admission, caching, metering) becomes a
*multi-party* decision with cross-tenant externalities, and the economics stop
being a per-endpoint concern and become a *platform* concern.

## The core mental model: a chain

```
GPU CAPACITY
     ↓
MODEL CAPACITY
     ↓
TOKENS / REQUESTS
     ↓
TENANT CONSUMPTION
     ↓
QUALITY + LATENCY + RELIABILITY
     ↓
COST
     ↓
PRICING / CHARGEBACK
     ↓
GOVERNANCE
```

Every box is a decision surface. You cannot control cost without controlling
the earlier links; you cannot govern without metering; you cannot price without
a cost model. The platform is **not** just:

```
GPU cluster + vLLM endpoint
```

It is the conjunction:

```
Compute + Memory + Models + Schedulers + Routing + Policies +
Identity + Quotas + SLOs + Metering + Economics + Governance
```

## Key terms

| Term | Definition |
|---|---|
| **Tenant** | A distinct consumer of the platform with its own identity, quotas, budget, and policy domain. The unit that *owns* cost and *receives* service. |
| **User** | A person (or service account) acting within a tenant. Adding users does not add tenants. |
| **Team / Business Unit** | An organizational grouping of users; a tenant is often mapped to one (e.g. a BU is the tenant of record). |
| **Project / Namespace** | A scoped grouping of workloads *within* a tenant — the unit a quota is usually attached to (analogous to a Kubernetes namespace, but at the platform, not cluster, level). |
| **Application** | A product that consumes the platform (chatbot, copilot, batch pipeline, agent). |
| **Model** | A deployable artifact with its own cost, context limit, and risk profile. |
| **Endpoint** | A serving address exposing a model (or router) to consumers; the natural metering boundary. |
| **GPU Pool** | A set of GPUs with shared characteristics (model, isolation, region, ownership). |
| **Quota** | An allowed ceiling on some resource (requests, tokens, GPU-hours, budget, concurrency). |
| **Budget** | An economic constraint on consumption, usually currency per period. |
| **SLO** | A measurable service-level objective (latency, availability, quality) a tenant is entitled to. |
| **Policy** | A rule (who may use which model/cloud/pool, under what data and budget conditions) enforced by machinery, not documentation. |

## Possible tenancy boundaries

A "tenant" can be cut at any organizational or technical seam. Picking the wrong
one is the most common design error:

- **User** — simplest; but users are noisy and multiply fast (huge cardinality).
- **Team** — good default for internal platforms.
- **Department / Business Unit** — the natural *accounting* boundary for showback/chargeback.
- **Customer** — the correct boundary for multi-tenant SaaS.
- **Application** — useful when one app has many internal users (an app is a tenant).
- **Environment** — dev / test / prod as separate tenants to protect production SLOs.
- **Organization** — full isolation for subsidiaries or external orgs on shared infra.

> **[I]** The practical rule: make the **tenant = the unit that owns a budget and
> that you would invoice or showback to**. Everything below it (users, apps,
> namespaces) is nesting inside that. Choosing user-level tenancy is usually a
> mistake: it explodes cardinality (see [13-tenant-metering](13-tenant-metering.md))
> and gives you no economic unit to allocate cost to.

## Reference architecture

```
                         Enterprise Users
                               │
                       Identity / SSO
                               │
                         API Gateway
                               │
                       Tenant Resolver
                               │
                    Policy + Admission Control
                               │
                          LLM Router
                               │
                   Scheduler / Placement Layer
                    /          |           \
                   ▼           ▼            ▼
               GPU Pool A   GPU Pool B   Cloud API
                   │
            Inference Engines
                   │
                 Models
                   │
              Metering Layer
                   │
          Billing / Showback / FinOps
```

Each layer has a multi-tenant responsibility:

| Layer | Multi-tenant responsibility |
|---|---|
| SSO/IAM | Resolve who is calling; bind them to a tenant + project. |
| API Gateway | Authenticate, rate-limit at the edge, route to tenant resolver. |
| Tenant Resolver | Map credential → tenant → entitlements/policies. |
| Policy + Admission | Decide accept/queue/downgrade/reject/burst ([21](21-admission-control-governance.md)). |
| LLM Router | Choose model/pool/cloud per tenant, budget, SLO, policy ([11](11-economic-model-routing.md)). |
| Scheduler | Place work on GPUs while honoring tenant fairness ([19](19-noisy-neighbor.md)). |
| Metering | Record every consumption event with tenant attributes ([13](13-tenant-metering.md)). |
| Billing/FinOps | Turn metering into showback/chargeback ([14](14-showback-chargeback.md)). |

## Why multi-tenancy affects every layer

Single-tenant optimization optimizes one workload. Multi-tenant optimization
must optimize a **society of workloads**:

1. **Scheduling** — fairness and priority join pure efficiency
   (see [Inference/Production-Serving/13-multi-tenancy-fairness-priority](../Inference/Production-Serving/13-multi-tenancy-fairness-priority.md)).
2. **Caching** — the KV/prefix cache is *shared state*; tenant A can evict
   tenant B's hot prefix (see [08-kv-cache-economics](08-kv-cache-economics.md)).
3. **Admission** — one tenant's burst can destroy another's SLO unless
   controlled ([19](19-noisy-neighbor.md), [09-batching-and-economics](09-batching-and-economics.md)).
4. **Security** — isolation now spans identity, cache, logs, RAG, vector DBs
   ([23-tenant-security-isolation](23-tenant-security-isolation.md)).
5. **Economics** — cost is *allocated*, not just *incurred*: it must be
   attributable to a tenant to be governed ([14](14-showback-chargeback.md)).
6. **Governance** — which model, cloud, and pool each tenant may use becomes a
   policed decision ([27-policy-as-code](27-policy-as-code.md)).

## Related

[02-multi-tenancy-models](02-multi-tenancy-models.md) · [03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md) ·
[48-enterprise-multi-tenant-llm-platform](48-enterprise-multi-tenant-llm-platform.md) ·
[13-tenant-metering](13-tenant-metering.md)

## Key takeaways

1. A multi-tenant platform is a *society of workloads*, not one workload at scale.
2. The value chain runs GPU → model → tokens → tenant → quality/latency →
   cost → pricing → governance; you can't govern the tail without metering the head.
3. Choose the tenant boundary at the *accounting* unit, not the smallest unit.
4. Multi-tenancy changes every layer: caching, scheduling, admission, security,
   economics, and governance all become multi-party decisions.
