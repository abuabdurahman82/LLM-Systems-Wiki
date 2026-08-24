# Lab 1 — Measure TTFT and TPOT

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [05-production-latency-debugging](../05-production-latency-debugging.md)

## Goal
Measure **TTFT** (time to first token) and **TPOT** (time per output token) for a
local LLM endpoint, with **synthetic** traffic only.

## Why
TTFT and TPOT have different physics; you cannot tune what you can't separate
([05](../05-production-latency-debugging.md), [04](../04-llm-golden-signals.md)).

## Method
Send a streaming request to an OpenAI-compatible endpoint you control (or a
loop-back mock). Record: time to first chunk, per-token arrival times, total time.

```python
import time, httpx, statistics

URL = "http://127.0.0.1:8000/v1/chat/completions"   # your synthetic/local endpoint
body = {
    "model": "local-mock",
    "messages": [{"role":"user","content":"Write 5 sentences."}],
    "stream": True, "max_tokens": 128,
}
t0 = time.perf_counter()
first = None; arrivals = []
with httpx.stream("POST", URL, json=body, timeout=None) as r:
    for line in r.iter_lines():
        if not line or not line.startswith("data:"):
            continue
        now = time.perf_counter()
        if first is None:
            first = now; ttft = now - t0
        arrivals.append(now)
if arrivals:
    dt = [(arrivals[i+1]-arrivals[i]) for i in range(len(arrivals)-1)]
    tpot = sum(dt)/len(dt) if dt else None
print(f"TTFT = {ttft*1000:.0f} ms")
print(f"TPOT ~ mean ITL = {tpot*1000:.1f} ms/token" if tpot else "no tokens")
```

## Interpretation
- Repeat N≥20 times, compute **P50/P95/P99** for TTFT and TPOT (`[E]` on your box).
- TTFT reflects queue+prefill; TPOT reflects decode ([05](../05-production-latency-debugging.md)).

## Safety
Synthetic single-stream; no load. Keep the endpoint local.
