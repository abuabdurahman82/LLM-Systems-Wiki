# Modern LLM Inference Engines and Serving Architectures
`LAST_UPDATED: 2026-08-24 · Status: core page (section landing)` · The Inference-Engines landing page:
the layer stack, the category distinctions, and the map of everything in this wiki that covers
running, packaging, and distributing LLM inference. Engine *deep dives* live in
`GPU-Systems/` (`vLLM.md`, `SGLang.md`, `TensorRT-LLM.md`); the new gap pages —
`Llama-CPP.md` (this section), `NVIDIA-NIM.md` (this section), `Engine-Mega-Comparison.md`
(this section), and `Distributed-Inference/NVIDIA-Dynamo.md` / `llm-d.md` / `Dynamo-vs-llm-d.md`
(sister section) — round out the picture.

## 30-Second Explanation
"LLM inference stack" is not one thing. A single request from a chat app to a GPU passes
through **up to five distinct software layers**, and the seven technologies this section
covers live at **four different layers**:

- **vLLM, SGLang, TensorRT-LLM, llama.cpp** are *inference engines / runtimes* — the software
  that schedules requests, owns the KV cache, and launches kernels.
- **NVIDIA NIM** is a *packaging and deployment layer* above an engine (in current NIM LLM
  2.x, the engine inside the container is vLLM) [F: docs.nvidia.com/nim, 2026-08-24].
- **NVIDIA Dynamo** and **llm-d** are *distributed serving platforms* — orchestration layers
  that coordinate many engine instances across a cluster (routing, P/D disaggregation,
  KV-cache-aware placement, autoscaling).
- **CUDA / Triton / CUTLASS / cuBLAS / FlashAttention / NCCL** are the *execution layer* every
  engine eventually compiles down to.

The single most common category error: comparing Dynamo (a cluster orchestrator) against
vLLM (an engine) as if they were alternatives. They are *complements at different layers* —
Dynamo's own tagline is "the orchestration layer **above** inference engines — it doesn't
replace SGLang, TensorRT-LLM, or vLLM" [F: ai-dynamo/dynamo README, main branch, 2026-08-24].
llm-d says the same thing in CNCF terms: it "provides state-of-the-art orchestration and
optimizations **above model servers** like vLLM and SGLang" [F: llm-d/llm-d README, v0.8,
2026-08-24].

## The Layer Stack (mental model)
```
Application
     │
     ▼
API / SDK
     │
     ▼
Inference Gateway                    (K8s Gateway API, load balancers, auth/rate-limit)
     │
     ▼
Distributed Serving Platform         (cluster-level: routing, P/D split, KV-aware placement)
     │      ├── NVIDIA Dynamo         (vendor OSS, Rust core, K8s operator + native frontends)
     │      └── llm-d                 (CNCF Sandbox, K8s-native, Gateway API first)
     │
     ▼
Inference Server / Microservice      (packaging: container, profiles, health, support)
     │      └── NVIDIA NIM            (NIM LLM 2.x = vLLM + nim-llm + nimlib)
     │
     ▼
Inference Engine / Runtime           (the actual scheduling + KV-cache + kernel layer)
     │      ├── vLLM                  (PagedAttention, continuous batching, pluggable kernels)
     │      ├── SGLang                (RadixAttention, program-aware runtime)
     │      ├── TensorRT-LLM          (compiled per-(model,arch,TP) engine, NVIDIA-peak)
     │      └── llama.cpp             (C/C++ portable runtime, GGUF, CPU→edge→datacenter)
     │
     ▼
Execution Layer
     │      ├── CUDA                  (NVIDIA GPU programming model)
     │      ├── Triton kernels        (DSL-compiled attention/GEMM)
     │      ├── CUTLASS               (NVIDIA GEMM template library)
     │      ├── cuBLAS                (NVIDIA BLAS)
     │      ├── FlashAttention        (IO-aware attention kernel family)
     │      └── NCCL                  (collectives: AllReduce/AllGather/AllToAll)
     │
     ▼
Hardware
            ├── CPU  ──── GPU  ──── GPU memory (HBM)
            └── NVLink / NVSwitch (intra-node) · InfiniBand / RoCE (inter-node)
```
[Source: composed from the official architecture docs of each project, 2026-08-24; the
stack itself is the standard 2025+ serving topology described in
`Inference/Production-Serving/01-production-serving-overview.md` and
`Inference/Prefill-Decode-Disaggregation.md`.]

## The Category Distinctions (the four things to never blur)

**1. An engine is not a platform.** vLLM is not the same architectural category as Dynamo.
vLLM answers "how do I run this model on these GPUs efficiently?" — its whole architecture
(PagedAttention, the iteration-level scheduler, the attention-backend plugin system) is
*inside one serving instance*. Dynamo answers "how do I run *many* engine instances across a
cluster so that prefill doesn't starve decode, the KV cache is shared-aware-routed, and the
pool sizes track the SLA?" Dynamo has no kernel of its own; its units of work are
*frontends, routers, workers, KV-block-managers* [F: ai-dynamo/dynamo README +
docs.nvidia.com/dynamo design docs, 2026-08-24]. The relationship is composition:
Dynamo ships prebuilt containers named `sglang-runtime`, `tensorrtllm-runtime`,
`vllm-runtime` [F: README quick-start].

**2. A microservice is not an engine.** NIM is not the same thing as TensorRT-LLM.
In the current NIM LLM line (2.x, and the 3.0 docs branch), the NIM container contains a
three-component stack: `nim-llm` (orchestration: startup sequence, config priority, LoRA
adapter injection), `nimlib` (model licensing, hardware-aware *profile selection*, model
download, health/readiness management APIs), and the inference engine — **vLLM** — which
serves the native OpenAI-compatible endpoints [F: docs.nvidia.com/nim/large-language-models
"Overview", 2026-08-24]. The 1.x generation bundled multiple backends (vLLM,
TensorRT-LLM, …) in one container; 2.0 deliberately moved to **one container, one backend**
(vLLM) for "inference performance parity with upstream engines" [F: same source]. NIM's
value-add is packaging: validated containers, curated weights/quantization profiles,
enterprise lifecycle (NIM Certified: CVE patching, OSRB, FedRAMP-ready branches,
AI-Enterprise support) — not new kernels. See `NVIDIA-NIM.md` for the full breakdown and
the NIM-vs-everything comparisons.

**3. llm-d is not "another inference engine".** It is a Kubernetes-native *distributed
serving stack*: an intelligent router, a tiered global prefix-cache index, P/D
disaggregation, wide-expert-parallelism recipes, SLO-aware autoscaling, and a batch
gateway — all expressed as K8s workloads (Gateway API, Helm charts, well-lit-path
guides) on top of vLLM/SGLang pods [F: llm-d/llm-d README v0.8 + llm-d.ai docs,
2026-08-24]. It is a CNCF Sandbox project founded by Red Hat, Google Cloud, IBM Research,
CoreWeave, and NVIDIA (joined CNCF March 2026) [F: README]. It shares Dynamo's *problem*
(cluster-wide P/D + KV-aware routing) but is built *differently*: K8s-native primitives and
vendor-neutral accelerator support (tested on NVIDIA, AMD MI300X, Intel XPU, Google TPU)
versus Dynamo's Rust core + NVIDIA-centric container/operator ecosystem. The head-to-head
is `Distributed-Inference/Dynamo-vs-llm-d.md`.

**4. llama.cpp targets different deployment environments.** Its README states the goal:
"LLM (and VLM) inference with minimal setup and state-of-the-art performance on a wide
range of hardware — locally and in the cloud" [F: ggml-org/llama.cpp README, 2026-08-24].
It is a plain C/C++ runtime with no dependencies, first-class Apple Silicon support,
AVX/AVX512/AMX on x86, RISC-V vector support, and a 17-entry backend matrix (BLAS, CUDA,
HIP, Metal, Vulkan, SYCL, ROCm-adjacent MUSA, OpenCL, WebGPU, …) [F: same]. It can serve
a 4090 workstation and a datacenter node, but its architecture — GGUF quantized weights,
`ggml` tensor graph, thread-pool CPU execution with optional GPU layer offload — is built
for **device breadth and constrained memory**, not for iteration-level continuous batching
at thousands of concurrent requests. That is a design difference, not a quality
difference. Deep dive: `Llama-CPP.md`.

## 30-Second Architectures (verified against official docs, 2026-08-24)
| Project | One-line description (verified) |
|---|---|
| **llama.cpp** | Portable C/C++ inference runtime (GGUF; CPU → Apple Silicon → GPU → edge) [F: repo] |
| **vLLM** | High-throughput, memory-efficient general-purpose LLM serving engine (PagedAttention) [F: repo] |
| **SGLang** | Fast serving runtime for LLM + multimodal programs; strong prefix reuse (RadixAttention) and structured-workload execution [F: repo] |
| **TensorRT-LLM** | Highly optimized, compiled inference runtime for NVIDIA GPUs [F: NVIDIA repo] |
| **NVIDIA NIM** | Packaged production inference microservice (validated container + engine + lifecycle) [F: docs.nvidia.com/nim] |
| **NVIDIA Dynamo** | Open-source, datacenter-scale *distributed inference stack* / orchestration layer above engines [F: ai-dynamo README] |
| **llm-d** | Kubernetes-native high-performance distributed inference serving stack (CNCF Sandbox) [F: llm-d README] |

## What each layer is responsible for (and what it is NOT)
| Layer | Owns | Does NOT own |
|---|---|---|
| Gateway / platform (Dynamo, llm-d) | request routing, P/D placement, cluster KV-cache state, pool autoscaling, fault handling | the model math, per-request kernel selection |
| Microservice (NIM) | container lifecycle, model download/caching, profile selection, health APIs, support SLAs | the scheduler's batching decisions |
| Engine (vLLM/SGLang/TRT-LLM/llama.cpp) | scheduler, KV cache, batching, kernels, parallelism within the instance | cluster placement across replicas |
| Execution layer (CUDA/Triton/NCCL/…) | compute + collective primitives | any request semantics |

The practical consequence: **a bad layer choice shows up as the wrong kind of waste.**
No cluster routing → prefill hogs GPUs and decode ITL spikes (fix: P/D split + KV-aware
routing, the Dynamo/llm-d layer). No engine-level KV paging → OOM or fragmentation at
modest concurrency (fix: PagedAttention-class engine). No packaging → every deploy is a
heroics project with no CVE story (fix: NIM-class container). Picking a layer to solve a
problem two layers down is the classic mis-stack.

## How this maps to the rest of the wiki
- **Why engines exist** (the `generate()` → engine gap): `GPU-Systems/Inference-Engines.md`
- **Engine deep dives**: `GPU-Systems/vLLM.md` · `GPU-Systems/SGLang.md` ·
  `GPU-Systems/TensorRT-LLM.md` · **this section: `Llama-CPP.md`**
- **Three-engine comparison + fair-benchmark protocol**: `GPU-Systems/Engine-Comparison.md`
- **Seven-way comparison (engines + NIM + Dynamo + llm-d)**: `Engine-Mega-Comparison.md`
- **Request lifecycle / roofline / batching**: `Inference/The-Life-of-a-Token.md` ·
  `Inference/Roofline.md` · `Inference/Continuous-Batching.md`
- **KV cache**: `KV-Cache/README.md` · **P/D disaggregation + KV-transfer physics**:
  `Inference/Prefill-Decode-Disaggregation.md`
- **Scheduling & routing at scale (16-page handbook)**: `Inference/Production-Serving/`
- **Distributed serving platforms**: `Distributed-Inference/Overview.md` ·
  `NVIDIA-Dynamo.md` · `llm-d.md` · `Dynamo-vs-llm-d.md`
- **Parallelism dimensions (TP/PP/DP/CP/EP)**: `Distributed-Inference/README.md`
- **Networking (NVLink/RDMA/GPUDirect)**: `Networking/README.md`
- **Benchmark methodology**: `GPU-Systems/Perf-Experiment-Template.md` · `Benchmarks/`

## Final mental model
```
                    APPLICATION
                         │
                         ▼
                      API
                         │
                         ▼
              INFERENCE PLATFORM           (Dynamo | llm-d)
                         │
                         ▼
                  MODEL SERVICE           (NIM)
                         │
                         ▼
                 INFERENCE ENGINE         (vLLM | SGLang | TensorRT-LLM | llama.cpp)
                         │
                         ▼
                CUDA / Kernels / NCCL
                         │
                         ▼
                GPU + Memory + Network
```
Real stacks skip or merge layers: a laptop runs engine-only (llama.cpp, no gateway, no
platform); a single-node API service is usually gateway + engine (NIM-style packaging is
optional); a large fleet is all five. The layers are *separation of concerns*, and each
one has its own failure modes and its own scaling axis — which is exactly why the wiki
treats them in separate sections.

## Key Takeaways
1. The seven projects sit at **four different layers**: engines (vLLM/SGLang/TRT-LLM/
   llama.cpp) ⊂ microservice packaging (NIM) ⊂ distributed platforms (Dynamo/llm-d),
   all running on the CUDA/Triton/NCCL execution layer.
2. **Composition, not competition**, is the relationship: NIM wraps vLLM; Dynamo and
   llm-d orchestrate vLLM/SGLang/TRT-LLM instances. Each layer adds one capability the
   layer below cannot: package → schedule one instance → coordinate many instances.
3. "Fastest engine" is the wrong question without a layer qualifier: cluster-level
   TTFT/ITL wins usually come from the *routing/placement* layer, not from swapping
   engines. Measure per layer (`GPU-Systems/Perf-Experiment-Template.md` for engines;
   `Distributed-Inference/Overview.md` for cluster metrics).
4. No universal winner exists at any layer — model, hardware, workload, and SLO all
   change the answer. Hypotheses to test, not facts to believe:
   `GPU-Systems/Engine-Comparison.md` (3-engine) and `Engine-Mega-Comparison.md`
   (7-way).

## References
- ai-dynamo/dynamo — README, main branch (v1.4.x line), fetched 2026-08-24
  (github.com/ai-dynamo/dynamo); design docs at docs.nvidia.com/dynamo.
- llm-d/llm-d — README v0.8 + llm-d.ai docs, fetched 2026-08-24
  (github.com/llm-d/llm-d; CNCF Sandbox, joined 2026-03).
- NVIDIA NIM for LLMs — docs.nvidia.com/nim/large-language-models/latest
  (Overview + NIM Offerings), fetched 2026-08-24.
- ggml-org/llama.cpp — README, master, fetched 2026-08-24.
- vLLM/sgl-project/sglang/NVIDIA-TensorRT-LLM — repos; architecture claims in
  `GPU-Systems/` deep dives (verified 2026-08).
- No arXiv citations on this page (per the citation bank: Dynamo/llm-d are
  repo/docs-cited projects).
