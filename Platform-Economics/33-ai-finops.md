# 33 — FinOps for AI

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

FinOps (from the FinOps Foundation's **Inform → Optimize → Operate** lifecycle)
is the discipline of *managing cloud/AI spend as an engineering practice*. For
LLM platforms it adds **AI-specific cost dimensions** — tokens, GPU-hours, KV
utilization, model replicas, context length, cloud API spend, reasoning tokens,
and unused reservations — on top of generic FinOps. The goal: **visibility,
allocation, optimization, governance, and forecasting** of an expensive, highly
variable resource.

## The five FinOps capabilities, mapped to AI

| Capability | What it means for an LLM platform |
|---|---|
| **Visibility** | unit cost per token/request/GPU-hour; dashboards ([42-multi-tenant-observability](42-multi-tenant-observability.md)) |
| **Allocation** | attribute cost to tenant/model/pool ([13-tenant-metering](13-tenant-metering.md), [14-showback-chargeback](14-showback-chargeback.md)) |
| **Optimization** | right-size models, improve utilization/cache, cut waste ([34-ai-cost-waste](34-ai-cost-waste.md), [05](05-gpu-utilization-economics.md)) |
| **Governance** | quotas, budgets, policies ([20-quota-engineering](20-quota-engineering.md), [27-policy-as-code](27-policy-as-code.md)) |
| **Forecasting** | percentiled demand + cost projection ([32-demand-forecasting](32-demand-forecasting.md)) |

## AI-specific cost dimensions

| Dimension | What to track | Why it varies |
|---|---|---|
| **Tokens** | in / out / cached / reasoning ([06](06-token-economics.md)) | shape & model drive price |
| **GPU-hours** | actually consumed ([03](03-llm-inference-unit-economics.md)) | utilization |
| **KV utilization** | cache usage vs capacity ([08](08-kv-cache-economics.md)) | memory economics + waste |
| **Model replicas** | how many of each deployed ([25-model-governance](25-model-governance.md)) | the biggest structural cost |
| **Context length** | avg + P99 prompt length ([38-long-context-economics](38-long-context-economics.md)) | long context is super-linear |
| **Cloud API spend** | per provider/model ([28](28-cloud-bursting-economics.md)) | bursting & API usage |
| **Reasoning tokens** | hidden thinking tokens ([35](35-agent-economics.md)) | can dominate agent cost |
| **Unused reservations** | reserved-but-idle capacity ([30](30-capacity-reservation.md)) | the classic FinOps waste |

## FinOps practices specific to AI

- **Right-size the model**, not just the instance: a smaller model that meets the
  quality bar cuts both GPU and cost ([12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)).
- **Reward caching** in price/behavior to cut prefill ([08](08-kv-cache-economics.md)).
- **Reconcile capacity to demand** regularly: scale replicas, release unused
  reservations ([31](31-capacity-planning.md), [30](30-capacity-reservation.md)).
- **Tag everything** for allocation ([13](13-tenant-metering.md)).
- **Chargeback feeds FinOps**: when tenants see their cost, they optimize
  ([14](14-showback-chargeback.md)).

## Related

[14-showback-chargeback](14-showback-chargeback.md) ·
[34-ai-cost-waste](34-ai-cost-waste.md) · [42-multi-tenant-observability](42-multi-tenant-observability.md) ·
[13-tenant-metering](13-tenant-metering.md) · [31-capacity-planning](31-capacity-planning.md)

## Key takeaways

1. FinOps = Inform → Optimize → Operate; visibility first.
2. Track AI-specific units: tokens, GPU-hours, KV, replicas, context, API, reasoning, reservations.
3. Optimize the model before the hardware.
4. Metering + allocation is the foundation that makes every other capability possible.
