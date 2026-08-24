# Inference Metrics — Glossary
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
The same system looks "fast" or "slow" depending on which clock you read. Each metric
answers a different question; match the metric to the workload.

## Definitions
- **TTFT (Time To First Token)** — request-in → first generated token out.
  *Dominates:* interactive UX, RAG, "does it feel fast". Prefill + queue.
- **ITL (Inter-Token Latency)** — gap between two consecutive generated tokens.
  *Dominates:* streaming UX, "steady-state feel". Decode.
- **TPOT (Time Per Output Token)** — (total time − TTFT) / output tokens. ≈ mean ITL.
- **tokens/sec** — client-side throughput; = 1/ITL for a single stream.
- **requests/sec** — system throughput; = completed requests / time.
- **total tokens/sec** — system output throughput; the "cost" metric (tokens per $).
- **queue time** — time waiting in the scheduler before admission. High queue = overload.
- **prefill latency** — time to process the prompt (≈ TTFT minus queue + first-token).
- **decode latency** — time to generate all output tokens.
- **P50 / P95 / P99** — 50th / 95th / 99th percentile. P99 is what SLOs are built on.
- **goodput** — *SLO-conforming* requests/sec (not raw throughput). The metric that
  reflects real capacity under latency limits. [F: used in DistServe, Orca, llm-d]

## Which metric matters for which workload
| Workload | Primary metric | Secondary |
|---|---|---|
| Interactive chat | **TTFT**, P95 ITL | P99 TTFT |
| Coding / agentic | **total task time**, P99 ITL | tokens/$ |
| Long-context QA | **TTFT** (prefill-bound) | P99 TTFT |
| RAG | TTFT + P95 ITL | retrieval p95 (out of scope) |
| Batch / offline | **total tokens/sec** | goodput, $/token |
| Streaming media (TTS) | **ITL** (steady) | P99 ITL |

## Common misreadings
- **Average vs percentile:** mean ITL can look fine while P99 is terrible (preemption,
  KV contention, long-prefill interference). Always report P50/P95/P99.
- **Throughput vs goodput:** you can maximize tokens/sec by admitting until the queue
  explodes — goodput collapses.
- **TTFT under load:** TTFT at B=1 ≠ TTFT at B=128 (queue + chunked-prefill
  interference). Always report concurrency.
- **tokens/sec vs tokens/sec/GB:** two GPUs with different HBM can both be "fast" by
  different economics; report $/token where relevant.

## Related
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` · `Inference/Inference-Optimization.md` ·
`../Evaluation-Engineering/Harness-Serving-Evaluation.md` (turning these metrics into SLO tests) ·
`Production-Serving/12-observability-and-slos.md` (wiring these metrics into the routing/scheduling control loops).

## Key Takeaways
Match metric to workload. Report **percentiles at a fixed concurrency**, not averages.
Goodput > throughput for SLO reasoning.
