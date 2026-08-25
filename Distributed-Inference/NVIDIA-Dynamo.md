# NVIDIA Dynamo — Distributed Inference Architecture Deep Dive
`LAST_UPDATED: 2026-08-24 · Status: core page` · Dynamo is NVIDIA's **open-source,
datacenter-scale distributed inference stack** — the orchestration layer *above*
inference engines. It "doesn't replace SGLang, TensorRT-LLM, or vLLM — it turns them
into a coordinated multi-node inference system" [F: ai-dynamo/dynamo README, main
branch, v1.4.x line, fetched 2026-08-24]. Built **in Rust for performance, Python for
extensibility**, fully open-source (Apache-2.0, OSS-first) [F: README + docs].
Repo: `github.com/ai-dynamo/dynamo` (note: the *ai-dynamo* org, not `NVIDIA/`).
Version anchors (2026-08-24): main-branch containers `*:1.4.1`; docs detail
below pinned to the published v0.8.0 design docs (the architecture is stable across
1.x; see §Recent Changes).

## 30-Second Explanation
An inference engine optimizes *one instance*. Dynamo optimizes *the fleet*: it
(1) **disaggregates** prefill and decode into independently scalable GPU pools,
(2) **routes** each request to the worker with the best KV-cache overlap while
keeping pools balanced, (3) **tiers** the KV cache across GPU→CPU→SSD→remote storage,
(4) **plans** pool sizes from an SLO (TTFT/ITL targets) instead of static replica
counts, and (5) **transfers** KV between pools via NIXL faster than recomputation
often costs. The result the docs demonstrate on H100s: ~3× TTFT and ~2× average
latency from KV-aware routing alone on 100k real R1 queries, and 30%→2×+
throughput-per-GPU from disaggregation on Llama-70B-FP8 [F: Dynamo v0.8.0 design
docs, cited with full workload context below].

## What It Is (five key features, per the official architecture)
From the v0.8.0 overall-architecture doc [F, docs.nvidia.com/dynamo/v-0-8-0/design-docs/overall-architecture, fetched 2026-08-24]:
1. **Disaggregated Serving** — prefill and decode as separate, independently
   scalable worker pools (citing DistServe arXiv:2401.09670).
2. **Smart Router (KV-aware routing)** — "directs requests to the worker with the
   highest cache hit rate while maintaining load balance"; backed by a **KV cache
   manager that maintains a global radix tree registry for hit-rate calculation**
   [F: doc's exact phrasing — the routing state is a *radix tree*, the same data
   structure SGLang uses inside-engine, lifted to the cluster level].
3. **KV Block Manager (KVBM)** — multi-tier KV storage/eviction: "GPU, CPU, SSD, and
   object storage"; "in many cases, KV transfer is faster than recomputation" [F].
4. **Planner** — SLA-driven autoscaler; "event plane" captures deployment signals
   (e.g. a surge in long-input requests → scale up prefill workers), zero-downtime
   adjustments [F]. AIConfigurator simulates 10K+ deployment configs to find the
   topology [F: README].
5. **NIXL** (NVIDIA Inference tranXfer Library) — "designed to expedite transfers
   through reduced synchronization and intelligent batching"; the KV-transfer engine
   for disaggregated serving [F: doc; repo ai-dynamo/nixl].

Plus, from the README's capability table [F, 2026-08-24]:
- **ModelExpress** — streams model weights GPU-to-GPU via NIXL/NVLink; 7× faster
  model startup (DeepSeek-V3 on H200) [F: README key results].
- **Grove** — K8s operator for topology-aware gang scheduling (NVL72) [F: README].
- **Fault tolerance** — canary health checks + **in-flight request migration**:
  "workers fail; user requests don't" [F: README].
- **Multimodal E/P/D** (new in 1.0) — disaggregated encode/prefill/decode with an
  embedding cache; 30% faster TTFT on image workloads [F: README].
- **Video generation** (1.0) — FastVideo + SGLang-Diffusion; real-time 1080p on a
  single B200 [F: README].

## Why It Was Created (the five problems, in the docs' own framing)
The v0.8.0 doc states the motivation as five challenges [F, verbatim topics]:
1. **Difficult UX** — managing a distributed inference runtime is complex; poor UX
   makes it inaccessible and error-prone. (Dynamo's answer: declarative
   `DynamoGraphDeploymentRequest` + recipes + agent skills.)
2. **GPU underutilization** — "monolithic inference pipelines often leave GPUs idle
   due to the imbalance between prefill and decode stages" (citing DistServe).
   (Answer: disaggregated pools.)
3. **Expensive KV re-computation** — bad routing flushes and recomputes KV; "KV-aware
   request routing eliminates redundant KV cache regeneration" (citing the DeepSeek
   report arXiv:2501.12948).
4. **Memory bottlenecks** — KV overwhelms HBM; offloading across HBM/DDR/NVMe/remote
   scales context beyond GPU memory (citing Mooncake, AIBrix, LMCache).
5. **Fluctuating demand / static GPU allocation** — demand surges vs static
   provisioning (citing AzureTrace); and a **communication-layer gap**: "contemporary
   libraries are built for static, synchronous operations [training] and lack the
   dynamicity needed for inference serving" → hence NIXL [F].

## Core Architecture (component diagram)
```
                    Client (OpenAI-compatible API)
                          │
            ┌─────────────┴──────────────────────┐
            │                                    │
   Dynamo-native topology              Gateway API topology (K8s)
            │                                    │
   ┌────────▼─────────┐              ┌───────────▼──────────┐
   │  Frontend (Rust) │              │ K8s Gateway + GAIE   │
   │  · HTTP/OpenAI   │              │ (Inference Ext.)     │
   │  · /openapi.json │              └───────────┬──────────┘
   └────────┬─────────┘                          │
            │                        ┌───────────▼──────────┐
            └────────────────────────►   Router (Rust)      │
                                   │  · KV-aware worker     │
                                   │    selection (global   │
                                   │    radix-tree registry)│
                                   │  · load balancing      │
                                   │  · direct/forward mode │
                                   └───────────┬────────────┘
                                   ┌───────────▼────────────┐
                                   │  Planner              │
                                   │  · SLA targets (TTFT/ │
                                   │    ITL) → pool sizing │
                                   │  · event plane signals│
                                   │  · AIConfigurator     │
                                   └───────────┬────────────┘
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
          ┌─────────▼─────────┐      ┌─────────▼─────────┐      ┌────────▼──────────┐
          │ Prefill workers   │      │ Decode workers     │      │ KVBM (KV Block   │
          │ (engine instances)│      │ (engine instances) │      │  Manager)        │
          │ vLLM / SGLang /   │      │ vLLM / SGLang /    │      │ · GPU HBM        │
          │ TensorRT-LLM      │─────►│ TRT-LLM            │◄────►│ · CPU/DDR        │
          │ (per-instance TP/ │ NIXL │                     │ NIXL │ · SSD/NVMe      │
          │  EP inside)        │ KV  │                     │ KV   │ · remote/S3/Azure│
          └────────────────────┘     └─────────────────────┘     └──────────────────┘
                    └──────────────────────────┬──────────────────────────┘
                                               │
                                   service discovery: K8s CRDs +
                                   EndpointSlices (or file/etcd/NATS)
```
Every component "is independently scalable and portable" [F: v0.8.0 doc]. The
request plane is **TCP**; discovery is K8s-native (CRDs + EndpointSlices) with etcd /
NATS-JetStream / file backends available for non-K8s or local development —
"KV-aware routing does not require NATS" (event-backed cache tracking is optional,
or use `--no-router-kv-events` for prediction-based routing) [F: README].

## Request Lifecycle (one request, end to end)
1. **Arrival** — HTTP to the Frontend (Dynamo-native) or the K8s Gateway (GAIE
   topology, where the router acts as an **Endpoint Picker Plugin**, EPP, and the
   selected worker's Frontend sidecar runs in `--router-mode direct`) [F: README
   "Request Routing Topologies"].
2. **Routing** — the Router consults its **global radix-tree registry** of KV cache
   state: for this prompt, which worker pool/instance has the longest cached prefix,
   *and* is not overloaded. Decision = argmax of (cache-hit rate, remaining-capacity)
   [F: "highest cache hit rate while maintaining load balance"]. Agentic requests can
   carry per-request hints (priority, expected output length, speculative prefill,
   session metadata) since 1.0 [F: README].
3. **Prefill** — the chosen prefill worker runs the prompt through the engine
   (vLLM/SGLang/TRT-LLM instance, with its own TP/EP inside the instance); KV blocks
   registered with the KVBM; first token produced.
4. **KV transfer** — NIXL moves the KV blocks to the decode worker (RDMA /
   NVLink; intelligent batching + reduced synchronization per the design doc) [F].
   If the prefix was cached on the decode side already (KVBM hit), the transfer
   shrinks by the cached fraction — "(1−h)" discount, §KVBM.
5. **Decode** — the decode worker streams tokens; its per-request KV is registered
   cluster-wide so *the next* request in the same conversation can hit it.
6. **Completion/failure** — on worker death, canary checks trigger **request
   migration**: in-flight requests move to a live worker; their KV (if tiered) is
   fetched from KVBM rather than re-prefilled [F: README fault tolerance].
7. **Scaling feedback** — event-plane signals (queue depth, ISL distribution,
   SLA pressure) feed the Planner, which right-sizes pools — "if Dynamo detects an
   increase in requests with long input sequences, the Planner automatically scales
   up prefill workers" [F: v0.8.0 doc].

## Router & Scheduler Architecture
- **Global radix-tree registry**: cluster-level prefix index — the structural cousin
  of SGLang's in-process RadixAttention cache (`GPU-Systems/SGLang.md`), lifted from
  one engine instance to the whole cluster. This is why Dynamo's KV routing and
  llm-d's "precise global indexing of the KV cache state" [F: llm-d README] are
  same-mechanism, different-vendor solutions.
- **Two routing signals** (same taxonomy as the router deep-dive,
  `Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md`): cache overlap
  (TTFT dividend) + load (ITL/tail dividend). Dynamo's documented result on 100k
  real R1 queries (R1 Distilled Llama-70B-FP8, 2×H100 nodes, 4K ISL / 800 OSL):
  **3× TTFT, 2× average latency vs random routing** [F: v0.8.0 doc, vendor benchmark —
  cite as such, not a wiki-lab result].
- **Prediction-based mode**: without KV event infrastructure, the router estimates
  cache state (`--no-router-kv-events`) [F: README] — a latency-model variant of
  llm-d's predicted-latency scheduling [F: llm-d README, v0.7 GA].
- **Scheduling inside workers** is unchanged: the engine's own scheduler (vLLM
  iteration-level, SGLang program-aware, TRT-LLM inflight) runs per instance
  (`Serving-Engines/Engine-Landscape.md` layer model). Dynamo does not replace
  in-engine scheduling; it places requests so the in-engine schedulers get easy
  workloads (warm caches, balanced loads).

## KVBM (KV Block Manager) — Multi-Tier Cache
```
hot:   GPU HBM (engine paged KV)
warm:  CPU/DDR
cool:  local SSD/NVMe
cold:  remote storage / S3 / Azure blob (1.0: storage-tier offload +
       global KV events for cluster-wide cache visibility [F: README])
```
- The KVBM "oversees a multi-tiered memory system, enabling rapid KV cache storage
  and eviction" [F: v0.8.0 doc]; blocks are addressable cluster-wide, so a decode
  worker can *pull* a block from another node's tier instead of re-prefilling.
- Documented result: CPU-memory offload gave **2.2×–12× improvement** in a 20-
  multi-turn-conversation / 15-user scenario [F: v0.8.0 doc, vendor benchmark].
- Backend status (README feature matrix, 2026-08-24): KVBM ✅ vLLM, ✅
  TensorRT-LLM, 🚧 (in progress) SGLang [F: README].
- Physics check [I: consistent with `Inference/Prefill-Decode-Disaggregation.md`
  break-even model]: "KV transfer is faster than recomputation" holds when
  transfer(S·(1−h)) < recompute(S·(1−h)) — on HBM- vs HBM- this is the recompute
  ratio; off-tier, it holds for any S where the fabric beats the prefill compute
  roof by more than the tier's read latency. The KVBM's value scales with
  conversation turn count (multi-turn = repeated prefixes = high h).

## Disaggregated Serving
Full physics in `Inference/Prefill-Decode-Disaggregation.md` and
`Distributed-Inference/Overview.md` §P/D. Dynamo specifics:
- All three backends support disagg [F: README feature matrix ✅/✅/✅].
- Documented H100 results, R1 Distilled Llama-70B-FP8 via **vLLM**, 3K ISL / 150 OSL:
  **30% throughput/GPU on 1 node, >2× on 2 nodes** [F: v0.8.0 doc, vendor benchmark].
- P:D worker allocation is the SLO dial: "adjusting worker allocation can provide
  tailored performance … prioritizing faster TTFT, lower ITL, or higher throughput"
  [F: v0.8.0 doc].
- E/P/D (multimodal): encode is a *third* disaggregated phase since 1.0, with an
  embedding cache [F: README].
- Key cluster claims (context-specific, [F: vendor/partner]): 7× throughput/GPU
  DeepSeek-R1 GB200 NVL72 vs B200 (InferenceX); 750× throughput on GB300 NVL72
  (InferenceX v2); 2× TTFT Baseten/Qwen3-Coder-480B; 80% fewer SLA breaches at 5%
  lower TCO (Alibaba APSARA 2025 planner demo) [F: README key results].

## Planner — SLA-Based Autoscaling
- Input: SLA targets (e.g. `ttft: 200 ms, itl: 20 ms` in the `DynamoGraphDeploymentRequest`
  manifest) + workload profile. [F: README quick-start K8s example]
- Method: AIConfigurator "simulates 10K+ deployment configs in seconds — finds the
  optimal serving config without burning GPU-hours" [F: README]; the Planner applies
  the choice and then tracks the event plane for demand shifts [F: v0.8.0 doc].
- 1.0 **DGDR zero-config deploy (beta)**: "specify model, HW, and SLA in one YAML —
  AIConfigurator auto-profiles, Planner optimizes topology, Dynamo deploys" [F: README].
- Contrast: engine-native scaling is static-replica or K8s HPA on generic metrics;
  the Planner is *inference-aware* (ISL/OSL distribution, cache state, pool
  utilization per phase) — the same "workload-variant autoscaling" idea llm-d
  previews [F: llm-d README v0.4 news].

## NIXL — The Transfer Layer
- "Expedite[s] transfers through reduced synchronization and intelligent batching"
  [F: v0.8.0 doc]; designed for inference's *dynamic* topology (workers scaling in
  and out, unlike training's static ranks) [F: doc motivation].
- Transports: UCX-class networking under a unified API that "abstracts heterogeneous
  memory (remote memory or storage) and dynamically selects the best transport"
  [F: doc motivation — the doc explicitly positions NIXL against configuring UCX by
  hand].
- Also used by ModelExpress for weight streaming (GPU-to-GPU over NVLink/NIXL;
  partner results: Dell PowerScale 19× faster TTFT, WEKA KV storage integration —
  [F: README news items, partner claims]).
- Note: NIXL is not exclusive to Dynamo — vLLM's disagg connector ecosystem and
  TRT-LLM's cache transmission include NIXL/Mooncake-class paths
  (`Inference/Prefill-Decode-Disaggregation.md` §research lineage).

## Fault Tolerance
- **Canary health checks** on workers; on failure, **in-flight request migration**:
  the request's state (prompt, generated tokens so far, KV location) moves to a live
  worker [F: README]. KVBM is what makes migration cheap: KV lives in the tiered
  store, not only in the dead worker's HBM.
- Cross-pool fault propagation is the known open risk of disagg generally
  [F: DistServe §4.3, via the P/D page] — migration is the mitigation.

## Backends & Integration
| Backend | Disagg | KV routing | SLA planner | KVBM | Notes |
|---|---|---|---|---|---|
| SGLang | ✅ | ✅ | ✅ | 🚧 | [F: README matrix, 2026-08-24] |
| TensorRT-LLM | ✅ | ✅ | ✅ | ✅ | deepest NVIDIA coupling |
| vLLM | ✅ | ✅ | ✅ | ✅ | containers `vllm-runtime:1.4.1` |
- "Inference engine agnostic, supporting TRT-LLM, vLLM, SGLang and others"
  [F: v0.8.0 doc]. Prebuilt NGC containers per backend [F: README].
- Speculative decoding, LoRA, request migration: tracked in the docs' feature
  matrix (check current per backend) [F: README link].

## Kubernetes & Deployment
- **Dynamo Platform** install for K8s clusters; single-manifest deploy via the
  `DynamoGraphDeploymentRequest` CRD (`nvidia.com/v1beta1`) [F: README].
- Two routing topologies: Dynamo-native (Frontend owns HTTP+Router — local dev /
  single cluster) vs **Gateway API + GAIE EPP** (cluster-edge gateway owns
  policy/auth/rate-limit; router as Endpoint Picker Plugin; worker Frontend sidecars
  in `--router-mode direct`) [F: README] — the same topology choice as llm-d's
  Gateway-API-first design, differing in *where the KV state lives* (Dynamo router
  holds the global radix registry; GAIE delegates picking to the EPP that
  consults it).
- Grove: K8s operator for topology-aware **gang scheduling** on NVL72 (rack/host/
  NUMA placement) [F: README].
- Service discovery: K8s CRDs + EndpointSlices; etcd/NATS optional; file backend for
  local dev [F: README].
- Cloud guides: EKS/GKE/AKS/ECS [F: README].
- Non-K8s: Slurm/etcd/NATS modes supported [F: README] — Dynamo is not
  K8s-*required*, unlike llm-d's core identity.

## Recent Enhancements (1.0 → 1.4, verified 2026-08-24)
- **0.8 (docs baseline)** — the five-feature architecture above [F: v0.8.0 docs].
- **1.0 (2025-03-15)** — "production-ready with strong community adoption"; DGDR
  zero-config (beta); agentic per-request hints; E/P/D multimodal; video generation
  (FastVideo/SGLang-Diffusion); K8s Inference Gateway plugin; S3/Azure storage-tier
  KV offload + global KV events [F: README "New in 1.0"].
- **→1.4.x (2026 main)** — Rust core + feature matrix per backend (KVBM
  SGLang 🚧); community events/office hours; agent-skills in repo (Claude Code /
  Codex / Cursor deploy & benchmark workflows) [F: README]. Production user news:
  Moonshot Kimi-K2 "10× inference speedup on GB200" (12/2025), Mistral-Large-3
  "10× faster on GB200 NVL72" (12/2025) [F: README news items, partner claims].
  (Verify per release notes before citing as stable.)

## Observability
- Per-component metrics + Prometheus (check current docs for the metric catalog);
  router/cache signals (hit rate, pool queue depth) are *inputs* to the Planner, so
  the control loop is observable end-to-end [I: structural from the event-plane
  design]. AIPerf is the documented benchmarking tool ("compare deployment
  topologies") [F: README benchmarking guide link].

## Performance Evidence — Classification
| Result | Source class | Context |
|---|---|---|
| 30% / >2× throughput-GPU from disagg | **Vendor** (docs) | Llama-70B-FP8, H100, vLLM, 3K/150 |
| 3× TTFT / 2× avg latency, KV routing | **Vendor** (docs) | 100k R1 queries, Llama-70B-FP8, 2×H100, 4K/800 |
| 2.2–12× from CPU KV offload | **Vendor** (docs) | 20 multi-turn convs, 15 users |
| 7× tok/GPU GB200 NVL72 vs B200 | **Vendor/partner** (InferenceX) | DeepSeek-R1 |
| 2× TTFT | **Partner** (Baseten blog) | Qwen3-Coder-480B |
| 80% fewer SLA breaches, −5% TCO | **Partner** (Alibaba) | planner autoscaling |
Wiki-lab results: **none yet** — reproduce with the cluster-metric set in
`Distributed-Inference/Overview.md` §metrics before making workload claims.

## Strengths
1. **The five-feature completeness**: routing + P/D + KV tiers + SLA planning +
   transfer, in one coherent OSS stack — no other single project covers all five
   with published architecture docs [A: scope comparison, 2026-08-24].
2. **Rust performance-critical path** (frontend/router/planner) + Python
   extensibility — the data plane is not a Python bottleneck [F].
3. **NVIDIA fabric gravity**: NVL72/GB200/GB300-class results, Grove gang
   scheduling, ModelExpress weight streaming — the deepest published
   datacenter-scale integration [F: README].
4. **Backend-agnostic** with per-backend feature matrix — no lock-in to TRT-LLM
   [F: README], correcting the older "Dynamo = TRT-LLM only" impression.
5. **Fault-tolerant by design**: request migration + tiered KV [F].

## Limitations
1. **Ops weight** — a platform install, P/D pools, KVBM, planner: meaningful
   complexity vs a single vLLM replica; the README itself says "if you're running a
   single model on a single GPU, your inference engine alone is probably sufficient"
   [F: README].
2. **NVIDIA-centric hardware assumptions** (NVLink/NVL72/NIXL/ModelExpress) — the
   accelerator-neutral claim is weaker than llm-d's tested AMD/Intel/TPU matrix
   [F: llm-d README] [I: comparison judgment].
3. **Vendor benchmark gravity** — most headline numbers are vendor/partner;
   independent replication is the reader's job (performance-claim rule,
   `Engine-Landscape.md`).
4. **SGLang KVBM in progress** as of 2026-08-24 [F: README matrix] — check current
   matrix.
5. **K8s optional but the story is datacenter** — not a local/edge tool.

## Best Use / When Not To Use
- **Use**: multi-node NVIDIA fleets (especially NVLink/NVL72); reasoning/agentic
  workloads with long shared contexts; P/D SLO work where both TTFT and ITL bind;
  enterprise wanting OSS (Apache-2.0) instead of a proprietary orchestrator.
- **Don't**: single-node or single-GPU serving (engine suffices [F: README]);
  vendor-neutral multi-accelerator clusters (llm-d's tested matrix [F]);
  "I just need a router in front of 4 vLLM replicas" (Gateway API + a cache-aware
  EPP, e.g. llm-d's router alone, may be enough — verify).

## Alternatives
- **llm-d** — same layer, K8s-native + vendor-neutral; `Dynamo-vs-llm-d.md`.
- **Engine-native disagg** (vLLM/SGLang/TRT-LLM P/D + connectors) — for 1-node/
  pair-scale; no platform layer; `Inference/Prefill-Decode-Disaggregation.md`.
- **Trained routers / academic systems** (DistServe, Mooncake, Splitwise) —
  research lineage behind both platforms [F: P/D page].

## Key Takeaways
1. Dynamo = the **five cluster jobs** as one OSS Rust/Python stack: route
   (KV-aware, global radix registry), split (P/D pools), tier (KVBM), plan
   (SLA-driven autoscaler), move (NIXL) — on top of vLLM/SGLang/TRT-LLM workers.
2. The documented wins are *mechanism-attached*: KV routing wins come from the
   radix registry + (1−h) transfer discount; disagg wins from roofline separation;
   planner wins from event-plane signals — each is reproducible if you measure the
   corresponding cluster metric.
3. Version posture (2026-08-24): main = v1.4.x containers; architecture stable
   since the v0.8 design docs; SGLang-KVBM still 🚧; check the feature matrix
   before planning.
4. Dynamo is a *platform*, not an engine: benchmarking it means benchmarking the
   cluster (hit rate, pool utilization, transfer latency, goodput-at-SLO), never
   a single-GPU tok/s.

## Related
`Overview.md` (cluster-layer framing + KV-transfer physics) · `llm-d.md` ·
`Dynamo-vs-llm-d.md` · `Inference/Prefill-Decode-Disaggregation.md` ·
`Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` ·
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` ·
`Inference/Production-Serving/09-pd-disaggregated-routing.md` ·
`GPU-Systems/SGLang.md` (the in-engine radix cousin of Dynamo's global registry) ·
`GPU-Systems/vLLM.md` · `Networking/README.md` · `Serving-Engines/Engine-Landscape.md`

## References
- ai-dynamo/dynamo README — main branch, v1.4.x (fetched 2026-08-24): capabilities,
  key results, feature matrix, routing topologies, K8s manifests, discovery modes
  [F].
- Dynamo v0.8.0 design docs — docs.nvidia.com/dynamo/v-0-8-0/design-docs/overall-architecture
  (fetched 2026-08-24): motivation (five challenges), five key features, router
  radix-tree registry, Planner event plane, NIXL, KVBM tiers, H100 benchmark
  charts with full workload context [F].
- NIXL — github.com/ai-dynamo/nixl [F].
- Cited-by-Dynamo research: DistServe arXiv:2401.09670; DeepSeek report
  arXiv:2501.12948 [F: as cited in the v0.8.0 doc; IDs unchanged from the
  citation bank].
- No new arXiv IDs introduced here beyond those cited by the primary source.
