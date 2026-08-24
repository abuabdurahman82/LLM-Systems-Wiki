# Scheduling Inside the Engine — The L2 Layer in One Page
`LAST_UPDATED: 2026-08-22` · Status: cross-link page · This page defines only
what the L1 router may *assume* about L2. Full mechanics live in the linked
pages — do not duplicate them.

## 30-Second Explanation
Inside each replica, the engine runs an iteration-level scheduler: it
re-composes the batch every step (continuous batching), splits long prefills
into chunks that share steps with decodes (chunked prefill), pages KV like a
virtual-memory system (paged attention), and preempts when KV runs out. The
router's job is to feed each engine a queue it can absorb without thrashing —
and to never try to do L2's job from L1.

## The division of labor

| L1 (router) — owns | L2 (engine) — owns |
|---|---|
| Which replica/pool gets the request | Which requests run *this iteration* |
| Admission at the pool boundary | Preemption/eviction inside the replica |
| Cache-aware placement across replicas | Radix/paged prefix cache *within* a replica |
| ERW scoring from per-replica scalars | Chunk schedules from per-batch state |

The contract: **L1 may assume** L2 extracts near-maximal throughput from
whatever queue it is given, and **may not assume** anything about per-step
internals (chunk sizes, kernel choices, exact KV layout). A router that shapes
chunk schedules or guesses batch composition is an anti-pattern
[I: deep-dive §5.5] — it couples itself to engine internals it cannot see at
decision time.

## The four L2 mechanisms, in one paragraph each
- **Continuous batching**: requests join/leave the batch at every iteration,
  not every sequence boundary — the reason GPUs stay busy under heterogeneous
  output lengths. Full treatment: `../Continuous-Batching.md`.
- **Chunked prefill**: long prefills are split so decode ITL stays within SLO
  while prefill progresses; the engine's answer to the prefill/decode
  interference problem. Full treatment: `../Prefill-Decode-Disaggregation.md`
  and engine pages.
- **KV paging & prefix caching**: KV lives in blocks, shared via radix trees
  (SGLang RadixAttention) or block hashes (vLLM APC); what L1's "cache hit"
  signal actually refers to. Full treatment: `../../KV-Cache/README.md`,
  `../../KV-Cache/Eviction.md`.
- **Preemption**: when KV is exhausted, the engine swaps/recomputes
  lower-priority requests — catastrophic for latency, so L1's memory-pressure
  term ([03](03-estimating-remaining-work.md)) exists to keep L2 far from this
  regime.

Engine specifics: `../../Serving-Engines/vLLM.md` ·
`../../Serving-Engines/SGLang.md` · `../../Serving-Engines/TensorRT-LLM.md`.

## Signals L2 must export for L1 to work
Minimum viable telemetry per replica (≥10 Hz): queued prompt tokens, running
batch size, KV blocks free/total, prefix-cache hit counters, per-request
TTFT/TPOT histograms, preemption count. Engine-specific metric names:
see [12-observability-and-slos](12-observability-and-slos.md).

## Where the boundary blurs (legitimately)
- **Llumnix-style rescheduling** [F: arXiv:2406.03243]: engines migrate
  running requests between replicas mid-stream — an L2 mechanism doing L1
  work, from the inside. Complementary to L1 admission-time placement.
- **In-engine admission**: Mooncake's prediction-based early rejection
  [F: arXiv:2407.00079] happens inside the serving layer — fine, as long as
  the router learns the verdict immediately (it affects ERW of the pool).
- **P/D-aware engines**: engines that know their pool role change what L1's
  filters must check (see [09](09-pd-disaggregated-routing.md)).

## 80/20
You do not need to modify engines to route well. You need engines to *report*
token-queue depth, KV headroom, and cache hits. If your engine can't report
them, wrap it with a sidecar that infers them from request logs (weaker, but
better than flying blind).

## Failure modes
- **L1/L2 impedance**: router admits faster than the engine's queue can drain
  → engine queues grow → TTFT SLO dies inside L2 where L1 can't see it. Fix:
  router tracks engine queue tokens (not just its own placements).
- **Preemption surprise**: L2 preemption invalidates the cache-hit assumption
  of in-flight and future requests. Fix: subscribe to preemption/eviction
  events; age out cache-hit claims under KV pressure.
- **Cross-layer oscillation**: L1 moves load off a hot replica at the same
  time L2 finishes a long batch there → both overcorrect. Fix: act on
  different timescales (L1 per request, L2 per step) and damp L1 reactions to
  fast-recovering signals.

## How to measure it
- Engine-reported queue tokens vs router-estimated queue tokens (drift =
  telemetry gap).
- Preemption rate per replica (target ~0; any sustained rate = L1 admission
  or L3 capacity failure).
- Batch occupancy histogram per replica (is L2 actually being fed enough to
  batch?).

## Related
[01-production-serving-overview](01-production-serving-overview.md) ·
`../Continuous-Batching.md` · `../../KV-Cache/README.md` ·
`../../KV-Cache/Eviction.md` · `../../Serving-Engines/README.md` ·
`../Prefill-Decode-Disaggregation.md`

## Key Takeaways
1. L2 re-schedules every iteration; L1 places once per request. Respect the
   boundary.
2. The router's leverage over the engine is *what queue it hands over* —
   nothing more.
3. Engine telemetry (token queue, KV headroom, cache hits, preemptions) is
   the contract surface; get it before building anything smart at L1.
