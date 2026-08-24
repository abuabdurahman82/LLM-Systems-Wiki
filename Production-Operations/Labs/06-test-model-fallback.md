# Lab 6 — Test Model Fallback

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [15-model-fallback-and-resilience](../15-model-fallback-and-resilience.md)

## Goal
Use two synthetic model endpoints (a "primary" and a "fallback"); make the
primary fail; verify traffic **falls back** and that the fallback response is
**tagged with provenance** so you can see which model served.

## Why
Fallback raises availability but changes quality/latency/cost — you must be able
to tell *what served* and evaluate it ([15](../15-model-fallback-and-resilience.md)).

## Method
```python
import httpx
PRIMARY="http://127.0.0.1:9001/v1/chat/completions"
FALLBACK="http://127.0.0.1:9002/v1/chat/completions"

def serve(msg):
    for url,label in ((PRIMARY,"primary"),(FALLBACK,"fallback")):
        try:
            r=httpx.post(url,json={"model":"m","messages":[{"role":"user","content":msg}],"max_tokens":32},timeout=5)
            r.raise_for_status()
            return {"served_by":label,"fallback_reason":"" if label=="primary" else "primary_down","content":r.json()}
        except httpx.HTTPStatusError as e:
            # circuit-breaker would trip for providers here (14)
            if e.response.status_code in (429,500,503):
                continue
        except (httpx.TimeoutException, httpx.ConnectError):
            continue
    return {"served_by":None,"fallback_reason":"all_down"}
```

## Test + interpretation
1. **Primary healthy** → served_by primary.
2. **Primary down** (stop it / return 500) → served_by fallback; `fallback_reason` set.
3. **Both down** → honest failure, no silent garbage.
4. Check the fallback path is *evaluated*: does fallback meet your quality/latency/
   cost bar for *this* request class? ([15](../15-model-fallback-and-resilience.md),
   [28](../28-llm-regression-testing.md)).
5. Watch for the **silent expensive fallback** trap — tag and cost it
   ([33](../33-cost-as-an-sre-signal.md)).

## Safety
Local synthetic endpoints only.
