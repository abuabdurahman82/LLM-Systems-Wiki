# Inference-Engine Mega Comparison — vLLM vs SGLang vs TensorRT-LLM vs llama.cpp vs NIM vs Dynamo vs llm-d
`LAST_UPDATED: 2026-08-24 · Status: core page` · The seven-way matrix. Extends
`GPU-Systems/Engine-Comparison.md` (the three-engine matrix + fair-benchmark protocol,
which this page inherits wholesale) to the *full stack* including the packaging layer
(NIM) and the two distributed platforms (Dynamo, llm-d).

**Reading rules (from the 3-engine page, re-stated):**
1. Architecture cells are [F]/[A] — stable planning facts.
2. **No benchmark numbers in this page, by design.** Every performance claim is a
   hypothesis to test with `GPU-Systems/Perf-Experiment-Template.md` (single-instance)
   or the cluster metrics in `Distributed-Inference/Overview.md` (platform layer).
3. Layers differ: rows about *cluster* behavior don't apply to single-instance engines
   and vice versa — "❌/n/a" usually means "that's not this layer's job".

## The 7-Way Matrix

| Dimension | **vLLM** | **SGLang** | **TensorRT-LLM** | **llama.cpp** | **NIM** | **Dynamo** | **llm-d** |
|---|---|---|---|---|---|---|---|
| **Category** | engine | engine | engine | portable runtime | packaging/microservice layer | distributed platform | K8s-native distributed platform |
| **Main purpose** | high-throughput general serving [F] | structured/agentic serving, prefix reuse [F] | peak NVIDIA per-model perf [F] | LLM/VLM inference on any hardware, minimal setup [F: README 2026-08-24] | validated container + engine + enterprise lifecycle [F: NIM docs 2026-08-24] | cluster coordination above engines: P/D, routing, KV tiers, scaling [F: README] | K8s-native orchestration above vLLM/SGLang: routing, KV mgmt, P/D, WEP [F: README v0.8] |
| **Core architecture** | Python async scheduler + paged KV + pluggable kernels [F] | Python program-aware runtime + RadixAttention [F] | C++ runtime, build-time-compiled per (model,quant,arch,TP) engine [F] | C/C++ ggml graph, 17 backends, layer placement [F: README] | nim-llm + nimlib + vLLM in one container [F: NIM docs] | Rust core + Python; frontend/router/planner/KVBM + engine workers [F: README] | Gateway API + router + tiered prefix cache + P/D + autoscaler, on K8s [F: README] |
| **Scheduler** | Python async, iteration-level continuous batching [F] | Python, "zero-overhead" design goal, program-aware [F] | C++ inflight batching, ADP balance [F] | server-mode request queue + `--parallel` slots; not iteration-level research-grade [A] | inherits vLLM's [F: 2.x=vLLM] | per-engine schedulers + cluster-level planner (SLA-driven pool sizing) [F] | per-engine schedulers + predicted-latency scheduling at the router (GA in v0.7) [F: README] |
| **KV architecture** | PagedAttention blocks + hash APC [F] | Radix tree prefix cache [F] | paged KV + config-level reuse [F] | contiguous per-context cache (no paging, no cross-request sharing) [A: verify] | inherits vLLM's [F] | KVBM: multi-tier GPU→CPU→SSD→remote [F: README] | tiered prefix cache (GPU→CPU/disk) + global cache index [F: README] |
| **Prefix caching** | hash APC, shared paged blocks [F] | RadixAttention (structural) [F] | config-level [F] | none at runtime level [A] | inherits vLLM's [F] | KV-aware routing over cache state; storage-tier offload (1.0) [F: README] | prefix-cache-aware routing; hierarchical KV offloading (13.9× claim) [F: README] |
| **Continuous batching** | ✅ native [F] | ✅ native [F] | ✅ inflight batching [F] | 🟡 server queue, not iteration-level [A] | ✅ (via vLLM) [F] | n/a — delegates to engine [F: structural] | n/a — delegates to engine [F: structural] |
| **P/D disaggregation** | 🟡 native disagg (NIXL/LMCache connectors; "no throughput gain, better SLOs" per docs) [F] | ✅ P/D + E/P/D [F] | ✅ (incl. Mooncake backend) [F] | ❌ [I] | n/a — engine feature [F: structural] | ✅ core capability; all 3 backends ✅ [F: feature matrix] | ✅ core capability (vLLM + SGLang; wide-EP+P/D for giant MoE) [F: README] |
| **Quantization** | widest: FP8/NVFP4/INT8/INT4/GPTQ/AWQ/GGUF/ModelOpt [F] | FP8/FP4-class/INT4/AWQ/GPTQ [F] | FP8/INT8/INT4/NVFP4 + ModelOpt [F] | K-quants Q2–Q8 + i-quants (weight-only, memory-centric) [F: README] | curated quant profiles per model (via vLLM) [F: NIM docs] | inherits backends' [F: structural] | inherits vLLM's [F: structural] |
| **CPU inference** | 🟡 limited/experimental paths [A] | ❌ (GPU-first) [I] | ❌ NVIDIA GPU only [F] | ✅ the home turf (AVX/AVX512/AMX/NEON/RVV) [F: README] | ❌ (GPU product) [F: structural] | ❌ [I] | ❌ (accelerator-focused) [I] |
| **Apple Silicon** | ❌ [I] | ❌ [I] | ❌ [F: NVIDIA-only] | ✅ first-class (Metal+NEON+Accelerate) [F: README] | ❌ [F: structural] | ❌ [I] | 🟡 untested path; K8s+accelerators [A] |
| **NVIDIA optimization depth** | high (pluggable incl. TRTLLM-GEN, FlashMLA) [F] | high (FlashInfer-centric, 96×H100 EP) [F] | highest (compiled per-arch kernels) [F] | moderate (custom CUDA kernels; not datacenter-tuned) [F: README] | high (validated profiles per SKU) [F: NIM docs] | high (NVLink/NIXL, GB200/NVL72 gravity) [F: README] | high (NVIDIA is a founder; B200/MI300X/Tesla tests) [F: README] |
| **Kubernetes** | ✅ (common) [A] | ✅ [A] | ✅ (NVIDIA ecosystem) [A] | 🟡 possible, not the focus [I] | ✅ designed for it (health APIs, probes) [F: NIM docs] | ✅ Dynamo Platform K8s operator + CRDs + native & Gateway-API routing [F: README] | ✅ K8s-native is the architecture (Gateway API, Helm, well-lit paths) [F: README] |
| **Multi-node** | ✅ TP/PP/DP/EP over NCCL [F] | ✅ TP intra-node + large-scale EP (96×H100) [F] | ✅ TP/PP/EP/ADP/DWDP + NVL72 [F] | ❌ intra-host only [I] | per-replica [F: structural] | ✅ the whole point; GB200/GB300 NVL72 results [F: README] | ✅ wide-EP + P/D across nodes (16×16 B200 results) [F: README] |
| **MoE** | FusedMoE + EP [F] | MoE + large-scale EP [F] | wide-EP series, grouped GEMM [F] | runs GGUF MoE, no EP fabric [A] | per model [F: structural] | MoE workloads (DeepSeek-class recipes) [F: README] | wide expert parallelism as a named theme [F: README] |
| **Enterprise packaging** | community [A] | community [A] | NVIDIA first-party [A] | community, MIT [F] | **the packaging itself** (NIM Certified, FedRAMP/OSRB) [F] | open-source + NVIDIA containers (Apache-2.0) [F] | CNCF Sandbox, Apache-2.0, vendor-neutral [F: README] |
| **Ease of use** | high (pip + OpenAI API) [A] | high [A] | medium (build pipeline) [A] | highest (one file + one binary) [F: README] | high (pull + run) [F: NIM docs] | medium (platform install + recipes) [F: README] | medium (K8s stack + well-lit paths) [F: README] |
| **Peak optimization** | high, pluggable [F] | high, program-aware [F] | highest (compiled) [F] | low ceiling (bandwidth-bound quant) [I] | = its engine's [F: structural] | = engine's + cluster placement [F: structural] | = engine's + cluster placement [F: structural] |
| **Operational complexity** | medium | medium | high (builds, per-config) | low | low–medium | high (platform + P/D pools) | high (K8s stack + SLO tuning) |

Legend: ✅ mature/native · 🟡 supported with caveats · ❌ unsupported / not that
layer's job · n/a = structural (the capability lives in the layer below/above).
Version anchors (verified 2026-08-24): Dynamo main branch v1.4.x containers; llm-d
v0.8 (v0.7 = predicted-latency GA); NIM LLM docs "latest" 2.0.11 + 3.0.0 branch;
llama.cpp master; vLLM/SGLang/TRT-LLM per `GPU-Systems/` deep dives (2026-08).

## The Optimization Matrix (PART 18)

| Optimization | vLLM | SGLang | TRT-LLM | llama.cpp | NIM |
|---|---|---|---|---|---|
| Continuous batching | ✅ [F] | ✅ [F] | ✅ (inflight) [F] | 🟡 [A] | ✅ via vLLM [F] |
| Chunked prefill | ✅ [F] | ✅ [F] | ✅ (chunked context) [F] | ❌ [I] | ✅ via vLLM [F] |
| Paged KV cache | ✅ [F] | ✅ [F] | ✅ [F] | ❌ [A: verify] | ✅ via vLLM [F] |
| Prefix caching | ✅ (APC) [F] | ✅ [F] | 🟡 config-level [F] | ❌ [A] | ✅ via vLLM [F] |
| Radix cache | 🟡 (hash-based, not radix) [I] | ✅ native [F] | 🟡 [I] | ❌ [A] | 🟡 via vLLM [F] |
| CUDA graphs | ✅ [F] | ✅ [F] | ✅ [F] | 🟡 CUDA graph usage limited [A] | ✅ via vLLM [F] |
| Fused kernels | ✅ [F] | ✅ [F] | ✅ (compile-time) [F] | ✅ (K-quant fused dequant+GEMM) [F] | ✅ via vLLM [F] |
| FlashAttention | ✅ (FA + FlashInfer + TRTLLM-GEN + FlashMLA + Triton) [F] | ✅ (FlashInfer-centric) [F] | ✅ custom FMHA [F] | 🟡 attention kernels, FA-class [A] | ✅ via vLLM [F] |
| Speculative decoding | ✅ (n-gram/EAGLE/DFlash) [F] | ✅ (EAGLE/STAGE/Spec V2) [F] | ✅ (EAGLE + guided coop) [F] | 🟡 draft-model spec [A: verify tools] | ✅ via vLLM [F] |
| FP8 | ✅ [F] | ✅ [F] | ✅ [F] | ❌ (weight-quant only) [I] | ✅ via vLLM profiles [F] |
| INT4 | ✅ (GPTQ/AWQ) [F] | ✅ [F] | ✅ [F] | ✅ (K-quants) [F] | ✅ via profiles [F] |
| NVFP4 | ✅ [F] | 🟡 [A: check] | ✅ [F] | ❌ [I] | 🟡 via profile [A: check] |
| CPU inference | 🟡 [A] | ❌ [I] | ❌ [F] | ✅ [F] | ❌ [F: structural] |
| Apple Metal | ❌ [I] | ❌ [I] | ❌ [F] | ✅ [F] | ❌ [F: structural] |
| LoRA | ✅ [F] | 🟡 [A: check] | 🟡 [A: check] | 🟡 (via adapters/tools) [A: check] | ✅ (adapter injection is a named feature) [F: NIM docs] |
| Multimodal | ✅ [F] | ✅ [F] | ✅ [F] | ✅ VLM subsystem [F: README] | 🟡 model-dependent [A] |
| MoE | ✅ [F] | ✅ [F] | ✅ [F] | 🟡 GGUF MoE, no EP [A] | model-dependent [A] |

(Dynamo and llm-d are deliberately absent from this matrix: they do not execute
model operations — they place the instances that do. Their "optimizations" are
routing, P/D, KV-tiering, and autoscaling: see the two distributed sections.)

## Decision Matrix (PART 33 — explained, not table-only)

| Scenario | Recommended candidates | Why (and what to verify) |
|---|---|---|
| Local Mac inference | **llama.cpp** | Metal + unified memory + K-quants are first-class [F]; no other mainstream runtime targets this class. Verify: target latency at your context (`-ngl`, `n_ctx`). |
| CPU-only inference | **llama.cpp** | AVX/AVX512/AMX kernels + quant memory profile [F]. Verify: bandwidth-bound ceiling arithmetic (`Inference/Roofline.md`). |
| Single NVIDIA workstation | vLLM / SGLang / TRT-LLM | All three viable; default vLLM for coverage [A]; TRT-LLM for peak stable-model perf if you accept the build pipeline [A]. Verify with the pinned protocol. |
| High-throughput API | vLLM / SGLang / TRT-LLM | Engine choice + concurrency tuning dominate; SGLang if measured prefix overlap is high [I: consistent with its design goals]. Verify: goodput at your SLO. |
| Repeated agent prefixes | **SGLang** (vLLM close second) | RadixAttention structural sharing targets exactly this [F]. Verify: your *measured* prefix hit rate first — the win scales with it. |
| Highly optimized NVIDIA deployment | **TRT-LLM** | Compiled per-(model,arch,TP) kernels = the peak-pole [F]. Cost: rebuild per config change [A]. Verify at your SLO on a stable model. |
| Packaged enterprise NVIDIA API | **NIM** | NIM Certified: lifecycle, CVE/OSRB/FedRAMP, validated profiles [F]. Know: steady-state perf = underlying vLLM [I]. Verify: profile coverage for your model. |
| Large distributed NVIDIA environment | **Dynamo** | P/D + KV-aware routing + KVBM + SLA planner + NVL72 gravity [F: README key results]. Verify: fabric class (its wins assume ≥fast RDMA/NVLink) and SLO shape. |
| Kubernetes-native distributed inference | **llm-d** | K8s-native stack, vendor-neutral accelerators (NVIDIA/AMD/Intel/TPU tested) [F: README], CNCF governance. Verify: your accelerator + the "well-lit path" for your workload. |
| P/D disaggregated serving | **Dynamo / llm-d** (or engine-native P/D at small scale) | Both platforms; engine-native (vLLM/SGLang/TRT-LLM disagg) for 1-node or pair deployments — see `Inference/Prefill-Decode-Disaggregation.md` for the break-even model (fabric bandwidth decides). |

**Do not use this table alone.** Every row hides a workload shape (context length,
prefix overlap, SLO, model rotation rate) that can flip the recommendation; the
3-engine page's H1–H5 hypotheses + the pinned benchmark protocol are the
verification half of each row.

## Why No Universal Winner (the layer argument)
1. **Different layers, different winners.** A "which is fastest" question across
   Dynamo and llama.cpp is category error — one is a cluster router, one is a laptop
   runtime. The stack wins by *each layer being right for its job*.
2. **The roofline doesn't care who you are.** Token streaming is bandwidth-bound
   regardless of engine; what engines change is *bytes per token* (quant), *launch
   overhead* (CUDA graphs), *useful work per byte* (batching), and *cache locality*
   (prefix reuse). Each project optimizes a different subset.
3. **Cluster metrics move the winner.** TTFT/ITL at scale are decided by routing and
   P/D placement before the engine's kernels ever run — the `Inference/Production-Serving/`
   handbook's core thesis [F: structural, from that section].
4. **Economics are a fourth axis.** tokens/$ and SLO-goodput, not raw tok/s, are the
   production objective (`Inference/Inference-Metrics.md`).

## Key Takeaways
1. The seven projects form a **stack, not a race**: llama.cpp (portable runtime) →
   vLLM/SGLang/TRT-LLM (engines) → NIM (packaging) → Dynamo/llm-d (platforms).
2. NIM's row is short *by design* — it inherits the engine's capabilities and adds
   lifecycle; benchmarking it means benchmarking its engine
   (`NVIDIA-NIM.md` §decomposition).
3. Dynamo vs llm-d is the only true same-layer rivalry — and even there the
   difference is philosophy (vendor OSS Rust core + NVIDIA gravity vs CNCF
   K8s-native vendor-neutral), not capability class: `Distributed-Inference/Dynamo-vs-llm-d.md`.
4. Performance rows are hypotheses: replace them with your [E] numbers via
   `GPU-Systems/Perf-Experiment-Template.md` (engine layer) and the cluster-metric
   list in `Distributed-Inference/Overview.md` (platform layer).

## Related
`Engine-Landscape.md` (layer stack) · `NVIDIA-NIM.md` · `Llama-CPP.md` ·
`GPU-Systems/Engine-Comparison.md` (3-engine matrix + fair-protocol, inherited here) ·
`GPU-Systems/Perf-Experiment-Template.md` · `Distributed-Inference/Overview.md` ·
`Distributed-Inference/Dynamo-vs-llm-d.md` · `Inference/Prefill-Decode-Disaggregation.md` ·
`Inference/Inference-Metrics.md` · `Inference/Production-Serving/14-production-routers-comparison.md`
