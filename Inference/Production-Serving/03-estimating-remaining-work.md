# Estimating Remaining Work — The Router's Core Equation
`LAST_UPDATED: 2026-08-22` · Status: core page · Builds on
[02-requests-are-not-equal](02-requests-are-not-equal.md); formal version in
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`.

## 30-Second Explanation
Routing well means answering one question per candidate replica: *"if I send
this request there, when does it finish?"* You answer it with a sum of
physically meaningful terms:

```
Estimated Remaining Work (ERW) =
      Queue Delay                  # drain what's already waiting
    + Prefill Work                 # process the uncached prompt tokens
    + Decode Work                  # generate the expected output tokens
    − Cache Benefit                # prefix hits subtract prefill work
    + Memory Pressure Penalty      # KV exhaustion risk → preemption cost
    + Placement / Communication    # KV transfer, topology, wrong-pool cost
```

Predicted completion time = `now + ERW` (with each term converted to seconds
via the replica's measured service rates). Route to the argmin. Every
production LLM router (llm-d, Dynamo, SGLang, AIBrix) implements some
approximation of this [F: READMEs, /tmp/ps-research audit 2026-08-22].

## The terms, one by one
Constants below are the verified 7B-BF16-on-H100 model from the deep-dive
(prefill rate TPR = 35.3k prompt-tok/s at MFU 0.5 [A for MFU]; KV = 0.114 MB/
token; decode step at batch B, 3k ctx = (14.0 GB + B·0.34 GB)/3.35 TB/s) [E:
verify_production_serving.py].

**1. Queue Delay** = tokens already waiting ÷ replica prefill rate.
`W_q(i) = Q_tokens(i) / TPR_i`. Measure the queue in **tokens** (a 50-request
backlog of 128k prompts ≠ 50 of 128 tokens). This is usually the dominant
term under burst: a 90k-token backlog on one replica = 2.55 s of pure wait [E].

**2. Prefill Work** = `S·(1 − h_i) / TPR_i`, where `h_i` is the fraction of
this request's prompt already in replica i's prefix cache. Note the cache
benefit is not a separate guess — it is a *reduction of prefill work*, which is
why the ERW formula subtracts it rather than adding a bonus term.

**3. Decode Work** = `n̂ × step_time(B_i + 1)`. Each decode step emits one
token per request, so a request's decode duration is its output length times
the per-step time at the batch it joins. Step time grows ~linearly with batch
until the KV-capacity knee (≈180 requests at 3k ctx on H100 [E]) — then
preemption, not slowdown, is the risk (term 5).

**4. Cache Benefit** — the subtraction side of term 2, but tracked separately
in implementations because it has second-order value: the request also *adds*
cache value for future requests (see
[08-cache-aware-routing](08-cache-aware-routing.md)).

**5. Memory Pressure Penalty** — nonzero when `(KV_used_i + n̂·kv_per_tok)`
approaches `KV_total_i`. A replica that fills its KV pool mid-stream preempts
(recompute) or evicts (destroying term 4's cache). Model as a hard filter below
a floor (e.g. reject candidates at >90% projected KV) plus a soft penalty above
a warning band [A: thresholds are tuning knobs].

**6. Placement / Communication Cost** — in colocated serving this is ~0. In
P/D-disaggregated serving it is the KV-transfer time from the chosen prefill
replica to the chosen decode replica over the actual fabric (NVLink ≫ PCIe ≫
RoCE; 400 GbE RoCE ≈ 47.5 GB/s effective [E]). See
[09-pd-disaggregated-routing](09-pd-disaggregated-routing.md) and
`../Prefill-Decode-Disaggregation.md`.

## Worked example [E]
Request R: S = 3,000 prompt tokens, n̂ = 600 output tokens, KV footprint
0.41 GB. Candidates on the verified model:

| Replica | State | Queue Delay | Prefill | Decode | ERW |
|---|---|---|---|---|---|
| **A** | hit 2,400/3,000; B=10→11 | 0 | 17.0 ms | 600 × 5.31 ms = 3.19 s | **3.20 s** |
| **B** | no hit; queue 90k ptok; B=6→7 | 2.55 s | 85.0 ms | 600 × 4.90 ms = 2.94 s | **5.57 s** |

Predicted completion differs by **1.7×**; TTFT by **155×** (17 ms vs 2.63 s).
Least-connections picks B (6 < 10 in flight) — wrong on both axes. Note the
decomposition tells you *why*: A wins on TTFT via cache, ties on decode via
similar step times, and B's queue delay alone exceeds A's entire ERW.

## From ERW to predicted completion time
ERW is in "seconds of work on replica i." Completion time adds two
refinements:
1. **Uncertainty**: n̂ is a distribution, not a point. Score with P50 for
   average latency, P90 for SLO admission and KV reservation. Track predictor
   calibration online; fall back to class priors on drift
   [I; deep-dive §3.4, §5.2].
2. **Interaction**: the request you place changes the state for the next one.
   Re-score per decision (state at ≥10 Hz) and never batch-assign from one
   snapshot — see herd avoidance in
   [06-router-architectures](06-router-architectures.md).

## Graceful degradation (when signals are missing)
| Available signals | ERW degenerates to | ≈ Policy |
|---|---|---|
| None | 0 for all | random / round-robin |
| Queue depth only | queue term | least-connections (weak) |
| + queue in tokens | W_q | least-token-queue (strong for prefill-bound) |
| + prefix-cache shadow | W_q + prefill | cache-aware (strong for agentic/RAG) |
| + batch state + n̂ | full ERW | predicted-latency routing |

Design the scorer so each term defaults to 0/unknown rather than crashing —
you get the best available policy for the telemetry you actually have [I; this
is H4/H5 territory in the deep-dive — open hypotheses, not settled fact].

## 80/20
Implement two terms first — **queue delay in tokens** and **prefill after
cache hit**. On colocated pools they capture most of the win (deep-dive H4
hypothesis); decode work and memory pressure become decisive only near the KV
knee or under P/D disaggregation.

## Failure modes
- **Point-estimate n̂**: systematically wrong on new workloads → mis-sized KV
  reservations → preemption storms. Use quantiles; monitor calibration.
- **Stale snapshots**: at 50 ms staleness, 10 decode steps of drift at 5 ms
  ITL [E]. Score as ranking, not truth.
- **Double-counting cache**: term 2 already includes the hit; adding a separate
  "cache bonus" over-credits warm replicas → hot-spotting (see 08).

## How to measure it
- Scatter predicted vs actual TTFT/completion per request (from router decision
  logs); report calibration error by workload class.
- Term dominance histogram: which term won the argmin, how often (tells you
  what your workload is actually bound by).
- Oracle gap: % of decisions where argmin ERW ≠ argmin actual latency
  (computable offline from logs).

## Related
[02-requests-are-not-equal](02-requests-are-not-equal.md) ·
[04-queueing-theory-80-20](04-queueing-theory-80-20.md) ·
[05-routing-policies-from-classic-to-llm-aware](05-routing-policies-from-classic-to-llm-aware.md) ·
`../../GPU-Systems/Load-Balancing.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. ERW = queue delay + prefill + decode − cache benefit + memory penalty +
   placement cost; predicted completion = now + ERW.
2. Every term is a *physical* quantity with a measurable estimator — no
   learned black box required to start.
3. Degrade gracefully: two terms (token queue + cache-aware prefill) capture
   most of the value on colocated pools.
