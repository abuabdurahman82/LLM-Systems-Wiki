# Observability & SLOs — The Feedback Loop Made Concrete
`LAST_UPDATED: 2026-08-22` · Status: core page · Metric *definitions* live in
`../Inference-Metrics.md`; this page covers what to instrument so the L0–L3
control loops actually close.

## 30-Second Explanation
Every mechanism in this section is only as good as its telemetry. The minimum
viable observability set: per-request latency decomposition (TTFT / TPOT /
TTLT), per-replica state (token queue, batch, KV headroom, cache hits), and
**router decision logs** (what was scored, what was picked, what happened).
Without the third one you can never debug the router — you can only guess.

## The three metric planes

### 1. Request plane (what users feel)
- **TTFT** (time to first token), **TPOT/ITL** (inter-token latency),
  **TTLT** (total latency) — as histograms per model/tenant/SLO class.
  Definitions and pitfalls: `../Inference-Metrics.md`.
- **Goodput at SLO**: req/s where P99 stays inside target — the only
  throughput number that should appear on an executive dashboard.
- Decompose TTFT for P/D setups: queue + prefill + KV transfer (09).

### 2. Replica plane (what the router eats)
Per replica, exported at ≥10 Hz (07): queued prompt tokens, running batch
size, KV blocks free/total, prefix-cache hit counters, preemption count,
measured prefill/decode rates. This is the scorer's entire worldview — if a
signal is missing here, the corresponding ERW term is dead
([03](03-estimating-remaining-work.md)'s graceful-degradation table).

### 3. Decision plane (what the router did)
Per routing decision, log: candidate set after filters, per-candidate score
breakdown (each ERW term), chosen replica, state age at decision time, and —
joined later — realized TTFT/completion. This gives you:
- **Calibration**: predicted vs actual, per workload class (drives n̂ and
  weight tuning).
- **Oracle gap / misroute rate**: how often argmin-ERW ≠ argmin-actual.
- **Auditable incidents**: "why did request X go to the saturated replica?"
  is a log query, not a postmortem guessing game.

## SLOs and burn alerts
- Define SLOs per class (interactive: TTFT and TPOT; batch: TTLT and cost).
- Alert on **burn rate** (error-budget consumption speed), not on raw P99 —
  raw-P99 alerts fire during every burst; burn-rate alerts fire when the
  budget is actually threatened.
- Track admitted-set SLO attainment separately from rejection rate (10):
  a system can hit P99 by rejecting half the traffic — that is admission
  working, not serving working.

## Dashboards worth building (in order)
1. Pool heatmap: per-replica token-queue seconds + KV headroom (the remaining-
  work balance from [02](02-requests-are-not-equal.md) made visible).
2. SLO attainment vs offered load (the cliff, live — [04](04-queueing-theory-80-20.md)).
3. Cache: hit rate per replica, hot-prefix concentration, eviction rate (08).
4. Router: decision latency, state age, herd signature (06).
5. Capacity: goodput-at-SLO per replica, time-to-useful per scale event (11).

## 80/20
Per-replica token-queue seconds and KV headroom on one dashboard, plus a
router decision log you can replay offline. Those two unlock almost every
diagnosis in this section.

## Failure modes
- **Aggregated-away signals**: pool-averaged queue depth hides single-replica
  hot spots; always keep per-replica resolution.
- **Metric gaps disguised as zeros**: a missing KV metric read as "0% used"
  routes everything into OOM. Distinguish *absent* from *zero*; alarm on
  staleness of the metrics themselves.
- **Dashboards without actuators**: metrics nobody's control loop reads are
  decoration; every dashboard panel should name the layer (L0–L3) that acts
  on it.

## How to measure it
- Metric freshness histogram per replica (lag between engine emission and
  router visibility).
- Replay coverage: % of decisions reconstructable from logs (target 100%).
- Join latency: how fast realized outcomes link back to their decision
  records (drives how quickly you can detect scorer regressions).

## Related
`../Inference-Metrics.md` ·
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[06-router-architectures](06-router-architectures.md) ·
[15-failure-modes-and-operations](15-failure-modes-and-operations.md) ·
`../../GPU-Systems/GPU-Metrics.md` · `../../GPU-Systems/Profiling.md`

## Key Takeaways
1. Three planes: request (SLOs), replica (router input), decision (router
   audit). All three or the loop isn't closed.
2. Goodput at SLO is the only throughput metric that matters operationally.
3. Router decision logs turn routing incidents from guesswork into queries.
