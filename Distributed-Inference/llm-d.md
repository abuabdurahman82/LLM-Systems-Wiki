# llm-d — Kubernetes-Native Distributed LLM Inference Architecture Deep Dive
`LAST_UPDATED: 2026-08-26 · Status: core page` · llm-d is a **Kubernetes-native,
high-performance distributed inference serving stack** — "state-of-the-art
orchestration and optimizations **above model servers** like vLLM and SGLang" [F:
llm-d/llm-d README, v0.8 badge, fetched 2026-08-24]. It is a **CNCF Sandbox project**
(joined March 2026), founded by **Red Hat, Google Cloud, IBM Research, CoreWeave, and
NVIDIA**, with support from AMD, Cisco, Hugging Face, Intel, Lambda, Mistral AI, UC
Berkeley, and the University of Chicago [F: README]. Repo: `github.com/llm-d/llm-d`;
docs: `llm-d.ai`. Apache-2.0. Version anchors (2026-08-24): README badge **v0.8**;
docs "latest" branch **v0.9** (component details below are from the v0.9
architecture docs; v0.8 notes: multimodal, batch & flow-control graduated to
production, broader accelerator support, initial RL [F: docs banner]).

**The category point** (restated from `Serving-Engines/Engine-Landscape.md`): llm-d is
*not* "another inference engine." It contains no model-execution code — its model
servers **are** vLLM/SGLang pods. llm-d's artifacts are routing, cache state,
placement, scaling, and flow-control expressed as **Kubernetes primitives**.

## 30-Second Explanation
llm-d answers the fleet question the engine-answer cannot: "which pod should serve
this request, on which phase (prefill/decode), with what cache locality, and how many
pods of what variant should exist to hit this SLO at minimum cost?" Its five stated
offering themes [F: README]:
1. **Intelligent Routing** — prefix-cache + load-aware balancing, plus
   predicted-latency-based scheduling (GA in v0.7).
2. **Advanced KV-Cache Management** — tiered offloading (CPU/disk) + "precise
   global indexing of the KV cache state."
3. **Serving Large Models** — P/D disaggregation + wide expert-parallelism over fast
   interconnects (DeepSeek-R1, GPT-OSS class).
4. **Operational Excellence** — flow control for multi-tenant serving; proactive,
   SLO-aware autoscaling from real-time inference signals.
5. **Batch Processing** — OpenAI-compatible Batch API + async dispatch (offline
   workloads).
"Deliverables" come as **well-lit paths**: benchmarked recipes + Helm charts per
workload/accelerator, so "eliminate the heavy lifting common in tuning and deploying
generative AI inference on modern accelerators" [F: README].

## Why It Was Created
The founding problem [I: from the stated mission + architecture]: K8s is the default
deployment fabric, but stock K8s serving primitives (Service + HPA) are
**LLM-blind**: round-robin/DNS load balancing ignores KV-cache state (re-prefilling
the same 32k system prompt on every request), generic metrics can't express TTFT/ITL
SLOs, and P/D phase-splitting has no K8s representation. llm-d builds that layer as
**K8s-native components** (Gateway API, CRDs, operators, Helm) instead of a
vendor framework — the design goal "achieve the fastest time to SOTA performance for
key OSS LLMs across **most hardware accelerators**" [F: README] is explicitly
vendor-neutral (NVIDIA, AMD MI300X, Intel XPU, Google TPU all appear in tested
recipes [F: README performance highlights]).

## Core Architecture (the three primary concepts)
From the v0.9 architecture docs [F: llm-d.ai/docs/architecture, fetched 2026-08-24]:
```
                    Client
                       │  (OpenAI-compatible API)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ llm-d Router                                                 │
│  ├── Proxy  — L7 proxy, GAIE-conformant; accepts requests,  │
│  │            consults the EPP via the `ext-proc` protocol  │
│  └── EPP    — Endpoint Picker: scores & selects model-server│
│               pods from real-time metrics, KV-cache affinity│
│               and configured policies                       │
└─────────────────────────────────────────────────────────────┘
                       │ routes to
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ InferencePool   ("LLM-optimized Service" — the discovery    │
│  target for the Router; groups pods serving the same base   │
│   model via label selector)                                  │
│   ├── Variant: logical sub-grouping by pod labels —         │
│   │    serving role (prefill vs decode), cost/perf profile  │
│   │    (e.g. cheap prefill vs fast decode)                  │
│   └── Model Server pods: vLLM / SGLang executing the model  │
│        on GPUs / TPUs / HPUs                                │
└─────────────────────────────────────────────────────────────┘
```
Key design facts [F: v0.9 docs, verbatim concepts]:
- **Proxy + EPP split**: the Proxy is a thin GAIE-conformant L7 proxy; all routing
  intelligence lives in the **EPP** ("scores and selects model server pods based on
  real-time metrics, KV-cache affinity, and configured policies"), reached over the
  standard `ext-proc` protocol — i.e. llm-d plugs into the *Kubernetes ecosystem's*
  routing standard (Gateway API Inference Extension) rather than defining its own.
- **InferencePool as "LLM-optimized Service"**: pods are discovered by label
  selector; the **Variant** mechanism expresses role/cost/perf differences
  *without a new resource type* — prefill vs decode is just labels + policy.
- **Model servers** are unmodified vLLM/SGLang (or other) instances — llm-d adds
  sidecars and policies around them, not inside them.

## Advanced Patterns (the capability modules)
All optional composites on top of the core [F: v0.9 docs]:
| Module | What it is | Mechanism |
|---|---|---|
| **Prefix-Cache-Aware Routing** | maximize KV hits | "heuristic and precise techniques" — precise = cache-index-driven; heuristic = estimated |
| **KV-Cache Indexing** | cluster-wide cache-state map | **event-driven tracking of cache state across all model servers** (vLLM KV-cache events → global index) |
| **KV Offloading** | extend cache capacity | tiered storage hierarchy (CPU, SSD) — the "hierarchical KV offloading" behind the 13.9× claim [F: README] |
| **Disaggregated Serving** | P/D split | Router "selects both a prefill and a decode endpoint and coordinates the KV-cache transfer between them" [F: v0.9 docs] |
| **Latency Predictor** | predicted-latency routing | "consultant" sidecars; the primary one "trains an **XGBoost model online** to predict request latency" for endpoint scoring + SLO enforcement [F: v0.9 docs; GA in v0.7 per README] |
| **Batch Gateway + Async Processor** | offline workloads | OpenAI-compatible Batch API for job management; Async Processor dispatches queued requests with **flow-control gating**; compose or deploy independently [F: v0.9 docs] |
| **Autoscaling** | SLO-aware scale | two complements: **HPA/KEDA** on EPP-exported metrics (queue depth etc.) + **Workload Variant Autoscaler (WVA)** — "globally optimized scaling that minimizes cost by placing replicas across different variants or across inference pools while meeting latency targets" [F: v0.9 docs] |

The XGBoost latency predictor is the clearest architectural tell of llm-d's
philosophy: it *learns the model's latency behavior online* rather than encoding it
in static rules — routing decisions become regression outputs [F: v0.9 docs;
README: "40% reduction in TTFT and ITL with predicted-latency scheduling vs
heuristics on NVIDIA GPUs" (Google blog) — partner result, cite as such].

## Request Lifecycle (one request)
1. **Arrival** — request hits the Router's Proxy (GAIE L7 proxy; in production
   deployments this sits behind or *is* the cluster gateway — policy/auth/
   rate-limit belong at that edge [I: standard K8s edge topology]).
2. **ext-proc consult** — the Proxy forwards the request metadata to the EPP.
3. **EPP scoring** — the EPP scores candidate pods (within the InferencePool,
   respecting Variants): current load/queue metrics + **KV-cache affinity** (from
   the global cache index: which pod's prefix cache overlaps this prompt most) +
   policy (SLO class, variant targeting, flow-control admission).
4. **Disaggregation (when enabled)** — the EPP selects **two** endpoints (prefill
   pod + decode pod); the router "coordinates the KV-cache transfer between them"
   [F: v0.9 docs] — the transfer runs between the model servers' KV connectors
   (vLLM-native disagg connectors / UCCL-based transport; v0.5 added "UCCL-based
   transport resilience" [F: README news]).
5. **Execution** — the model server pod runs the request through its engine
   (vLLM/SGLang) — all in-engine scheduling (continuous batching, paged KV, etc.)
   is unchanged engine behavior (`Serving-Engines/Engine-Landscape.md`).
6. **Feedback** — pod metrics + KV-cache events stream back to the EPP/index;
   queue-depth and SLO-pressure signals feed HPA/KEDA and the WVA.
7. **Flow control** — under overload, the Async Processor / router apply
   flow-control gating (multi-tenant isolation graduated to production in v0.8)
   [F: README + v0.9 docs].

## KV-Cache State at Cluster Scale
The three-part KV ecosystem [F: v0.9 docs] maps 1:1 onto the tier model in
`Distributed-Inference/Overview.md`:
- **Indexing (global)** — event-driven; vLLM emits KV-cache block events, the
  indexer aggregates them into a cluster map. This is the "precise global indexing"
  of the README and the same structural idea as Dynamo's "global radix tree
  registry" (`NVIDIA-Dynamo.md`) — the difference: llm-d's index is assembled from
  **engine-emitted events** on K8s, Dynamo's is a router-owned registry in its own
  control plane [I: structural comparison from both sources].
- **Routing (consumer)** — the EPP's KV-cache-affinity score reads the index.
- **Offloading (capacity)** — tiered CPU/SSD storage extends the *effective working
  set* for multi-turn traffic; documented result: "13.9× throughput improvement with
  hierarchical KV offloading at 250 concurrent users vs GPU-only — 4× NVIDIA H100"
  [F: README v0.5 blog, vendor-adjacent result].

## P/D Disaggregation & Wide-EP (the large-model story)
- **P/D**: prefill and decode are *Variants* (label-defined roles); the Router
  orchestrates the two-endpoint flow and the KV transfer (above) [F: v0.9 docs].
  Documented result: "up to 70% higher tokens/sec with prefill/decode
  disaggregation vs standard vLLM — GPT-OSS on NVIDIA B200 (p6-b200), AWS" [F:
  README, partner blog]. The break-even physics (when the transfer cancels the
  win) is `Inference/Prefill-Decode-Disaggregation.md` + `Overview.md` §P/D.
- **Wide Expert Parallelism**: for giant MoE (DeepSeek-R1, GPT-OSS class), llm-d's
  "well-lit path" is **wide-EP across the accelerator fabric + P/D** — experts
  spread across many nodes, KV-aware placement on top. Documented result: "50k
  tokens/sec cluster throughput with Wide Expert-Parallelism — 16×16 NVIDIA B200,
  ~3.1k tok/s per GPU" [F: README v0.5 blog]. **Read carefully** [I: arithmetic,
  2026-08-24]: 50k/256 GPUs ≈ 195 tok/s per GPU, so the ~3.1k figure is *per
  DECODE* GPU only — the release note's own phrasing ("~3.1k tok/s per B200 decode
  GPU … 50k output tok/s on a 16×16 B200 prefill/decode topology" [F: README v0.5
  news]) makes the split explicit; 16 decode GPUs × ~3.1k ≈ 50k cluster, prefill
  GPUs excluded from the per-GPU denominator. The AllToAll/fabric dependence is
  `Distributed-Inference/README.md` §5 + `Overview.md` §MoE.
- **Accelerator neutrality in practice**: the P/D and WEP paths are tested on NVIDIA
  B200/H100/H200, AMD MI300X, and (v0.4+) **Intel XPU and Google TPU** for TTFT
  [F: README v0.4 news] — the broadest accelerator matrix of any serving platform
  [A: comparison judgment, 2026-08-24].

## Kubernetes-Nativeness (what it means concretely)
- **Gateway API** is the routing standard (Proxy is GAIE-conformant) — llm-d composes
  with existing ingress/gateway stacks instead of replacing them [F: v0.9 docs].
- **Helm + well-lit paths**: every tested configuration ships as a chart + recipe +
  benchmark; "kustomize-first" since v0.7 [F: README news].
- **Autoscaling on K8s primitives**: HPA/KEDA read EPP-exported *inference* metrics
  (queue depth, SLO pressure) — not just CPU [F: v0.9 docs]; the WVA adds
  cross-pool cost optimization (scale-to-zero appeared in v0.5 [F: README news]).
- **No vendor control plane required** — the stack is OSS K8s resources; contrast
  with Dynamo's Dynamo Platform install + NVL72 gang-scheduler operator
  (`NVIDIA-Dynamo.md`) [I: comparison].
- **Accelerator scheduling**: recipes assume the cluster's accelerator
  scheduler (GPU operator / device plugins / K8s topology features); llm-d layers
  LLM-awareness on top rather than replacing device scheduling [I: from the
  well-lit-path structure].

## Observability & Operations
- EPP-exported metrics drive autoscaling — queue depth, SLO attainment, cache
  stats are first-class signals [F: v0.9 docs autoscaling section].
- **Prism** (prism.llm-d.ai) — "detailed, reproducible benchmarks" public portal
  [F: README] — the closest thing to wiki-lab-class results for llm-d (still
  project-run; treat as vendor-adjacent until independently reproduced).
- Multi-tenant flow control graduated to production in v0.8 [F: README banner].
- Active-active HA (v0.5) for the control plane [F: README news].

## Performance Evidence (classified, 2026-08-24)
| Result | Source class | Context (from README) |
|---|---|---|
| 3× output throughput, 2× faster TTFT vs round-robin (prefix-aware routing) | Partner (Tesla/Red Hat) | Llama 3.1 70B, 4× AMD MI300X |
| 40% lower TTFT & ITL (predicted-latency scheduling vs heuristics) | Partner (Google) | NVIDIA GPUs |
| up to 70% higher tok/s (P/D vs standard vLLM) | Partner (AWS) | GPT-OSS, B200 (p6-b200) |
| 10–30% throughput (disagg, identical infra) | Partner (Oracle) | GPT-OSS-120B + Llama 3.3 70B, MI300X |
| 50k tok/s cluster, ~3.1k/GPU (wide-EP) | Project (v0.5 blog) | 16×16 B200 |
| 13.9× throughput (hierarchical KV offload @250 concurrent) | Project (v0.5 blog) | 4× H100 |
All context-specific; none is a universal claim (performance-claim rule,
`Serving-Engines/Engine-Landscape.md`). Independent replication: the `Overview.md`
§cluster-metric set.

## Strengths
1. **True K8s-native**: Gateway API/GAIE, CRDs-as-labels (Variant), HPA/KEDA,
   Helm — the stack *is* K8s, so ops tooling, multi-tenancy, and existing gateway
   investment all compose [F: v0.9 docs].
2. **Vendor-neutral accelerator matrix** (NVIDIA/AMD/Intel/TPU tested) — unique
   among serving platforms [F: README].
3. **Learned routing** (online XGBoost latency predictor) — a genuinely different
   routing signal class vs pure cache/load heuristics [F: v0.9 docs].
4. **Multi-vendor governance** (CNCF Sandbox; Red Hat + Google + NVIDIA + IBM +
   CoreWeave) — no single-vendor lock-in in the roadmap [F: README].
5. **Full workload spectrum in one stack**: interactive + P/D + wide-EP + batch +
   flow control [F: v0.9 docs].

## Limitations
1. **Young (v0.8/0.9)** — several features still experimental (batch gateway
   experimental until v0.8 graduation; check per feature) [F: README news]; the
   platform is moving fast (0.4→0.5→0.7→0.8 in months).
2. **Engine-dependent floor** — all in-engine performance is vLLM/SGLang's; llm-d
   adds placement dividends, not kernel wins [I: structural].
3. **K8s is mandatory** — the stack's identity *is* K8s; non-K8s fleets (bare Slurm
   HPC, single bare-metal nodes) are out of scope, whereas Dynamo runs file/etcd
   discovery without K8s [F: both READMEs] [I: comparison].
4. **Project-run benchmarks** — Prism results are not independent; the same
   evidence gap applies to all platform claims [I].
5. **WVA/flow-control tuning surface** — SLO-aware autoscaling + multi-tenant
   gating add real configuration complexity vs plain HPA [I].

## Best Use / When Not To Use
- **Use**: K8s-first organizations; multi-accelerator fleets (or planned
  mixed-vendor); P/D or wide-EP at scale on K8s; teams that want CNCF-governed,
  vendor-neutral tooling; batch + interactive workloads under one roof.
- **Don't**: non-K8s infrastructure (→ Dynamo with file/etcd discovery, or
  engine-native serving); single-node serving (engine suffices); environments
  needing NVIDIA NVL72-class gang-scheduling and ModelExpress cold-start
  streaming (Dynamo's Grove/ModelExpress territory [F: Dynamo README]);
  production-critical deployments that need the maturity of the 1.x Dynamo line
  [I: maturity judgment, verify per release].

## Alternatives
- **NVIDIA Dynamo** — same layer, vendor-OSS + NVIDIA fabric gravity:
  `Dynamo-vs-llm-d.md`.
- **Engine-native P/D** (vLLM/SGLang disagg) — pair-scale, no platform layer.
- **Gateway API EPPs generally** — llm-d's router is one EPP; lighter deployments
  can use GAIE directly with a simpler scorer [I].

## Key Takeaways
1. llm-d = **Kubernetes as the inference control plane**: Router (Proxy+ext-proc+EPP),
   InferencePool(+Variant), Model Server pods — LLM-awareness layered onto stock
   K8s primitives [F: v0.9 docs].
2. Its five themes (intelligent routing, cluster KV management, large-model
   P/D + wide-EP, ops/autoscaling, batch) all ship as composable modules with a
   shared cache-state substrate (event-driven index → routing; tiered offload →
   capacity) [F: v0.9 docs + README].
3. The differentiators vs Dynamo are *mechanism and philosophy*, not capability
   class: learned latency predictor, GAIE-native routing, vendor-neutral
   accelerators, CNCF governance — vs Dynamo's Rust control plane, NVL72 gravity,
   and NVIDIA fabric integrations. `Dynamo-vs-llm-d.md` makes the table.
4. Platform results (3×/40%/70%/13.9×/50k-tok/s) are all context-specific partner
   or project benchmarks — reproduce with the cluster-metric set before
   planning around any of them.

## Related
`Overview.md` (cluster-layer framing + KV-transfer physics + P/D break-even) ·
`NVIDIA-Dynamo.md` · `Dynamo-vs-llm-d.md` · **`Implementation/`** (PART 2 — how the
five jobs are built: `Implementation/05-global-kv-state.md` for the event-driven global
index, `Implementation/03-kv-aware-routing.md` for Proxy+EPP + latency predictor,
`Implementation/02-offload-and-tiering.md` for tiered KV offload, `Implementation/04-pd-orchestration.md`
for Variants + WVA) ·
`Inference/Prefill-Decode-Disaggregation.md` ·
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` ·
`Inference/Production-Serving/08-cache-aware-routing.md` ·
`Inference/Production-Serving/09-pd-disaggregated-routing.md` ·
`Inference/Production-Serving/11-autoscaling-and-capacity-planning.md` ·
`GPU-Systems/vLLM.md` · `GPU-Systems/SGLang.md` · `Distributed-Inference/README.md`
(parallelism dimensions) · `Networking/README.md` · `Serving-Engines/Engine-Landscape.md`

## References
- llm-d/llm-d README — v0.8 (fetched 2026-08-24): mission, five themes, performance
  highlights with full context, release notes (0.4–0.7), CNCF founding [F].
- llm-d.ai/docs/architecture — v0.9 (fetched 2026-08-24): core components (Router
  Proxy/EPP, InferencePool/Variant, Model Server) + advanced patterns (KV
  management, disagg, latency predictor, batch, autoscaling HPA/KEDA/WVA) [F].
- No arXiv citations (repo/docs-cited project per the citation bank).
