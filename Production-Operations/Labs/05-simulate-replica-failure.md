# Lab 5 — Simulate Replica Failure

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [16-routing-failure-modes](../16-routing-failure-modes.md), [29-chaos-engineering-for-llms](../29-chaos-engineering-for-llms.md)

## Goal
Run **two synthetic replicas** behind a tiny router; **kill one**; observe the
failover: remaining replica takes over, errors stay bounded, traffic recovers.

## Why
Router failover is routine ops — but only reliable if *drilled*
([16](../16-routing-failure-modes.md), [29](../29-chaos-engineering-for-llms.md)).

## Method (synthetic)
1. Start two local HTTP "replica" servers (distinct ports) that return ok.
2. A minimal round-robin + health-check router forwards requests, skipping any
   replica whose health check fails.
3. Crash replica B. Watch: router stops sending to B; A absorbs traffic; latency
   may rise; no unbounded errors if A has headroom.
4. Restart B; watch the router re-include it (readiness, [19](../19-llm-health-checks.md)).

```python
import threading, time, http.server, socketserver

# Router: list of (port, alive). health = GET /health on each. serve = forward.
# (teach the loop; keep it in the lab notes)
def router():
    while True:
        for r in replicas:
            r.alive = health_ok(r.port)   # bounded-time GET /health
        time.sleep(1)
```
> In production this is a real router with readiness/circuit logic
> ([16](../16-routing-failure-modes.md), [14](../14-retries-timeouts-circuit-breakers.md)).

## Interpretation
- **Blast radius**: only the killed replica's in-flight requests are lost
  (bounded); with replicated state, handoff is clean.
- **Health check quality matters**: a stale "alive" routes to a dead replica →
  avoid by fast health + circuit breaker ([19](../19-llm-health-checks.md), [14](../14-retries-timeouts-circuit-breakers.md)).
- Time-to-failover and error dip = your recovery story.

## Safety
Local synthetic replicas only; no real services touched without confirmation.
