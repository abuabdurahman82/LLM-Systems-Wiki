# NVIDIA Dynamo vs llm-d — Distributed Serving Platforms, Head-to-Head
`LAST_UPDATED: 2026-08-24 · Status: core page` · The one true same-layer rivalry in
this section: **both are distributed inference platforms** that sit *above* engines
(vLLM/SGLang/TRT-LLM) and implement the same five cluster jobs — route, place, move,
scale, fail (`Distributed-Inference/Overview.md`). Every cell below is verified
against primary sources on **2026-08-24**: Dynamo main-branch README (v1.4.x
containers) + Dynamo v0.8.0 design docs; llm-d README (v0.8) + llm-d.ai v0.9
architecture docs. Where a claim could not be verified, it is marked `[A]` or
`UNVERIFIED`.

## 30-Second Explanation
They solve the same problem (cluster-wide P/D + KV-aware routing + SLA-driven
scaling of engine instances) with different *substrates*:
- **Dynamo** is a vendor-open-source framework: a **Rust control/data plane**
  (frontend, router, planner) with its own KV-state registry, its own transfer
  library (NIXL), and NVIDIA datacenter gravity (NVLink/NVL72, Grove gang
  scheduling, ModelExpress). K8s is a *deployment option*, not a requirement
  (file/etcd/NATS discovery also work) [F: both READMEs].
- **llm-d** is a **CNCF-governed, Kubernetes-native stack**: its routing is the
  Kubernetes Gateway API (ext-proc + EPP), its pools are K8s label-selectors
  (InferencePool + Variant), its cache state is an event-driven index fed by
  engine KV events, and its accelerator matrix is vendor-neutral (NVIDIA/AMD/
  Intel/TPU tested) [F: both READMEs + llm-d v0.9 docs].

Same problem, same five jobs, different substrate and governance. The table below
is the verified breakdown; the diagrams and philosophy sections follow.

## The Full Comparison Table (all entries verified 2026-08-24)

| Category | **NVIDIA Dynamo** | **llm-d** |
|---|---|---|
| **Primary objective** | "Open-source, datacenter-scale inference stack" — orchestration layer above engines for max throughput / min latency at scale [F: README] | "High-performance distributed inference serving stack optimized for production deployments on Kubernetes" — fastest time-to-SOTA across accelerators [F: README] |
| **Architectural layer** | Distributed serving platform (cluster control plane + transfer) [F] | Distributed serving platform, K8s-native [F] |
| **Governance / origin** | NVIDIA, OSS-first, Apache-2.0; repo `ai-dynamo/dynamo`; 160+ community contributors [F: README] | CNCF Sandbox (joined 2026-03); founded by Red Hat, Google Cloud, IBM Research, CoreWeave, NVIDIA; + AMD/Cisco/HF/Intel/Lambda/Mistral/Berkeley/Chicago [F: README] |
| **Kubernetes dependency** | Optional — K8s operator/CRDs/EndpointSlices for production; file/etcd/NATS-JetStream discovery for local/Slurm [F: README discovery table] | **Core** — Gateway API (GAIE), InferencePool/Variant as label-selected K8s groups, HPA/KEDA, Helm; K8s is the architecture [F: v0.9 docs] |
| **Runtime integration** | TRT-LLM ✅, vLLM ✅, SGLang ✅ ("and others") — engine-agnostic [F: v0.8.0 doc + README] | vLLM + SGLang as model servers ("model servers like vLLM and SGLang") [F: README + v0.9 docs]; TRT-LLM: UNVERIFIED as a first-class model server [A: check current docs] |
| **vLLM integration** | ✅ full (disagg/KV-routing/planner/KVBM all ✅ per feature matrix; `vllm-runtime:1.4.1` containers) [F: README] | ✅ first-class (KV index reads vLLM KV-cache events; WEP + P/D recipes) [F: v0.9 docs + README] |
| **TensorRT-LLM integration** | ✅ full (all five capabilities ✅ per feature matrix) [F: README matrix] | UNVERIFIED — not in the README's model-server list [A: verify] |
| **SGLang integration** | ✅ (disagg/routing/planner ✅; KVBM 🚧 in progress) [F: README matrix] | ✅ (named model server) [F: README] |
| **P/D disaggregation** | ✅ core capability, all 3 backends ✅ [F: README matrix]; + E/P/D multimodal split (1.0) [F] | ✅ core pattern — Router selects prefill + decode endpoints and coordinates KV transfer [F: v0.9 docs] |
| **KV-aware routing** | ✅ "Smart Router": global **radix tree registry**; "highest cache hit rate while maintaining load balance" [F: v0.8.0 doc] | ✅ prefix-cache-aware routing: "heuristic and precise techniques"; EPP scores on "real-time metrics, KV-cache affinity" [F: v0.9 docs] |
| **Prefix-aware routing** | ✅ (same router; radix registry = prefix index) [F] | ✅ (same capability, indexed by vLLM events) [F] |
| **KV transfer** | **NIXL** — purpose-built inference transfer library (UCX-class transports, dynamic, batching) [F: v0.8.0 doc]; also ModelExpress weight streaming [F: README] | Engine-side KV connectors + "UCCL-based transport resilience" (v0.5) [F: README news]; vLLM-native CPU memory tiering path (v0.4) [F: README news] |
| **KV cache tiers** | **KVBM**: GPU → CPU → SSD → remote storage (S3/Azure); global KV events (1.0) [F: README + v0.8.0 doc] | **KV Offloading**: "tiered storage hierarchy (CPU, SSD)" + global index [F: v0.9 docs] |
| **Worker discovery** | K8s CRDs + EndpointSlices; etcd / NATS-JetStream / file backends [F: README] | K8s label selectors (InferencePool) + EndpointSlices via Gateway API [F: v0.9 docs] |
| **Scheduling (cluster)** | **Planner**: SLA-driven; event-plane demand signals; AIConfigurator simulates 10K+ configs; zero-downtime pool resizing [F: README + v0.8.0 doc] | **HPA/KEDA** on EPP-exported inference metrics + **WVA** (Workload Variant Autoscaler: cross-variant/pool cost-optimized placement under latency targets) [F: v0.9 docs] |
| **Routing** | Rust Router in Dynamo Frontend (or GAIE EPP in Gateway topology); prediction-based mode w/o KV events (`--no-router-kv-events`) [F: README] | GAIE Proxy + **EPP** via `ext-proc`; optional **Latency Predictor** sidecar: **online-trained XGBoost** ITL/TTFT model (GA in v0.7) [F: v0.9 docs + README] |
| **Autoscaling** | Planner (SLA/TCO-driven) [F] | HPA/KEDA (queue-depth metrics) + WVA (cost-optimal, cross-pool) + scale-to-zero (v0.5) [F: v0.9 docs + README] |
| **Multi-node support** | ✅ core — NVL72/GB200/GB300-class results; Grove topology-aware gang scheduling [F: README] | ✅ core — 16×16 B200 wide-EP + P/D results; cross-node fabric via UCCL/RDMA [F: README] |
| **MoE support** | ✅ (DeepSeek-class recipes; NVL72 gravity) [F: README key results] | ✅ **wide expert parallelism** as a named theme + well-lit path [F: README] |
| **Accelerator matrix** | NVIDIA-centric (NVLink/NIXL/Grove/ModelExpress assume NVIDIA fabric) [I: structural from the feature set] | Vendor-neutral: NVIDIA (B200/H100/H200), **AMD MI300X**, **Intel XPU**, **Google TPU** tested [F: README + v0.4 news] |
| **Observability** | AIPerf benchmarking; per-component metrics; event plane [F: README]; Prometheus (check current docs) [A] | EPP-exported metrics drive autoscaling; **Prism** reproducible-benchmark portal; multi-tenant flow control (v0.8 production) [F: v0.9 docs + README] |
| **Batch/offline workloads** | Not a named capability (check current docs) [A: UNVERIFIED] | ✅ Batch Gateway (OpenAI Batch API) + Async Processor with flow-control gating (v0.8 production) [F: v0.9 docs + README] |
| **Multimodal** | ✅ E/P/D disaggregation + embedding cache (1.0) [F: README] | ✅ graduated to production in v0.8 [F: docs banner] |
| **Fault handling** | ✅ canary health checks + **in-flight request migration** [F: README] | Active-active HA for control plane (v0.5); flow control (v0.8); request-level migration: UNVERIFIED [A: check] |
| **Production maturity** | v1.x line ("1.0 is here — production-ready", 2025-03); named production users (Baseten, Alibaba, Mistral, Moonshot) [F: README] | v0.8 (docs v0.9) — pre-1.0; partner deployments (Tesla, Google, AWS, Oracle, OCI) [F: README]; young but fast-moving (0.4→0.8 in ~5 months) |
| **Operational complexity** | High: platform install + P/D pools + KVBM + planner + (optional) gateway; but single-vendor docs path [I: judgment from component set] | High: K8s stack + router + index + offloader + autoscalers; but everything is stock-K8s-native (existing platform team's tooling applies) [I: judgment] |
| **Best deployment environment** | Multi-node **NVIDIA** datacenters, esp. NVLink/NVL72 fabric; Slurm/HPC also supported [F: README + I: inference] | **Kubernetes-first** organizations, multi-vendor or mixed accelerator fleets; K8s gateway/ingress standardization [F: README + I: inference] |

## Side-by-Side Architecture (verified shapes)

### NVIDIA Dynamo
```
Application
    │
    ▼
Dynamo Frontend (Rust, OpenAI-compatible, /openapi.json)
    │            └─ (alt topology: K8s Gateway + GAIE EPP → Frontend sidecars)
    ▼
Dynamo Router (Rust)
    │  · global radix-tree registry of KV state (cache-hit-rate scoring)
    │  · load balancing · prediction-based mode (no event infra)
    ▼
Planner (SLA targets → pool sizing; AIConfigurator; event plane)
    │
 ┌──┴──────────────────┐
 ▼                     ▼
Prefill workers      Decode workers
(vLLM/SGLang/        (vLLM/SGLang/
TensorRT-LLM)        TensorRT-LLM)
    │  NIXL KV transfer  │
    └────────┬───────────┘
             ▼
      KVBM tiers: GPU HBM → CPU/DDR → SSD → S3/Azure
             │
             ▼
   K8s (CRDs + EndpointSlices) or file/etcd/NATS discovery
```
[Components: v0.8.0 design doc + README routing topologies, 2026-08-24]

### llm-d
```
Application
     │
     ▼
K8s Gateway (Gateway API / GAIE — cluster edge: policy/auth/rate-limit)
     │
     ▼
llm-d Router
   ├─ Proxy: L7 proxy (GAIE-conformant), ext-proc protocol
   └─ EPP: Endpoint Picker — scores pods on real-time metrics
          + KV-cache affinity + policy
          └─ (optional) Latency Predictor sidecar (online XGBoost ITL/TTFT)
     │
     ▼
InferencePool ("LLM-optimized Service", label selector)
   ├─ Variant: prefill role  ──┐
   └─ Variant: decode role  ──┤ (role/cost/perf via pod labels)
     │                       │
     ▼                       ▼
Prefill pods             Decode pods
(vLLM/SGLang model      (vLLM/SGLang model
 servers)                servers)
     │  KV transfer (engine connectors; UCCL transport)
     └──────────┬──────────┘
                ▼
  KV subsystem: event-driven global index (vLLM KV events)
               + tiered offloading (CPU, SSD)
                │
                ▼
Autoscaling: HPA/KEDA (EPP metrics) + WVA (cross-variant/pool)
```
[Components: llm-d v0.9 architecture docs + README, 2026-08-24]

### What the diagrams show
- **Both** split prefill/decode pools, both keep a cluster-wide KV-state map, both
  route on cache overlap + load, both autoscale from inference signals, both
  coordinate the KV transfer between pools. The *capability surface* is the same.
- **Dynamo** owns its control plane (Rust frontend+router+planner, its own KV
  registry, its own NIXL transfer library) — it *can* run without K8s.
- **llm-d** borrows the control plane from the K8s ecosystem (Gateway API,
  ext-proc/EPP, label selectors, HPA/KEDA) and adds LLM-awareness as sidecars and
  operators — it *requires* K8s.

## The Philosophical Difference (verified, not hypothesis)
The master prompt flagged this as a hypothesis to investigate. Verified against
primary sources, the difference is real and concrete:

### Dynamo's emphasis (evidence-verified)
- **High-performance proprietary control plane**: "Built in Rust for performance,
  Python for extensibility … critical performance-sensitive modules with Rust for
  speed, memory safety, and robust concurrency" [F: v0.8.0 doc]. The data plane is
  not Python; the router's radix registry and NIXL are in-project artifacts.
- **Heterogeneous-backend orchestration on NVIDIA fabric**: first-class support
  for all three major engines *with a per-backend feature matrix*, plus
  NVIDIA-fabric-specific accelerators (ModelExpress weight streaming over
  NVLink/NIXL, Grove gang scheduling for NVL72 topology) [F: README].
- **Aggressive SLO/TCO optimization as a product**: the Planner + AIConfigurator
  pair is a published cost-optimization story ("80% fewer SLA breaches at 5%
  lower TCO") [F: README key result, partner claim].
- **Single-vendor gravity, OSS packaging**: Apache-2.0 and community-governed in
  practice (160+ contributors, office hours, design proposals) [F: README], but
  roadmap and fabric assumptions center on NVIDIA datacenters.

### llm-d's emphasis (evidence-verified)
- **Kubernetes-native by construction**: every capability is expressed in K8s
  vocabulary — Gateway API routing (ext-proc/EPP), InferencePool as "LLM-optimized
  Service" (label selectors), Variant as pod labels, HPA/KEDA autoscaling, Helm
  + well-lit paths [F: v0.9 docs]. The design explicitly rides the *ecosystem's*
  routing standard (GAIE) rather than inventing one.
- **Vendor-neutral accelerator strategy**: "achieve SOTA … across most hardware
  accelerators" with tested paths on NVIDIA, AMD MI300X, Intel XPU, and Google
  TPU [F: README] — including partner results *on AMD* (Tesla/Red Hat 3×/2× on
  MI300X; Oracle 10–30% on MI300X) [F: README].
- **Governance neutrality**: CNCF Sandbox with five founding vendors (Red Hat,
  Google Cloud, IBM Research, CoreWeave, **and** NVIDIA — NVIDIA is one of five,
  not the owner) [F: README]. The roadmap is multi-vendor.
- **Learned + open components**: the XGBoost latency predictor is open,
  online-trained, and swappable via "consultant" sidecars [F: v0.9 docs];
  reproducibility is productized (Prism portal) [F: README].

**One-line synthesis** [I: synthesis of the verified evidence above]:
*Dynamo optimizes the **fabric and the control plane** (Rust data plane, NIXL,
NVL72) under a single-vendor OSS umbrella; llm-d optimizes the **Kubernetes
control plane and the accelerator matrix** (GAIE, label-based pools, multi-vendor
tested paths) under CNCF governance. Neither philosophy is wrong — they predict
different win conditions: Dynamo on NVIDIA-heavy datacenter fleets where fabric
integration is the bottleneck; llm-d on K8s-standardized, multi-vendor
organizations where platform tooling is the bottleneck.*

## Where They Overlap (be precise)
- **Same five jobs** — route/place/move/scale/fail; both ship P/D, KV-aware
  routing, tiered KV, SLO-aware autoscaling [F: both].
- **Both use GAIE** — Dynamo ships a "K8s Inference Gateway plugin: KV-aware
  routing inside the standard Kubernetes gateway" (1.0) [F: README]; llm-d's
  router *is* a GAIE Proxy/EPP. On a K8s cluster both can sit behind the same
  Gateway API edge — the difference is what the EPP consults (Dynamo's registry
  vs llm-d's event index + learned predictor).
- **Both compose with vLLM/SGLang**; both treat in-engine scheduling as
  unchanged [F: both].
- **Neither is an engine** — both are composition layers; the engine's
  continuous-batching/paged-KV/kernel work happens in the pods/workers
  (`Serving-Engines/Engine-Landscape.md` layer model).

## Performance Posture (no universal winner, per the rule)
All evidence is partner/project-class, context-specific (full tables:
`NVIDIA-Dynamo.md` §Performance Evidence, `llm-d.md` §Performance Evidence):
- **Dynamo**: 7× tok/GPU (GB200 NVL72, InferenceX), 2× TTFT (Baseten, 480B
  coder), 80% fewer SLA breaches (Alibaba planner) [F: vendor/partner].
- **llm-d**: 3×/2× on MI300X (Tesla/Red Hat), 70% tok/s (AWS, B200 P/D), 13.9×
  (hierarchical KV @250 conc, 4×H100), 50k cluster tok/s wide-EP (16×16 B200)
  [F: partner/project].
The two result sets do **not** compare like-for-like: different models, GPUs,
workloads, and baselines. The reproducible comparison is: your model + your
cluster + your SLO, measured with the cluster-metric set in
`Distributed-Inference/Overview.md` — run both stacks (or one stack with/without
P/D) and compare goodput-at-SLO. That is the only honest "Dynamo vs llm-d
benchmark" that exists.

## Decision Guide (hypotheses to verify on your fleet)
- **H-dyn: NVIDIA-heavy, fabric-rich, single-vendor ops team** → Dynamo first.
  NVL72-class topologies, ModelExpress cold-start, Grove gang scheduling, and
  the TRT-LLM full-feature path are Dynamo-only territory [F: both READMEs].
  Verify: your fabric class (≥100 GbE cross-node or NVLink) and SLO shape
  (both TTFT+ITL binding).
- **H-llmd: K8s-standardized, multi-vendor or mixed-accelerator** → llm-d first.
  GAIE-native routing composes with existing gateways; AMD/Intel/TPU recipes are
  llm-d-only territory [F: both]; CNCF governance fits platform teams.
  Verify: K8s maturity (Helm, gateway, HPA/KEDA already in the org) and
  accelerator mix.
- **H-both: P/D on K8s with NVIDIA GPUs** → both viable; the decider is *which
  control plane your team wants to own* (Rust framework vs stock-K8s components)
  and *which accelerator matrix you need now vs later*. Run the P/D break-even
  model (`Inference/Prefill-Decode-Disaggregation.md`) first — if the fabric
  doesn't clear break-even, neither stack's P/D pays off.
- **H-neither: <2 nodes or <2 pools** → engine-native P/D (vLLM/SGLang) or
  colocation; a platform's complexity is not justified below the multi-pool
  scale [I: consistent with Dynamo's own "single model on a single GPU"
  disclaimer, F: README].

## Key Takeaways
1. **Same layer, same five jobs, different substrate**: Dynamo = Rust control
   plane + NIXL + NVIDIA fabric gravity (K8s optional); llm-d = K8s-native
   (GAIE/InferencePool/Variant/HPA-KEDA-WVA) + vendor-neutral accelerators
   (CNCF) [F: all cells verified 2026-08-24].
2. **The KV mechanism is the same idea, different plumbing**: Dynamo's
   router-owned global radix registry vs llm-d's event-driven index fed by
   vLLM cache events; both feed cache-aware EPP/routing decisions.
3. **Transfer layering differs**: Dynamo ships NIXL as its own library
   (dynamic, inference-shaped); llm-d relies on engine-side KV connectors +
   UCCL transport resilience. On NVIDIA fabrics both reach RDMA/NVLink; the
   operational difference is who owns the transfer stack.
4. **Maturity is a real axis**: Dynamo is on the 1.x "production-ready" line
   (named datacenter users); llm-d is v0.8/0.9 (pre-1.0, partner deployments,
   fast-moving). Choose the risk profile that matches the workload's
   criticality [F: both READMEs, 2026-08-24].
5. **No performance verdict exists** — the evidence sets are not
   comparable; the only valid benchmark is your workload on your cluster,
   measured with cluster metrics, both stacks, P/D on/off.

## Related
`NVIDIA-Dynamo.md` · `llm-d.md` · `Overview.md` (five cluster jobs + KV-transfer
physics + cluster metrics) · `Inference/Prefill-Decode-Disaggregation.md`
(break-even model + DistServe/Splitwise/Mooncake lineage) ·
`Inference/Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` (routing signals
both platforms consume) · `Inference/Production-Serving/14-production-routers-comparison.md`
· `GPU-Systems/Engine-Comparison.md` (the engine layer beneath both) ·
`Serving-Engines/Engine-Landscape.md` · `Networking/README.md`

## References
- ai-dynamo/dynamo README — main, v1.4.x (fetched 2026-08-24) [F].
- Dynamo v0.8.0 design docs — docs.nvidia.com/dynamo/v-0-8-0/design-docs/overall-architecture
  (fetched 2026-08-24) [F].
- llm-d/llm-d README — v0.8 (fetched 2026-08-24) [F].
- llm-d.ai/docs/architecture — v0.9 (fetched 2026-08-24) [F].
- No arXiv citations introduced (both projects are repo/docs-cited per the
  citation bank; P/D research IDs are cited by Dynamo's doc and listed in
  `Inference/Prefill-Decode-Disaggregation.md`).
