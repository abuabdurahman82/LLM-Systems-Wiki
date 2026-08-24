# 55 — Governance Anti-Patterns

`LAST_UPDATED: 2026-08-24` · Status: reference page

## 30-Second Explanation

Most shared-LLM-platform failures aren't novel — they're **recognizable
recurring anti-patterns**, most of which amount to *"nobody metered, nobody
owned, nobody capped."* This catalog names them, explains **why they fail**, the
**symptoms**, the **business impact**, and the **technical remediation**. If your
platform has three or more of these, you have a governance debt problem, not a
series of one-off incidents ([40-llm-platform-governance-model](40-llm-platform-governance-model.md)).

## The catalog

| Anti-pattern | Why it fails | Symptoms | Business impact | Remediation |
|---|---|---|---|---|
| **Unlimited free access** | no scarcity signal; tragedy of the commons | runaway spend, hoarded GPUs, idle fleet | budget blowout ([34](34-ai-cost-waste.md)) | meter + showback ([13](13-tenant-metering.md), [14](14-showback-chargeback.md)) |
| **No tenant IDs** | can't attribute → can't allocate or secure | phantom costs, cross-tenant leaks | no accountability, audit fails | identity + resolver ([01](01-multi-tenant-llm-platform-overview.md)) |
| **No quotas** | one team consumes all | noisy-neighbor latency ([19](19-noisy-neighbor.md)) | SLO breaches, trust loss | quota engine ([20](20-quota-engineering.md)) |
| **No budgets** | cost unbounded | surprise overruns | CFO alarm, unfunded spend | budgets + budget routing ([22](22-budget-aware-routing.md)) |
| **One model for everything** | pays big-model price on trivial work | over-spend, slow trivial requests | high $/token | model routing ([11](11-economic-model-routing.md)) |
| **No data classification** | sensitive data to wrong model/cloud | policy breach, data leak ([24](24-data-governance.md)) | legal/regulatory exposure | classify-then-route ([24](24-data-governance.md)) |
| **No model approval** | insecure/unauthorized models serve prod | malicious/broken model | incident, liability | model lifecycle ([25](25-model-governance.md)) |
| **No cloud policy** | data exfil to arbitrary cloud | residency breach | compliance failure | cloud gating ([28](28-cloud-bursting-economics.md)) |
| **No SLO definitions** | no promise, no measurement | vague "slow" complaints | no recourse, no pricing ([17](17-slo-economics.md)) | SLO tiers ([16](16-llm-service-tiers.md)) |
| **No cost visibility** | nobody sees spend | silent waste | budget blown ([34](34-ai-cost-waste.md)) | FinOps dashboards ([42](42-multi-tenant-observability.md)) |
| **No chargeback ownership** | cost unowned → unmanaged | everyone blames everyone | can't sustain platform | RACI ownership ([40](40-llm-platform-governance-model.md)) |
| **No audit logs** | no accountability | cannot investigate | compliance/forensics fail | audit logging ([42](42-multi-tenant-observability.md)) |
| **Shared credentials** | no attribution / accountability | can't meter, can't secure ([23](23-tenant-security-isolation.md)) | breach | per-tenant keys ([26](26-model-access-control.md)) |
| **Unbounded agents** | a runaway agent burns a month of budget | token/cost spikes | single run bankrupts budget ([35](35-agent-economics.md)) | step/time/cost budgets ([Production-Operations/34-agent-sre](../Production-Operations/34-agent-sre.md)) |
| **Unlimited max_tokens** | long outputs waste decode + KV | truncation at cap, cost | $/req inflation ([07](07-prefill-decode-economics.md)) | hard output caps ([34](34-ai-cost-waste.md)) |
| **Unlimited context** | super-linear prefill/KV | long-context cost, cache eviction ([38](38-long-context-economics.md)) | $/req inflation | context budgets ([20](20-quota-engineering.md)) |
| **No retirement process** | zombie models on expensive hardware | stranded cost, stale quality | wasteful fleet ([25](25-model-governance.md)) | scheduled retirement ([25](25-model-governance.md)) |

## How to use this

Treat it as a **triage checklist**: if a failure occurs, find the anti-pattern it
maps to, apply the remediation, and add the **control/observability** that makes
it visible going forward ([42-multi-tenant-observability](42-multi-tenant-observability.md)).
Themes cluster into: **metering & attribution, capacity & fairness, security &
data, and organizational ownership** — which mirrors the section's structure.

## Related

[40-llm-platform-governance-model](40-llm-platform-governance-model.md) ·
[51-multi-tenant-llm-platform-80-20](51-multi-tenant-llm-platform-80-20.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md) · [14-showback-chargeback](14-showback-chargeback.md)

## Key takeaways

1. Most failures are recognizable anti-patterns, mostly "no meter / no owner / no cap".
2. Each has a why, symptoms, impact, and a concrete remediation.
3. Use as a triage checklist; keep the themes: meter, allocate, secure, own.
