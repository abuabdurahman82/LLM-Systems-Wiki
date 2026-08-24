# 23 — Logging & Distributed Tracing

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

An LLM request crosses many systems (gateway, router, LLM, RAG, tools,
sub-agents). **Distributed tracing** concatenates those hops into one attributable
story per request; **correlation ids** make a single user request findable from
first byte to final token. Correct grounding (`trace_id`, `request_id`,
`session_id`, `model_id`, `replica_id`) is the difference between "which layer
failed?" being answered in seconds vs hours ([01](01-llm-reliability-overview.md)).

## The trace across the path

```
User request
   ↓
Gateway
   ↓
Router
   ↓
LLM
   ↓
RAG
   ↓
Tool
   ↓
Sub-agent
      ↓
      LLM
   ↓
Response
```

Each hop becomes a **span** carrying the shared `trace_id`; each span has its own
`start`/`end`, attributes and errors. Nested LLM calls (e.g. a sub-agent that
itself calls the LLM) become child spans under the same trace.

## Correlation ids

| Id | Scope | Used to |
|---|---|---|
| **trace_id** | whole request across all hops | join all spans |
| **request_id** | the API request | find it in logs & metrics |
| **session_id** | a user conversation/session | see multi-turn context, agents |
| **model_id** | which model served | know what actually answered ([15](15-model-fallback-and-resilience.md), [24](24-quality-observability.md)) |
| **replica_id** | which replica/rank | distributed failure attribution ([11](11-distributed-inference-failures.md)) |

## OpenTelemetry

**OpenTelemetry (OTel)** is the industry-standard, vendor-neutral way to emit
metrics, logs, and traces to any backend (Prometheus, Jaeger/Tempo, etc.)
(`[F]` OTel project). Wires the stack in [20](20-llm-observability-stack.md):
instrument the gateway/router/engine/harness to propagate the `trace_id` and
export spans, so the full path is observable and you can answer "which layer by
how much" from [05](05-production-latency-debugging.md)'s latency budget.

## Logging essentials

- **Structured logs** (JSON) keyed by the ids above — not free-text.
- **Decision logs** — routing decision, model chosen, fallback reason
  ([16](16-routing-failure-modes.md), [15](15-model-fallback-and-resilience.md)).
- **Outcome logs** — success/error per request with token counts and latency.
- **Quality/grounding metadata** — which retrieved docs, which tool results,
  ground-truth handles for eval ([24](24-quality-observability.md)).

## ⚠️ Sensitive prompt/content logging

Prompts and model outputs can contain **PII, secrets, proprietary data, and
legally protected content** (`[F]` privacy norm, OWASP/NIST-l-adjacent practice;
applies to your own data). **Do not log full prompts/outputs by default.**

Rules:
1. Redact/minimize: log token **counts** and **metadata**, not full content.
2. Encrypt and restrict access to any retained content.
3. Apply retention limits and audits.
4. Handle consent/sovereignty per region ([36](36-multi-region-llm-reliability.md)).
5. Sample content capture at very low rate, only where required for quality eval,
   with explicit policy ([24](24-quality-observability.md)).

## Related

`05-production-latency-debugging.md` · `16-routing-failure-modes.md` ·
`20-llm-observability-stack.md` · `24-quality-observability.md` ·
`OpenTelemetry docs`

## Key takeaways

1. Trace spans across gateway→router→LLM→RAG→tool→agent under one trace_id.
2. Correlate with trace_id/request_id/session_id/model_id/replica_id.
3. Use OpenTelemetry for vendor-neutral metrics+logs+traces.
4. Never log full prompts/outputs by default — redact, encrypt, limit retention.
