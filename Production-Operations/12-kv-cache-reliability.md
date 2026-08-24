# 12 — KV Cache Reliability

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

The KV cache is the **scarce reliability resource** of an LLM platform: it is
finite, per-request, contention-prone, and when it runs out the engine must
evict, preempt, or reject — each of which is a user-visible failure mode
(latency/quality). Treat KV as first-class capacity, not an implementation detail.

## The KV cache as a reliability resource

Every in-flight request holds its **K/V tensors** in device memory, sized by
*context length × batch × heads*. Available blocks bound the number and length
of concurrent requests. Running out has no graceful "disk full" analog: the
engine must chose among reject / wait (TTFT ↑) / evict (quality ↓) / preempt
(latency ↑).

## Failure modes

| Mode | What it is | User-visible effect |
|---|---|---|
| **KV exhaustion** | no free KV blocks | reject, or TTFT spike (waiting), or OOM |
| **Fragmentation** | free memory split into unusable small blocks | effective capacity < total; PagedAttention mitigates `[F]`-concept (`KV-Cache/`) |
| **Eviction** | blocks reclaimed under pressure | quality loss (context truncated), re-compute |
| **Cache churn** | prefix cache constantly invalidated | low hit rate → prefill cost, TTFT ↑ |
| **Prefix-cache poisoning risk** | reused cached prefix yields stale/wrong continuation | correctness risk if cache invariants break |
| **Stale cache** | cached prefix used after the source changed | wrong grounding (ties to RAG freshness, [35](35-rag-sre.md)) |
| **Session-affinity failure** | request routed to replica without its cache | cache miss, TTFT ↑ ([16](16-routing-failure-modes.md)) |
| **Distributed KV transfer problems** | P/D handoff / remote KV fetch fails | disaggregated path errors, request failure |

## Operational indicators (`[I]`)

| Indicator | Definition / reading | Watch for |
|---|---|---|
| **KV utilization** | fraction of KV blocks in use | approaching 1 → eviction/reject risk |
| **Cache hit rate** | fraction of tokens served from prefix cache | falling → more prefill work, higher TTFT |
| **Evictions/sec** | blocks reclaimed per second | rising → quality/latency risk |
| **Allocation failures** | times no block could be granted | OOM / reject |
| **Waiting requests** | queued due to KV pressure | TTFT blowup ([08](08-queueing-theory-for-llm-sre.md)) |

## Operational practice (`[I]`)

1. **Monitor KV utilization with a headroom buffer** — trigger scaling/admission
   *before* it hits 100% (autoscaling on KV, [17](17-llm-autoscaling-reliability.md)).
2. **Right-size concurrency** to KV capacity — concurrency × longest context
   that must fit ([07](07-llm-capacity-planning.md)).
3. **Keep cache affinity** in routing so requests reusing prefixes land on the
   replica holding them ([16](16-routing-failure-modes.md));
   `Inference/Production-Serving/08-cache-aware-routing.md`.
4. **Validate cache invariants** — a broken prefix-cache assumption is a silent
   correctness risk; add a round-trip check when you change cache/eviction policy.
5. **Plan for P/D handoff** reliability if disaggregated
   (`Inference/Production-Serving/09-pd-disaggregated-routing.md`).

## Connect to existing Wiki pages

- KV mechanics, PagedAttention, eviction, compression: `KV-Cache/`
- Continuous batching & scheduling interaction: `Inference/Continuous-Batching.md`
- Cache-aware routing: `Inference/Production-Serving/08-cache-aware-routing.md`
- P/D disaggregation & KV transfer: `Inference/Prefill-Decode-Disaggregation.md`

## Related

`07-llm-capacity-planning.md` · `13-overload-protection.md` ·
`16-routing-failure-modes.md` · `17-llm-autoscaling-reliability.md` ·
`KV-Cache/README.md`

## Key takeaways

1. KV cache is a finite, contention-prone reliability resource.
2. Exhaustion forces reject/evict/preempt — all user-visible.
3. Watch KV utilization, hit rate, eviction rate, allocation failures, waiting requests.
4. Right-size concurrency, keep cache affinity, validate cache invariants.
