# 16 — Model Routing Reliability & Failure Modes

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

The **router** decides which replica/pool serves each request. Routing failures
are often *subtle* — a request is served, but to the wrong place, or to a dead
replica, or sub-optimally — yielding latency/quality/cost problems that look like
other failures. See `Inference/Production-Serving/` for routing *design*; this
page is routing *reliability*.

## Routing failure modes

| Mode | What it is | User-visible effect |
|---|---|---|
| **Stale router telemetry** | router acts on outdated metrics | wrong placement, imbalance |
| **Herding** | many requests to the same replica | overload of that replica ([08](08-queueing-theory-for-llm-sre.md)) |
| **Unequal queues** | replicas have wildly different backlogs | some replicas idle, others saturated |
| **Cache-affinity mistakes** | request sent to replica without its prefix cache | cache miss → TTFT ↑ ([12](12-kv-cache-reliability.md)) |
| **Dead replica routing** | traffic sent to a failed/starting replica | errors, timeouts |
| **Partial failure** | some replicas degraded, router doesn't know | mixed latency/quality |
| **Wrong model routing** | request served by an ineligible/wrong model | wrong capability/quality/cost |
| **Adapter mismatch** | request for adapter A served by base without A | wrong behaviour/output |

## The routing decision pipeline

```
Router decision
     ↓
eligibility      (is this request valid for this pool?)
     ↓
health          (is the target healthy? probes / circuit state)
     ↓
predicted work  (how much work will this request need? — ERW)
     ↓
cache affinity  (does the target hold the prefix cache?)
     ↓
SLO             (can the target meet TTFT/TPOT? queue/headroom)
     ↓
placement       (admit + bind)
```

`[I]` pipeline; every step is a place a failure can be introduced. The "predicted
work" step is the `Inference/Production-Serving/03-estimating-remaining-work.md`
principle applied in microcosm.

## Reliability practice (`[I]`)

1. **Feed the router live health** — a health check that is stale is worse than
   none (probe health, [19](19-llm-health-checks.md)).
2. **Debounce/anti-herding** — smooth assignments so traffic doesn't pile onto
   the "best" replica (jitter, consistent hashing, load-aware scoring).
3. **Cache-affinity correctness** — route to the replica holding the prefix cache
   (`Inference/Production-Serving/08-cache-aware-routing.md`).
4. **Observe the router** — instrument per-target health, backlog, and routing
   decisions ([20](20-llm-observability-stack.md)).
5. **Test routing in chaos drills** — kill a replica and verify the router
   fails over cleanly ([29](29-chaos-engineering-for-llms.md)).

## Related

`08-queueing-theory-for-llm-sre.md` · `12-kv-cache-reliability.md` ·
`19-llm-health-checks.md` · `Inference/Production-Serving/05-routing-policies-from-classic-to-llm-aware.md`

## Key takeaways

1. Routing failures are subtle: wrong place, dead replica, imbalance, cache miss.
2. The decision pipeline is eligibility → health → predicted work → cache
   affinity → SLO → placement.
3. Live health, anti-herding, and cache-affinity correctness are the core protections.
4. Observe and chaos-test the router like any critical component.
