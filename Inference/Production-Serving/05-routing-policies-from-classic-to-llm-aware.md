# Routing Policies — From Classic Load Balancing to LLM-Aware
`LAST_UPDATED: 2026-08-22` · Status: core page · Handbook-level summary of the
policy zoo; proofs and failure taxonomy in
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`.

## 30-Second Explanation
Classic load-balancing policies assume service times are IID and short. LLM
serving violates both, so every classic policy fails in a *characteristic* way.
The fix is not a fancier classic policy — it is scoring each candidate replica
by predicted remaining work ([03](03-estimating-remaining-work.md)) using five
signals: queue backlog **in tokens**, prefix-cache state, active decode work,
predicted output length, and KV state.

## The policy zoo and where each breaks

| Policy | Idea | Structural failure in LLM serving |
|---|---|---|
| Round-robin | next replica in rotation | Blind to load, cache, SLO. OK only if replicas homogeneous AND request sizes near-identical — rare in production. |
| Random | pick uniformly | Same blindness + no convergence on skew; useful as an A/B baseline only. |
| Least-connections | fewest open connections | Connections decouple from work (keep-alive, SSE streaming); anti-informative exactly when service times are heterogeneous. |
| Least-requests | fewest in-flight requests | Counts jobs, not work; blind to *future* decode length (a 50k-output request looks like a 30-token one at admission). |
| Power of two choices | pick 2 random, take less loaded | Strictly better than random under IID service; still uses count/load proxies blind to tokens and cache. |
| Session/token-hash stickiness | same session → same replica | Justified only as *cache* affinity; later turns may diverge — use cache-aware scoring, not stickiness. |
| **Token-queue** | least queued prompt tokens | First genuinely LLM-aware policy; strong when prefill-bound; ignores decode and cache. |
| **Cache-aware** | maximize prefix hit | Dominant signal in agentic/RAG workloads (50–90% hit rates plausible [I]); can hot-spot (see 08). |
| **Predicted-latency (ERW)** | argmin of full ERW | The general form (03); degrades gracefully to simpler policies when signals are missing. |

## The five signals (and five addenda)
Condensed from the deep-dive §3, where each is derived and failure-moded:

1. **Queue backlog in tokens** — `Q_tokens = Σ(S_j − hit_j)` over queued
   requests; dominant TTFT term under burst.
2. **Prefix-cache state of the request** — hit fraction `h_i(r)`; shrinks
   TTFT, queue footprint, and KV-write traffic simultaneously.
3. **Active decode work** — batch size, aggregate context, KV headroom.
   Weak signal below the routing-relevant range; decisive near the KV knee
   and in P/D decode pools (where decode backlog *is* the queue).
4. **Expected output length n̂** — input to decode work, KV reservation,
   admission; the most uncertain signal — carry it as quantiles.
5. **KV/prefix state of the replica** — free blocks, eviction pressure, hot
   prefixes; the cache is a shared resource with cross-tenant externalities.

Addenda the naive list misses (deep-dive §3.6): **SLO class/deadline**,
**fault domain & topology** (P/D pairing, fabric class), **fairness/tenant
weight**, **hardware heterogeneity/cost**, **cold-start state**.

## Evidence check (all [F], fetched READMEs, audit in /tmp/ps-research)
Every production system examined routes on a superset of the five signals —
none routes on raw connections:
- **llm-d EPP**: KV-cache utilization, prefix-cache locality, queue depth,
  active counts; experimental predicted-latency scheduler; vendor-reported 3×
  throughput + 2× TTFT vs round-robin with prefix-cache-aware routing.
- **NVIDIA Dynamo**: KV-aware routing on worker load + KV overlap.
- **SGLang**: RadixAttention in-engine + cache-aware load balancer.
- **vLLM Production Stack**: KV-cache-aware routing + prefix-aware.
- **AIBrix**: token-based, SLO-aware routing.
- **LiteLLM**: classic strategies (weighted pick, least-busy, latency-based,
  usage/cost-aware) — L0-gateway class, not KV-aware [F: docs.litellm.ai/docs/routing].

## Choosing a policy for your scale
- **1–2 replicas**: weighted RR + cache-affinity tie-break is ~90% of the value
  at ~10% of the complexity [I: deep-dive H5, engineering judgment].
- **Small pool, heterogeneous workload**: token-queue + cache hit (two-term
  ERW) — the 80/20 of [03](03-estimating-remaining-work.md).
- **Large pool / P/D / multi-tenant**: full ERW scorer with fairness and SLO
  filters (06, 09, 13).
The trigger to climb the ladder is measured heterogeneity: CV of service time
> ~0.5 (Lab 1) means count-based policies are leaking tail latency.

## 80/20
Replace "least connections" with "least **queued prompt tokens**, tie-broken by
prefix-cache hit." That two-signal policy is simple to implement, robust to
most failure modes in this page's table, and within reach of a afternoon's work
on top of any proxy that can read engine metrics.

## Failure modes
- **Herd behavior**: all routers independently pick the same argmax replica →
  oscillation. Mitigate with score jitter / two-choice sampling (06).
- **Signal staleness**: 50 ms-old state is 10 decode steps stale at 5 ms ITL
  [E]; treat scores as rankings, not truths.
- **Policy oscillation during deploys**: canarying a new scorer on 5% of
  traffic can starve it of the cache warmth it needs to win — evaluate routing
  changes on shadow decisions first (Lab 8 methodology).

## How to measure it
- Policy bake-offs on identical replayed workloads: P50/P99 TTFT, TPOT,
  goodput at SLO (pins: model, precision, GPU, engine+version, arrival λ,
  length distributions, cache warm-up — deep-dive §7).
- Misrouting rate: fraction of decisions where the chosen replica's realized
  TTFT was >2× the best candidate's (offline replay).

## Related
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[06-router-architectures](06-router-architectures.md) ·
[14-production-routers-comparison](14-production-routers-comparison.md) ·
`../../GPU-Systems/Load-Balancing.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. Classic policies fail *characteristically* on LLM workloads because service
   times are heavy-tailed, predictable, and cache-coupled.
2. The five signals (token queue, cache hit, decode work, n̂, KV state) are the
   observed production consensus [F].
3. Climb the policy ladder only as far as your measured heterogeneity
   justifies.
