# 25 — Model Release Engineering

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

For LLM platforms, a "release" is not just code — **a new model, quantization,
prompt, system prompt, RAG index, inference engine, or kernel is also a release**,
and each deserves the same staging discipline as a code deploy. The most common
production quality regressions come from shipping one of these *without* a
release gate.

## What counts as a release

| Change | Why it's risky | Example failure |
|---|---|---|
| New model | behaviour/quality/latency shift | refusal regression, format break |
| New quantization | accuracy/perf trade-off | quality drop, OOM |
| New prompt / system prompt | output behaviour changes | degraded reasoning, tool misuse |
| New RAG index / embedding | grounding changes | stale or mis-retrieved context |
| New inference engine / version | throughput/behaviour change | scheduler bug, latency shift |
| New kernel / CUDA | crash/perf risk | GPU error, throughput drop |

## The environments

```
dev → staging → canary → production
```

- **dev** — quick iteration, not for reliability signal.
- **staging** — realistic-ish, gate for smoke + automated checks.
- **canary** — small real traffic with guardrails ([27](27-canary-deployment.md)).
- **production** — full rollout, still under error budget ([06](06-error-budgets-for-ai-systems.md)).

## Deployment strategies

| Strategy | How | Used for | Notes |
|---|---|---|---|
| **Rolling** | replace instances gradually | safe low-risk changes | keep capacity (maxUnavailable=0) |
| **Blue/green** | full second fleet, switch | big/engine changes | easy rollback via DNS/router flip |
| **Canary** | small % then ramp | any risky change | guard via SLO/quality ([27](27-canary-deployment.md)) |
| **Shadow** | run candidate on copies of traffic | quality/latency comparison | candidate never serves user ([26](26-shadow-testing.md)) |

## The release gate (`[I]`)

1. **Version everything** — model, weights, quant config, prompt, index, engine,
   kernel each get a version recorded in every trace ([23](23-llm-tracing.md)).
2. **Gate on error budget** — don't ship a risky change when the budget is burnt
   ([06](06-error-budgets-for-ai-systems.md)).
3. **Run regression tests** — quality, latency, throughput, memory, tool/RAG/safety
   ([28](28-llm-regression-testing.md)).
4. **Canary with rollback criteria** — automated rollback on SLO/quality breach
   ([27](27-canary-deployment.md)).
5. **Tag output provenance** — every response records exactly what shipped it
   ([24](24-quality-observability.md)).

## Related

`06-error-budgets-for-ai-systems.md` · `26-shadow-testing.md` ·
`27-canary-deployment.md` · `28-llm-regression-testing.md` ·
`18-kubernetes-for-llm-sre.md`

## Key takeaways

1. Model/quant/prompt/index/engine/kernel changes are all releases.
2. Promote dev → staging → canary → production.
3. Use rolling, blue/green, canary, or shadow per risk.
4. Gate every release on versioning, error budget, regression tests, and rollback.
