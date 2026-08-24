# 38 — Production Reliability Reference Architecture

`LAST_UPDATED: 2026-08-23` · Status: synthesis page

## 30-Second Explanation

Everything in this section composes into one **reference architecture**: a
gateway → rate limiting → admission control → router → engine/GPU pools, wrapped
in observability, SLOs, and alerting, with RAG/tools/agents/eval/cost as
first-class subsystems. Mindful that only the portions actually exercised here
are `[E]`; the rest is a `[I]` design synthesis of validated mechanisms.

## The architecture

```
                    USERS
                      │
                API GATEWAY          (auth, REST/stream, model-name mapping)
                      │
               RATE LIMITING          (per-tenant RPM/TPM quotas)
                      │
              ADMISSION CONTROL       (queue/reject/degrade — 13)
                      │
                 LLM ROUTER           (eligibility→health→work→cache→SLO→placement — 16)
                  /       \
                 /         \
            MODEL POOL   FALLBACK      (replica/model/provider — 15)
               │
         ┌─────┼─────┐
         ▼     ▼     ▼
       vLLM  SGLang  TRT-LLM          (engine/GPU pools — 20)
         │
       GPU POOL                        (DCGM telemetry — 10)
         │
   DCGM / Metrics / Logs               (OTel — 20)
         │
      OpenTelemetry
         │
   Prometheus / Grafana                (dashboards 21, alerting 22)
         │
    SLO / Alerting                     (error budget 06, burn-rate 22)
```

## Subsystems

| Subsystem | Wired how | Pages |
|---|---|---|
| **RAG** | router/eval aware; retrieval SLO | [35](35-rag-sre.md) |
| **Tools** | agent/harness timeouts, circuit breakers | [34](34-agent-sre.md), [14](14-retries-timeouts-circuit-breakers.md) |
| **Agents** | harness budgets + tracing | [34](34-agent-sre.md), [23](23-llm-tracing.md) |
| **Evaluation** | release gate + quality observability | [24](24-quality-observability.md), [28](28-llm-regression-testing.md) |
| **Cost monitoring** | cost SLIs + fallback/agent burn guards | [33](33-cost-as-an-sre-signal.md) |

## Key design properties (`[I]`)

1. **Protection at the edge** — rate limiting + admission control before any GPU
   work, so overload is rejected cheaply, not absorbed expensively ([13](13-overload-protection.md)).
2. **Router is the control point** — it decides placement and thus holds the
   health/cache/SLO logic ([16](16-routing-failure-modes.md)).
3. **Everything observable** — every hop emits metrics/traces under one trace_id
   ([20](20-llm-observability-stack.md), [23](23-llm-tracing.md)).
4. **SLO-driven** — alerting and rollback hinge on error budgets, not raw gauges
   ([06](06-error-budgets-for-ai-systems.md), [22](22-alerting-strategy.md)).
5. **Quality in the loop** — eval gates releases and quality SLIs pulse in
   production ([24](24-quality-observability.md), [28](28-llm-regression-testing.md)).

## Related

`13-overload-protection.md` · `16-routing-failure-modes.md` ·
`20-llm-observability-stack.md` · `21-production-dashboard.md` ·
`22-alerting-strategy.md` · `README.md`

## Key takeaways

1. The reference architecture composes this whole section into one deployable shape.
2. Protect the edge (rate+admission), centralize decision (router), observe everything (OTel→Prometheus→Grafana).
3. Add RAG/tools/agents/eval/cost as wired subsystems.
4. Everything is SLO/error-budget and quality driven.
