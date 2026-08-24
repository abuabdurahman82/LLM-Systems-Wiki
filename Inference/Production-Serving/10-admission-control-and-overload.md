# Admission Control & Overload — Deciding *Whether*, Not Just *Where*
`LAST_UPDATED: 2026-08-22` · Status: core page · The overload counterpart of
[04](04-queueing-theory-80-20.md) (bounded queues) and
[03](03-estimating-remaining-work.md) (predicted latency).

## 30-Second Explanation
Past the utilization cliff, routing cannot help — every candidate is bad.
The decision that still matters is **admission**: reject (or hold) the
requests you cannot serve within SLO, so the admitted set keeps its SLO.
Unbounded queues turn overload into universal latency; bounded admission
turns it into partial errors. Production systems choose partial errors.

## Why admission beats queueing at overload
At ρ > 1 the queue grows without bound; every admitted request's latency
includes the drain of everything ahead of it ([04](04-queueing-theory-80-20.md)).
Admitting everything is a *global* SLO breach; rejecting the excess is a
*local* one — and clients with timeouts/retries can act on a fast 429 far
better than on a slow 200. Mooncake does prediction-based early rejection
in-engine and reports 75% more requests served in production scenarios
[F: arXiv:2407.00079, vendor-reported].

## The admission decision
Admit request r only if its predicted latency fits its SLO *and* its
reservation fits capacity:
```
admit(r) iff  predicted_completion(r, best_pool) < deadline(r)
          and  Σ reservations + n̂_P90(r)·kv_per_tok < KV_budget
```
- Use **P90 n̂** for the reservation (P50 under-reserves; the tail request is
  the one that forces preemption) [I: deep-dive §5.2; H3 is an open
  experiment].
- Reject **fast and informatively**: 429/503 + `Retry-After` + queue-position
  or expected-wait hint, so well-behaved clients back off instead of
  hammering (see retry amplification in
  [15](15-failure-modes-and-operations.md)).
- **Hold vs reject**: holding (parking at the gateway with a deadline) is
  better when overload is bursty and short (drain time < SLO slack); rejecting
  is better when overload is chronic (drain time ≫ SLO) — the burst math of
  [04](04-queueing-theory-80-20.md) decides which regime you are in.

## Where admission lives (unsettled split)
- **Router-level** (llm-d EPP flow control [F]): sees the whole pool, can
  compare across replicas, can redirect instead of reject. Right default.
- **Engine-level** (Mooncake [F]): has ground-truth KV state, acts after
  placement — necessary as a backstop even with router admission, because
  state moves between decision and arrival.
- **Gateway-level** (LiteLLM RPM/TPM caps [F]): per-tenant quota enforcement,
  blind to load — fairness, not overload protection (see 13).
Run router-level as primary, engine-level as backstop; they answer different
questions with different state.

## Priority classes under saturation
Admission is where priority becomes real. Define classes (e.g. interactive >
batch) and under saturation: admit higher classes first, and only let lower
classes in with *headroom-scaled* thresholds (a batch job that fits at ρ=0.5
does not fit at ρ=0.9). Preemption of running low-priority work is the engine's
tool (L2) — expensive (recompute); prefer refusing admission over preempting.

## 80/20
Add one check at your router/gateway today: `if predicted_queue_delay >
TTFT_SLO: return 429 + Retry-After`. Queue delay is estimable from
token-queue depth alone (two-term ERW) — no other machinery needed. This
single rule converts your worst overload incidents from "everyone times out"
to "excess load gets a clean error."

## Failure modes
- **Retry storms**: rejected clients retrying immediately multiply λ during
  overload; exponential backoff + jitter client-side, and `Retry-After`
  server-side.
- **Thundering admission**: after a hold, releasing all parked requests at
  once re-creates the burst; release at drain rate.
- **Reservation inflation**: P90 reservations on every request strand KV
  headroom at low load; scale reservation strictness to current pressure
  (adaptive quantile) [I].
- **Deadline-ignorant queueing**: a held request whose deadline already
  passed should be dropped, not served — check deadlines at *dispatch*, not
  just at admission.

## How to measure it
- Rejection rate and its correlation with realized P99 (the knob you're
  buying tail latency with).
- Admitted-set SLO attainment under overload (this should stay ~flat as
  rejection rises; if it doesn't, your predictor is mis-calibrated).
- Preemption rate (should fall toward 0 when admission works).
- Retry amplification factor: offered λ / unique-request λ.

## Related
[04-queueing-theory-80-20](04-queueing-theory-80-20.md) ·
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[13-multi-tenancy-fairness-priority](13-multi-tenancy-fairness-priority.md) ·
[15-failure-modes-and-operations](15-failure-modes-and-operations.md) ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §5

## Key Takeaways
1. Under overload, admission — not routing — is the decision that protects
   SLOs.
2. Admit iff predicted completion fits the deadline AND the KV reservation
   fits; use P90 output-length for reservations.
3. Reject fast (429 + Retry-After), hold only for short bursts, and keep an
   engine-level backstop.
