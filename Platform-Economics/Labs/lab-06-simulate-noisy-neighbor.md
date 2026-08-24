# Lab 6 — Simulate the Noisy Neighbor

`LAST_UPDATED: 2026-08-24` · Concept: noisy neighbor · Builds on
[../19-noisy-neighbor](../19-noisy-neighbor.md).

## Goal
Reproduce how **one tenant's burst destroys another tenant's latency** in a
shared queue, then show that a concurrency cap fixes it.

## Approach (discrete-event sim)
- Shared single queue, FIFO.
- **Tenant A** sends 100 long jobs at t=0 (each 100 time units).
- **Tenant B** sends a short interactive job (1 time unit) at t=5.
- Without control: B waits behind all 100 of A's jobs → B's wait ≈ 100× its work.
- Now cap A's **concurrency** to 4: A's jobs drip through, and B's job slips
  into the next available slot region → B's wait collapses.

```python
# pseudo
queued = {"A": [100]*100, "B": [1]}   # jobs with service time; B enqueued at t=5
# FIFO dispatch single-server: B waits until all prior A jobs drain -> ~100
# With per-tenant concurrency cap=4, A has 4 in service; B threaded in -> ~1-3
```

## Expected result
FIFO: B's wait ≈ **100×** its own service time. Concurrency-capped: B's wait
drops to O(cap) regardless of A's flood.

## Interpretation
This is *the* mechanism behind the noisy-neighbor failure
([19](../19-noisy-neighbor.md)). Concurrency limits + queue isolation
([18](../18-tenant-fairness.md)) convert "A starves B" into "A only delays A".

## Verify
Double A's job count and show B's FIFO wait doubles but capped-wait stays flat.
