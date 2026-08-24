# Failure Modes & Operations — The Incident Catalog
`LAST_UPDATED: 2026-08-22` · Status: core page · Runbook companion to the
whole section; each entry names detection signal + first mitigation.

## 30-Second Explanation
Production LLM serving fails in a *short list of characteristic ways*, most of
them invisible to request-count monitoring. Learn the signatures below and
most incidents become a dashboard lookup, not an investigation.

## The catalog

| # | Failure | Signature (detection) | First mitigation | Deep link |
|---|---|---|---|---|
| 1 | **Hot-spotting** | top-1 replica traffic share ≫ peers; its KV fills | cap cache-driven placement; pin hot prefixes | 08 |
| 2 | **Stale-state misrouting** | decisions made on >100 ms-old state; sudden TTFT spikes after load shifts | raise metric rate; anticipatory accounting; treat scores as rankings | 06 |
| 3 | **n̂ drift** | output-length predictor calibration error spikes after a workload change | online calibration tracking; fall back to class priors | 03 |
| 4 | **Preemption storm** | engine preemption count > 0 sustained | admission check with P90 reservation; scale out on KV headroom | 10, 11 |
| 5 | **Herd routing** | placements all land on one replica per metrics period; oscillation at that period | score jitter; two-choice; anticipatory accounting | 06 |
| 6 | **Cold-start dump** | new replica gets a burst, serves it slowly | warm-up cap; cold-start penalty in scorer; pre-warm prefixes | 06, 11 |
| 7 | **Retry amplification** | offered λ / unique λ > 1.2 during overload | 429 + Retry-After; client backoff+jitter; hold-don't-queue | 10 |
| 8 | **KV transfer storm** (P/D) | per-link transfer throughput at fabric rating; decode pods stalled on receive | bytes-in-flight tracking; fabric-class cost term; capacity fix at L3 | 09 |
| 9 | **Thundering admission release** | post-hold release re-creates the burst | release parked requests at drain rate | 10 |
| 10 | **Quota gaming** | tenant within RPM but pool saturation tracks their TPM | token-based quotas | 13 |
| 11 | **Metric-gap-as-zero** | a missing metric reads 0 → routing into OOM/saturated replicas | staleness alarms; filters require *fresh* signals | 12 |
| 12 | **Pool-ratio ossification** (P/D) | one pool saturated, other idle as S:n̂ mix drifts | per-pool goodput to L3; dynamic P/D ratio | 09, 11 |
| 13 | **Cache churn** | hit rate collapsing while evictions spike | cache-value accounting; per-tenant namespaces | 08, 13 |
| 14 | **L1/L2 impedance** | engine queue tokens grow while router thinks pool is fine | router tracks engine-side queue, not just own placements | 07 |
| 15 | **Util-metric complacency** | GPU util ~90%, yet tails dead (or util 40% and fine) | replace util with token-queue seconds + goodput-at-SLO | 02, 12 |

## Operational hygiene
- **Decision-log replay before policy changes**: evaluate any scorer change
  on recorded decisions (shadow mode) before canarying — a scorer that wins
  in shadow can still lose live if it changes cache warmth (05, 12).
- **Runbook order**: check (a) pool heatmap (hot spots?), (b) preemptions
  (memory pressure?), (c) state age (stale?), (d) rejection rate (admission
  working?), (e) retry amplification (client behavior?). This order resolves
  most incidents in minutes [I].
- **Change one weight at a time**: ERW term weights interact; A/B on shadow
  decisions with pinned workloads (deep-dive §7 pins).

## 80/20
Alarm on four things: per-replica token-queue seconds, preemption count,
metrics staleness, retry amplification. These catch 1, 2, 4, 5, 7, 11 — the
majority of the catalog — before users report anything.

## Related
[06-router-architectures](06-router-architectures.md) ·
[10-admission-control-and-overload](10-admission-control-and-overload.md) ·
[12-observability-and-slos](12-observability-and-slos.md) ·
`../../GPU-Systems/Diagnostics.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §5

## Key Takeaways
1. The failure set is small and characteristic — instrument for the
   signatures, not for everything.
2. Most "model is slow" incidents are routing/admission/telemetry incidents
   (hot spots, stale state, herds, retries).
3. Replay decision logs before changing the scorer; never canary blind.
