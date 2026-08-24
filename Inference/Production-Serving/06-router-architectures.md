# Router Architectures — Where the Scorer Lives and How It Stays Sane
`LAST_UPDATED: 2026-08-22` · Status: core page · Mechanism deep-cut for the
L1 layer defined in [01](01-production-serving-overview.md).

## 30-Second Explanation
An LLM router is a **control plane bolted onto a data plane**: a proxy parks
the request, a scorer ranks candidate replicas by ERW
([03](03-estimating-remaining-work.md)), and a picker commits — all inside a
latency budget of a few milliseconds, on state that is already going stale.
The architecture question is *where the scorer runs* and *how fresh its state
is*, not which algorithm it implements.

## Deployment shapes

| Shape | How | Used by | Trade-off |
|---|---|---|---|
| **In-process library** | routing logic inside the client/gateway process | LiteLLM Router [F] | Zero network hop; sees only what the process tracks; L0-class signals (no KV state) |
| **Sidecar proxy** | per-node or per-pool proxy intercepts and routes | SGLang router [F] | Local view, fast; needs a control loop to share cross-node state |
| **ext-proc / EPP** | gateway (Envoy) delegates the pick to an Endpoint Picker service | llm-d, Gateway API Inference Extension [F] | Clean separation, language-agnostic, hot path adds one RPC; the converged production pattern |
| **In-engine** | the engine itself admits/places (cluster-aware engine) | Dynamo planner + KV-aware router [F] | Freshest state; couples scaling and routing; engine-specific |

The converged architecture [F/I, deep-dive §2]: a sidecar/ext-proc plane that
is **never inline in the engine's hot path**, a data layer that watches cluster
state asynchronously (K8s API + engine metrics), a **filter → scorer → picker**
plugin pipeline, and a flow-control stage that can hold or reject.

## The decision pipeline
```
request → FILTERS (hard constraints) → SCORERS (soft costs) → PICKER (commit)
```
- **Filters**: model/adapter match, KV headroom floor, SLO class, fault
  domain, cold-start exclusion. A replica that fails a filter is not "more
  expensive" — it is *ineligible*. (Sending a 70B request to a 7B replica is a
  404/quality disaster, not a latency penalty.)
- **Scorers**: ERW terms from [03](03-estimating-remaining-work.md), weighted
  per workload. Keep them O(1) scalars: at 1,000 replicas × ~20 scalar ops the
  argmax is microseconds [A] — the ext-proc RPC, not the math, is the budget.
- **Picker**: argmax with anti-herd measures (below); emits the decision +
  the score breakdown to the decision log ([12](12-observability-and-slos.md)).

Reference scorer (adapted from deep-dive §8 [I]):
```
score(r, i) = -( W_q(i) + S*(1-h_i)/TPR_i + n_hat_P90/DRate_i + c_xfer(i) )
              - guard(KV_headroom_i, n_hat_P90 * kv_per_tok)
              + w_cache_value(i, r) + w_slo(r, i)
pick i* = argmax over filtered candidates
```

## State propagation and staleness
The scorer's state is a snapshot; the cluster keeps moving. Budget the
staleness: at 5 ms ITL, a 50 ms-old snapshot is 10 decode steps stale [E].
Design rules:
- Push per-replica **scalars** (queue tokens, batch size, KV free, hit-map
  digests) at ≥10 Hz; pull-on-decision does not scale (it puts a fan-out read
  in the request path).
- Treat scores as **rankings stable to 10–20% noise**, not exact predictions;
  when the top-2 gap is within noise, choose cheaply (random or cache-biased).
- In P/D setups, track **in-flight KV transfers** as load — a decode pod
  receiving 4 GB of KV over RoCE has pre-committed HBM bandwidth [I].

## Herd avoidance
Deterministic argmax creates a thundering-herd failure: every concurrent
decision picks the same "emptiest" replica, which then spikes while others
drain. Mitigations (compose them):
1. **Score jitter**: add small random noise proportional to the score scale.
2. **Power of two choices on scores**: pick 2 candidates at random, take the
   better score — provably robust to stale state [classic result; I here].
3. **Anticipatory accounting**: increment the chosen replica's queue estimate
   *at decision time* (by this request's S·(1−h)), so the next decision sees
   the placement before the metrics pipeline reports it. This is the single
   most important herd fix — it makes the router's own decisions
   self-consistent at sub-metrics-latency.

## Decision latency budget
Every millisecond of router latency adds to every request's TTFT. Budget
[I/A]: < 1 ms for scoring (O(replicas) scalar math), < 5 ms for the ext-proc
round trip, zero synchronous external calls (no DB, no remote cache lookup) in
the decision path. Anything slower belongs in the async data layer.

## 80/20
Filter → two-term scorer (token queue + cache hit) → argmax-with-jitter →
anticipatory accounting. That pipeline, in any proxy, outperforms a
sophisticated scorer fed by slow state.

## Failure modes
- **Cold-start dump**: a fresh replica has maximal KV headroom and an empty
  cache; naive scoring sends it a burst it serves slowly (un-warmed CUDA
  graphs, cold prefix cache). Penalize or cap new replicas for a warm-up
  window.
- **Split-brain scorers**: multiple router replicas with divergent state →
  oscillating placements. Prefer a single active scorer per pool, or shard
  pools per scorer.
- **Metrics feedback loop**: routing on a metric your own placements distort
  (e.g. "GPU util") without anticipatory accounting → oscillation at the
  metrics period.

## How to measure it
- Decision latency histogram (p50/p99) and its share of TTFT.
- State age at decision time (decision_ts − metric_ts).
- Herd signature: per-replica placement rate autocorrelation at the metrics
  period; post-fix, placement spread should track score spread, not collapse
  to argmax.

## Related
[03-estimating-remaining-work](03-estimating-remaining-work.md) ·
[05-routing-policies-from-classic-to-llm-aware](05-routing-policies-from-classic-to-llm-aware.md) ·
[08-cache-aware-routing](08-cache-aware-routing.md) ·
[14-production-routers-comparison](14-production-routers-comparison.md) ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. Production routers converge on filter → scorer → picker in an ext-proc /
   sidecar plane, never in the engine hot path.
2. Staleness is the binding constraint: cheap scalars at ≥10 Hz, scores as
   rankings, anticipatory accounting to stop herds.
3. Scoring math is microseconds; the RPC and the state pipeline are the
   budget.
