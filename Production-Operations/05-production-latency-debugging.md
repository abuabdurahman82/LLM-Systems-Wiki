# 05 — Production Latency Debugging for LLMs

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Total user-visible latency is a **sum** of contributions across the request
path. Debugging means breaking the sum into parts (with tracing + histograms),
identifying which term dominates, and attacking that one — not guessing.

## The latency budget equation

```
T_total =
    T_gateway
  + T_routing
  + T_queue
  + T_prefill
  + T_decode
  + T_tools
  + T_retrieval
  + T_network
```

Each term has a different owner and different levers. `[I]` decomposition.

| Term | What it is | Common cause of blowup | Lever |
|---|---|---|---|
| `T_gateway` | auth, quotas, proxy | overloaded gateway, TLS, auth | scale gateway, cache auth |
| `T_routing` | deciding which replica | slow router, stale telemetry, herding | router perf, cache-aware routing |
| `T_queue` | waiting for admission/batch | overload, unbounded queue | admission control, autoscaling |
| `T_prefill` | processing the prompt | long prompts, compute-bound | chunked prefill, prefix cache, P/D split |
| `T_decode` | per-token generation × length | memory-bandwidth bound, long output | batching, quantization, decode engine |
| `T_tools` | function/tool calls | hung tool, slow upstream | timeouts, retries, parallel tool calls |
| `T_retrieval` | RAG lookup | slow/overloaded vector DB | index, caching, DB scaling |
| `T_network` | transport | congestion, distance, slow client | egress, connection pooling |

## TTFT vs TPOT vs E2E

- **TTFT** (time to first token) ≈ `T_queue + T_prefill (+ T_routing + T_gateway)`.
- **TPOT** (time per output token) ≈ average `T_decode` (and is why
  *time-to-completion ≈ TTFT + TPOT × output_tokens*).
- **E2E** (total request) = the full sum above, including tools/RAG/agents.

TTFT and TPOT are governed by **different physics**: TTFT is *compute/queue* —
it grows with prompt length and prefill load; TPOT is *memory-bandwidth* — it
grows with batch size and decode contention. Optimizing one often does not fix
the other (see `Inference/Inference-Metrics.md`, `GPU-Systems/Bandwidth-vs-Compute.md`).

## Debugging flowchart — High TTFT

```
High TTFT
   ↓
Is the request even admitted? ──no──► gateway/routing issue (T_gateway/T_routing)
   │ yes
Queue depth high? ──yes──► overload / admission control / autoscaling (T_queue)
   │ no
Prompt unusually long? ──yes──► prefill cost; chunked prefill / prefix cache (T_prefill)
   │ no
Batching hurting prefill? ──yes──► chunked prefill; P/D disaggregation
   │ no
Prefix cache reuse low? ──yes──► cache affinity / warm prefixes (cache hit rate)
   │ no
GPU saturated / throttling? ──yes──► prefill congestion / clocks / capacity
   │ no
Distributed sync slow? ──yes──► NCCL / straggler (see 11)
   ▼
Measure T_prefill directly and profile the prefill kernel
```

`[I]` flowchart; every branch is an observable SLI from [04](04-llm-golden-signals.md).

## Debugging flowchart — High TPOT

```
High TPOT
   ↓
Decode token-rate low across batch? ──check decode throughput
   ↓
Memory bandwidth saturated? ──yes──► decode is bandwidth-bound; smaller batch / fewer params / quantization
   │ no
Batch pressure (too many concurrent decodes)? ──yes──► reduce concurrency / admission
   │ no
KV pressure / fragmentation / eviction? ──yes──► KV reliability (see 12)
   │ no
GPU clocks throttled (power/thermal)? ──yes──► check nvidia-smi clocks, power caps
   │ no
Distributed communication stalls (NCCL)? ──yes──► see 11
   │ no
Long context making each decode step expensive
   ▼
Profile decode kernel / attention (see GPU-Systems/Profiling.md)
```

## Operational principles

1. **Instrument every term** of the budget as a histogram with
   `trace_id`/`request_id` so you can attribute a slow request ([23](23-llm-tracing.md)).
2. **Never guess the dominant term.** A 3-second "slow answer" is most often a
   long TTFT (queue+prefill) or a long output (TPOT × length) — confirm with
   per-term metrics.
3. **Separate the SLOs.** TTFT and TPOT should have independent budgets and
   alerts, because they have independent causes.

## Related

`04-llm-golden-signals.md` · `08-queueing-theory-for-llm-sre.md` ·
`11-distributed-inference-failures.md` · `12-kv-cache-reliability.md` ·
`23-llm-tracing.md` · `GPU-Systems/Profiling.md` · `Inference/Inference-Metrics.md`

## Key takeaways

1. T_total is a sum; instrument each term separately.
2. TTFT (queue+prefill, compute-bound) and TPOT (decode, bandwidth-bound) have
   different physics and different levers.
3. Debug from a flowchart against measured SLIs — never guess the dominant term.
4. Attribute slow requests with distributed tracing.
