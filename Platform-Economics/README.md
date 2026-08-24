# Multi-Tenant LLM Platform — Economics & Governance

`LAST_UPDATED: 2026-08-24` · Status: core section · Home of the
**Multi-Tenant LLM Platform Economics & Governance** handbook.

> **How do you turn expensive shared AI infrastructure into a fair, secure,
> measurable, economically sustainable platform?**

## 30-Second Explanation

A shared LLM platform serves many **users, teams, business units, tenants,
applications, models, GPU pools, environments, regions, cost centers, trust
levels, and service tiers** at once. The central engineering problem is that
every one of those consumers adds a *multi-party* decision: scheduling, routing,
caching, admission, metering, and economics all have cross-tenant consequences.
This section is a **zero-to-hero + 80/20 handbook** connecting **LLM systems
engineering, GPU infrastructure, inference economics, multi-tenancy, FinOps,
capacity management, SLO engineering, security, governance, and policy** into
one mental model — running from **GPU capacity → model → tokens → tenant →
quality/latency → cost → pricing → governance**, closed back into optimization.

## The value chain (the core mental model)

```
GPU CAPACITY → MODEL CAPACITY → TOKENS/REQUESTS → TENANT CONSUMPTION →
QUALITY + LATENCY + RELIABILITY → COST → PRICING/CHARGEBACK → GOVERNANCE
```

The platform is **not** just *GPU cluster + vLLM endpoint*. It is
`Compute + Memory + Models + Schedulers + Routing + Policies + Identity +
Quotas + SLOs + Metering + Economics + Governance`.

## How this section is organized (57 pages + 15 labs + 2 calculators)

- **Foundations (01–05):** what a multi-tenant platform is, tenancy models,
  inference unit economics, CAPEX vs OPEX, utilization economics.
- **Inference economics (06–09):** token economics, prefill vs decode, KV-cache
  economics, batching economics.
- **Model economics (10–12):** model cost, economic routing, the
  quality/cost/latency frontier.
- **Metering, pricing, tiers (13–17):** tenant metering, showback/chargeback,
  pricing models, service tiers, SLO economics.
- **Fairness & control (18–22):** fairness, noisy neighbor, quotas, admission
  control, budget-aware routing.
- **Security & governance (23–27):** tenant isolation, data governance, model
  governance, model access control, policy-as-code.
- **Capacity & FinOps (28–34):** cloud bursting, local-vs-API, reservation,
  capacity planning, forecasting, FinOps, waste detection.
- **Workload economics (35–39):** agents, evaluators, RAG, long context, multimodal.
- **Organization & observability (40–45):** governance model, exceptions,
  observability, goodput, energy, failure cost.
- **Architecture & tools (46–49):** GPUaaS pricing, Kubernetes tenancy, reference
  architecture, economic simulator.
- **Synthesis (50–57):** case studies, 80/20, zero-to-hero, decision framework,
  formulas, anti-patterns, research questions, big picture.

## Entry points

- **Fast:** [51-multi-tenant-llm-platform-80-20](51-multi-tenant-llm-platform-80-20.md) (the 15 levers)
- **Deep:** [52-multi-tenant-platform-zero-to-hero](52-multi-tenant-platform-zero-to-hero.md) (levels 0–10)
- **Numbers:** [54-economics-formulas](54-economics-formulas.md) + [49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md)
- **One picture:** [57-economics-governance-big-picture](57-economics-governance-big-picture.md)
- **Hands-on:** [Labs/README](Labs/README.md) (15 labs)

## Calibrating the numbers

Every cost figure in this section is **ILLUSTRATIVE** and **dated** (price
snapshot **2026-08**, USD), computed by
[scripts/economic_foundation.py](scripts/economic_foundation.py) from declared
assumptions — never mental arithmetic. Signposts:

- On-prem H100 fully-loaded ≈ **$1.49/GPU-hr @100% util**, **$2.13 @70%**, **$7.45 @20%**.
- Cloud H100 on-demand (2026-07/08, US): AWS **$6.88**, Azure **$6.98**, GCP **$11.06**, neocloud ~**$3**.
- API per 1M (2026): GPT-4.1 **$2/$8**, GPT-4o-mini **$0.15/$0.60**.

**Re-verify any number against your provider and your own measured throughput
before relying on it.** Provenance tags follow the whole Wiki: `[F]` primary
source, `[E]` measured, `[I]` author inference, `[A]` assumption, `UNVERIFIED`.

## Relationship to other sections

| Topic | Lives in |
|---|---|
| Routing & scheduling mechanics | `Inference/Production-Serving/` (esp. 04 queueing, 13 multi-tenancy) |
| Reliability & SRE (incl. cost signal) | `Production-Operations/` (esp. 03 goodput, 08 queueing, 33 cost, 34 agent SRE) |
| KV-cache mechanics | `KV-Cache/`, `Inference/` |
| GPU systems & engines | `GPU-Systems/`, `Serving-Engines/` |
| Evaluation | `Evaluation-Engineering/` |
| Kubernetes for LLMs | `Production-Operations/18-kubernetes-for-llm-sre.md` |
| Agents / context / RAG | `Agents/`, `Context-Engineering/`, `RAG/` |

## Provenance & authorship

Drafted by the **DeepSeek V4 Flash** agent (main model) on 2026-08-24 against
existing Wiki conventions. Economic numbers machine-computed and audited. An
independent evaluator review was run and adjudicated — see
[the review record](57-economics-governance-big-picture.md) and the section of
`CHANGELOG.md` for 2026-08-24.

## Key takeaways

1. A shared LLM platform is a *society of workloads* — every layer becomes a multi-party decision.
2. **Utilization, SLO headroom, and token shape** dominate unit economics.
3. **Meter before you govern; showback before chargeback; policy, not prose.**
4. The goal: **right model → right tenant → right hardware → right priority → right cost → right policy**, measured as **cost per good SLO-compliant outcome**.
