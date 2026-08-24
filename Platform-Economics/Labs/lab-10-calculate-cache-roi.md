# Lab 10 — Calculate Cache ROI

`LAST_UPDATED: 2026-08-24` · Concept: cache economics · Builds on
[../08-kv-cache-economics](../08-kv-cache-economics.md).

## Goal
Compute **Cache Value = Avoided Prefill Cost − Memory Opportunity Cost** for
self-host and for a cloud API, and see where caching is worth it.

## Approach (computation)
1. Self-host: avoided prefill = $/1M prefill at your utilization
   (`economic_foundation.py` prints ≈ **$0.07/1M** at 20% util); memory opp ≈
   $0.02/1M → cache value ≈ **$0.03/1M** per hit.
2. Cloud API: cached input discount is big — e.g. GPT-4.1 **$2.00 → $0.50**
   per 1M input (2026) = **$1.50/1M saved** on every cached input token.

```python
def cache_value(avoid_prefill_per_1m, mem_opp_per_1m, hit_rate):
    return hit_rate * (avoid_prefill_per_1m - mem_opp_per_1m)
print("self-host @20%:", cache_value(0.07,0.02,0.6))   # ≈ 0.03
print("api gpt41     :", cache_value(1.50,0.0,0.6))    # ≈ 0.90 (per 1M cached in)
```

## Expected result
Self-host caching's *dollar* value is small (latency is the real win); cloud-API
caching is a **direct, large money saver** via the cached-input discount.

## Interpretation
Cache economics are context-dependent: **self-host = latency + utilization win;
cloud = direct $ win** ([08](../08-kv-cache-economics.md)). Price cached tokens
cheaper ([15](../15-llm-platform-pricing-models.md)) to drive adoption.

## Verify
Halve the hit rate in both cases; show self-host value → ~0 but API still saves.
