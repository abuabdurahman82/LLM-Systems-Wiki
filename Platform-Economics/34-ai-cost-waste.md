# 34 — AI Cost Waste Detection

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Most of a shared platform's wasted money comes from a **small set of recurring
patterns** — idle GPUs, oversized models, fat `max_tokens`, bloated context,
bad batching, low cache hits, expensive cloud routing, retry/agent loops, and
unused reservations. Finding them is a matter of **knowing the pattern, its
detection signal, and its remediation** — then monitoring ([42-multi-tenant-observability](42-multi-tenant-observability.md))
and fixing. This is the operational heart of [33-ai-finops](33-ai-finops.md).

## Waste catalog

| Pattern | Detection signal | Economic impact | Remediation |
|---|---|---|---|
| **Idle GPU** | GPU util ≈ 0 for sustained windows | pays for nothing | scale down/downsize; schedule batch to fill ([05](05-gpu-utilization-economics.md)) |
| **Over-sized model** | smaller model meets quality bar | pays for big-model price/latency | right-size via evals ([12](12-quality-cost-latency-frontier.md), [10](10-model-economics.md)) |
| **Unused replicas** | replica counts >> demand | redundant fixed cost | autoscale replicas ([30](30-capacity-reservation.md)) |
| **Huge max_tokens** | requests truncated / output capped at max | decode + KV waste ([07](07-prefill-decode-economics.md)) | set realistic caps; hard-cap max_tokens |
| **Unnecessary context** | context far exceeds what's needed | prefill + KV super-linear ([38](38-long-context-economics.md)) | context budgets/compaction ([Context-Engineering/](../Context-Engineering/README.md)) |
| **Poor batching** | low concurrency, low throughput/GPU | underutilized GPU | raise batch/concurrency within SLO ([09](09-batching-and-economics.md)) |
| **Low cache hit rate** | cache hit % low on repeated prefixes | re-prefill waste | cache-friendly routing, stable prefixes ([08](08-kv-cache-economics.md)) |
| **Expensive cloud routing** | cloud used when local suffices | cloud premium | policy + budget-aware routing ([28](28-cloud-bursting-economics.md), [22](22-budget-aware-routing.md)) |
| **Duplicate embeddings** | same text re-embedded repeatedly | embedding cost | cache embeddings / dedupe ([37-rag-economics](37-rag-economics.md)) |
| **Repeated RAG retrieval** | same queries re-retrieved | retrieval + rerank cost | cache retrieval results ([37](37-rag-economics.md)) |
| **Retry loops** | high retry counts, backoff failures | multiplies cost | circuit-breakers, budgets ([Production-Operations/14-retries-timeouts-circuit-breakers](../Production-Operations/14-retries-timeouts-circuit-breakers.md)) |
| **Agent loops** | agents running unbounded | multiplicative cost ([35](35-agent-economics.md)) | step/token/time/cost budgets ([Production-Operations/34-agent-sre](../Production-Operations/34-agent-sre.md)) |
| **Unused reserved capacity** | reservations idle most of month | fixed cost for nothing | release / downsize reservations ([30](30-capacity-reservation.md)) |

## Making waste visible

Waste only gets fixed if it's seen. Wire the detection signals into
**FinOps/tenant dashboards** ([42](42-multi-tenant-observability.md)) with the
AI cost units from [33](33-ai-finops.md), and alert on the high-leverage ones
(runaway agents, idle GPU, truncation-at-max_tokens). Then it's a process, not a
postmortem.

## Related

[33-ai-finops](33-ai-finops.md) · [42-multi-tenant-observability](42-multi-tenant-observability.md) ·
[08-kv-cache-economics](08-kv-cache-economics.md) · [35-agent-economics](35-agent-economics.md) ·
[38-long-context-economics](38-long-context-economics.md)

## Key takeaways

1. Idle GPUs, oversized models, fat max_tokens, long context, low cache hits, and loops are the big waste patterns.
2. Each pattern has a measurable signal — monitor them.
3. Fix via right-sizing, budgets, caching, policy routing, and autoscaling.
4. Waste fuels the run-away patterns; detection is a control loop, not a report.
