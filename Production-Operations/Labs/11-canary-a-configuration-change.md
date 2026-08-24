# Lab 11 — Canary a Configuration Change

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [25-model-release-engineering](../25-model-release-engineering.md), [27-canary-deployment](../27-canary-deployment.md)

## Goal
Take a **configuration change** (e.g. a `max_tokens` / prompt / model setting on
a synthetic endpoint) through a **1%→5%→10%→25%→50%→100% canary**, gating each
step on SLO/quality/cost and **rolling back automatically** on a breach.

## Why
Config changes are releases too; canary-with-rollback is how they're shipped
safely ([25](../25-model-release-engineering.md), [27](../27-canary-deployment.md)).

## Method
```python
import random, statistics, json

STEPS=[1,5,10,25,50,100]

def current_metrics(new_version_pct):
    # illustrative: latency and quality depend on % on the new config
    latency = 1.0 + 0.3*(new_version_pct/100)
    quality = 0.95 - 0.05*(new_version_pct/100)   # new config hurts quality
    return {"p95_ttft":latency,"quality":quality}

SLO_TTFT=1.4; QUALITY_MIN=0.93   # gates (your call)

for pct in STEPS:
    m=current_metrics(pct)
    ok_ttft = m["p95_ttft"] <= SLO_TTFT
    ok_q    = m["quality"]  >= QUALITY_MIN
    if not (ok_ttft and ok_q):
        print(f"{pct}% -> ROLLBACK (ttft={m['p95_ttft']:.2f}, q={m['quality']:.3f})")
        break
    print(f"{pct}% -> pass (ttft={m['p95_ttft']:.2f}, q={m['quality']:.3f})")
```
In reality you'd gate on real SLO/quality/cost/GPU/errors from [27](../27-canary-deployment.md).

## Interpretation
- **Ramp only while gates pass**; hold or roll back otherwise.
- **Rollback = divert to old version** automatically — that's the safety net.
- Tag canary outputs with provenance so sample cohorts are comparable
  ([23](../23-llm-tracing.md)).

## Safety
Synthetic simulation; the same discipline transferred to a real config change
should be gated and reversible, on non-production first.
