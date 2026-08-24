# 31 — Production Runbooks

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

A **runbook** is the prescribed, pre-agreed response to a predictable failure. It
removes improvisation during incidents: *symptoms → checks → commands → likely
causes → mitigation → escalation → recovery → validation*. Runbooks here are
**templates to adapt to your stack** — commands are illustrative, safe, and must
be adjusted to your environment. **We do not invent unsafe commands.**

## The runbook template

| Section | Purpose |
|---|---|
| **Symptoms** | how you'll recognise it |
| **Impact** | who/what it affects, severity |
| **Immediate checks** | read-only commands to confirm |
| **Commands** | safe, scoped actions (illustrative) |
| **Likely causes** | ranked hypotheses |
| **Mitigation** | protect users first |
| **Escalation** | who to call, when |
| **Recovery** | restore full service |
| **Post-incident validation** | prove it's really fixed |

## Runbooks

### 1. High TTFT
- **Symptoms:** TTFT SLO burn; first-token delay.
- **Immediate checks:** queue depth, admitted/waiting requests, prefix-cache hit rate, prompt-length distribution ([05](05-production-latency-debugging.md)).
- **Likely causes:** overload (queue), prefill congestion, long prompts, KV exhaustion, cache misses, router imbalance.
- **Commands (illustrative):** `curl` engine `/metrics` for `TTFT`/queue; `nvidia-smi` for GPU load; check router health.
- **Mitigation:** admission control, scale out, cache-aware routing; shed low-priority.
- **Escalation:** on-call platform + inference SME if capacity is the cause.

### 2. High TPOT
- **Symptoms:** slow streaming; decode token-rate drop.
- **Immediate checks:** decode throughput, batch size, KV util, HBM/bandwidth, clocks ([05](05-production-latency-debugging.md), [10](10-gpu-reliability.md)).
- **Likely causes:** decode bandwidth saturation, batch pressure, KV fragmentation, throttling, NCCL stalls.
- **Mitigation:** reduce concurrency, reduce context, check clocks/power caps.

### 3. GPU OOM
- **Symptoms:** OOM errors, CUDA out-of-memory, rejected requests.
- **Immediate checks:** GPU memory, KV util, concurrency × context ([12](12-kv-cache-reliability.md)).
- **Mitigation:** drain, reduce concurrency, degrade/fallback ([15](15-model-fallback-and-resilience.md)).

### 4. KV saturation
- **Symptoms:** rising evictions, allocation failures, waiting requests.
- **Immediate checks:** KV util, hit rate, concurrency ([12](12-kv-cache-reliability.md)).
- **Mitigation:** admission, scale, compress/offload context; fallback smaller model.

### 5. GPU Xid
- **Symptoms:** `NVRM: Xid` in dmesg/journal; app errors.
- **Immediate checks:** `dmesg | grep NVRM`, `nvidia-smi -q` ECC/errors ([10](10-gpu-reliability.md)).
- **Important:** Xid is a *diagnostic*; check the Xid catalog (`[F]` docs.nvidia.com) before acting; do not guess code meanings.
- **Mitigation:** drain GPU, reset per vendor guidance; escalate for persistent DBE (RMA path).

### 6. NCCL timeout
- **Symptoms:** distributed request failures, `NCCL timeout`.
- **Immediate checks:** per-rank health, network/fabric, lockstep stalls ([11](11-distributed-inference-failures.md)).
- **Mitigation:** rebuild group, drain straggler, fail fast with timeout; DP replication.

### 7. Queue explosion
- **Symptoms:** queue depth climbing; admission rejects; TTFT blowup.
- **Immediate checks:** arrival rate, ρ, autoscaler state, admission limits ([08](08-queueing-theory-for-llm-sre.md), [13](13-overload-protection.md)).
- **Mitigation:** shed load, rate-limit, scale out; guard against retry storm ([14](14-retries-timeouts-circuit-breakers.md)).

### 8. Model unavailable
- **Symptoms:** model errors, readiness false, health failing.
- **Immediate checks:** model loaded? crash-loop? engine logs.
- **Mitigation:** replica failover, model fallback ([15](15-model-fallback-and-resilience.md)).

### 9. Tool timeout
- **Symptoms:** agent requests stuck on tool calls; E2E blowup.
- **Immediate checks:** tool endpoint health, per-tool latency, timeout budget ([34](34-agent-sre.md), [14](14-retries-timeouts-circuit-breakers.md)).
- **Mitigation:** timeout/retry policy, circuit-break the tool, fallback answer path.

### 10. RAG outage
- **Symptoms:** retrieval failures, groundedness drop, trace shows RAG errors.
- **Immediate checks:** vector DB health, index freshness, retrieval latency ([35](35-rag-sre.md)).
- **Mitigation:** RAG fallback/failover; serve from fresher/replicated index; degrade to context-less answers.

### 11. Provider failure
- **Symptoms:** provider error rate/limits; circuit breaker trips.
- **Immediate checks:** provider status, breaker state.
- **Mitigation:** provider fallback, region failover ([15](15-model-fallback-and-resilience.md), [36](36-multi-region-llm-reliability.md)).

## Using runbooks

1. **Draft for your stack** — replace illustrative commands with your real endpoints.
2. **Drill them** in chaos sessions ([29](29-chaos-engineering-for-llms.md)) so they're exercised, not aspirational.
3. **Update after every incident** ([32](32-blameless-postmortems.md)).
4. **Read-only first** — confirm with safe checks before any mutating command.

## Related

`05-production-latency-debugging.md` · `10-gpu-reliability.md` ·
`11-distributed-inference-failures.md` · `12-kv-cache-reliability.md` ·
`30-llm-incident-response.md` · `32-blameless-postmortems.md`

## Key takeaways

1. Runbooks convert known failures into prescribed, safe, fast responses.
2. Template: symptoms → impact → checks → commands → causes → mitigation → escalation → recovery → validation.
3. Adapt to your stack; drill them; update after incidents.
4. Read-only checks before mutating actions; never invent unsafe commands.
