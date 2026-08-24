# 15 — Model Fallback & Resilience

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

**Fallback** is how an LLM platform keeps *availability* up when its primary
path fails — by serving with an alternative that may differ in quality, latency,
price, privacy, or capability. Because fallback changes the *outcome*, it must
be designed and evaluated, not just "tried when things break."

## Fallback dimensions

| Fallback type | What it substitutes | Typical trigger |
|---|---|---|
| **Replica fallback** | another identical replica/pod | replica failure, health check |
| **Model fallback** | different model (same family/size) | model error, quality regression |
| **Provider fallback** | different API provider | provider outage/limits (e.g. OpenRouter down) |
| **Region fallback** | different region/deployment | regional incident, sovereignty failover |
| **Quantized-model fallback** | lower-precision version | OOM, throughput target, cost |
| **Cloud fallback** | external cloud API | local capacity/latency issue |
| **Local fallback** | self-hosted model | external cost/privacy/capability reasons |

## Example chains

> `[A]` illustrative example naming specific products ONLY as a generic
> local→remote and large→small pattern; not a claim that this exact pairing was
> tested/verified here.

```
local Qwen
   ↓ unavailable
GLM via OpenRouter

primary large model
   ↓ overloaded
smaller model
```

## The trade-off table

Fallback improves availability but changes these — **and each must be evaluated**:

| Dimension | Direction fallback typically moves |
|---|---|
| **Quality** | often lower (smaller/quantized model) |
| **Latency** | may be higher (remote) or lower (small model) |
| **Price** | may be higher (cloud API) or lower (small/quantized) |
| **Privacy** | worse if sending data to external provider |
| **Capability** | worse if smaller model lacks tooling/formatting/reasoning |

## Why fallback must be evaluated

Availability math says a fallback raises uptime. But a *usefulness* lens says the
fallback only counts if the outcome is acceptable — a fallback that silently
serves garbage-quality answers is availability theater. Evaluate fallback against:
- **quality regression** on your eval/golden set ([28](28-llm-regression-testing.md)),
- **SLO compliance** on latency ([02](02-sli-slo-sla-for-llms.md)),
- **cost** per successful request ([33](33-cost-as-an-sre-signal.md)),
- **privacy/sovereignty** constraints ([36](36-multi-region-llm-reliability.md)),
- **goodput** ([03](03-goodput-vs-throughput.md)), not just success rate.

## Operational practice (`[I]`)

1. **Define fallback tiers** (same-family → smaller-self → remote) with explicit
   criteria for promotion.
2. **Tag response provenance** — record `model_id`/`fallback_reason` on every
   response so users/ops know *what actually served* ([23](23-llm-tracing.md)).
3. **Test the fallback path in chaos drills** ([29](29-chaos-engineering-for-llms.md)),
   not only in real incidents.
4. **Add cost/latency guards** so an expensive fallback doesn't become the new
   silent cost problem ([33](33-cost-as-an-sre-signal.md)).
5. **Prefer circuit-breaking per provider** over hammering ([14](14-retries-timeouts-circuit-breakers.md)).

## Related

`14-retries-timeouts-circuit-breakers.md` · `27-canary-deployment.md` ·
`28-llm-regression-testing.md` · `33-cost-as-an-sre-signal.md` ·
`36-multi-region-llm-reliability.md` · `Labs/06-test-model-fallback.md`

## Key takeaways

1. Fallback keeps availability up but changes quality/latency/price/privacy/capability.
2. Because it changes the outcome, fallback must be evaluated — not blind.
3. Tag every response with what actually served it.
4. Drill the fallback path in chaos tests; guard against expensive silent fallback.
