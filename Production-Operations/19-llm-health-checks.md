# 19 — LLM Health Check Design

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

"There is a difference between 'the process is up,' 'the model is loaded,' and
'the model is actually working.'" Health checks must distinguish these — and the
deeper they get, the more they must be paid for, because a deep probe that
overloads the service self-inflicts the outage it's meant to detect.

## The three (or four) levels

```
PROCESS ALIVE
   ↓
MODEL READY
   ↓
MODEL USEFUL
```

| Level | Probe kind | Answers | Example | Continuous? |
|---|---|---|---|---|
| **Process alive** | liveness | is the process up / not deadlocked? | HTTP OK endpoint, pid | cheap, always |
| **Model ready** | readiness | model loaded + enough resources to serve? | model weights loaded, KV headroom > 0, warmed | moderate, as readiness |
| **Model useful** | deep/quality | does a *real* inference work and meet a bar? | small inference returns valid output | expensive, sampled |
| **Quality health** | quality | does a golden prompt still pass? | known golden prompt passes a check | offline / low-frequency |

## The levels in practice

- **Liveness:** "process responds" — must stay *cheap and never false-fail on
  load*. If it trips while the replica is merely busy, k8s kills a *working*
  replica and makes the outage worse ([18](18-kubernetes-for-llm-sre.md)).
- **Readiness:** "model loaded + enough resources" — the right gate for traffic.
  Failing readiness removes the replica from the load balancer (doesn't kill it),
  which is the *correct* half-open behaviour; it should be sensitive to real
  un-readiness (not loaded, OOM, no KV block).
- **Deep readiness:** "a small inference works" — a lightweight generative or
  echo check that actually exercises the decode path, run periodically (not per
  request). Catches "loaded but stuck."
- **Quality health:** "a known golden prompt still passes" — the model-level
  health that catches *silent* quality regressions (refusal, format break, bad
  reasoning). This is eval territory ([24](24-quality-observability.md),
  [28](28-llm-regression-testing.md)) and is typically run as a batched/low-rate
  job, not a hot-path probe.

## Why deep probes must not overload the service

A deep probe **spends GPU, KV and queue capacity every time it runs.** If it runs
too often (or synchronously at high concurrency), it competes with real traffic:
Raise TTFT, saturate KV, and consume the very headroom that keeps the service
healthy — turning health checking into a self-DoS. `[I]`.

Rules:
1. **Cheap probes run often** (liveness always, readiness on a schedule).
2. **Expensive probes run rarely and asynchronously** (deep/quality on a timer,
   off the hot path, with their own token budget).
3. **Never put a deep probe in the liveness path.**
4. **Budget probe load** — account for probe tokens in capacity planning
   ([07](07-llm-capacity-planning.md)) and cost ([33](33-cost-as-an-sre-signal.md)).

## Related

`18-kubernetes-for-llm-sre.md` · `24-quality-observability.md` ·
`28-llm-regression-testing.md` · `31-production-runbooks.md`

## Key takeaways

1. Distinguish process-alive, model-ready, model-useful, and quality-health.
2. Liveness = cheap, never false-fails on load; readiness = model ready + resources.
3. Deep/quality probes are expensive — run rarely, asynchronously, never in liveness.
4. Unbudgeted deep probes can self-DoS the service they guard.
