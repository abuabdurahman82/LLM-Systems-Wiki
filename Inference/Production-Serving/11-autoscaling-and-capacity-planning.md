# Autoscaling & Capacity Planning — The L3 Loop
`LAST_UPDATED: 2026-08-22` · Status: core page · The slow control loop from
[01](01-production-serving-overview.md); consumes [04](04-queueing-theory-80-20.md)'s
utilization math.

## 30-Second Explanation
L3 decides *how many* replicas exist per pool. The input is offered load in
**tokens** (not requests); the target is ρ ≤ 0.7–0.8 with KV headroom; the
obstacle is that LLM replicas take minutes to become useful (weights load,
CUDA-graph capture, cache warm-up). Scale on *leading* indicators (token-queue
depth trend, KV headroom trend), not on the lagging one (P99 already
breached).

## Capacity math that actually works
Required replicas per pool ≈ offered-token-rate / safe-rate, where safe-rate
= measured token throughput × ρ_target:
```
replicas ≥ ceil( λ_tokens / (TPR_effective × ρ_target) )
```
with ρ_target = 0.7–0.8 ([04](04-queueing-theory-80-20.md): the cliff makes
ρ≈1 sizing meaningless). Derive `TPR_effective` from *measured* rates under
your workload mix — the reference model's 35.3k ptok/s prefill and ~2.2k
tok/s aggregate decode at B=12 [E] are model+hardware+MFU-specific; re-derive,
don't copy. Add constraints the mean hides:
- **KV-capacity ceiling**: concurrent long-context decodes per replica are
  bounded by KV pool size (≈180 at 3k ctx on H100 in the reference model
  [E: deep-dive]) — at long contexts this binds *before* compute.
- **Burst drain**: P99 burst / pool rate < TTFT SLO ([04]).
- **N+1 (or N+2)**: losing a replica at ρ=0.8 pushes the rest to ρ≥1 —
  size for the failure case, not the steady case.

## Scaling signals (leading → lagging)
1. **Token-queue depth trend** (seconds of queued work) — earliest; scale out
   when drain time exceeds SLO slack.
2. **KV headroom trend** — scale out before preemption starts; preemptions
   mean you were already late.
3. **Goodput at SLO** (req/s with P99 ITL inside target) — the honest
   utilization metric; scale when goodput saturates even if raw throughput
   hasn't peaked.
4. GPU util / power — weak proxy (see 02); use only as a sanity floor.
Scale-*in* on the reverse signals with long cooldowns — flapping replicas are
worse than slightly idle ones, because cold starts are expensive (below).

## Cold start is the hidden constant
A new replica is not capacity until it has: loaded weights (minutes for large
models over network storage), captured CUDA graphs, warmed JIT kernels, and —
critically — **warmed its prefix cache**. Routing floods a fresh replica
because it looks empty (see cold-start dump, [06](06-router-architectures.md));
its actual goodput is a fraction of nominal for the first minutes. Handle by:
warm-up traffic caps, explicit cold-start penalty in the scorer, and
pre-warming shared prefixes (08) during bring-up.

## SLA-based planners
Dynamo's planner [F: README] is the reference pattern: given a target SLO, it
simulates/measure the per-pool capacity needed and scales prefill and decode
pools *independently* (including the P/D ratio — see
[09](09-pd-disaggregated-routing.md)). K8s-native equivalent: HPA/KEDA on
custom metrics (token-queue seconds, KV headroom) rather than CPU/GPU util.
Either way, the loop period is minutes — L3 absorbs *trend* changes, not
bursts; bursts are L1's admission problem ([10](10-admission-control-and-overload.md)).

## Capacity worksheet (per pool)
1. Measure: arrival token rate (P50/P99), service-time C², KV per request at
   P90 (S+n̂), target SLOs.
2. Compute replicas at ρ_target; apply KV ceiling; add N+1.
3. Verify burst drain < TTFT SLO at P99 burst.
4. Set autoscale triggers: queue-seconds trend, KV headroom floor, goodput
   ceiling; cooldowns ≥ 2× cold-start time.
5. Re-derive monthly or on any model/engine/hardware change.

## 80/20
Size with `replicas = offered_tokens / (measured_rate × 0.75) + 1`, trigger
scale-out on token-queue seconds, and set cooldowns longer than cold start.
That beats any util-based HPA config for LLM pools.

## Failure modes
- **Util-based autoscaling**: GPU util saturates late and ambiguously (02) →
  scale-out arrives after the tail is already dead.
- **Cold-start thrash**: cooldown < cold-start time → replicas killed before
  they ever served at nominal → capacity seesaw.
- **Pool-ratio ossification**: fixed P/D replica ratios while the S:n̂ mix
  drifts → one pool saturated, the other idle (09).
- **Scaling into a storage wall**: N replicas simultaneously pulling
  100+ GB weights from one registry/bucket — pre-bake images or use a local
  model cache (your `~/models` NFS/HF-cache pattern).

## How to measure it
- Time-to-useful per scale-out event (start → first request inside SLO).
- Scale-out precision: % of events followed by sustained ρ in target band
  (vs. immediate scale-in).
- Goodput-at-SLO per replica over time (the definitive capacity metric).

## Related
[04-queueing-theory-80-20](04-queueing-theory-80-20.md) ·
[09-pd-disaggregated-routing](09-pd-disaggregated-routing.md) ·
[10-admission-control-and-overload](10-admission-control-and-overload.md) ·
[12-observability-and-slos](12-observability-and-slos.md) ·
`../../GPU-Systems/Scale-Up-vs-Scale-Out.md`

## Key Takeaways
1. Scale on tokens and KV headroom, never on request rate or raw GPU util.
2. ρ_target = 0.7–0.8 plus N+1; the cliff punishes "just enough" capacity.
3. Cold start (weights + graphs + cache warm-up) is minutes of false
   capacity — route and scale around it explicitly.
