# 13 — Overload Protection & Admission Control

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

The cheapest way to fail is to collapse. **Admission control** decides what gets
served when demand exceeds capacity, so the platform degrades *gracefully*
(increasing latency, shedding low-priority work) instead of *catastrophically*
(everything queues into oblivion or retry-storms). See also
`Inference/Production-Serving/10-admission-control-and-overload.md`.

## The admission decision

```
Request arrives
     ↓
Do we have capacity?
     ↓
YES → admit
NO  → queue / reject / degrade
```

Queuing, rejecting and degrading are all valid "no" answers — the art is picking
per request, per tenant, per priority.

## The controls

| Mechanism | What it does | Notes |
|---|---|---|
| **Queue limits** | cap how many wait | unbounded queues cause head-of-line collapse |
| **Rate limiting** | cap requests (or tokens) per tenant/period | RPM/TPM quotas (L0 gateway) |
| **Token budgets** | cap input+output tokens per request | bounds per-request work |
| **Max prompt length** | reject/truncate over-long prompts | bounds prefill + KV |
| **Max output length** | bound decode work | prevents runaway long outputs |
| **Per-tenant quota** | fairness across tenants | protects everyone from one hog (see `Inference/Production-Serving/13-multi-tenancy-fairness-priority.md`) |
| **Priority** | serve important work first | premium / interactive > batch |
| **Backpressure** | propagate "slow down" upstream | producer throttling |
| **Load shedding** | drop a fraction of requests early | fail fast rather than hang |

## Graceful degradation (examples)

```
large model
   ↓ overloaded
small model fallback          → keep answering, lower quality

long context
   ↓ overload
summarize / compress context  → answer from less context, bounded KV

premium request
   ↓
priority queue                → important work first, other work waits
```

Graceful degradation keeps the *acceptable* outcome going under load by trading
a controlled dimension (quality, context, priority) instead of dumping traffic.

## Design rules (`[I]`)

1. **Bound the queue** — an unbounded queue is a latency bomb ([08](08-queueing-theory-for-llm-sre.md)).
2. **Fail fast** — early reject with a clear 429/503 is kinder than a hung request.
3. **Degrade, don't drop everything** — prefer fallback/priority/compression when possible.
4. **Backpressure to sources** — an agent that is told to slow down won't pile on
   ([34](34-agent-sre.md)).
5. **Measure admission decisions** — count admitted/queued/rejected/degraded as
   first-class metrics ([04](04-llm-golden-signals.md)).

## Related

`08-queueing-theory-for-llm-sre.md` · `12-kv-cache-reliability.md` ·
`14-retries-timeouts-circuit-breakers.md` · `15-model-fallback-and-resilience.md` ·
`Inference/Production-Serving/10-admission-control-and-overload.md`

## Key takeaways

1. Admission control makes overload graceful, not catastrophic.
2. No-capacity → queue (bounded) / reject (fast) / degrade (controlled).
3. Controls: queue limits, rate limits, token budgets, length caps, quotas, priority, backpressure, shedding.
4. Fail fast and degrade over keep-everything-queued.
