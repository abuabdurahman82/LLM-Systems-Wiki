# Implementation 03 — KV-Aware Routing: How the Router Picks the Warm Worker
`LAST_UPDATED: 2026-08-26 · Status: implementation page (PART 2 series)` · Concept (the
reuse stack, hit *fraction*, stable-prefix ordering) in `KV-Cache/Prompt-and-Prefix-Caching.md`;
routing *policy* theory in `Inference/Production-Serving/08-cache-aware-routing.md` and
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`. This page owns the
**implementation**: the concrete data structures and scoring that Dynamo's router and
llm-d's EPP use to answer "which worker has this request's prefix resident, and is it loaded?"

## 30-Second Explanation
KV-aware routing = compute, per candidate worker, a score = **f(cache overlap, load)** and
send the request to the max. The two implementations differ in *where the cache-overlap
signal lives*: **Dynamo** keeps a **router-owned global radix-tree registry**; **llm-d**
reads an **event-driven global index assembled from engine KV events** and (optionally)
adds a **learned XGBoost latency predictor**. Same scoring problem, different substrate.

## The scoring problem, precisely
A router must place a request whose prompt may share a prefix with blocks resident on
worker W. The two signals (from the router deep-dive + `Distributed-Inference/Overview.md` §KV-Aware Routing):
1. **Cache overlap** — how much of this request's prefix is cached on W, at which tier.
   Dictates the prefill compute avoided **and** (in P/D) the KV transfer fraction (1−h).
2. **Load / remaining work** — W's queue depth and the request's expected decode length;
   balance *work*, not requests (the ERW principle).

Score = combine the two; a naive "send to the most-cached worker" overloads it, so both
platforms balance cache-hit-rate and load — Dynamo's doc phrasing is verbatim "directs
requests to the worker with the highest cache hit rate while maintaining load balance"
[F: v0.8.0 design doc].

## Dynamo — the radix-tree registry router (implementation)
From the current README + design docs [F, fetched 2026-08-26]:
- **Data structure**: the router maintains a **global radix tree registry** of KV-cache
  state — the structural cousin of SGLang's in-process RadixAttention cache
  (`GPU-Systems/SGLang.md`), lifted to the whole cluster.
- **Topologies** (README): **Dynamo-native Frontend routing** (Dynamo Frontend serves HTTP
  and the integrated Dynamo Router decides) vs **Gateway API + GAIE** (a K8s Gateway API
  Inference Extension gateway calls the Dynamo **Endpoint Picker Plugin / EPP** before
  forwarding to the chosen worker's Frontend sidecar in `--router-mode direct`).
  Request flow: `client → Frontend → Router → workers` (native) or
  `client → Gateway → EPP → Frontend sidecar (direct) → workers` (GAIE) [F: README].
- **KV events, optional**: "KV-aware routing does not require NATS. Enable KV events when you
  need event-backed cache-state tracking, or use `--no-router-kv-events` for prediction-based
  routing without external event infrastructure" [F: README]. So there are two modes:
  *event-backed* (registry updated by real cache events) and *prediction-based* (estimate,
  no event infra) — a real knob in the implementation.
- **Per-request hints** (1.0): agentic requests can carry priority, expected output length,
  speculative prefill, session metadata (for SGLang subagent KV isolation) [F: README] —
  i.e. the scorer takes per-request metadata, not just the prompt bytes.

## llm-d — the EPP + event-driven index router (implementation)
From README (v0.8) + v0.9 docs [F, fetched 2026-08-26]:
- **Structure**: Router = **Proxy + EPP** split over the GAIE `ext-proc` protocol. The Proxy
  is a thin L7 gateway-conformant proxy; the **EPP** "scores and selects model server pods
  based on real-time metrics, KV-cache affinity, and configured policies" [F: v0.9 docs].
- **KV affinity signal**: reads the **global KV index** assembled from vLLM KV-cache events
  — the same structural idea as Dynamo's registry, but the index is built from
  *engine-emitted events on K8s* rather than a router-owned registry (`05-global-kv-state.md`).
- **Learned layer (optional)**: a **Latency Predictor** "consultant" sidecar trains an
  **XGBoost model online** to predict request latency → endpoint scoring + SLO enforcement
  [F: v0.9 docs; GA v0.7]. This is a genuinely different signal class: a *regression over
  history* instead of a pure cache/load heuristic.
- **Heuristic AND precise**: "prefix-cache-aware routing" via "heuristic and precise
  techniques" — precise = index-driven, heuristic = estimated [F: v0.9 docs].

## Why hit *fraction* (not binary) — the implementation consequence
Both platforms must score a *fraction* h of the prompt that is resident, because the value
is proportional: transfer time ∝ (1−h), prefill saved ∝ h. A binary "hit/miss" router would
miss the whole partial-prefix opportunity. [E] this session, 4 GiB @ 32k over 100 GbE:
| h | residual transfer | saving vs h=0 |
|---|---|---|
| 0    | 361 ms | — |
| 0.5  | 180 ms | 50% |
| 0.9  | 36 ms  | 90% |
| 0.95 | 18 ms  | 95% |
The radix tree / index exists precisely to compute h *per worker*, not to answer a boolean.

## Combining the two signals (the scorer, in words) [I: consistent with both docs]
```
for candidate worker W:
    overlap(W) = length of longest cached prefix for this prompt on W  → hit fraction h(W)  (from registry/index)
    load(W)    = queue depth + expected remaining work (from metrics / predictor)
    score(W)   = overlap(W) subject to a load-balance constraint      # "highest hit while load-balanced"
pick W* = argmax over (load-feasible) workers of score(W)
```
This is the shared shape of Dynamo's "highest hit rate while maintaining load balance" and
llm-d's "KV-cache affinity + real-time metrics + policy" [F: both]. The *data source* for
overlap(W) — router-owned radix tree vs event-driven index — is the implementation split.

## Failure / risk surfaces (implementation-relevant)
- **Stale hits**: index says W has the prefix, but W evicted it → route to a miss and pay
  re-prefill. Mitigation: event frequency, short TTLs on index entries (`05-global-kv-state.md`).
- **Cache double-count**: scoring "hit bonus" on top of already-reduced prefill work — same
  term twice (`Inference/Production-Serving/08-cache-aware-routing.md`).
- **Hot-spot flip**: routing everything cache-optimal overloads one worker = why the load
  term exists in the same score.
- **Prediction mode drift**: `--no-router-kv-events` / heuristic estimates go stale under
  churn — the predictable cost of skipping the event infrastructure.

## Related
`05-global-kv-state.md` (the registry/index both routers read) · `01-distributed-kv.md`
(what "resident prefix" means) · `02-offload-and-tiering.md` (hit-tier awareness) ·
`04-pd-orchestration.md` (P/D two-endpoint routing) · `06-nixl-transfer.md` (the (1−h)
set the router controls) · `KV-Cache/Prompt-and-Prefix-Caching.md` ·
`Inference/Production-Serving/08-cache-aware-routing.md` ·
`Inference/Production-Serving/09-pd-disaggregated-routing.md` ·
`Inference/Production-Serving/14-production-routers-comparison.md` ·
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`

## Key Takeaways
1. KV-aware routing = **score = f(cache-overlap fraction, load)** per worker; route to max;
   the mechanism for overlap is the implementation divergence.
2. Dynamo: router-owned **global radix-tree registry** (native or GAIE-EPP), with an
   event-backed / `--no-router-kv-events` prediction-mode knob [F].
3. llm-d: **Proxy+EPP** over GAIE `ext-proc`, reading an **event-driven global index**, plus
   an optional **online XGBoost latency predictor** [F].
4. Score h as a **fraction**: value ∝ (1−h) transfer saving — binary hit/miss throws away
   the partial-prefix opportunity.
5. The reason this is *capacity*, not nicety: aggregate demand `λ·KV·(1−h)` [E, 01 page].
