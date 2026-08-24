# Requests Are Not Equal — The Core Mental Model
`LAST_UPDATED: 2026-08-22` · Status: core page · Anchors the whole section.

## 30-Second Explanation
**Do not balance requests. Balance remaining work.** A request count is nearly
meaningless in LLM serving because two requests with identical connection
counts can differ by ~20× in actual remaining compute
[E: deep-dive §4, same-connections trap — 18.4 s vs 0.99 s at B=2].
Every routing, batching, and admission decision that treats "1 request" as a
unit of work is making an error that grows with workload heterogeneity — and
production workloads are *always* heterogeneous.

## The twelve dimensions of request heterogeneity
A request arriving at the router is characterized by (at least) twelve
properties, each of which can vary by 10–1000× across a real traffic mix:

| # | Dimension | Typical range | What it changes |
|---|---|---|---|
| 1 | Prompt length S | 100 → 1M tokens | prefill cost (∝S), TTFT |
| 2 | Expected output length n̂ | 20 → 50k tokens | decode duration (∝n̂), KV residency time |
| 3 | Prefill cost | compute-bound, ∝S FLOPs | GPU-seconds before first token |
| 4 | Decode cost | bandwidth-bound, per-step | HBM bandwidth share for n̂ steps |
| 5 | KV-cache footprint | 2·L·h_kv·d_h·(S+n̂)·bytes | how much scarce HBM the request holds |
| 6 | Prefix-cache hit probability | 0 → 90%+ | *effective* prefill cost on a warm replica |
| 7 | Model / adapter | model id, LoRA id | which replicas can serve it at all |
| 8 | GPU memory requirement | KV headroom needed | feasibility, preemption risk |
| 9 | Priority / tenant weight | batch → interactive | queue position, preemption rights |
| 10 | Latency SLO | TTFT/TPOT targets | admission and placement constraints |
| 11 | Agent/tool workflow | single-shot → 500-turn loop | request *shape over time* (bursts, shared prefixes) |
| 12 | Multimodal content | text → images/audio/video | extra encoder compute, non-token memory |

Dimensions 1–6 determine *how much work*; 7–8 determine *where it can run*;
9–10 determine *how urgently*; 11–12 determine *how the workload composes*
(agents generate correlated request streams with heavy shared prefixes — see
`../../Agents/Agent-Loops-and-Reasoning-Strategies.md`).

## Why counting fails, quantitatively
From the verified model in the router-signals deep-dive (7B BF16 on H100;
all numbers [E], audit in `../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`):

- Prefill of one 3,000-token prompt at MFU 0.5 costs ~85 ms of GPU time; a
  128-token prompt costs ~3.6 ms — **24× spread** on dimension 1 alone.
- One decode step at batch B=2 with 3k contexts takes 4.39 ms; a request with
  4,000 tokens left occupies ~17.5 s of decode residency; one with 200 tokens
  left, ~0.9 s — **~19× spread** on dimension 2 at identical request count.
- A 2.4k/3k prefix-cache hit turns an 85 ms prefill into 17 ms — **5× spread**
  on dimension 6 for *identical prompts on different replicas*.

Multiply the dimensions and "requests in flight" explains almost none of the
variance in remaining work. The coefficient of variation (CV) of service time
in a mixed agentic+RAG+chat workload is typically ≫1 [I — measure yours; Lab 1],
which is precisely the regime where least-connections and round-robin diverge
from optimal (see [04-queueing-theory-80-20](04-queueing-theory-80-20.md)).

## The same-connections trap (canonical example)
Two replicas, each with exactly 2 in-flight decodes (3k-token contexts):

- **Replica X**: 32k-token prefill queue + 2 decodes with 4,000 tokens left
  each → **18.4 s of remaining work**.
- **Replica Y**: 4k-token queue + 2 decodes with 200 tokens left each →
  **0.99 s of remaining work**.

Identical connections. Identical request counts. **~19× difference** in
remaining work [E: deep-dive §4]. Least-connections is indifferent between
them; a remaining-work router is not. This single example is the whole argument
for [03-estimating-remaining-work](03-estimating-remaining-work.md).

## Consequences for each scheduling level
- **L0 (gateway)**: per-tenant quotas in *tokens*, not just requests — a
  30 RPM tenant sending 128k prompts is not "30 RPM" of load.
- **L1 (router)**: score candidates by predicted remaining work, not counts
  (pages 03, 05, 06).
- **L2 (engine)**: continuous batching exists *because* requests differ —
  uniform workloads wouldn't need iteration-level re-scheduling
  (`../Continuous-Batching.md`).
- **L3 (autoscaler)**: scale on token-throughput saturation and KV headroom,
  not on request rate.

## 80/20
Measure the prompt-length and output-length distributions of your traffic
(Lab 1). If the CV of either is above ~0.5, count-based balancing is already
costing you double-digit tail-latency percentage. That one measurement decides
how much of this section you need.

## Failure modes
- **"Utilization looks fine"** — GPU util can read 90% while remaining work is
  wildly imbalanced, because util doesn't distinguish 2 long decodes from 20
  short ones.
- **Averaging away the tail**: mean service time hides the heavy tail that
  drives P99; report P50/P90/P99 of S and n̂ separately.
- **Assuming `max_tokens` = n̂**: clients set loose caps; use predicted output
  length with uncertainty bands ([03](03-estimating-remaining-work.md)).

## How to measure it
- Prompt/output length histograms per endpoint (gateway logs or engine
  metrics); compute CV.
- Remaining-work skew: per-replica `Σ(remaining prefill tokens) + Σ(remaining
  output tokens) / drain rate`, sampled at 10 Hz — should be balanced across
  replicas; if request counts are balanced but this isn't, your router is
  count-based.
- Cache hit-rate per replica (dimension 6).

## Related
[01-production-serving-overview](01-production-serving-overview.md) ·
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
`../The-Life-of-a-Token.md` · `../Inference-Metrics.md` ·
`../../GPU-Systems/Load-Balancing.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. A request is not a unit of work — it varies along ~12 dimensions, each with
   10–1000× range.
2. Identical connection counts can hide ~19× differences in remaining work [E].
3. Measure your workload's heterogeneity (CV of S and n̂) before choosing a
   routing policy.
