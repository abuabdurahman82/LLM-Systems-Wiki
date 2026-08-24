# 33 — Cost as an SRE Signal

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

**Uncontrolled cost is itself a reliability failure.** An LLM platform that burns
money has a harder constraint than "fast and correct" — it must be *economically
sustainable*, and runaway spend (a retry storm, a runaway agent, an unbounded
context) is a real production incident. Cost belongs in the SLO/alerting picture.

## Cost metrics that matter

| Metric | What it captures |
|---|---|
| **$/request** | unit economic health |
| **$/1M tokens** (in or out) | pricing exposure |
| **$/successful request** | useful-work cost — pairs with goodput ([03](03-goodput-vs-throughput.md)) |
| **GPU-hours** | hardware consumption |
| **energy/token** | physical/infra cost |
| **cloud API spend** | external provider burn ([15](15-model-fallback-and-resilience.md)) |

## Cost failure drivers

| Driver | Mechanism | Guard |
|---|---|---|
| **Runaway agent** | agent loops / never terminates | step + token + time + cost budgets ([34](34-agent-sre.md)) |
| **Retry storm** | retries multiply spend | retry budgets, backoff, circuit breaker ([14](14-retries-timeouts-circuit-breakers.md)) |
| **Oversized context** | huge prompts/token bloat | context budgets, compaction ([Context-Engineering]) |
| **Expensive fallback** | silent switch to costly cloud path | tag + cost-monitor fallback ([15](15-model-fallback-and-resilience.md)) |
| **Too many evaluator calls** | quality-eval LLM calls multiplying | budget/ration evaluator runs ([24](24-quality-observability.md)) |

## Making cost operational (`[I]`)

1. **Expose cost per request** (tokens × unit price), including hidden multiplies
   (internal LLM calls per user request — agents, evals, sub-calls).
2. **Set a cost budget** per tenant/session/request and hard-cap it.
3. **Alert on cost anomalies** — a spike in $/min or cost-per-request trend is a
   symptom of a runaway or retry storm ([22](22-alerting-strategy.md)).
4. **Include cost in rollback criteria** — a canary that multiplies cost should
   roll back even if it's fast ([27](27-canary-deployment.md), [33↔06](06-error-budgets-for-ai-systems.md)).
5. **Tag provenance** so cost can be attributed to model/tenant/campaign
   ([23](23-llm-tracing.md)).

## Related

`03-goodput-vs-throughput.md` · `06-error-budgets-for-ai-systems.md` ·
`14-retries-timeouts-circuit-breakers.md` · `15-model-fallback-and-resilience.md` ·
`34-agent-sre.md`

## Key takeaways

1. Uncontrolled cost is a reliability failure with its own SLOs.
2. Track $/request, $/1M tokens, $/successful request, GPU-hours, energy, cloud spend.
3. Runaway agents, retry storms, oversized context, expensive fallback, and
   excessive eval calls are the classic burn drivers.
4. Budget, alert on cost anomalies, and gate rollbacks on cost.
