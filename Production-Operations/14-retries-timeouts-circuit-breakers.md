# 14 — Retries, Timeouts & Circuit Breakers

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

On GPU systems, **retries are dangerous**: each retry *adds load* to the exact
system that is over capacity. Naive retry-on-failure converts a small incident
into a **retry storm**. The discipline is to retry sparingly, back off, and trip
a **circuit breaker** before you burn the platform.

## The retry storm

```
Failure
   ↓
retry (adds load)
   ↓
more load → more failures
   ↓
retry again → overload cascade / collapse
```

The mechanism: overload produces errors; callers retry; retries add demand;
demand worsens overload. Without control, ρ climbs past the cliff
([08](08-queueing-theory-for-llm-sre.md)) and the system collapses under its own
retry traffic.

## The controls

| Control | What it does |
|---|---|
| **Exponential backoff** | exponentially growing delay between retries (e.g. 1s→2s→4s…) |
| **Jitter** | randomize retry timing so clients don't synchronize (thundering herd) |
| **Retry budget** | hard cap on total retries per request unit of time |
| **Idempotency** | ensure retries don't double-do side-effecting work (important for tools/payments, not pure reads). For **streamed LLM** requests, a retry after the first token is a *fresh non-deterministic* response, not a continuation — treat it as new, never as a resume |
| **Circuit breaker** | stop calling a failing dependency after N failures, for a cool-down, then half-open probe |
| **Timeout hierarchy** | every stage gets its own bounded timeout, so failures are *fast* |

## Timeout hierarchy (`[I]` budgets)

Give each hop its own timeout so a slow dependency is bounded locally:

| Hop | Timeout budget (illustrative) |
|---|---|
| Gateway | outer bound (e.g. overall request) |
| Model (primary) | e.g. N s to first token / N s total |
| Tool | e.g. bounded per tool call |
| RAG / retrieval | e.g. bounded per lookup |
| Remote API | per provider call |
| Agent step | per agent iteration |

The **outer timeout** must be ≥ the sum of inner timeouts you'll tolerate; a
request with no outer bound can hang forever across nested hops. Timeouts make
failures *fast*, which is essential for admission control and for avoiding
resource pile-up.

## Circuit breaker pattern

```
Closed (healthy)  → failures accumulate
     ↓ threshold exceeded
Open (short-circuit; fail fast, no calls)
     ↓ cool-down
Half-open (probe one call)
     ↓ success → Closed   /   failure → Open
```

For LLM platforms, circuit breakers are most valuable per-dependency: a
downstream provider ([15](15-model-fallback-and-resilience.md)) or a RAG store
([35](35-rag-sre.md)) that is failing should short-circuit to fallback rather
than be hammered.

## Operational practice (`[I]`)

1. **Retry only idempotent, cheap-enough operations** and cap the retry budget.
2. **Distinguish transient from capacity failures** — the most important LLM
   distinction. Network timeouts/connection resets are *transient* (retry helps).
   GPU OOM, KV exhaustion, and overload/429 are *capacity* failures: the
   resource is still full on the next attempt, so retrying is almost always
   pointless and adds load. For capacity failures the correct response is
   **admission control / backpressure / shedding**
   ([13](13-overload-protection.md), [12](12-kv-cache-reliability.md)), not retry.
3. **Back off exponentially with jitter** to avoid sync and storming.
4. **Set every timeout** in the hierarchy; add an outer bound.
5. **Trip the breaker on systemic failure** (e.g. provider 5xx), not on one-off
   request errors.
6. **Watch retry amplification** as a metric — a rising retry:success ratio is a
   leading indicator of a brewing storm ([04](04-llm-golden-signals.md)).
7. **Coordinate with admission control** — reject early rather than retry into
   a collapsed system ([13](13-overload-protection.md)).

## Related

`08-queueing-theory-for-llm-sre.md` · `13-overload-protection.md` ·
`15-model-fallback-and-resilience.md` · `34-agent-sre.md` ·
`Inference/Production-Serving/15-failure-modes-and-operations.md`

## Key takeaways

1. Retries add load to the thing that's failing → retry storm.
2. Use exponential backoff, jitter, and a retry budget.
3. A timeout hierarchy (with an outer bound) makes failures fast and local.
4. Circuit breakers short-circuit failing dependencies; watch retry amplification.
