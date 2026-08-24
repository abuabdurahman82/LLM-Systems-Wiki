# 01 — What Does Reliability Mean for LLMs?

`LAST_UPDATED: 2026-08-23` · Status: foundational page

> **Central question of this section:** *What does reliability mean for an LLM system?*
> Answer: it means the *user-visible outcome* stays good despite any single layer
> failing — and "good" includes speed, availability, correctness, cost, and recoverability.

## 30-Second Explanation

Classical reliability engineering optimizes a short, deterministic request path.
An LLM system optimizes a long, stateful, *streamed, probabilistic* request that
can branch into tools and agents. That changes what we even mean by "reliable,"
so this page defines the vocabulary before anything else.

## Defining the terms

| Term | Meaning (traditional) | Meaning for an LLM system |
|---|---|---|
| **Reliability** | System does what it is supposed to, for a specified period, under stated conditions | System produces *useful* answers within latency, quality and cost bounds |
| **Availability** | Uptime fraction ((time up) / (total time)) | Fraction of requests that get a *usable* response (not merely a 200 OK) |
| **Durability** | Data survives failures (no loss once acknowledged) | Model weights, adapters, prompts, indexes, logs, eval sets survive; in-flight KVs do not need to |
| **Resilience** | Graceful degradation under stress or component failure | Continues to answer acceptably under load, GPU/node/provider loss, degraded capacity |
| **Fault tolerance** | Continues operating (often degraded) despite faults | Continues serving with a fallback model / fewer GPUs / degraded RAG |
| **Recoverability** | Can be restored after failure within RTO, data loss within RPO | Failed replica/node/model is restored; state and artifacts restored per DR plan |
| **Serviceability** | Ease of repair/maintenance; observable internals | Can diagnose, replace, upgrade a GPU/model/engine without long outage |

## How an LLM request differs from a normal REST request

**Traditional request:**

```
request
  ↓
compute
  ↓
response
```

Short, stateless, deterministic, single stage. Reliability = "did it return
quickly, correctly, and is the box up?"

**LLM request:**

```
request
  ↓
tokenization
  ↓
queue
  ↓
prefill
  ↓
KV-cache allocation
  ↓
decode loop
  ↓
possibly tools / RAG / agents
  ↓
streamed response
```

Every stage is a distinct reliability risk:

| Stage | Reliability risk example |
|---|---|
| Tokenization | Tokenizer mismatch, unknown-token blowup, very long prompt |
| Queue | Head-of-line blocking, overload, unbounded queue |
| Prefill | Compute-bound (could saturate GPU), long-prompt prefill starving decode |
| KV-cache allocation | OOM, fragmentation, no free blocks → reject or kill |
| Decode loop | Memory-bandwidth bound, batch pressure, slow tokens |
| Tools / RAG / agents | Tool hang, retrieval failure, runaway loop, provider outage |
| Streamed response | Connection drop, partial output, no end-of-stream signal |

Because the response is **streamed**, partial progress is visible and a failure
halfway through looks different from a failure before the first token. This is
why TTFT and TPOT/ITL are separate signals (see [05](05-production-latency-debugging.md)).

## Recurring theme: one symptom, many layers

A single *user-visible symptom* can originate at almost any layer of the
reliability stack (see [README](README.md)). Example — **"slow answer":**

- overloaded API gateway
- router imbalance (herding onto one replica)
- long queue / admission delay
- prefill congestion (long prompts monopolizing GPU)
- decode contention (batch too big, iteration too slow)
- KV-cache exhaustion (no free blocks → preempt/wait)
- GPU throttling (power/thermal)
- NCCL communication issue (distributed)
- slow retrieval (vector DB)
- overloaded vector DB
- tool timeout (function call hung)
- model provider degradation (downstream API slow)
- excessively long context (more work per token)
- inefficient prompt (huge irrelevant prefix)
- network congestion

**This distinction is the recurring theme of the whole section.** Your whole
ops toolkit — SLIs, goodput, golden signals, error budgets, tracing, runbooks,
incident drill — exists to make "which layer is failing" answerable quickly and
to bound the blast radius when it is not.

## Reliability axioms for LLM systems

1. **Availability is not enough.** A 200 OK with a hallucination, a refusal
   regression, or a 30-second stream is not a good outcome. See
   [02-sli-slo-sla-for-llms](02-sli-slo-sla-for-llms.md).
2. **The stack is deep; failure is multi-causal.** Plan for *simultaneous*,
   correlated failures, not independent ones (GPU errors cluster; overload
   produces more errors via retries — see [14](14-retries-timeouts-circuit-breakers.md)).
3. **Partial failure is the normal case.** Distributed inference means a single
   slow worker can stall an entire request ([11](11-distributed-inference-failures.md)).
4. **State is more valuable than compute.** GPUs are replaceable; weights,
   prompts, indexes, and eval sets may not be ([37](37-disaster-recovery.md)).
5. **Quality is part of reliability.** A platform whose GPUs are 99.99% healthy
   but whose model quality regressed appears *reliable* and is not
   ([24](24-quality-observability.md)).

## Related

`Production-Operations/README.md` · `Inference/Production-Serving/01-production-serving-overview.md` ·
`Inference/Inference-Metrics.md` · `Harness-Engineering/Model-vs-Harness.md`

## Key takeaways

1. Define reliability for the *user-visible outcome*, not the uptime counter.
2. An LLM request has many serial, stateful, streamed stages — each with its own
   failure modes.
3. The same symptom (e.g. "slow answer") can come from almost any layer; knowing
   *which* is the core ops skill.
4. Availability ≠ useful output. Quality, latency, correctness and cost all count.
