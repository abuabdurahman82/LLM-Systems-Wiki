# 20 — LLM Observability Stack

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Observability is the **control loop** of the reliability stack — without it you
cannot answer "which layer is failing" ([01](01-llm-reliability-overview.md)).
The standard stack: engines emit **metrics/logs/traces** → **OpenTelemetry** →
**Prometheus** → **Grafana**, with **DCGM** providing GPU telemetry.

## The architecture

```
Inference Engine (vLLM / SGLang / TRT-LLM)
    ↓  metrics / logs / traces
OpenTelemetry
    ↓
Prometheus (metrics storage + alerting rules)
    ↓
Grafana (dashboards)
```

MW side streams: **DCGM Exporter** → Prometheus for GPU hardware metrics
([10](10-gpu-reliability.md)); **logs** → Loki/Elastic; **traces** → Jaeger/Tempo
([23](23-llm-tracing.md)).

## The four data types

| Type | Question | LLM specifics |
|---|---|---|
| **Metrics** | how many / how fast / how full | TTFT/TPOT histograms, token rates, KV util, queue depth, goodput |
| **Logs** | what happened | request outcomes, errors, warnings, provenance (`model_id`, `fallback_reason`) |
| **Traces** | what happened *across* the path | gateway→router→LLM→RAG→tool→agent ([23](23-llm-tracing.md)) |
| **Profiles** | where time/memory went | GPU kernel profiles, CPU profiling ([GPU-Systems/Profiling.md]) |

## Sources of metrics

| Source | What it provides | Notes / provenance |
|---|---|---|
| **vLLM metrics** | server-level and per-request metrics via Prometheus endpoint | engine metrics endpoint (`[F]` vLLM docs for exact metric names) |
| **SGLang metrics** | latency/throughput metrics via its monitoring endpoint | `[F]` SGLang docs where documented |
| **TensorRT-LLM observability** | Triton backend metrics, per-stage timing | `[F]` TRT-LLM/Triton docs where documented; mark unverified gaps `UNVERIFIED` |
| **DCGM (Exporter)** | GPU hardware: temp, clocks, power, memory, ECC, NVLink | `[F]` NVIDIA; exporter Prometheus on :9400 |
| **OpenTelemetry** | unified instrumentation/export of metrics+traces+logs | `[F]` OTel project |
| **Prometheus / Grafana** | storage + dashboards + alerting | `[F]` project docs |

> **Tagging note:** exact metric names differ per version and engine; verify
> against the installed version's docs before wiring alerts. Where a metric is
> not confirmed for a specific engine it is `UNVERIFIED`.

## Minimum set to export per replica

- TTFT, TPOT, E2E (histograms: P50/P95/P99) — [05](05-production-latency-debugging.md)
- requests/sec, input tokens/sec, output tokens/sec, concurrent requests — [04](04-llm-golden-signals.md)
- queue depth, KV utilization, cache hit rate, evictions/sec — [12](12-kv-cache-reliability.md)
- errors (HTTP/model/OOM/tool/retrieval/timeout) — [04](04-llm-golden-signals.md)
- goodput — [03](03-goodput-vs-throughput.md)
- GPU: utilization, HBM, memory, power, temp, clocks, ECC — [10](10-gpu-reliability.md)

## Related

`04-llm-golden-signals.md` · `10-gpu-reliability.md` · `21-production-dashboard.md` ·
`23-llm-tracing.md` · `Labs/07-build-prometheus-dashboard.md` ·
`Labs/08-monitor-gpu-with-dcgm.md` · `GPU-Systems/GPU-Metrics.md`

## Key takeaways

1. Observability is a control loop, not a dashboard — signals must drive alerting,
   routing, scaling.
2. Standard: engine → OTel → Prometheus → Grafana, + DCGM for GPU.
3. Four data types all matter: metrics, logs, traces, profiles.
4. Export the minimum LLM set (TTFT/TPOT/KV/queue/goodput/GPU) and verify metric
   names per engine version.
