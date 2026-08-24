# Queueing Theory 80/20 for LLM Serving
`LAST_UPDATED: 2026-08-22` · Status: core page · The 20% of queueing theory
that explains 80% of production behavior.

## 30-Second Explanation
Three facts explain most production latency behavior:
1. **Little's law**: wait ≈ work in queue ÷ service rate — and the queue is
   measured in *tokens*, not requests.
2. **The utilization cliff**: mean response stretch grows like `1/(1−ρ)`;
   at 90% utilization you pay 10× the service time, at 95%, 20× [E].
3. **Variance multiplies wait**: Pollaczek–Khinchine — mean queue wait scales
   with `(1 + C²)/2` where C² is the service-time variance ratio. LLM service
   times have C² ≫ 1 (see
   [02-requests-are-not-equal](02-requests-are-not-equal.md)), so you sit
   *deeper* into the cliff than a uniform-workload system at the same ρ.

## The five tools

### 1. Little's law, in tokens
`L = λ·W`. Applied to a prefill queue: queued work `Q_tokens` drains at the
replica's prompt-token rate, so the last arrival waits `Q_tokens / TPR`.
Worked [E: verify_production_serving.py]: a burst of 100 × 3k prompts
(300k tokens) on a 3-replica pool at 35.3k ptok/s each drains in **2.83 s**
(mean wait ~1.4 s); misrouted onto one replica, **8.49 s**. The same burst at
128-token prompts drains in 0.12 s — identical "100 requests," 70× different
wait. This is why every queue metric in this section is in tokens.

### 2. The utilization cliff (M/M/1 intuition)
For a memoryless server, mean response time = service time × `1/(1−ρ)`:

| ρ (utilization) | 0.5 | 0.7 | 0.8 | 0.9 | 0.95 |
|---|---|---|---|---|---|
| Latency stretch | 2× | 3.3× | 5× | 10× | 20× |

[E: verify_production_serving.py]. Two operational consequences:
- **Plan capacity at ρ ≤ 0.7–0.8**, not ρ ≈ 1. A pool sized to "exactly meet"
  average demand has *infinite* mean queue in the model — and in practice,
  unbounded P99.
- The marginal cost of the last 10% of utilization is enormous: going
  ρ = 0.8 → 0.9 doubles stretch (5× → 10×). Overprovisioning 20% is cheaper
  than it looks because the tail is what users remember.

### 3. Variance multiplies wait (Pollaczek–Khinchine)
For general service times (M/G/1), mean queue wait
`Wq ∝ (1 + C_s²)/2 · ρ/(1−ρ) · E[S]`. The `(1 + C_s²)/2` factor is pure
service-time variance:

| Service-time C² | 0 (deterministic) | 1 (exponential) | 4 | 9 |
|---|---|---|---|---|
| Wait multiplier | 1× | 1× (baseline M/M/1) | 2.5× | 5× |

[E]. Production LLM mixes routinely sit at C² = 2–10 [I — workload-dependent;
Lab 1 measures it]. Two mitigations, both used by real systems:
- **Reduce C² by splitting the workload**: separate pools for short vs long
  requests (P/D disaggregation is partly this — `../Prefill-Decode-Disaggregation.md`;
  so is per-SLO-class pooling, see
  [13-multi-tenancy-fairness-priority](13-multi-tenancy-fairness-priority.md)).
- **Steal the variance's information**: LLM service time is *partially known
  at arrival* (S is known, n̂ is predictable). Routing on that knowledge is
  scheduling with a size-aware policy — the entire point of
  [03-estimating-remaining-work](03-estimating-remaining-work.md).

### 4. Bursts and drain time
Arrivals are Poisson-ish on average and *bursty* in reality (agent fan-outs,
retries, cron). The number that matters is drain time `T_drain = Q / (pool
rate)`: if a burst's drain time exceeds your TTFT SLO, no router can save you —
only admission control ([10-admission-control-and-overload](10-admission-control-and-overload.md))
or more replicas ([11-autoscaling-and-capacity-planning](11-autoscaling-and-capacity-planning.md)).
Rule: keep `P99 burst size / pool rate < TTFT SLO`.

### 5. Backpressure and bounded queues
An unbounded queue converts overload into *latency for everyone*; a bounded
queue converts it into *errors for some*. Production systems choose the second:
bounded queues + fast rejection (429/503 with `Retry-After`) keep the
admitted set inside its SLO. The deep-dive's Mooncake reference
(prediction-based early rejection) is the in-engine version [F:
arXiv:2407.00079]. At the gateway, the analogue is per-tenant concurrency caps
and quota enforcement ([13](13-multi-tenancy-fairness-priority.md)).

## What queueing theory does NOT tell you here
- **Optimal policy under size-aware, cache-coupled routing** — no closed form;
  the deep-dive's H1–H5 are open experiments, not theorems.
- **Service times are not exogenous**: batching makes service rate depend on
  the batch composition (decode step time grows with B [E]). Treat ρ as a
  moving target and re-derive it from measured step times, not static specs.
- **Correlated arrivals**: agentic fan-outs arrive as bursts of related
  requests sharing prefixes — violates the independence assumptions; this is
  where cache-aware routing (08) earns its keep.

## 80/20
Measure three numbers continuously — ρ per replica, C² of service time, and
burst drain time vs TTFT SLO. ρ > 0.8 → add capacity. C² > 2 → split pools or
adopt size-aware routing. Drain time > SLO → admission control. That covers
most incidents you will ever see.

## Failure modes
- **Sizing to mean load**: ρ = 1 at the mean → unbounded tail at P99.
- **Request-count queues**: hiding token skew behind a count (see 02).
- **Ignoring retry amplification**: client retries during overload multiply λ;
  a 30% retry rate at ρ = 0.95 is a feedback loop into collapse (see
  [15-failure-modes-and-operations](15-failure-modes-and-operations.md)).
- **Treating throughput saturation as the capacity limit**: KV-capacity knee
  can bind first at long context (≈180 concurrent 3k-ctx requests per H100 in
  the reference model [E: deep-dive §1.1]).

## How to measure it
- ρ per replica = busy time / wall time (or tokens processed / rated rate).
- C² from logged per-request service times (gateway or engine traces).
- Arrival process: inter-arrival distribution + burst-size histogram.
- Little's-law consistency check: `mean queue depth ≈ λ × mean wait` — if it
  doesn't hold, your telemetry is lying somewhere.

## Related
[02-requests-are-not-equal](02-requests-are-not-equal.md) ·
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[10-admission-control-and-overload](10-admission-control-and-overload.md) ·
[11-autoscaling-and-capacity-planning](11-autoscaling-and-capacity-planning.md) ·
`../Inference-Metrics.md` · `../Roofline.md`

## Key Takeaways
1. Little's law in tokens; the queue's currency is work, not requests.
2. `1/(1−ρ)` is a cliff: run at ρ ≤ 0.7–0.8, and treat the last 10% of
   utilization as the most expensive capacity you own.
3. Service-time variance (C²) multiplies queue wait — reduce it (pool
   splitting) or exploit its predictability (size-aware routing).
