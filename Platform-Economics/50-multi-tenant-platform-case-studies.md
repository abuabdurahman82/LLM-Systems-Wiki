# 50 — Multi-Tenant Platform Case Studies

`LAST_UPDATED: 2026-08-24` · Status: reference page · `[S]` = **synthetic**
case studies — **illustrative archetypes, NOT descriptions of any specific
organization.** Names and figures are invented to teach the patterns.

## CASE A — University AI platform

- **Shape:** thousands of students, limited budget, shared GPUs.
- **Tenancy:** department/program as tenant; students under each.
- **Economics:** budget-first; heavy showback, light chargeback
  ([14](14-showback-chargeback.md)); soft multi-tenancy for cost
  ([02](02-multi-tenancy-models.md)).
- **Controls:** token + concurrency quotas per program ([20](20-quota-engineering.md)),
  batch to fill idle GPUs ([05](05-gpu-utilization-economics.md)),
  small models by default with escalation ([11](11-economic-model-routing.md)).
- **Lesson:** with a hard budget and bursty student load, **metering + quota +
  small-model routing** keeps a small fleet sustainable ([22](22-budget-aware-routing.md)).

## CASE B — Enterprise internal LLM platform

- **Shape:** multiple business units, varied data classifications, chargeback.
- **Tenancy:** business unit as tenant = accounting boundary ([01](01-multi-tenant-llm-platform-overview.md)).
- **Economics:** mixed local + approved cloud by data class
  ([24-data-governance](24-data-governance.md)); showback → soft → hard
  chargeback over time ([14](14-showback-chargeback.md)) .
- **Controls:** service tiers per BU ([16-llm-service-tiers](16-llm-service-tiers.md)),
  budget-aware routing ([22](22-budget-aware-routing.md)), model governance
  ([25-model-governance](25-model-governance.md)).
- **Lesson:** **classify data first, then route**; chargeback only after the
  allocation method is trusted.

## CASE C — SaaS provider (external customers)

- **Shape:** external customers as tenants on shared infra; token billing.
- **Tenancy:** customer = tenant; **hard isolation between customers**
  ([23-tenant-security-isolation](23-tenant-security-isolation.md)).
- **Economics:** usage-based token billing with per-customer metering
  ([13-tenant-metering](13-tenant-metering.md), [15-llm-platform-pricing-models](15-llm-platform-pricing-models.md));
  per-customer RAG/vector isolation ([37-rag-economics](37-rag-economics.md)).
- **Controls:** strict per-customer quotas, cache namespaces, data isolation.
- **Lesson:** the **noisy-neighbor problem is a revenue problem** when customers
  share a pool — isolation and quotas are commercially mandatory
  ([19-noisy-neighbor](19-noisy-neighbor.md)).

## CASE D — Government / private-cloud environment

- **Shape:** high security, data residency, no public cloud for sensitive.
- **Tenancy:** agency/program as tenant; **hard isolation + residency**.
- **Economics:** on-prem/private cloud only for sensitive
  ([04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md));
  cost of compliance is a real budget line ([24-data-governance](24-data-governance.md)).
- **Controls:** "no cloud for confidential" policy ([24](24-data-governance.md)),
  policy-as-code + audit ([27-policy-as-code](27-policy-as-code.md)),
  dedicated pools for regulated tenants ([02](02-multi-tenancy-models.md)).
- **Lesson:** **residency hard-constrains routing**; governance is non-negotiable
  and economics must absorb the isolation premium.

## CASE E — AI research platform

- **Shape:** large bursty training/inference jobs, many researchers.
- **Tenancy:** lab/team as tenant; jobs as bursty consumers.
- **Economics:** **spiky demand** — reserve baseline + burst/spot overflow
  ([30-capacity-reservation](30-capacity-reservation.md),
  [28-cloud-bursting-economics](28-cloud-bursting-economics.md));
  capacity as a shared scheduler (Kueue/Volcano, [47-kubernetes-multi-tenancy](47-kubernetes-multi-tenancy.md)).
- **Controls:** priority classes for training vs inference, quota'd batch queues.
- **Lesson:** bursty science workloads need **elastic capacity + fair batch
  scheduling**, not over-reservation ([32-demand-forecasting](32-demand-forecasting.md)).

## Cross-cutting lessons

1. **Tenant boundary = the accounting/isolation unit** that fits the org.
2. **Meter before you manage** in every case ([13](13-tenant-metering.md)).
3. **Data class drives routing** in B and D; **isolation drives revenue** in C.
4. **Budget-first (A), chargeback (B), token-billing (C), residency (D),
   elasticity (E)** — pick the governance center of gravity to match the mission.

## Related

[01-multi-tenant-llm-platform-overview](01-multi-tenant-llm-platform-overview.md) ·
[02-multi-tenancy-models](02-multi-tenancy-models.md) ·
[14-showback-chargeback](14-showback-chargeback.md) ·
[53-platform-governance-decision-framework](53-platform-governance-decision-framework.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md)

## Key takeaways

1. These are synthetic archetypes, not real orgs.
2. Each domain picks a governance center of gravity: budget, trust, revenue, residency, or elasticity.
3. Metering, quotas, isolation, and data-class routing appear in all five.
4. Use them as design seeds for your own platform, not as templates to copy.
