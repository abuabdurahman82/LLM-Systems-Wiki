# 30 — LLM Incident Response

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

When an LLM platform is degrading, a **structured incident response** gets you
from "something's wrong" to "user impact contained" fast and safely — and, because
many LLM failures are *silent* or *multi-layered* ([01](01-llm-reliability-overview.md)),
incident response here must check quality signals, not just HTTP status.

## The response loop

```
Detect
  ↓
Triage
  ↓
Mitigate
  ↓
Recover
  ↓
Learn
```

- **Detect** — from alerting ([22](22-alerting-strategy.md)), dashboards, or user reports.
- **Triage** — confirm impact, classify (which layer? [09](09-llm-failure-taxonomy.md)),
  declare severity, assign roles.
- **Mitigate** — protect users *first* (fallback, drain, shed load) before finding
  root cause.
- **Recover** — restore full service; verify quality, not just uptime.
- **Learn** — postmortem ([32](32-blameless-postmortems.md)), runbook update
  ([31](31-production-runbooks.md)), fix root cause.

## The incident roles

| Role | Responsibility |
|---|---|
| **Incident Commander (IC)** | owns the response, declares severity, coordinates, de-escalates only when resolved |
| **Operations** | runs mitigations/rollbacks, executes runbooks |
| **Communications** | status to stakeholders/users; blameless updates |
| **Subject Matter Expert (SME)** | deep diagnosis per layer (GPU, engine, RAG, model, network) |

The IC does **not** also debug; they direct. SMEs own diagnosis and mitigation
in their domain.

## Example incidents

**"TTFT suddenly doubles"**
- Detect: TTFT SLO burn alert ([22](22-alerting-strategy.md)).
- Triage: is it overload (queue↑) or prefill (long prompts)? ([05](05-production-latency-debugging.md))
- Mitigate: admission control / scale / fallback-to-smaller.
- Recover: capacity restored; TTFT back in budget.
- Learn: why lacked headroom? ([08](08-queueing-theory-for-llm-sre.md))

**"GPU OOM cascade"**
- Detect: OOM errors + KV exhaustion.
- Mitigate: drain, reduce concurrency, fallback ([12](12-kv-cache-reliability.md), [10](10-gpu-reliability.md)).
- Learn: right-size concurrency × context ([07](07-llm-capacity-planning.md)).

**"Model responses become incorrect"**
- Detect: quality SLI drop ([24](24-quality-observability.md)) — *no HTTP error*.
- Mitigate: roll back model/prompt ([25](25-model-release-engineering.md)).
- Learn: why wasn't golden-set gate enough? ([28](28-llm-regression-testing.md))

**"RAG returns stale documents"**
- Detect: grounding/retrieval quality drop ([35](35-rag-sre.md)).
- Mitigate: fix/rollback index; fall back to fresher index.
- Learn: index freshness SLO ([35](35-rag-sre.md)).

**"OpenRouter unavailable"**
- Detect: provider error rate / circuit breaker.
- Mitigate: provider fallback ([15](15-model-fallback-and-resilience.md)).
- Learn: is remote provider a single point of failure?

## Operational practice (`[I]`)

1. **Mitigate before root-cause** — user impact first; diagnosis second.
2. **Blameless coordination** — communications assume good intent ([32](32-blameless-postmortems.md)).
3. **Time-stamp everything** — full timeline into the postmortem.
4. **Check quality, not just availability** — a "recovered" system must pass
   quality SLIs, or you've only brought the silence back ([24](24-quality-observability.md)).

## Related

`22-alerting-strategy.md` · `29-chaos-engineering-for-llms.md` ·
`31-production-runbooks.md` · `32-blameless-postmortems.md`

## Key takeaways

1. Response loop: detect → triage → mitigate → recover → learn.
2. Roles: Incident Commander, Operations, Communications, SMEs.
3. Mitigate before root-cause; protect users first.
4. For LLMs, "recovered" must include quality, not just HTTP 200.
