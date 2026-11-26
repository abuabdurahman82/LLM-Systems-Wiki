# llm-d & NVIDIA Dynamo — The Distributed Inference Platforms Capstone
`LAST_UPDATED: 2026-09-06 · Status: capstone page (section PART 3)` · All version anchors
re-verified against primary sources on **2026-09-06**: Dynamo releases page (stable
v1.4.2, 2026-08-29; v1.5.0 dev snapshots), llm-d releases page (v0.9.0, 2026-08-17),
vLLM disagg-prefill docs (9 connectors, experimental). Claim tags per house style;
arithmetic Python-verified this session (`llmd-dynamo-research/` working notes).

## 30-Second Explanation
llm-d and NVIDIA Dynamo are the two production answers to the same question: *what
runs above the inference engines?* An engine (vLLM, SGLang, TensorRT-LLM) makes one
instance fast. A **distributed inference platform** makes a fleet fast — it routes
each request to the replica whose KV cache already holds the prompt's prefix
(cache-aware routing), splits prefill and decode into independently scaled GPU pools
(P/D disaggregation), moves KV between them faster than recomputing it (NIXL /
engine connectors over RDMA), sizes the pools from TTFT/ITL SLOs instead of static
replica counts, and migrates in-flight requests when a worker dies. **Dynamo**
implements this as a Rust/Python control plane with its own transfer library
(NIXL) and NVIDIA datacenter gravity; **llm-d** implements it as Kubernetes-native
components (Gateway API Inference Extension, label-defined pools, event-driven KV
index) with a vendor-neutral accelerator matrix. Neither executes model math.
This page is the section capstone: the full arc from history to decision framework,
with the worked arithmetic the platform claims rest on.

## 1. Executive Overview

**What they are (category, verified against both READMEs 2026-09-06):**
- **Dynamo** [F: ai-dynamo/dynamo README]: "a high-performance open-source inference
  serving software... designed to streamline inference in **multi-node distributed
  environments**." Components: Rust frontend + router + planner, KVBM cache manager,
  NIXL transfer library, engine runtimes (vLLM/SGLang/TRT-LLM) as workers.
- **llm-d** [F: llm-d/llm-d README]: "a Kubernetes-native, high-performance
  distributed LLM inference **framework**... state-of-the-art orchestration above
  model servers like vLLM and SGLang." Components: router (proxy + EPP over
  ext-proc), InferencePool/Variant (K8s labels), event-driven KV index, tiered
  offload, HPA/KEDA + WVA autoscaling, disagg sidecar.
- Classification: both are **distributed inference frameworks = serving control
  planes (+ partial data-plane ownership for KV transfer)**. They are *not*
  inference engines (no kernels, no model execution), *not* gateways (they compose
  with Gateway API/Envoy/Istio), *not* batch schedulers. The one data-plane element
  they own is **KV movement** — Dynamo via NIXL/KVBM, llm-d via engine connectors +
  its disagg sidecar (`Serving-Engines/Engine-Landscape.md` layer model).

**Why they exist when vLLM/SGLang/TRT-LLM/Triton/KServe already existed** [I:
synthesis of both projects' stated motivations, F: Dynamo v0.8.0 design doc "five
challenges", llm-d README mission]: each existing layer solves a different problem —
engines optimize one instance; Triton is a model-server *package*; KServe is a
generic K8s model-*serving* control plane (scale-to-zero, canary) that is not
LLM-cache-aware; HPA-style autoscaling reads CPU, not TTFT/ITL. None of them answer
the fleet questions: which replica has this prompt's prefix cached? where should
prefill vs decode run? when is moving KV cheaper than recomputing it? how many
prefill vs decode pods does this SLO need *this week*? Those five jobs — route,
place, move, scale, fail — are the platforms' entire reason to exist
(`Overview.md` §five jobs).

**The evolution story in one paragraph:** vLLM (2023) proved paged KV +
continuous batching on one instance [F: arXiv:2309.06180]; SGLang (2023) added
RadixAttention prefix reuse inside one instance [F: arXiv:2312.07104]; both then
multi-node'd the *model* (TP/PP/EP, 2024). DistServe (OSDI'24) [F: arXiv:2401.09670],
Splitwise (ISCA'24) [F: arXiv:2311.18677] and Mooncake (FAST'25) [F: arXiv:2407.00079]
showed the *next* win is splitting prefill from decode across pools and treating KV
as a cluster resource — wins no single instance can capture because they are
placement decisions. Dynamo (NVIDIA, 2025) and llm-d (Red Hat/Google/IBM/CoreWeave/
NVIDIA → CNCF Sandbox 2026-03) are the production-grade productization of that
research layer. Engines kept getting faster; the *remaining* waste moved to routing
and placement, and both projects are the orchestration answer (`Serving-Engines/Engine-Landscape.md`).

**Status classes used throughout this page** (documented vs experimental vs
roadmap discipline):

| Capability | Class | Evidence anchor |
|---|---|---|
| Dynamo P/D + KV router + Planner + NIXL | **documented, shipping** (v1.4.2 stable) [F] | release notes + design docs, fetched 2026-09-06 |
| Dynamo KVBM tiering | **documented — "in progress across all combinations"** (matrix caution) [F] | feature matrix, fetched 2026-09-06 |
| Dynamo multi-DC KV Relay; `/inference/v1/generate` | **experimental** (opt-in) [F] | v1.4.0 notes |
| Dynamo DGDR deploy-by-intent; Enterprise artifacts | **documented** (DGDR beta; Enterprise = support SKU, no binary diff) [F] | v1.4.2 notes + DGDR API docs |
| Dynamo 1.5.0 | **pre-release/roadmap** — model-specific dev snapshots only, no stable 1.5 as of 2026-09-06 [F] | releases page |
| llm-d router/EPP/KV index/offload/P/D | **documented, shipping** (v0.9.0 GA 2026-08-17) [F] | release notes + "Hardened for Scale" blog |
| llm-d sticky-until-saturated routing; KEDA foundation | **documented** (v0.9 defaults) [F] | v0.9 blog |
| llm-d P2P KV sharing | **documented well-lit path** (young; published measured crossovers) [F] | P2P blog 2026-08-15 |
| llm-d RL integrations + GPU time-slicing | **incubation/roadmap** (v0.10 target) [F] | v0.9 blog "What Is Next" |
| vLLM disaggregated prefilling + 9 connectors | **experimental** (docs state it explicitly) [F] | vLLM docs, fetched 2026-09-06 |

## 2. Historical Context — the serving-stack timeline

| Year | Step | What changed | Canonical artifact |
|---|---|---|---|
| 2020–22 | single-GPU serving | one process, static batch, naive KV | FasterTransformer era |
| 2022 | continuous batching | iteration-level scheduling, no batch drain | Orca [F: arXiv:2211.05102] |
| 2023 | paged KV cache | OS-paging for KV → fragmentation gone | vLLM/PagedAttention [F: arXiv:2309.06180] |
| 2023 | prefix reuse in-engine | radix-tree cache over prompts | SGLang/RadixAttention [F: arXiv:2312.07104] |
| 2023 | tensor parallel serving | multi-GPU one-instance | vLLM/SGLang TP; Megatron lineage [F: arXiv:1909.08053] |
| 2024 | chunked prefill | TTFT/ITL trade dial inside engine | Sarathi-Serve [F: arXiv:2403.02310] |
| 2024 | P/D disaggregation (papers) | separate pools + KV transfer; goodput-optimal P:D | DistServe [F: 2401.09670], Splitwise [F: 2311.18677] |
| 2024 | KV as cluster resource | distributed KV pool, cache-aware global scheduler | Mooncake [F: 2407.00079] (FAST'25 best paper) |
| 2025-03 | Dynamo open-sourced | P/D + KV router + KVBM + Planner + NIXL as one stack | ai-dynamo/dynamo [F: repo] |
| 2025-06→ | llm-d (→CNCF Sandbox 2026-03) | the same five jobs as K8s primitives | llm-d/llm-d [F: repo] |
| 2025-03→ | Dynamo 1.0 "production-ready" | DGDR deploy-by-intent, E/P/D multimodal | [F: README 1.0 notes] |
| 2026 | consolidation | KV connector ecosystem in vLLM; platform recipes for frontier MoE | vLLM disagg docs; Dynamo 1.4.x/1.5.0-dev [F: 2026-09-06 fetches] |

Positioning: llm-d and Dynamo are the **L3–L4 layer** of the scale ladder — many
replicas, one SLO contract (`Overview.md` §Scale Ladder). They absorb the 2024
research systems' ideas (cache-aware routing, P/D, tiered KV) and re-express them
as operable software: Dynamo as a framework, llm-d as Kubernetes extensions.

## 3. Why Distributed LLM Inference Is Hard

The engine-internal problem is solved; the fleet-level problem is not, because the
bottlenecks live in *different resources* that want different shapes:

| Bottleneck | Regime | Why one-deployment-per-model fails |
|---|---|---|
| prefill compute | FLOP-bound (AI ≈ d/b high for S≥512 [E]) | a 32K prompt costs ~4.6 PFLOP on 70B [E]; it stalls every co-batched decode |
| decode bandwidth | HBM-bound (B=1 AI ≈ 1.0 FLOP/B [E]) | needs bandwidth, not FLOPS; GPUs idle behind prefill bursts |
| KV capacity | bytes-bound | 70B FP16 @32K = 10 GiB/seq [E]; capacity ⇒ concurrency ⇒ $ |
| KV movement | network-bound | transfer = whole-sequence KV, on the TTFT critical path (§16) |
| load imbalance | queueing | request work varies 1000× (ISL×OSL); round-robin balances *requests*, not *work* |
| scheduling | combinatorial | which (request, replica, phase) triple — needs cache+load signals |
| long context | all of the above, squared | prefill ~S² attention FLOPs [E]; KV linear in S |
| MoE comm | AllToAll-bound | dispatch+combine per MoE layer, every layer |
| tail latency | SLO-shaped | P99 ITL set by the *worst* interference, not the mean |
| multi-tenancy | fairness | one tenant's 128K prompt cannot evict another's chat session |

**Why "one model server = one deployment" becomes inefficient at scale:** a monolith
must run prefill and decode in one process, so it must pick *one* batch configuration,
*one* GPU shape, *one* scaling policy for two opposite roofline regimes
(`Overview.md` §P/D). The consequences, each verified in the sources: (1) interference
— prefill steps stall decode steps and vice versa, and chunked prefill "cannot
eliminate the interference" [F: DistServe §2.2]; (2) re-computation — without
cache-aware routing, multi-turn/RAG traffic re-prefills the same system prompt on
whichever replica the load balancer happens to pick [F: DeepSeek report 2501.12948
motivation; Dynamo "expensive KV re-computation"]; (3) static allocation vs
fluctuating demand — a fixed pool sized for peak long-prompt load wastes decode
capacity at night [F: Dynamo design doc, AzureTrace motivation]; (4) memory walls —
KV, not weights, is the resident-memory binding constraint at context (§17).

## 4. Disaggregated Prefill & Decode (the platform-defining pattern)

Full physics + break-even model: `Inference/Prefill-Decode-Disaggregation.md`
(Python-verified 2026-08-17). Capstone summary with the platform-relevant pieces:

```
              ┌─────────────┐  KV (NIXL / connector)  ┌─────────────┐
 request ───▶ │ PREFILL POOL│ ───────────────────────▶│ DECODE POOL │──▶ stream
              │ compute-opt │  once per request        │ bw-opt      │
              │ TP large    │                          │ high batch  │
              └─────────────┘                          └─────────────┘
              TTFT SLO owns here                       TPOT/ITL SLO owns here
```

- **Roles**: prefill worker = compute-bound, bursty, wants FLOPS + large TP;
  decode worker = bandwidth-bound, persistent, wants HBM bandwidth + high batch.
  Work-ratio intuition [E]: a 4K-prompt→512-output chat request on H100 is ≈1:35
  prefill:decode work (70 ms vs 2.45 s) — chat shapes want more D GPUs, RAG shapes
  invert it (`Overview.md` §P:D).
- **Components a platform must provide**: request router (which pool), KV transfer
  (how the cache moves), cache manager (so the *next* request finds the KV),
  scheduler (P:D sizing), GPU pools (independent scaling).
- **Why the split pays**: each pool runs at its own roofline optimum; TTFT and ITL
  stop fighting over the same SMs; tail ITL becomes controllable (vLLM docs:
  disaggregated prefilling lets you "control tail ITL", while noting it "DOES NOT
  improve throughput" [F: docs.vllm.ai disagg_prefill, fetched 2026-09-06]).
- **When it makes things worse** [I: from the break-even model + community
  evidence]: slow fabric (10–25 GbE cross-node: transfer ≈ or > recompute); short
  prompts with high prefix reuse and no cache-aware routing; loose-SLO throughput
  objectives (extra hardware for no tokens/$); operational simplicity budgets.
  Documented counterexample: Dynamo+vLLM P/D measured *slower* than aggregated
  vLLM by a user on 8×H100 (ai-dynamo/dynamo#2552, opened 2025) [F: issue exists;
  resolution state UNVERIFIED] — disagg is a topology decision, not a free win.
- **The two regimes that decide it** (from the break-even model, restated):
  per-request: `t_transfer(S) = S·KV_tok·(1−h) / BW_fabric` must be ≪ `t_prefill(S)`;
  sustained: `λ · KV_bytes · (1−h)` must fit the fabric. Both tables in §16/§15 here.

## 5. llm-d Architecture Deep Dive (v0.9.0, verified 2026-09-06)

Full component detail: `llm-d.md`; the K8s objects: `Implementation/04-pd-orchestration.md`.
The architecture is unchanged in shape since the 2026-08-24 verification [F: llm-d README +
docs, refetched 2026-09-06]; v0.9.0 (tagged 2026-08-17, "Hardened for Scale" blog 2026-08-28)
hardened it operationally [F: llm-d.ai/blog/llm-d-v0.9-hardened-for-scale]:

```
 clients ──▶ K8s Gateway (Envoy/Istio/agentgateway)
                 │ Gateway API + GAIE (InferencePool v1, GA in GAIE 1.0 [F: GAIE docs])
                 ▼
        ┌─────────────────────┐      ext-proc gRPC (9002)
        │ llm-d Router        │◀──────────────────────────────┐
        │ · Proxy (L7, GAIE)  │                               │
        │ · EPP: filter/scorer│   metrics + KV events + OTel  │
        │   plugins (Alpha/   │◀──── model-server pods ───────┘
        │   Beta/Stable)      │
        └─────────┬───────────┘
                  │ pick endpoint(s)
     ┌────────────┴───────────────┐
     ▼                            ▼
 InferencePool: prefill      InferencePool: decode
 Variant pods (vLLM/SGLang)  Variant pods  ── P/D: disagg sidecar coordinates
     │        ▲                   │              KV transfer (NIXL/UCCL/OffloadingConnector)
     └─ KV events ──▶ event-driven global KV index (cluster-wide cache state)
                      + tiered offload (CPU/SSD) + P2P KV sharing (peer CPU tiers)
 Autoscaling: KEDA (foundation, replacing Prometheus Adapter) + WVA (cross-pool cost-opt)
```

**Request lifecycle** (this is the wiki-canonical walk; expanded mechanics in
`Implementation/03-kv-aware-routing.md`): gateway → Proxy consults EPP via ext-proc →
EPP runs the plugin chain (saturation filter → prefix-cache-affinity scorer →
token-load scorer, v0.9 defaults [F: sticky-until-saturated blog]) → for P/D, the
router selects **two** endpoints (prefill + decode Variant) and the disagg sidecar
coordinates the KV transfer → the decode pod streams → KV events update the global
index; OTel spans mark every decision point (W3C trace context, metadata-only [F: tracing blog 2026-08-26]).

**v0.9 deltas that matter operationally** [F: v0.9 blog + release notes]:
- Router HA: standby EPP replicas route (no 503s) + `--drain-timeout` graceful rollout.
- Flow control with bounded defaults: request TTL 60 s, 5000/band, **503 (empty pool)
  vs 429 (backpressure)** status split.
- Sticky-until-saturated/token-aware routing is the default (replaced the 4-signal
  weighted blend whose behavior was "hard to predict and tune"); claimed 2–3× vs
  round-robin on prefill-bound workloads [F: blog; vendor claim].
- P/D rolling-update safety: revision-aware routing so KV never crosses model
  checkpoints (DisaggregatedSet); topology-aware routing + proportional pull-source
  selection across prefill replicas.
- KEDA becomes the autoscaling foundation; WVA retained on the legacy path.
- New well-lit paths: P2P KV sharing, Fast Model Actuation (+ ModelExpress-style P2P
  weight pull), IPP multi-model routing, diffusion/image-gen routing, E/P/D on
  mixed GPU+XPU, GB200/GB300 (DRA+RDMA), TPU v7 P/D benchmarks.
- RL incubation (veRL/vime integrations, GPU time-slicing targeting the 45–66% idle
  in synchronous RL loops) — explicitly not serving-GA; v0.10 targets a standardized
  model-server interface + KV-observability framework [F: v0.9 blog "What Is Next"].

## 6. llm-d Scheduling (the EPP plugin chain)

The EPP scores endpoints with a *filter → scorer* pipeline; what changed in v0.9 is
the doctrine: **bottleneck-matched configurations** [F: v0.9 blog]:
- prefill-bound workload → `prefix-cache-affinity-filter` + `token-load-scorer`
  (route to the endpoint whose cache holds the longest prefix; balance by prompt
  tokens, not request count).
- decode-bound workload → `prefix-cache-affinity-filter` + `active-request-scorer`.
- Saturation: sticky-until-saturated — requests stay on the best-prefix endpoint
  until a utilization threshold, then spill to the next-best (protects hit rate h
  without hot-spotting one pod).
- GPU-utilization-aware routing: DCGM-derived scorer (real utilization, not just
  queue depth) [F: v0.9 blog]; session affinity via `session_id` (multi-turn stays
  on the KV holder); header-based profile handler = per-traffic-class routing.
- Long-context: predicted-latency scheduling (online XGBoost, GA v0.7) plus the
  latency predictor extended to image/video token cost [F: v0.9 blog].

**Effect chain** [I: mechanism → metric]: prefix affinity raises h → cuts re-prefill
(§16 arithmetic) → TTFT falls and prefill pool utilization falls; token-aware
scoring balances *work* → tail ITL falls; saturation stickiness prevents cache
churn → hit rate survives high load. One practitioner measurement (Google Cloud,
config-specific): EPP prefix affinity hit rate 62.3% → 93.4% vs native vLLM DP8,
ceiling 95.8% [F: medium.com/google-cloud writeup, fetched 2026-09-06 — single
practitioner, not canonical]. Compare: K8s Service round-robin is LLM-blind (no
cache signal, no token weighting) — llm-d's entire value proposition is that gap.

## 7. llm-d and vLLM (engine vs platform, concretely)

| Question | Answer | Owner |
|---|---|---|
| Does llm-d replace vLLM? | **No** — model servers *are* unmodified vLLM pods (default image vLLM v0.26.0, SGLang v0.5.16 [F: v0.9 component tables]) | — |
| Model execution | vLLM (kernels, paged KV, continuous batching) | engine |
| Request scheduling (fleet) | EPP plugin chain + router | llm-d |
| Request scheduling (in-instance) | vLLM scheduler, untouched | engine |
| KV cache (per-instance) | vLLM paged KV + prefix cache | engine |
| KV cache (cluster view) | event-driven global index + offload + P2P | llm-d |
| KV transfer (P/D) | vLLM KV connectors (Nixl/LMCache/Mooncake/Offloading) driven by llm-d's disagg sidecar | engine transport, llm-d orchestration |
| Distributed inference (wide-EP) | vLLM/SGLang EP inside/below; llm-d places and scales the pools | both |
| Other engines? | SGLang first-class; TRT-LLM not a first-class llm-d model server as of 2026-09-06 [F: artifacts page lists vLLM/SGLang/TRTLLM *images*; TRTLLM via `nvcr.io` release image listed among upstream recommended model-server images — treat TRT-LLM-on-llm-d as possible-but-not-a-well-lit-path, UNVERIFIED at recipe level] | — |

**Inference engine vs distributed serving system**: the engine answers "how fast is
one GPU's work on one request-stream"; the platform answers "which of 200 pods, in
which role, holds this request's cache". Confusing them is the category error this
section exists to prevent (`Serving-Engines/Engine-Landscape.md`).

## 8. NVIDIA Dynamo Architecture Deep Dive (v1.4.x, verified 2026-09-06)

Full detail: `NVIDIA-Dynamo.md`. Current shape [F: docs.nvidia.com/dynamo + releases,
2026-09-06; stable v1.4.2 (2026-08-29), v1.4.0 GA 2026-08-14 ("17th feature release",
640 PRs/127 contributors), monthly cadence 1.0 Mar→1.4 Aug 2026, N-2 support window]:

```
 clients ──▶ Dynamo Frontend (Rust; OpenAI-compatible; /inference/v1/generate token API)
             │  (alt: K8s Gateway + GAIE → Dynamo EPP → worker Frontend sidecars direct)
             ▼
        Router (Rust) ── modes: kv | round-robin | random | power-of-two | least-loaded
             │          | device-aware-weighted | direct
             │  · global KV indexer (CRTC compressed radix tree; 13.49M block-ops/s [F: release note])
             │  · documented cost model (below) · multi-DC KV Relay (experimental)
             ▼
   ┌─────────────────────┬──────────────────────┬────────────────────┐
   ▼                     ▼                      ▼                    ▼
 Prefill workers      Decode workers         KVBM (tiers)        Planner (SLA → pools;
 vLLM/SGLang/TRT-LLM  same engines           GPU→CPU→SSD→object   event plane; Spica/AISimulate
 (TP/EP inside)  ─NIXL KV transfer─▶          + KV events global   config search; DGDR intent)
   └────────────── service discovery: etcd / NATS / TCP · K8s CRDs + EndpointSlices
```

**The router's documented cost model** [F: Dynamo router docs, fetched 2026-09-06 —
this is the clearest published scoring function in the space]:
`cost = prefill_load_scale · adjusted_prefill_blocks + potential_decode_blocks +
active_request_blocks`, where prefix overlap credits are per-tier: device (HBM) 1.0,
host (CPU) 0.75 (`--router-host-cache-hit-weight`), disk 0.25, shared cache 0.5 —
i.e., a cached block's routing value *depends on which tier it sits in*, encoding
the (1−h) physics of §16 directly into the scheduler. `decode_active_request_weight`
defaults 0 (opt-in); `router_temperature` → softmax sampling.

**2026 routing deltas** [F: v1.4.0 notes]: multi-datacenter KV routing (DC-scoped
Relay + lossy Cuckoo-filter projection across ≤16 DC lanes; reservation replay via
a selection cache so peers replay bookings instead of re-sending prompts); cache-salt
KV isolation (`x-tenant-id`/`nvext.cache_salt`) for multi-tenant caches; session
affinity synced across router replicas; decode-affinity + ISL-based aggregate-pool
routing; overload → HTTP **529** (configurable).

## 9. Dynamo Distributed Runtime

- **Workers communicate over**: TCP request plane (default), ZMQ event plane, NATS
  optional transports; KV plane = NIXL (UCX/libfabric) — control messages never ride
  the KV fabric [F: docs; k8s-ops findings].
- **Discovery**: etcd (default-off in chart), NATS-JetStream, or plain file/TCP for
  local; K8s CRDs (`nvidia.com/v1beta1`: DGD/DGDR) + EndpointSlices in production
  [F: platform chart README, fetched 2026-09-06].
- **Lifecycle**: the operator reconciles DGDs; admission webhooks mandatory (v1.0+);
  Grove PodCliqueSets (or LWS+Volcano) for multinode; DGDR = deploy-by-intent
  (model + SLA + hardware → profiler sweep → generated DGD; phases
  Pending→Profiling→Ready→Deploying→Deployed [F: DGDR API docs]).
- **Metadata**: KV events (block-level) feed the indexer; `dynamo.request.trace.v1`
  OTel stream carries audit/trace [F: metrics catalog].
- **Scale ladder**: 1 GPU (Dynamo local, file discovery) → multi-GPU node (worker
  with TP/EP) → single node agg/disagg → multi-node (Grove/KAI or Slurm) → multi-DC
  (KV Relay, experimental). The same binary graph scales; the discovery + scheduling
  layer changes per rung [F: README discovery modes].

## 10. Dynamo KV-Cache Architecture

- **Local**: engine paged KV (vLLM blocks / SGLang / TRT-LLM pools).
- **Cluster state**: the router's KV indexer — block-level events → CRTC radix tree
  → (multi-DC) lossy CKF projection. Router-owned, contrast llm-d's event-index
  assembled from engine emissions [I: structural].
- **KVBM tiers**: GPU HBM → CPU (host) → SSD/NVMe → object (S3/Azure; Infinia via
  NIXL). **Status caution** [F: feature matrix, fetched 2026-09-06]: KVBM is now
  marked "work in progress across all combinations" — the clean per-backend ✅/🚧
  of earlier releases is gone; the *offloading support matrix* is the current truth:
  vLLM GPU✅/CPU✅ (OffloadingConnector)/disk⚠️/shared-pool🚧; SGLang
  HiCache GPU✅/CPU✅ + Mooncake shared-pool✅; TRT-LLM merged GPU+RAM view 🟡.
- **Lookup → decision**: on request, router scores workers by per-tier overlap
  credits (§8 cost model); if the prefix lives on a decode-side tier, transfer
  shrinks by the hit fraction; if it lives behind slow storage, the planner trades
  pull latency vs recompute (§16 ratio).
- **Recompute vs transfer** — the platform encodings: Dynamo's per-tier weights
  (1.0/0.75/0.25) [F] and vLLM's new **bidirectional KV transfer** (P *pulls* from
  D over RDMA for multi-turn; TTFT drop on long-prefill multi-turn [F: NixlConnector
  usage guide, fetched 2026-09-06]) and llm-d's **P2P KV sharing** (peer CPU-tier
  pulls; measured crossover points: gpt-oss-120b/H200 48K-prefix recompute 1,988 ms
  vs 235 ms pull (−88%); on a 753B GLM testbed P2P wins only above ~8.7K tokens
  [F: llm-d P2P blog, 2026-08-15]) all implement the same rule: *pull if
  `bytes(1−h)/BW < t_prefill(miss)`; else recompute.* The crossover is model- and
  bandwidth-dependent — there is no universal answer (§27 #4).

## 11. NIXL (the transfer layer, current state)

Deep dives: `GPU-Communication/07-nixl-deep-dive.md`, `Implementation/06-nixl-transfer.md`.
2026-09-06 verified state [F: ai-dynamo/nixl repo + releases]:
- **Version line**: releases v1.3.0 (Jun 15) → 1.3.1 → 1.3.2 → 1.4.0 (Aug 14) →
  1.4.1 (Sep 1); main at 1.5.0; ~monthly cadence. Dynamo 1.4.2 pins NIXL 1.3.2
  (vLLM path) / 1.3.1 (TRT-LLM) / 1.3.0 (SGLang), UCX 1.21.
- **14 buildable plugins** (meson.build): UCX, LIBFABRIC, POSIX, OBJ, GDS, GDS_MT,
  MOONCAKE, HF3FS, GUSLI, GPUNETIO, UCCL, AZURE_BLOB, INFINIA, TELEMETRY_DOCA —
  storage (GDS/GDS_MT/GUSLI/HF3FS/Infinia/Azure), network (UCX/libfabric/
  Mooncake/UCCL/GPUNETIO), memory (POSIX/OBJ) [F: meson.build]. New since Aug:
  GUSLI (userspace block I/O), INFINIA (DDN object store), GDS_MT split.
- **NIXL-EP**: expert-parallel dispatch/combine data plane (`nixl_ep`, CUDA-graph
  reuse across rank changes, 1.4.1) — NIXL is becoming the MoE a2a mover too [F].
- **Performance work**: stride/compressed descriptors (1.39M descriptors 44 MB→7 KB;
  `make_prepped_xfer` up to 5.4× faster in SGLang micro-bench [F: 1.4.0 notes]);
  NVTX tracing; Prometheus/DOCA telemetry (`nixl_bytes_transferred` et al., port 19090).
- **Packaging**: one PyPI wheel auto-selects CUDA 12/13 backends; ROCm wheel
  variant; Rust bindings (`nixl-sys`); ETCD metadata exchange first-class.
- **NIXL vs NCCL vs UCX** (restated, `GPU-Communication/15` has the table): NCCL =
  collectives for static training-shaped ranks; UCX = point-to-point transport
  substrate (NIXL's default backend); NIXL = inference-state mover that *selects*
  transports dynamically for dynamic topologies (workers churn, tiers, KV+weights).
- **Where it bites**: EFA requires LIBFABRIC backend and privileged pods; wrong
  backend = silent TCP fallback ~98 s TTFT [F: Dynamo EFA docs]; practitioner
  repro: misconfigured pod moved KV at 0.49 GB/s where raw GPU peer copy does
  48–51 GB/s [F: Google Cloud writeup — config-dependent]. NIXL telemetry on 19090
  is the "is RDMA actually on?" check (§20, §23).

## 12. Dynamo + Inference Engines (responsibility split, 2026-09-06 matrix)

| Responsibility | Dynamo | Engine (vLLM / SGLang / TRT-LLM) |
|---|---|---|
| kernels, model execution, in-instance batching | — | ✓ all three |
| P/D disagg wiring, KV routing, Planner, KVBM, migration | ✓ | expose hooks |
| KV transport | NIXL | engine-side connector/backend selection |
| Engine pins in Dynamo 1.4.2 | NIXL 1.3.2/1.3.1/1.3.0 | vLLM 0.26.0 / SGLang 0.5.16 / TRT-LLM 1.3.0rc22 [F: release notes] |
| Feature coverage | vLLM 14/15 · SGLang 9/15 · TRT-LLM 9/15 [F: feature matrix] | — |

Engine-specific notes [F: fetched 2026-09-06]:
- **vLLM**: NixlConnector fully-async; MultiConnector chains; OffloadingConnector
  CPU tier; bidirectional multi-turn pull; "Disaggregated prefilling DOES NOT
  improve throughput" remains the docs' honest framing [F: vLLM docs].
- **SGLang**: PD disagg with Mooncake *or* NIXL backends; NVLink KV transport for
  NVL72 (`MC_FORCE_MNNVL`); heterogeneous-TP staging buffer (2–5× at high
  concurrency; not for MLA models); SGLang router supports `--pd-disaggregation`
  standalone (a platform-lite path without Dynamo) [F: SGLang docs].
- **TRT-LLM**: MPI/UCX/NIXL all supported; direct device-to-device transfer;
  different parallel strategies for context vs generation phases; measured disagg
  wins 1.7× (DS-R1 @50 tok/s/user) to 6.11× (Qwen3, GB200) [F: TRT-LLM tech blog];
  per-layer KV-overlap still "future work"; KV event API exposed for cache-aware
  routing across executors [F: NVIDIA dev blog].

## 13. llm-d vs Dynamo (the head-to-head, current)

The full 25-row verified table lives in `Dynamo-vs-llm-d.md`; the 2026-09-06 state
compressed (no winner declared — different substrates):

| Area | llm-d (v0.9.0) | Dynamo (v1.4.2) |
|---|---|---|
| Substrate | K8s-native (GAIE InferencePool v1 + EPP, CRD-free role labels) | Own Rust control plane; K8s via operator/DGDR, or etcd/NATS/file |
| Routing state | event-driven KV index (engine-emitted events) | router-owned CRTC radix registry + CKF multi-DC projection |
| Routing policy | bottleneck-matched plugin chains; sticky-until-saturated default | documented cost model, per-tier credits; 7 modes; cache-salt tenancy |
| Transfer | engine connectors (NIXL/UCCL/Offloading) + disagg sidecar | NIXL in-project (+ ModelExpress weights) |
| KV tiers | CPU/SSD offload + P2P peer pulls | KVBM GPU→CPU→SSD→object ("in progress" caution) |
| Autoscaling | KEDA foundation + WVA | Planner SLA/TCO + Spica/AISimulate config search + DGDR intent |
| Engines | vLLM, SGLang (TRT-LLM not a well-lit path) | vLLM 14/15, SGLang 9/15, TRT-LLM 9/15 |
| Accelerators | NVIDIA/AMD/Intel/TPU tested paths | NVIDIA gravity (NVL72/Grove/Enterprise) |
| Maturity posture | v0.9 "hardened for scale", adopters incl. Vertex AI/Red Hat/Mistral/Snowflake | 1.x production line, monthly GA, Enterprise support SKU |
| Multimodal/E-P/D | diffusion routing, E/P/D GPU+XPU | vLLM-Omni NIXL RDMA AR→DIT, E/P/D + NVDEC |

Both implement the five jobs; they differ in *where the state lives* (K8s ecosystem
vs in-process), *who owns the transfer stack*, and *which fabric gravity* they assume.

## 14. Control Plane vs Data Plane (explicit separation, both systems)

```
        CONTROL PLANE (decisions, seconds–minutes)          DATA PLANE (bytes, microseconds–ms)
llm-d :  Gateway API policy · EPP filter/scorer chain ·     prompt/tokens over HTTP · engine batches
         KEDA/WVA scaling · KV index (events) ·             kernels · paged KV in HBM
         Variant membership · flow-control admission        KV transfer (NIXL/UCCL connectors, RDMA)
Dynamo:  Router cost model + indexer · Planner + DGDR ·     token streaming · engine kernels
         Grove/KAI scheduling · KV events → CRTC/CKF ·      NIXL KV + weight transfers (RDMA/NVLink/GDS)
         admission webhooks · migration decisions           MoE AllToAll (NCCL/NIXL-EP/DeepEP)
```
The rule that survives every release: **control planes may be wrong slowly; data
planes may not be slow at all.** A router picking a 2nd-best worker costs a few %;
KV transfer on TCP costs 200–500× [F: Dynamo RDMA docs]. That asymmetry is why both
projects keep decision logic insoftware-replaceable components while pushing bytes
through RDMA/NVLink. (Design lesson, not marketing.)

## 15. Networking Requirements (what the fabric must carry)

Only one message class is *unique* to disaggregated platforms — KV transfer — but it
is the one that sets fabric requirements. Everything else (TP AllReduce, PP p2p, MoE
AllToAll) exists in any multi-GPU deployment (`AI-Factory-Networking/README.md`).

**The KV-production-rate rule** [E, this session]: during prefill, a worker *produces*
KV at `r_prod = KV_bytes(S) / t_prefill(S)` bytes/s. The fabric must carry at least
`r_prod` to keep up, and **~8× `r_prod` to hide the transfer under the prefill itself**
(rule of thumb + arithmetic: `GPU-Communication/08-nixl-kv-cache-transfer.md` §overlap).
At 32K prompts, per node (H100-class, typical MFU [A: 45–50%]):

| Model class (32K prompt) | Prefill/sess [E] | KV/sess [E] | KV production [E] | Link to hide (8×) [E] |
|---|---|---|---|---|
| 7B dense, TP1 | 0.93 s | 4.0 GiB | 4.6 GB/s | ~296 Gb/s |
| 70B dense, TP8/1 node | 1.29 s | 10.0 GiB | 8.3 GB/s | ~533 Gb/s |
| 405B dense, TP8/1 node | 7.45 s | 15.75 GiB | 2.3 GB/s | ~145 Gb/s |
| DeepSeek-V3-class MoE (37B active), EP8 | 0.68 s | 2.14 GiB | 3.4 GB/s | ~216 Gb/s |

Read the table twice: **faster prefill raises the fabric bar** (the 7B row needs more
bandwidth than the 405B row because prefill finishes sooner), and MLA shrinks both KV
and the bar (MoE row). The 200–400 GbE class in the enterprise reference (§24) follows
directly from the 70B row — matching the DeepSeek-R1 report's own finding that
prefill:decode disaggregation "needs significantly larger bandwidth" [F: arXiv:2501.12948].

**Transfer time table** (what one request pays, serially, before first decode token)
[E: house 95%-efficiency fabric rates, same convention as `Overview.md` §Networking]:

| Prompt KV (70B FP16) | 25 GbE (3.0 GB/s) | 100 GbE (11.9) | 200 GbE (23.8) | 400 GbE (47.5) | 800 GbE (95) | NVLink domain (~450–900 GB/s) |
|---|---|---|---|---|---|---|
| 8K tokens (2.5 GiB) | 0.89 s | 0.23 s | 0.11 s | 57 ms | 28 ms | 3–6 ms |
| 32K tokens (10 GiB) | 3.6 s | 0.90 s | 0.45 s | 0.23 s | 0.11 s | 12–24 ms |
| 128K tokens (40 GiB) | 14.3 s | 3.6 s | 1.8 s | 0.90 s | 0.45 s | 47–95 ms |

With prefix-hit rate *h*, multiply by (1−h): at h=0.9 the 32K/100 GbE entry drops
to 90 ms [E: 0.90 s × 0.1]. **Why RDMA matters**: KV bytes cross the wire exactly once
and are on the TTFT critical path; TCP adds host staging + kernel copies + loss
recovery to a transfer the NIC could write straight into HBM. The Dynamo docs make
it concrete: KV transfer over TCP is "200-500x slower... roughly 98 s TTFT on TCP
versus 200-500 ms with RDMA" [F: docs.nvidia.com/dynamo RDMA overview, fetched
2026-09-06]. Same message in the fabric taxonomy: `AI-Factory-Networking/03-rdma-fundamentals.md`.

**Fabric shopping list by model class** [I: from the tables above + break-even page]:
- 7B-class, single node, modest SLOs: 100–200 GbE suffices even for disagg.
- 70B dense: 200 GbE floor, 400 GbE comfortable; NVLink-domain P/D (same NVL72 or
  pair-node) removes the question entirely.
- 200B+ dense: prefill time is long, so per-request ratios ease; capacity (KV GiB)
  and *aggregate* λ·KV dominate → 400 GbE class with tiering.
- Large MoE: MLA/MLA-class KV eases bytes, but AllToAll expert traffic shares the
  same fabric → rail-optimized, separate planes if possible (`AI-Factory-Networking/34-moe-all-to-all.md`).

## 16. KV Cache Transfer — the worked example (70B, 32K prompt, 8K generation)

Every number Python-verified this session. Model: Llama-3-class 70B, GQA 80 layers,
8 KV heads, head_dim 128, FP16 KV [F: hyperparams] → **KV/token = 2·80·8·128·2 B =
320 KiB/token** [E].

1. **KV size**: 32K prompt → `32768 × 320 KiB = 10.0 GiB` [E]; +8K generated →
   `40960 × 320 KiB = 12.5 GiB` per session [E].
2. **Where it lives**: TP8 → 40 KiB/token/GPU → 1.25 GiB per GPU for the prompt [E].
   The transfer must gather/re-shard across the TP rank group (sharded-mode note:
   `Implementation/01-distributed-kv.md`).
3. **Transfer cost** (10 GiB): 100 GbE ≈ 0.90 s; 400 GbE ≈ 0.23 s; NVLink ≈ 12–24 ms [E].
4. **Recompute cost**: one prefill of 32K tokens on 70B ≈ 4.6 PFLOP → 10.3 s on
   1×H100 at 45% MFU, 1.29 s on TP8 [E]. So: **recompute/transfer on TP8+400 GbE
   ≈ 6× — transfer wins**; on 1 GbE-class fabrics it inverts [E; and the full
   break-even model is `Inference/Prefill-Decode-Disaggregation.md`].
5. **The h-discount**: only uncached prefix crosses the wire — `bytes = S·KV_tok·(1−h)`.
   h=0.5 halves it; h=0.9 takes 100 GbE to 90 ms [E]. This single factor is why
   KV-aware routing and tiered caches are the platform layer's highest-leverage
   features (`Implementation/03-kv-aware-routing.md`).
6. **Decode economics** (why decode pools want batches): 70B TP8 H100 step bytes =
   16.3 GiB weights + B×ctx×40 KiB KV reads (full-attention worst case [A]) →
   at ctx=32K: B=1 → TPOT 5.6 ms; B=16 → 11.6 ms (86 tok/s/stream, 1375 tok/s/GPU);
   B=64 → 30.9 ms (32 tok/s/stream) [E]. Prefill-burst interference is exactly what
   the P/D split removes from this table.

## 17. Long-Context Workloads (128K → 1M)

70B FP16 reference [E throughout; decimal-1M convention consistent with wiki]:

| Context | KV/seq | KV/seq/GPU (TP8) | Prefill FLOPs (proj + causal attn) | TP8 prefill time (attn incl.) [E] | Concurrent 32K-class sessions per 80 GiB GPU |
|---|---|---|---|---|---|
| 128K | 40 GiB | 5.0 GiB | 18.4 + 22.5 PFLOP | ~12 s (TP8) | 1–2 @128K |
| 256K | 80 GiB | 10.0 GiB | 36.7 + 90.1 PFLOP | ~36 s (TP8) | — |
| 1M | 320 GiB | 40.0 GiB | 146.8 + 1441 PFLOP | ~7.4 min (TP8) | — |

- Attention FLOPs overtake projection FLOPs at S* ≈ 53K tokens for this shape [E:
  2P/(4·L·d_head·n_kv)], so beyond ~50K the quadratic term dominates and prefill
  becomes attention-kernel-bound — one reason long-context TTFT benefits from
  dedicated prefill pools with FA-3-class kernels (`Attention/README.md`).
- **KV capacity inverts the economics**: at 1M context a single session's KV
  (320 GiB) exceeds one H100's memory — the serving system *must* tier (KVBM GPU→
  CPU→SSD→object; llm-d CPU/SSD offload) or shard KV across a KV group. Distributed
  KV infrastructure is optional at 4K and structural at 1M [I].
- **Scheduling**: long-prompt requests are the prefill pool's bursty load; the
  Planner/DGDR's `workload.isl` and llm-d's SLO classes exist precisely to size
  pools for ISL distributions [F: DGDR spec defaults isl=4000/osl=1000, fetched
  2026-09-06; llm-d WVA docs].
- **Cache reuse**: RAG/chat reuse grows with context length; h rises, the (1−h)
  discount pays more, and prefix-cache-aware routing goes from nice to mandatory
  (`KV-Cache/Prompt-and-Prefix-Caching.md`).
- Frontier-MoE reality check [F: Dynamo release notes, fetched 2026-09-06]: the
  current Dynamo recipes serve 1M-context checkpoints (DeepSeek-V4-Pro-0813,
  FP8 KV) on GB200/H200 in aggregated *and* 1P1D disaggregated profiles — 1M-context
  P/D is a shipping configuration, not a paper claim, as of the 1.4.x/1.5.0-dev line.

## 18. MoE Models (DeepSeek / Qwen / GLM / Kimi class)

- **The MoE serving shape**: per token, a router picks top-k experts; dispatch and
  combine are **AllToAll** collectives, per MoE layer [F: standard; MoE math]. For
  DeepSeek-V3-class (d=7168, top-8, BF16) that is ~224 KiB/GPU/token each direction
  at EP8 [A: dispatch+combine volume] — which is why wide-EP is fabric-first
  (`AI-Factory-Networking/34-moe-all-to-all.md`, `Distributed-Inference/README.md` §EP).
- **Decode economics change**: only *active* params are read per token. DeepSeek-V3
  (37B active) → 8.6 GiB/GPU at EP8 → batch-1 decode roofline ≈ 362 tok/s/GPU [E:
  3.35 TB/s ÷ 8.6 GiB], rising toward 2900 tok/s/GPU at EP64 [E]. MoE decode is
  *more* bandwidth-efficient per GPU than dense-70B (16.3 GiB/GPU) — but the AllToAll
  traffic and expert-imbalance variance eat into it (`GPU-Communication/14-moe-communication.md`).
- **KV is the quiet win**: MLA-class KV (~69 KiB/token for DeepSeek-V3 vs 320 KiB
  for 70B GQA [E: 576×61×2]) shrinks both capacity and transfer 4.7× — MoE models
  are *easier* to disaggregate byte-wise, which is why the frontier-MoE recipes are
  P/D-first (Dynamo DeepSeek/Kimi recipes; llm-d wide-EP well-lit path).
- **P/D vs EP solve different problems** [I: categorical]: EP splits *one model's
  experts* across GPUs (intra-request parallelism); P/D splits *request phases*
  across pools (inter-request scheduling). Frontier deployments stack both — Dynamo
  1.4.x recipes run EP inside workers + P/D across pools (DeepSeek-V4-Pro-0813:
  aggregated TP8/EP8 or 1P1D 16-GPU [F: release notes 2026-09-06]); llm-d's wide-EP
  well-lit path does the same on K8s (16×16 B200 result [F: README]).

## 19. Kubernetes Reference Architectures

Object mapping (verified against the deployment docs 2026-09-06; full install detail
in the platform pages):

| Concern | Dynamo object | llm-d object |
|---|---|---|
| workload | `DynamoGraphDeployment` (DGD) / deploy-by-intent `DGDR` (`nvidia.com/v1beta1`) | Deployment + **InferencePool** (GAIE `inference.networking.k8s.io/v1`) label selector |
| role split (P/D) | components/pools inside the graph (PodClique via Grove) | **Variant** labels (prefill/decode) on pods |
| gang/multinode | **Grove** (+KAI scheduler) or LWS+Volcano; operator errors without one [F: install docs] | per-guide; LWS-based multinode [A: check current guides] |
| autoscaling | Planner (SLA/TCO) + KEDA/HPA on dynamo_* metrics | KEDA foundation + WVA; EPP queue/saturation metrics |
| gateway | Dynamo-native Frontend **or** GAIE (agentgateway/Istio) + Dynamo EPP | Gateway API + llm-d EPP (charts: router-standalone / router-gateway) |
| RDMA | Network Operator + RDMA shared device plugin (`rdma/hca_shared_devices_a`), GPU Operator GPUDirect, EFA/GKE-TCPXO/AKS-IB variants [F] | device plugin + `llm-d-cuda` image (GKE IB patches, DeepEP GB200 patches) [F: artifacts] |
| metrics | auto-created **PodMonitor** per DGD + ServiceMonitor for operator [F] | ServiceMonitor (EPP) + PodMonitors (prefill/decode pods) [F] |
| installer | dynamo-platform chart / **AICR** version-locked bundles (DRA ⇒ K8s 1.34+) | Helm (GAIE-published charts today, llm-d-published later [F]) |

```
Dynamo on K8s                                llm-d on K8s
helm: dynamo-platform (operator,             helm: llm-d-router-gateway
  Grove, KAI, NATS/etcd optional)               (InferencePool + EPP + proxy)
        │ DGDR (intent) ──profiler──▶ DGD           │ GAIE CRDs v1 (InferencePool GA)
        │                                           ▼
        ▼                                     Deployments: prefill / decode pods
Grove PodCliqueSets (multinode,                 (vLLM v0.26.0 / SGLang v0.5.16 images)
  topology-aware) or LWS+Volcano                │ Variant labels = roles
        │                                       ▼
        ▼                                     Envoy/agentgateway Gateway + HTTPRoute
Workers: vllm/sglang/trtllm-runtime            → EPP picks endpoint (ext-proc)
  + Network Operator RDMA resource             KV: engine connectors + offload/P2P
  + GPU Operator (GPUDirect)
```

Two verified snippets (shapes, not full manifests):
```yaml
# Dynamo deploy-by-intent (DGDR, nvidia.com/v1beta1) [F: DGDR API docs]
apiVersion: nvidia.com/v1beta1
kind: DynamoGraphDeploymentRequest
spec:
  model: deepseek-ai/DeepSeek-R1            # only required field
  backend: vllm                             # auto|vllm|sglang|trtllm
  workload: {isl: 4000, osl: 1000, concurrency: 100}
  sla: {ttft: 2000, itl: 30, optimizationType: throughput}   # ms defaults per spec
  features: {kvRouter: {enabled: true}}     # sets DYN_ROUTER_MODE=kv on the Frontend
```
```yaml
# llm-d serving pool (GAIE InferencePool v1) [F: GAIE docs; EPP port 9002]
apiVersion: inference.networking.k8s.io/v1
kind: InferencePool
spec:
  selector: {matchLabels: {app: vllm-qwen3-32b}}
  targetPorts: [{number: 8000}]
  endpointPickerRef: {name: vllm-qwen3-32b-epp, port: {number: 9002}, failureMode: FailOpen}
```

## 20. Observability — the metric inventory

| Signal | Dynamo | llm-d / engine |
|---|---|---|
| TTFT | `dynamo_frontend_time_to_first_token_seconds` (hist) [F] | `llm_d_epp_request_ttft_seconds`; `vllm:time_to_first_token_seconds` [F] |
| TPOT/ITL | `dynamo_frontend_inter_token_latency_seconds` | `llm_d_epp_request_streaming_tpot_seconds` / `_itl_seconds`; engine `vllm:time_per_output_token_seconds` (name drift across vLLM versions — check your pin, UNVERIFIED per-tag) |
| req/s, errors | `dynamo_frontend_requests_total`; 529 overload counter | `llm_d_epp_request_total` / `_error_total`; 503-vs-429 split [F] |
| KV hit rate | `dynamo_frontend_cached_tokens`, `dynamo_epp_cached_tokens` | `vllm:prefix_cache_hits_total`/`_queries_total`; llm-d docs: persistently low hit rate ⇒ EPP misrouting [F] |
| KV transfer | NIXL telemetry port **19090**: `nixl_bytes_transferred`, `nixl_num_failed_transfers` [F] | same NIXL counters via connectors; disagg-sidecar metrics |
| cache occupancy | `dynamo_component_gpu_cache_usage_percent` | `vllm:kv_cache_usage_perc`; llm-d `performance-kv-cache` dashboard |
| pools/queues | per-worker `worker_last_ttft/itl` gauges (worker_type labels) | `llm_d_epp_flow_control_queue_size` (the queue-depth signal), `_pool_saturation` (>1.0 = throttling) [F] |
| GPU mem/util | DCGM exporter (`DCGM_FI_DEV_GPU_UTIL/FB_USED/XID`), port 9400 std / 9401 local-docker [F] | same DCGM; llm-d GPU-utilization scorer consumes it |
| P50/95/99 | `histogram_quantile()` over the TTFT/ITL histograms (Prometheus) | same |
| traces | `dynamo.request.trace.v1` → OTel Collector (OTLP) [F] | W3C trace context Gateway→EPP→P/D→engine, metadata-only [F] |

Stack: kube-prometheus-stack (required for Planner `sla` mode — it reads live TTFT/ITL
from Prometheus [F]) + Grafana dashboards (llm-d ships named dashboards; Dynamo ships an
application dashboard incl. KV-router + GPU panels) + DCGM exporter (GPU Operator
DaemonSet) + OTel Collector. **The two metrics that catch 80% of platform incidents**:
KV hit rate (routing health) and NIXL bytes/failed-transfers (fabric health) [I].

## 21. Failure Modes & Recovery

| Failure | What breaks | Recovery mechanism | Design note |
|---|---|---|---|
| prefill worker dies | in-flight prefill + its KV (pre-transfer) | re-route to another prefill; recompute = one prefill cost | correctness safe; TTFT hit bounded by §16 math |
| decode worker dies | live streams | Dynamo: canary health + **in-flight request migration** [F: README] — needs KV in a reachable tier; llm-d: EPP reroutes new reqs; drain-timeout for rollouts | KV tiering is what makes migration cheap; without it, migration = re-prefill |
| KV transfer fails | request stalls pre-decode | NIXL `num_failed_transfers` counter → re-prefill fallback | push(WRITE)/pull(READ) connectors "must never be paired" [F: AWS deployment notes] |
| RDMA misconfigured | **silent** 100× slowdown (98 s TTFT symptom) [F: Dynamo docs] | NIXL telemetry + iperf3 baseline probe; EFA needs LIBFABRIC + privileged pods [F] | the #1 field failure class; test fabric before load |
| router/EPP fails | routing stops | llm-d: multi-EPP HA, standbys route (no 503) [F: v0.9]; GAIE `failureMode: FailOpen` = route cache-blind rather than fail | degraded mode = lose cache affinity, keep serving [I] |
| stale KV metadata | router sends to a cold worker | events are soft state; worst case = cache miss + re-prefill, never wrong output; Dynamo CKF projection is explicitly lossy/read-optimized [F] | correctness must never depend on cache state [I: architectural invariant both systems preserve] |
| cross-tenant KV leaks | privacy/isolation | Dynamo cache-salt routing (`x-tenant-id`) partitions the index [F: 1.4.0]; llm-d flow-control per flow ID/priority | multi-tenant caches need index-level isolation, not just quota |
| GPU OOM | crash or stall | admission control (flow-control gating; 503/429/529 statuses); KV watermark eviction; capacity planning via §17 | size pools from KV capacity, not FLOPS [I] |
| worker overload | ITL explosion | queue-depth autoscale (KEDA/Planner); backpressure (429 retryable vs 503 empty-pool; Dynamo 529) [F] | reject early at the gateway; never queue unboundedly |
| network congestion | transfer P95 spikes; fabric knee | QoS/ECN (RoCE: `AI-Factory-Networking/21-dcqcn.md`); separate planes for MoE a2a vs KV [A] | monitor fabric alongside pools (§20) |

## 22. Performance Engineering — how to benchmark a platform properly

A platform benchmark is a **cluster benchmark**: the unit of measurement is the
fleet at an SLO, never one GPU. Metric set: `Overview.md` §Cluster Benchmark Metrics.
Methodology:

- **Baseline**: same engine, same version, same model, monolithic pools, round-robin
  routing, HPA off. Every platform claim is measured *against this*.
- **Test 1 (monolithic)**: engine default; establishes engine-level TTFT/ITL/tp/s.
- **Test 2 (P/D)**: same model, pools split, P:D swept {1:1, 1:2, 1:4, 2:4};
  record TTFT P50/95/99, ITL P50/95/99, per-pool utilization, KV-transfer P50/95.
- **Test 3 (prefix-heavy)**: multi-turn trace replay (Mooncake trace via AIPerf is
  the current standard [F: Dynamo recipes use AIPerf trace-replay]); measure KV hit
  rate with router ON vs OFF — the hit-rate delta *is* the router's value.
- **Test 4 (long-context)**: ISL sweep 1K→128K at fixed OSL; watch TTFT scaling and
  fabric saturation (§15 aggregate regime).
- **Test 5 (high-concurrency)**: step request rate until goodput stops growing;
  find the two pool knees + the fabric knee [I: three-knee structure].
- **Test 6 (multi-node)**: repeat at N nodes; scaling efficiency = tok/s/GPU at N ÷
  at 1 (sublinearity = comm + transfer overhead).
- **Tools**: AIPerf (Dynamo's documented benchmarking tool [F: README]); llm-d
  benchmark repo (llm-d-benchmark, deployment→teardown automation [F: v0.9.0
  component table]); engine-native: vLLM benchmarks/, SGLang bench_serving.
- **Expected bottlenecks, in order of appearance**: prefill pool saturation (TTFT
  SLO breaks first) → decode pool saturation (ITL SLO) → fabric saturation (KV
  transfer P95 spikes; aggregate-oversubscription regime) → router starvation (hit
  rate falls as all caches churn). The metric that identifies each: queue depth per
  pool, per-pool utilization, `nixl_bytes_transferred` + retransmit counters,
  KV hit-rate time series [F: NIXL telemetry metric names, fetched 2026-09-06].

## 23. Practical Home-Lab Experiment — 2 × DGX Spark, P/D disaggregation

**Apparatus** [A: planning numbers, NOT measured — per standing rule no Spark box
cites latency as production evidence; DGX Spark/GB10 = ~273 GB/s LPDDR5X unified
memory, ConnectX-class 200 GbE networking]: Spark-1 = prefill worker, Spark-2 =
decode worker, both running vLLM (same version) with `NixlConnector` P/D over the
200 GbE link; AIPerf or vLLM benchmark client driving identical traces at each mode.

| Test | Config | Measure |
|---|---|---|
| baseline | single Spark, monolithic vLLM | TTFT/TPOT/tok-s at B=1,8,32 |
| disagg | 1P1D across the 200 GbE link | same metrics + transfer time |
| KV transfer | vary ISL 1K/8K/32K/64K/128K | measured transfer time vs table below |
| generation sweep | OSL 128→2K at fixed ISL | where disagg crossover sits for chat shapes |

**Predicted numbers to check against** [E: 8B FP16 = 128 KiB/token KV; 200 GbE
≈ 23.75 GB/s effective; prefill at an assumed 50 TFLOP/s effective — Spark roofline
is compute-side [A]]:

| ISL (8B model) | KV produced | 200 GbE transfer [E] | Recompute @50 TF/s [A] | Transfer/recompute |
|---|---|---|---|---|
| 1K | 0.12 GiB | 5.4 ms | 0.33 s | 0.02× |
| 8K | 1.0 GiB | 43 ms | 2.6 s | 0.02× |
| 32K | 4.0 GiB | 172 ms | 10.5 s | 0.02× |
| 64K | 8.0 GiB | 344 ms | 21 s | 0.02× |
| 128K | 16 GiB | 687 ms | 42 s | 0.02× |

**What the lab will and will not show** [I]: transfer is 20–50× cheaper than
recompute even at 8B — so P/D *can* win on paper at every ISL. But Spark's decode
roofline is modest (8B FP16 ≈ 17 tok/s single-stream [E: 273 GB/s ÷ 15 GiB]), so
the interference P/D removes is a small absolute number, and the 200 GbE link is
*slower relative to Spark's memory* than in a datacenter. Expect: TTFT improves at
high ISL and concurrency; TPOT roughly unchanged; the exercise teaches the *moving
parts* (connectors, routing modes, transfer telemetry), not production economics.
The honest conclusion: 2×Spark is an excellent **topology classroom** and a poor
**economics simulator** — scale the same experiment's numbers to 70B/H100-class
hardware for production claims (and re-run on RTX 5090 / RTX PRO 6000 class boxes
for citable latency).

## 24. Enterprise Reference Architecture (production K8s)

Synthesis of the verified deployment docs (2026-09-06 fetches; details per-platform
in `NVIDIA-Dynamo.md`/`llm-d.md` K8s sections):

```
                    ┌────────────────────────────────────────────────┐
 clients ──TLS──▶   │ API/Gateway tier: Envoy/Istio/agentgateway     │
                    │ (auth, rate limit, multi-tenant policy)        │
                    └───────────────┬────────────────────────────────┘
                                    │ Gateway API (GAIE InferencePool v1)
                    ┌───────────────▼────────────────────────────────┐
                    │ Intelligent router: EPP (llm-d) / Dynamo EPP   │
                    │  · KV-cache affinity   · load + SLO class      │
                    │  · flow control (queue, saturation gating)     │
                    └───────┬───────────────────────────┬────────────┘
                            │                           │
              ┌─────────────▼──────────┐    ┌───────────▼────────────┐
              │ PREFILL POOL           │    │ DECODE POOL            │
              │ vLLM/SGLang/TRT-LLM    │KV  │ same engines, bw-tuned │
              │ (TP/EP per recipe)     │NIXL│ (batch-heavy)          │
              └─────────────┬──────────┘RDMA└───────────┬────────────┘
                            └──────────┬────────────────┘
                    ┌──────────────────▼──────────────────────────┐
                    │ KV tiering: HBM → CPU → SSD/NVMe → object    │
                    │ (KVBM / llm-d offload + global KV events)    │
                    └──────────────────────────────────────────────┘
   K8s substrate: GPU Operator · Network Operator + RDMA device plugin
   (rdma/hca_shared_devices) · Grove/KAI or LWS+Volcano for multinode ·
   kube-prometheus-stack (+ PodMonitor/ServiceMonitor) · DCGM exporter · OTLP
```

- **Fabric**: Spectrum-X or IB for the KV plane; GPUDirect RDMA enabled in GPU
  Operator; the RDMA-vs-TCP 200–500× gap [F: Dynamo docs] is why the Network
  Operator line is mandatory, not optional, in any P/D deployment.
- **Sizing flow**: SLO → DGDR profiler (Dynamo) or WVA/HPA-KEDA signals (llm-d) →
  P:D ratio → pool HPA. Autoscaling reads inference metrics (queue depth, TTFT/ITL),
  never CPU [F: both platforms' docs].

## 26. 80/20 Learning Guide

**MUST KNOW** (carries most practical judgment): prefill vs decode regimes; P/D
disaggregation + when it loses; KV bytes formula + worked example (§16);
KV-aware routing and the (1−h) discount; engine vs platform layer; KV transfer over
RDMA (and why TCP fails); the five cluster jobs.

**SHOULD KNOW**: KVBM/llm-d tiering; prefix caching vs exact-match routing; P:D
ratio as workload function; Gateway API Inference Extension (InferencePool/EPP);
SLO-driven autoscaling (Planner, WVA); AIPerf/trace-replay benchmarking; MoE AllToAll
fabric demands; MLA's effect on KV economics.

**ADVANCED**: NIXL backend selection per fabric (UCX vs libfabric/EFA; silent
failure modes); TP-sharded KV gather/re-shard on transfer; event-driven global KV
index vs router-owned radix registry; wide-EP + P/D stacking; chunked-prefill vs
disagg as competing TTFT/ITL controls; DRA/GPU scheduling on K8s 1.34+.

**DEEP SPECIALIZATION**: congestion control interaction (DCQCN/PFC) with KV bursts;
NVLink-domain P/D placement (DistServe low node-affinity trick); KV-cache eviction
policy co-design with routing; multi-plane fabrics separating MoE AllToAll from KV
traffic; goodput-at-SLO theory (DistServe §6.3 measurement template).

## 27. Common Misconceptions

1. **"llm-d replaces vLLM."** No — llm-d's model servers *are* vLLM/SGLang pods; it
   orchestrates them [F: both READMEs]. Replacing the engine leaves llm-d nothing to
   orchestrate.
2. **"Dynamo is just another inference engine."** No — it ships no model-execution
   code; its workers are vLLM/SGLang/TRT-LLM instances [F: v0.8.0 design doc].
3. **"P/D disaggregation always improves performance."** No — vLLM's own docs: it
   "DOES NOT improve throughput" [F]; community repros show slower-than-aggregated
   cases [F: dynamo#2552]; slow fabrics invert TTFT [E: §16]. It buys SLO control,
   not free throughput.
4. **"KV transfer is always cheaper than recomputation."** No — it is a ratio:
   `S·KV_tok·(1−h)/BW` vs `t_prefill(S)`; on ≤10 GbE it loses [E + break-even page];
   with high h, recomputation of the *miss* only can win over a cold-cache pull.
5. **"NCCL and NIXL do the same job."** No — NCCL is the collective library for
   model parallelism (AllReduce/AllToAll, static ranks); NIXL is a point-to-point
   inference-state mover for dynamic topologies (workers appearing/dying, KV tiers)
   [F: v0.8.0 doc motivation; `GPU-Communication/15-nccl-vs-nixl-vs-uccl.md`].
6. **"Fast GPUs eliminate the need for advanced scheduling."** No — faster GPUs
   finish prefill *sooner*, raising KV-production rate and the fabric bar (§15
   table); scheduling quality (hit rate h) multiplies into every transfer.
7. **"400 GbE networking guarantees good distributed inference."** No — §15 shows
   70B-class disaggregation wants ~500 Gb/s *to hide* transfer at 32K; and congestion/
   loss (RoCE tuning) can erase line rate. Fabric is necessary, not sufficient
   (`AI-Factory-Networking/17-why-roce-is-harder.md`).

## 28. Final Decision Framework

| You look like… | Choose | Why |
|---|---|---|
| single node, one model, modest SLO | **vLLM or SGLang alone** | engines are the right tool; platforms add ops weight for nothing [F: Dynamo README's own disclaimer] |
| one K8s cluster, prefix-heavy chat/RAG, multi-tenant | **llm-d + vLLM** | KV-aware routing + flow control + WVA on stock K8s; GAIE composes with existing gateways |
| NVIDIA-heavy fleet, P/D + frontier MoE, SLO/TCO focus | **Dynamo + vLLM** (or +SGLang) | five-job completeness, NIXL/RDMA path, Grove/KAI multinode, DGDR deploy-by-intent |
| NVIDIA fleet, max single-instance perf, closed recipes OK | **Dynamo + TensorRT-LLM** | deepest backend integration + Enterprise support track (v1.4.2+) [F: release notes] |
| generic model serving, many model types, scale-to-zero | **KServe + engine** | KServe's strength is generic serving lifecycle, not LLM cache-awareness |
| zero-ops packaged endpoints | **NIM** | packaged engine + API; platform layer below the hood where applicable (`Serving-Engines/NVIDIA-NIM.md`) |

Tie-breakers [I]: cluster size ≥2 pools before any platform pays off; latency SLA
with both TTFT and ITL binding → disaggregation stack; repeated prefixes dominate →
the routing layer matters more than the engine; MoE at frontier scale → Dynamo/llm-d
recipes (both) with EP-aware fabrics; NVIDIA dependency tolerance → llm-d if zero,
Dynamo acceptable, TRT-LLM+NIM if maximal.

## Key Takeaways
1. Engines make instances fast; **llm-d and Dynamo make fleets fast** — the five
   jobs (route, place, move, scale, fail) are the platform layer's entire content.
2. The physics is one formula family: KV bytes = 2·L·h_kv·d_h·S·b; transfer =
   S·KV_tok·(1−h)/BW; production rate sets the fabric bar; h multiplies everything
   (§15–§17) [E].
3. P/D is an SLO instrument, not a throughput trick — adopt it when TTFT and ITL
   bind and the fabric clears break-even; otherwise chunked prefill on a monolith.
4. Dynamo = vendor-OSS framework with its own control plane + NIXL; llm-d = CNCF
   K8s-native components + vendor-neutral accelerators; same layer, same jobs,
   different substrate — `Dynamo-vs-llm-d.md` is the table.
5. Benchmark platforms with cluster metrics (hit rate, pool utilization, transfer
   P95, goodput-at-SLO); every headline number in this space is workload-specific.

## Related
`Overview.md` (five jobs + transfer physics) · `NVIDIA-Dynamo.md` · `llm-d.md` ·
`Dynamo-vs-llm-d.md` · `Implementation/README.md` (PART 2 mechanics) ·
`Inference/Prefill-Decode-Disaggregation.md` (break-even) ·
`GPU-Communication/07-nixl-deep-dive.md` · `GPU-Communication/08-nixl-kv-cache-transfer.md` ·
`Serving-Engines/Engine-Landscape.md` (layer model) · `Networking/README.md` ·
`AI-Factory-Networking/README.md` (fabric design) · `KV-Cache/Distributed-KV-Cache.md` ·
`Production-Operations/README.md` (ops layer)

## References
- ai-dynamo/dynamo: README (main, 2026-09-06); Releases page v1.4.2 + v1.5.0-dev
  notes (fetched 2026-09-06); v0.8.0 design docs; RDMA overview + K8s install +
  metrics catalog (dev docs, fetched 2026-09-06).
- llm-d/llm-d: README + releases v0.9.0 (fetched 2026-09-06); llm-d.ai docs
  (architecture v0.9; artifacts/metrics pages, fetched 2026-09-06).
- vLLM: docs.vllm.ai disagg_prefill + NixlConnector guides (fetched 2026-09-06).
- ai-dynamo/nixl README; NIXL telemetry (port 19090) per Dynamo EFA docs.
- DistServe arXiv:2401.09670 · Splitwise arXiv:2311.18677 · Mooncake arXiv:2407.00079 ·
  DeepSeek report arXiv:2501.12948 · PagedAttention arXiv:2309.06180 · SGLang
  arXiv:2312.07104 · Orca arXiv:2211.05102 · Sarathi-Serve arXiv:2403.02310.
- Dynamo issue #2552 (P/D slower than aggregated, community repro) — fetched 2026-09-06.
