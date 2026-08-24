# 09 — LLM Failure Taxonomy

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

A shared **failure taxonomy** gives the whole team one vocabulary for "what
broke," so triage, alerting, dashboards and postmortems classify things the same
way. LLM failures span far more than "the server is down" — many are *silent*
(no HTTP error) and live up-stack.

## Classification categories

| Category | Where it sits | Character |
|---|---|---|
| **APPLICATION** | caller / API boundary | visible, addressable |
| **MODEL** | the model itself | often silent (wrong output, no error) |
| **HARNESS** | agent/orchestration scaffolding | can be runaway, silent |
| **RAG** | retrieval layer | often degrades quality silently |
| **INFERENCE ENGINE** | serving runtime | visible errors, stalls |
| **GPU** | hardware/device | visible vendor errors (Xid/ECC), throttling |
| **NETWORK** | fabric/comms | stalls, timeouts, congestion |
| **STORAGE** | checkpoints, indexes, logs | latency, corruption |
| **SCHEDULER** | engine/cluster scheduler | stalls, deadlocks, admission mistakes |
| **KUBERNETES** | orchestration | scheduling gaps, probe loops, failed rollout |
| **EXTERNAL PROVIDER** | downstream APIs | degradation, rate limits, outage |

## Examples per category (`[I]` taxonomy; each item is a real class of failure)

**APPLICATION**
- bad API request (invalid schema, over quota)
- malformed structured output (model returned non-conforming JSON, schema parse fail)

**MODEL**
- hallucination (confident wrong answer)
- refusal regression (model refuses valid requests)
- incorrect reasoning (confident wrong chain of logic)

**HARNESS**
- runaway agent (infinite loop, uncontrolled tool calls)
- tool loop (call → result → same call)
- context overflow (context budget exhausted mid-run)

**RAG**
- retrieval miss (correct doc not found)
- stale index (index not updated — grounding on old data)
- poisoning (adversarial/incorrect context injected)
- vector DB outage

**INFERENCE ENGINE**
- scheduler stall (scheduler hung, requests stuck queued)
- KV exhaustion (no free KV blocks)
- worker crash (replica/process dies)

**GPU**
- OOM (out of memory)
- ECC errors (single/double-bit; see [10](10-gpu-reliability.md))
- thermal throttling
- Xid errors (driver-reported GPU errors)

**NETWORK**
- NCCL timeout (collective stalls)
- RoCE / InfiniBand congestion causing packet loss on an RDMA fabric
- packet loss / link drops

**SCHEDULER**
- admission mistake (admitted work that can't fit)
- deadlock/stall (no progress)

**KUBERNETES**
- no schedulable node for GPU pod
- readiness/liveness probe failure loop
- failed rolling update

**EXTERNAL PROVIDER**
- downstream LLM API degradation
- rate limiting
- provider outage

## Why the taxonomy matters

1. **Triage speed** — a common vocabulary means incident roles agree fast
   ([30](30-llm-incident-response.md)).
2. **Alert design** — alerts should point at a category, not just a raw gauge
   ([22](22-alerting-strategy.md)).
3. **Dashboard grouping** — group panels by category so failure patterns are
   visible ([21](21-production-dashboard.md)).
4. **Postmortems** — consistent classification across incidents enables trend
   analysis ([32](32-blameless-postmortems.md)).

**Silent vs visible:** the single most important distinction. APPLICATION/HARNESS/
MODEL/RAG failures are frequently *silent* — the system answers, but wrongly. That
is why quality observability ([24](24-quality-observability.md)) and eval-in-loop
([28](28-llm-regression-testing.md)) are first-class.

## Related

`10-gpu-reliability.md` · `11-distributed-inference-failures.md` ·
`12-kv-cache-reliability.md` · `30-llm-incident-response.md` ·
`Inference/Production-Serving/15-failure-modes-and-operations.md`

## Key takeaways

1. Classify failures into a shared taxonomy so the team speaks one language.
2. LLM failures go far beyond "server down" — many are silent quality failures.
3. Categories map to alerting, dashboards and postmortem grouping.
4. The silent-vs-visible distinction is the most important axis.
