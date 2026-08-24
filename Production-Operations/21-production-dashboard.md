# 21 — Production Dashboard Design

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

A dashboard answers "is the system healthy, and if not, *where*?" at a glance.
For LLM platforms you need views per domain (service, GPU, model, queue, KV,
network, RAG, agent, cost) plus a **minimum dashboard** that captures the whole
serving loop in one screen.

## Dashboard views

| View | Answers | Key panels |
|---|---|---|
| **SERVICE** | is the API healthy? | requests/sec, error rate, latency percentiles, goodput |
| **GPU** | is the hardware healthy/saturated? | util, HBM, memory, power, temp, clocks, ECC ([10](10-gpu-reliability.md)) |
| **MODEL** | is the model serving OK? | TTFT/TPOT per model, refusal/quality signals ([24](24-quality-observability.md)) |
| **QUEUE** | is demand outpacing capacity? | queue depth, waiting time, admission/reject ([08](08-queueing-theory-for-llm-sre.md)) |
| **KV CACHE** | is KV exhausted? | KV util, hit rate, evictions, allocation failures ([12](12-kv-cache-reliability.md)) |
| **NETWORK** | is the fabric fine? | NCCL/bytes, packet loss, partition ([11](11-distributed-inference-failures.md)) |
| **RAG** | is retrieval healthy? | retrieval latency, miss rate, DB health ([35](35-rag-sre.md)) |
| **AGENT** | are agents looping/running-away? | steps, tool calls, budget use ([34](34-agent-sre.md)) |
| **COST** | are costs in control? | $/request, token spend ([33](33-cost-as-an-sre-signal.md)) |

## The minimum dashboard (`[I]`)

One screen for the serving loop, per pool/model, over a rolling window. Counts
`[E]`-measurable; the *set* is a recommendation, not a standard.

- Requests/sec
- Input tokens/sec
- Output tokens/sec
- TTFT (P50/P95/P99)
- TPOT (P50/P95/P99)
- Running requests
- Waiting requests
- KV utilization
- GPU utilization
- GPU memory
- GPU power
- Network traffic
- Errors (per class)
- Goodput

## Design rules (`[I]`)

1. **Percentiles over means** — show P50/P95/P99 (and P99.9 for tail); means hide
   TTFT blowups.
2. **Pair latency with queue/KV** — latency without a context signal is noise
   ([04](04-llm-golden-signals.md)).
3. **Read as a correlated set** — utilize → KV → errors → latency on one screen
   tells the story.
4. **Add SLO lines** — draw the SLO threshold on TTFT/error panels so "are we
   inside budget?" is instant ([02](02-sli-slo-sla-for-llms.md)).
5. **Keep it glanceable** — a dashboard that needs study is a report, not an ops tool.
6. **Per-request drill-through** from any panel to the trace
   ([23](23-llm-tracing.md)).

## Related

`04-llm-golden-signals.md` · `20-llm-observability-stack.md` ·
`22-alerting-strategy.md` · `Labs/07-build-prometheus-dashboard.md` ·
`GPU-Systems/GPU-Metrics.md`

## Key takeaways

1. Build per-domain dashboards (service, GPU, model, queue, KV, network, RAG, agent, cost).
2. The minimum dashboard captures the whole serving loop: requests, tokens,
   TTFT/TPOT, queue, KV, GPU, errors, goodput.
3. Use percentiles, SLO lines, and correlated readings — not means.
