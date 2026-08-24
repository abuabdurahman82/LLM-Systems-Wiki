# Lab 4 — Implement Admission Control

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [13-overload-protection](../13-overload-protection.md), [08-queueing-theory-for-llm-sre](../08-queueing-theory-for-llm-sre.md)

## Goal
Build a minimal **admission-control proxy** in front of a synthetic endpoint that
bounds the queue and rejects/degrades to protect latency — then show it works
under overload.

## Why
A bounded queue + fast-fail is what stops catastrophic collapse
([13](../13-overload-protection.md)).

## A minimal model in Python
```python
import time, heapq, threading

class Admission:
    def __init__(self, max_inflight=8, max_queue=16):
        self.inflight=0; self.queue=[]; self.max_i=max_inflight; self.max_q=max_queue
    def admit(self, req):
        if self.inflight < self.max_i:           # capacity
            self.inflight+=1; heapify=heapq; heapify.heappush(self.queue,(0,req)); return True,"admitted"
        if len(self.queue) >= self.max_q:         # queue full
            return False,"rejected_429"          # fail fast
        heapify.heappush(self.queue,(1,req)); return True,"queued"
    def done(self):
        self.inflight-=1
        while self.queue:
            _,req=heapq.heappop(self.queue); self.inflight+=1; return req
        return None
```
This is a **teaching sketch** (`[I]`), not production code: real admission also
considers KV/token budgets and priority ([13](../13-overload-protection.md)).

## Test + interpretation
1. Drive synthetic load above capacity (Lab 3).
2. **Without** admission: TTFT blows up ([08](../08-queueing-theory-for-llm-sre.md)).
3. **With** admission: once the queue fills, new requests are **rejected fast**
   (429) → TTFT of admitted work stays bounded; queue stays ≤ max.
4. Count admitted/queued/rejected as metrics — the "source of truth" for the
   admission decision ([04](../04-llm-golden-signals.md)).

## Safety
Local synthetic proxy + local endpoint only.
