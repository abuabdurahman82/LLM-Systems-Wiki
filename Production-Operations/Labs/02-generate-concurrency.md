# Lab 2 — Generate Concurrency and Observe the Trade-off

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [04-llm-golden-signals](../04-llm-golden-signals.md), [05-production-latency-debugging](../05-production-latency-debugging.md)

## Goal
Drive a synthetic endpoint with concurrency **1, 2, 4, 8, 16** and plot
concurrency vs **aggregate tok/s vs TTFT vs P95**, to see **ρ → 1** in action.

## Why
Utilization and tail latency trade off; more concurrency raises throughput until
it hits the KV/bandwidth wall, then latency explodes ([08](../08-queueing-theory-for-llm-sre.md)).

## Method
```python
import time, threading, httpx, statistics, matplotlib.pyplot as plt
from concurrent.futures import ThreadPoolExecutor

CONC = [1, 2, 4, 8, 16]
URL = "http://127.0.0.1:8000/v1/chat/completions"

def one():
    t0 = time.perf_counter()
    with httpx.stream("POST", URL, json={
        "model":"local-mock","messages":[{"role":"user","content":"Write a paragraph."}],
        "stream":True,"max_tokens":64}) as r:
        n=0; first=None
        for line in r.iter_lines():
            if line.startswith("data:"):
                if first is None: first=time.perf_counter()-t0
                n+=1
    return (first, n, time.perf_counter()-t0)

rows=[]
for c in CONC:
    with ThreadPoolExecutor(c) as ex:
        res=list(ex.map(lambda _: one(), range(40)))
    ttft=[x[0] for x in res]; toks=[x[1] for x in res]
    dur=max(x[2] for x in res)
    rows.append((c, sum(toks)/dur, statistics.median(ttft),
                 sorted(ttft)[int(len(ttft)*0.95)]))
    print(c, "tok/s=%.0f"%rows[-1][1], "TTFT med=%.2fs"%rows[-1][2], "P95=%.2fs"%rows[-1][3])

c,[ag,tt,p95]=zip(*rows)  # unpack
plt.plot(c, ag, marker='o'); plt.xlabel("concurrency"); plt.ylabel("aggregate tok/s"); plt.title("tok/s vs concurrency"); plt.savefig("lab2_tok.png")
plt.clf()
plt.plot(c, [tt,p95])  # illustrative
plt.xlabel("concurrency"); plt.ylabel("TTFT s"); plt.legend(["median","P95"]); plt.title("TTFT vs concurrency"); plt.savefig("lab2_ttft.png")
```

## Interpretation
- **tok/s** rises with concurrency then plateaus/falls as contention sets in.
- **TTFT** (esp. P95) rises steeply at high concurrency — the queueing cliff
  ([08](../08-queueing-theory-for-llm-sre.md)).
- Compare against your KV/goodput headroom ([12](../12-kv-cache-reliability.md)).

## Safety
Local synthetic endpoint, moderate duration; cap the run to avoid prolonged saturation.
