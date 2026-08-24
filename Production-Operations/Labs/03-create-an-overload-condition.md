# Lab 3 — Create an Overload Condition (Safely)

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [08-queueing-theory-for-llm-sre](../08-queueing-theory-for-llm-sre.md), [13-overload-protection](../13-overload-protection.md)

## Goal
Drive a synthetic endpoint past its capacity and observe **queue growth → TTFT
blowup → error rate**, then recover by shedding/admission. **Synthetic target
only; never overload a shared production-like service.**

## Why
Watching ρ→1 up close builds the intuition that runs operations
([08](../08-queueing-theory-for-llm-sre.md)).

## Method
1. Find the endpoint's sustainable rate (Lab 2's plateau) = your μ-ish ceiling.
2. Send arrivals at 1.5–2× that for a bounded window (60–120 s).
3. Record queue depth / TTFT / error rate over time.

```python
import time, httpx, threading
from concurrent.futures import ThreadPoolExecutor

URL="http://127.0.0.1:8000/v1/chat/completions"
RPS=40          # > sustainable
DUR=60

def worker(i):
    try:
        with httpx.stream("POST",URL,json={
            "model":"local-mock","messages":[{"role":"user","content":"x"*400}],
            "stream":True,"max_tokens":128}, timeout=20) as r:
            for _ in r.iter_lines(): pass
        return ("ok",0)
    except Exception as e:
        return ("err",type(e).__name__)

end=time.time()+DUR; i=0; ok=err=0
while time.time()<end:
    i+=1
    if i%RPS==0:  # throttle starts
        # sample queue from /metrics if exposed
        time.sleep(1/RPS)
    # in practice: schedule RPS requests/sec with a rate limiter
```

> Use a proper rate-limiter (e.g. `locust`/`hey -c -z`) for clean RPS. The loop
> above is illustrative.

## Interpretation
- **Queue depth** rises before TTFT does (leading indicator, [08](../08-queueing-theory-for-llm-sre.md)).
- **TTFT** grows as ρ→1; **errors/timeouts** appear as the queue/backlog saturates.
- **Recovery**: stop the load, watch queue drain, TTFT return to baseline.

## Safety
- Use a **disposable synthetic endpoint**; short window; cap concurrency.
- No interference with real workloads without explicit confirmation.
