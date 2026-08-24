# Lab 9 — Simulate a Retry Storm

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [14-retries-timeouts-circuit-breakers](../14-retries-timeouts-circuit-breakers.md)

## Goal
Show why **naive retries** create a storm that makes overload worse, then show
backoff+jitter+budget controlling it.

## Why
Retries add load to the thing that's failing; without control they collapse the
platform ([14](../14-retries-timeouts-circuit-breakers.md), [08](../08-queueing-theory-for-llm-sre.md)).

## Method (synthetic)
```python
import random, time

def server_busy(load):   # load ~ server pressure
    # return True (fail) with probability rising with load
    return random.random() < (load/100)

def naive(attempts=50):
    load=50
    for a in range(attempts):
        if not server_busy(load): return "ok"
        load+=1                       # each retry adds load (storm)
    return "failed"

def controlled(attempts=8):
    load=50; d=0.05
    for a in range(attempts):
        if not server_busy(load): return "ok"
        load+=0.2                     # bounded extra load
        time.sleep(d + random.uniform(0,d))   # exp backoff + jitter
        d*=2
    return "failed"
```

## Interpretation
- **Naive**: unbounded retries drive `load` up → more failures → storm.
- **Controlled**: few retries, growing delay with jitter, hard budget → bounded
  load, better odds of eventually succeeding, and falls back to "failed" fast.
- Note the **thundering herd**: without jitter, synchronized clients retry at
  once. Watch retry:success ratio as the storm metric ([04](../04-llm-golden-signals.md)).

## Safety
Pure local simulation; no real endpoints.
