# Implementation 04 — P/D Orchestration: The Phase-Split Control Loop
`LAST_UPDATED: 2026-08-26 · Status: implementation page (PART 2 series)` · Concept +
break-even physics in `Inference/Prefill-Decode-Disaggregation.md`, roofline reasoning in
`Inference/Roofline.md`, the handoff math in `GPU-Communication/08-nixl-kv-cache-transfer.md`.
This page owns the **implementation**: how Dynamo and llm-d actually split prefill/decode
into pools, select two endpoints, and coordinate the KV handoff — plus how pool sizes are
sized to the SLO.

## 30-Second Explanation
P/D disaggregation looks like "two pools"; the *implementation* is a **four-step control
loop**: (1) define two roles (prefill vs decode) as separately scalable entities, (2) on
each request, select *two* endpoints (one of each), (3) coordinate the KV transfer between
them so the decode starts with the full prefix, (4) size each pool from the SLO (TTFT/ITL),
not a static replica count. The two platforms implement these four steps differently —
Dynamo via Planner + worker pools, llm-d via label-defined **Variants** + the Router.

## Step 1 — Defining the two roles
Two different mechanism families:
- **Dynamo**: prefill and decode are **separate worker pools**, each an engine instance
  (vLLM/SGLang/TRT-LLM) running that phase; all three backends support disagg [F: README
  feature matrix ✅/✅/✅]. Multimodal adds a third **encode** phase (E/P/D) since 1.0 [F].
- **llm-d**: prefill vs decode is a **Variant** — a logical sub-grouping of the
  InferencePool **by pod labels** (role/cost/perf profile), no new resource type
  [F: v0.9 docs]. The Router "selects both a prefill and a decode endpoint and coordinates
  the KV-cache transfer between them" [F: v0.9 docs].
So Dynamo codifies phases as pools; llm-d codifies them as *labels + policy* on one pool.

## Step 2 — Two-endpoint selection
- **llm-d** makes it explicit: the EPP scores and selects **two** endpoints — a prefill pod
  and a decode pod — and the router coordinates the transfer between them [F: v0.9 docs].
- **Dynamo**'s router does the same at the pool level: routing places the request on a
  prefill worker (KV-aware, for the prefix) and the KVBM/transfer hands the blocks to a
  decode worker (`Distributed-Inference/NVIDIA-Dynamo.md` request lifecycle steps 3–5).

## Step 3 — The handoff protocol
```
prefill runs prompt → blocks appear incrementally (async) → NIXL moves block lists → decode notified → first token
```
- The transfer is **asynchronous and overlapped**: it starts as blocks complete, not after
  prefill finishes — hidden under prefill when the link's KV-carrying bandwidth is ≥ ~8×
  the prefill's KV-production rate (bytes/s; the `~8×` rule of thumb and its arithmetic
  are in `GPU-Communication/08-nixl-kv-cache-transfer.md` §4). Implementation consequence:
  TTFT ≈ prefill + ε, not prefill + transfer.
- The receiver re-hosts the (1−h) block IDs in its own block table (`01-distributed-kv.md`).
- **Failure surface**: P dies mid-transfer → partial prefix on decode → re-fetch/preemption
  policy; Dynamo's answer is **in-flight request migration** (canary health checks + move
  to a live worker, KV fetched from KVBM) [F: README fault tolerance].

## Step 4 — SLO-driven pool sizing (the Planner vs the autoscalers)
- **Dynamo Planner**: takes SLA targets (e.g. `ttft: 200 ms, itl: 20 ms` in the
  `DynamoGraphDeploymentRequest` manifest [F: README]) + workload signals via an **event
  plane**; **AIConfigurator** simulates 10K+ deployment configs to pick the topology
  [F: README]. "P:D worker allocation is the SLO dial" — allocating more prefill vs decode
  workers prioritizes TTFT vs ITL vs throughput [F: v0.8.0 doc].
- **llm-d**: **HPA/KEDA** on EPP-exported inference metrics (queue depth, SLO pressure)
  + the **Workload Variant Autoscaler (WVA)** which places replicas across variants/pools
  to minimize cost while meeting latency targets [F: v0.9 docs].
Both are *inference-aware* autoscalers (phase-specific, SLO-driven), unlike engine-native
static-replica or CPU-metric HPA (`Distributed-Inference/llm-d.md` §Kubernetes-Nativeness).

## The P:D ratio as a real dial (implementation, not theory)
The ratio is a per-workload experiment (`Distributed-Inference/Overview.md` §P/D). Chat-shaped (short prompt,
long output) → more decode GPUs; RAG-shaped (long prompt, short output) → more prefill.
The platforms exist to make this a configuration/tuning parameter rather than a code change:
Dynamo via Planner pool sizing, llm-d via prefill/decode Variant replica counts. The
break-even check (`Inference/Prefill-Decode-Disaggregation.md`) is a *prerequisite*: if
the fabric can't clear it, no platform's P/D pays off (`Distributed-Inference/Dynamo-vs-llm-d.md` H-neither).

## When the loop helps vs hurts (implementation judgment) [I]
- Helps: both TTFT and ITL SLOs bind; fast fabric (≥100 GbE or NVLink); KV-aware routing to
  defray the transfer; high sustained load.
- Hurts: ≤10 GbE cross-node (transfer inverts TTFT); loose-SLO tokens/$. Objectives (disagg
  costs extra hardware — the win is SLO attainment, not throughput [F: vLLM docs via Overview]).

## Failure modes
- **Cross-pool fault propagation**: a dead prefill worker strands in-flight requests
  (`Production-Operations/11-distributed-inference-failures.md`); mitigation = migration.
- **Transfer > payoff**: slow fabric or short contexts where transfer exceeds re-prefill
  (`Inference/Prefill-Decode-Disaggregation.md` break-even).
- **Two-phase utilization imbalance**: if only one pool is ~100%, the ratio is wrong —
  both pools ~100% is the signal the ratio is right (`Distributed-Inference/Overview.md` §cluster metrics).

## Related
`01-distributed-kv.md` (moved-KV handoff) · `03-kv-aware-routing.md` (the (1−h) the router
controls) · `06-nixl-transfer.md` (the transfer) · `05-global-kv-state.md` (index sees both
pools) · `02-offload-and-tiering.md` · `Inference/Prefill-Decode-Disaggregation.md` ·
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` ·
`Inference/Production-Serving/09-pd-disaggregated-routing.md` ·
`GPU-Communication/08-nixl-kv-cache-transfer.md` · `Inference/Roofline.md`

## Key Takeaways
1. P/D implementation = a **four-step control loop**: two roles → two endpoints →
   handoff protocol → SLO pool sizing. Both platforms implement all four, differently.
2. Dynamo: phases as **worker pools** + **Planner** (SLA manifest, AIConfigurator); llm-d:
   phases as **Variants (labels)** + **HPA/KEDA/WVA**.
3. The handoff is **async/overlapped** (NIXL block lists), so TTFT ≈ prefill + ε when the
   link is fast — the implementation detail most P/D designs get wrong.
4. P:D ratio is a per-workload dial; both platforms expose it as configuration; the
   break-even check is the prerequisite.
