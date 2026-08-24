# 04 — The Four Golden Signals for LLMs

`LAST_UPDATED: 2026-08-23` · Status: foundational page

## 30-Second Explanation

Google's SRE **four golden signals** — *latency, traffic, errors, saturation* —
are the minimal set that tells you whether a service is healthy. For LLM systems
each signal must be **extended** to the inference-specific quantities below. If
you instrument only the classic set, you will be blind to the failures that
matter most (TTFT blowups, KV exhaustion, quality stalls).

## Classic SRE golden signals

1. **Latency** — time to serve a request.
2. **Traffic** — demand on the system.
3. **Errors** — failed requests.
4. **Saturation** — how "full" the service is.

`[F]` Google SRE Book ("The Four Golden Signals"). Extended here for LLMs `[I]`.

## LATENCY (LLM-extended)

Where a REST service has one latency, an LLM stream has several:

- **TTFT** — time to first token (queue + prefill). Feels like dead air.
- **TPOT** — time per output token (decode). Sets perceived typing speed.
- **ITL** — inter-token latency (time between consecutive tokens ≈ TPOT).
- **E2E latency** — full request wall time (incl. tools/RAG/agents).
- **Tool latency** — time for a tool/function call to return.
- **Retrieval latency** — time for a RAG lookup.

Track each as P50/P95/P99 (see [05](05-production-latency-debugging.md) and
[21](21-production-dashboard.md)).

## TRAFFIC (LLM-extended)

- **requests/sec** (arrival rate)
- **input tokens/sec** (prefill demand — drives compute)
- **output tokens/sec** (decode demand — drives the decode loop)
- **concurrent requests** (in-flight; drives KV and batch pressure)
- **prompt length distribution** (long tails matter more than the mean:
  1×100-token + 1×10k-token request pair is not homogeneous)

See [07](07-llm-capacity-planning.md) for why requests/sec alone is insufficient.

## ERRORS (LLM-extended)

- **HTTP failures** (4xx/5xx, timeouts)
- **model errors** (inference engine returned an error)
- **GPU OOM**
- **tool failures** (tool call threw / hung)
- **retrieval failures** (vector DB miss/outage)
- **invalid structured output** (schema/json parse failures)
- **timeouts** (gateway / model / tool / agent-step)

Plus the *quality-tier* errors that have no HTTP status: hallucination, refusal
regression, incorrect reasoning ([24](24-quality-observability.md)).

## SATURATION (LLM-extended)

The signal that is most LLM-specific:

- **GPU utilization** (SM busy %) — *not* the whole story
- **HBM utilization** (memory bandwidth) — decode is bandwidth-bound
- **KV-cache utilization** — the scarce reliability resource ([12](12-kv-cache-reliability.md))
- **queue depth** — often more actionable than GPU% ([08](08-queueing-theory-for-llm-sre.md))
- **network** — bytes/s, NCCL stalls ([11](11-distributed-inference-failures.md))
- **CPU** — tokenization, scheduling, Python overhead
- **memory** — host RAM
- **storage** — checkpoint/index IO
- **batch occupancy** — how full the scheduler's running batch is

## How to use the four signals together

Signals are read as a **correlated set**, not individually. Examples:

- *Low GPU util + high latency* → request starvation / queue/jitter problem,
  not a GPU compute problem.
- *High GPU util + high TTFT* → prefill congestion or queueing; decode may be fine.
- *High KV util + rising errors* → capacity/KV exhaustion, likely OOMs and evictions.
- *High TPOT + high HBM %* → decode bandwidth saturation.

Reading signals as pairs is what separates a healthy-system diagnosis from noise.
This is the foundation for dashboards ([21](21-production-dashboard.md)) and
alerting ([22](22-alerting-strategy.md)).

## Related

`03-goodput-vs-throughput.md` · `05-production-latency-debugging.md` ·
`08-queueing-theory-for-llm-sre.md` · `12-kv-cache-reliability.md` ·
`21-production-dashboard.md` · `22-alerting-strategy.md` ·
`Inference/Production-Serving/07-scheduling-inside-the-engine.md`

## Key takeaways

1. Golden signals: latency, traffic, errors, saturation.
2. LLM latency is multi-headed (TTFT/TPOT/E2E/tool/retrieval).
3. LLM traffic is tokens and concurrency, not just requests.
4. Saturation for LLMs centers on KV cache and queue depth, not just GPU% —
   and the four signals are read as a correlated set.
