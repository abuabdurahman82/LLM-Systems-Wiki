# P/D-Disaggregated Routing — The Two-Level Placement Problem
`LAST_UPDATED: 2026-08-22` · Status: core page · Assumes
`../Prefill-Decode-Disaggregation.md` (KV transfer physics, break-even model)
and extends [03](03-estimating-remaining-work.md) term 6.

## 30-Second Explanation
With prefill and decode pools split, routing is **two coupled decisions**:
which prefill replica, then which decode replica — where the second choice's
cost includes shipping the KV cache from the first over a real fabric
(NVLink ≫ PCIe ≫ RoCE). Disaggregation buys independent TTFT/TPOT control;
the throughput comes from the *routing on top of it* [F/I: deep-dive §5.4].

## The two score functions
The pools have different physics, so they get different ERW reductions:

- **Prefill pool** (compute-bound, bursty): score on **prompt-token backlog +
  prefix hit**. `score_P(i) = W_q(i) + S·(1−h_i)/TPR_i`. Decode state of i is
  irrelevant.
- **Decode pool** (bandwidth-bound, long-lived): score on **decode backlog +
  KV headroom + transfer cost from the chosen prefill node**.
  `score_D(j|i) = Σ n̂_k / DRate_j + guard(KV_j) + c_xfer(i→j)`.
  Decode backlog (Σ remaining output tokens of admitted decodes) *is* the
  queue here [I: deep-dive §3.3].

## The KV-transfer cost term
`c_xfer(i→j) = KV_bytes(S) / effective_bandwidth(fabric i→j)`. Reference
numbers [E/F: deep-dive + P/D page]: KV for 7B GQA BF16 = 0.114 MB/token (so a
13k-context request moves ≈1.5 GB); 400 GbE RoCE ≈ 47.5 GB/s effective (≈32 ms
for that transfer) vs NVLink intra-node at ~900 GB/s (≈1.7 ms). Scale by your
model's KV/token (`2·L·h_kv·d_h·bytes`) — a 27B model moves several GB per
long request. Fabric choice changes whether disaggregation is viable at all
(the break-even model in `../Prefill-Decode-Disaggregation.md`).

## The coupling, and why there is no closed form
A globally latency-optimal router must sometimes **skip the highest-cache-hit
prefill node** when its decode partner is saturated — cache savings on one
pool vs queue delay on the other, priced in the same seconds. Production
answers [F/I]:
- Per-fabric-class transfer-cost terms in the score (DistServe-style
  bandwidth-aware placement; llm-d P/D pair selection).
- Pool-level autoscaling so no decode pod is chronically saturated (Dynamo
  SLA-based planner) — i.e. solve the chronic version of the problem at L3.
- Sustained KV demand > fabric capacity is a *capacity* failure: a router can
  only reject early ([10](10-admission-control-and-overload.md)).

## What the router must track additionally
- In-flight KV transfers (bytes in flight per link/pod) — a decode pod
  mid-receive has pre-committed HBM bandwidth [I].
- Pool roles and pairing constraints (which prefill pods can reach which
  decode pods at which fabric class).
- Per-pool SLO budgets: TTFT is owned by the prefill pool (+transfer), TPOT
  by the decode pool; the router splits the end-to-end SLO before scoring.

## When to disaggregate at all (routing view)
Colocated is simpler and wins when: contexts are short (KV transfer savings
don't bind), load is moderate, or the fabric is slow. Disaggregate when TTFT
and TPOT SLOs fight each other under continuous batching (prefill bursts
stomp decodes), when you can actually staff two pools, and when the fabric
moves per-request KV inside the TTFT budget. The physics and break-even:
`../Prefill-Decode-Disaggregation.md`; the placement math above decides
whether you *realize* the win — vLLM notes disagg alone "does NOT improve
throughput" [F, via P/D page]; llm-d reports up to 70% tok/s gain with P/D on
B200 [F: vendor-reported, AWS] — the difference is the routing layer.

## 80/20
If you run P/D: route prefill on (token queue + cache hit), route decode on
(decode backlog + KV headroom), and add `c_xfer` as a hard penalty per fabric
class. Most pairing sophistication beyond that is worth it only at large pool
counts.

## Failure modes
- **Symmetric blindness**: scoring both pools with one function (they measure
  different queues).
- **Transfer storms**: many large KV transfers converge on one decode pod or
  one link; track bytes-in-flight.
- **Orphaned KV**: decode pod selected after prefill fails/overloads → KV
  shipped to a pod that rejects. Preflight the decode admission *before*
  starting prefill (reserve KV headroom at pair-selection time).
- **Pool ratio drift**: fixed P/D ratios go stale as the workload mix shifts;
  feed goodput-at-SLO per pool to L3 ([11](11-autoscaling-and-capacity-planning.md)).

## How to measure it
- TTFT decomposition: prefill queue + prefill compute + KV transfer (three
  separate histograms).
- Per-link KV transfer throughput vs fabric rating.
- Pair regret: realized completion vs the best alternative pair (offline
  replay from decision logs).

## Related
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[06-router-architectures](06-router-architectures.md) ·
[10-admission-control-and-overload](10-admission-control-and-overload.md) ·
`../Prefill-Decode-Disaggregation.md` ·
`../../GPU-Systems/NCCL.md` · `../../GPU-Systems/Multi-Node.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §5.4

## Key Takeaways
1. P/D routing = two pool-specific score functions + a fabric-priced transfer
   term.
2. Decode backlog is the decode pool's queue; prompt-token backlog is the
   prefill pool's.
3. Disaggregation without good routing buys SLO control, not throughput —
   the router is where the throughput comes from [F/I].
