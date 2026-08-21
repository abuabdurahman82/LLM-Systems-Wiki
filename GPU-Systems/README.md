# GPU Systems, CUDA & Kernel Engineering — LLM Inference Handbook
`LAST_UPDATED: 2026-08-21 · Status: first-class section` · This section is a **living
engineering handbook**, not a one-time article. It is integrated with the rest of the
wiki (Transformer · Attention · KV-Cache · Inference · Quantization · Serving-Engines ·
Distributed-Inference · Networking · Hardware) so a reader can follow the complete path:

**Transformer → GPU hardware → CUDA kernel → memory movement → optimized kernel →
inference engine → multi-GPU execution → distributed serving system.**

## 30-Second Explanation
An LLM generates a token by moving **weights + activations + KV** through ~32 stacked
"compute blocks," where each block is dominated by **two GEMMs** (attention projections
+ MLP) and one **attention** computation. Everything that makes a token fast or slow
reduces to four physical resources: **Tensor Core FLOPs** (prefill), **HBM bandwidth**
(decode), **fabric bandwidth/latency** (parallelism), and **kernel-launch/scheduler
overhead** (small-batch decode). This handbook is a zero-to-hero map of how to reason
about, build on, and optimize those four resources.

## Who this is for
- **AI engineer (limited kernel background):** start at `Zero-to-Hero-Path.md`, read
  `Architecture.md` + `Bandwidth-vs-Compute.md`, then `GEMM.md` + `Kernel-Life.md`.
- **Inference / GPU infra engineer:** jump to `Diagnostics.md`, `Cross-Layer-Optimization.md`,
  `Case-Studies.md`, `Engine-Comparison.md`, `Perf-Experiment-Template.md`.
- **Kernel / compiler researcher:** `GEMM.md`, `Tensor-Cores.md`, `Custom-GEMM.md`,
  `Fused-Kernels.md`, `Triton.md`, `FlashAttention.md`, `Research-Lineage.md`.

---

# TABLE OF CONTENTS (this section)

> Read order = learning path. "★" = load-bearing for 80% of practical understanding.

## I. GPU computing foundations
1. `Architecture.md` — CPU vs GPU, SIMT, SMs, CUDA cores, Tensor Cores, warps, HBM,
   NVLink/NVSwitch; the Grid→Block→Warp→Thread execution hierarchy; why thousands of
   threads make slow memory appear fast. ★
2. `Bandwidth-vs-Compute.md` — arithmetic intensity, the Roofline model, compute-bound vs
   memory-bound vs latency-bound vs comm-bound; **why prefill is compute-bound and decode
   is memory-bound**; why bandwidth can matter more than TFLOPS for token generation. ★
3. `Memory-Hierarchy.md` — registers → shared/L1 → L2 → HBM → NVLink/PCIe → CPU → NVMe;
   coalescing, bank conflicts, cache lines, vectorization, alignment; good vs bad patterns. ★
4. `Memory-Optimizations.md` — tiling, register blocking, double buffering, async copies,
   pipelining, warp-specialized producer/consumer kernels, TMA; how optimization changes
   across GPU generations.

## II. CUDA from zero to hero
5. `CUDA-From-Zero.md` — CUDA runtime/driver, kernels, host/device code, launch syntax,
   thread indexing, H2D/D2H copies, sync; 8 worked examples (vec-add → matrix add → naive
   GEMM → tiled GEMM → reduction → softmax → LayerNorm → RMSNorm), each with thread
   organization, access pattern, bottleneck, and how to profile it. ★
6. `Kernel-Life.md` — the life of a CUDA kernel: Python → PyTorch op → runtime → launch →
   blocks → SM scheduling → warps → memory → Tensor/CUDA cores → sync → back to framework;
   launch overhead; why many tiny kernels hurt decode; CUDA streams, events, CUDA Graphs,
   kernel batching. ★
7. `Perf-Experiment-Template.md` — the discipline: baseline → hypothesis → one variable →
   benchmark → GPU metrics → serving metrics → compare → explain WHY → decide. Prevents
   benchmark theater.

## III. GEMM, Tensor Cores, kernels
8. `GEMM.md` — C = A×B from naive to Tensor Cores; M/N/K; mapping every Transformer op to
   a GEMM; why large prefill GEMMs and 1-token decode GEMVs behave differently. ★
9. `Tensor-Cores.md` — MMA, WMMA, Tensor Core tiles, FP32/TF32/FP16/BF16/FP8/INT8/INT4/FP4;
   the precision ↔ memory ↔ bandwidth ↔ throughput ↔ quality trade; why quantization helps
   by TWO independent routes.
10. `Triton.md` — CUDA C++ vs Triton vs PyTorn; programs, blocks, masks, autotune;
    vec-add/softmax/matmul/fused-activation; Triton's place in torch.compile + Inductor.
11. `Custom-GEMM.md` — why cuBLAS is optimized yet custom kernels matter; shape-specific,
    small, grouped/batched, MoE, quantized, skinny/decode GEMMs; cuBLAS/cuBLASLt/CUTLASS/
    Triton/custom — their roles.
12. `Fused-Kernels.md` — the fuse-N-kernels-into-one pattern; bias+act, RMSNorm, residual,
    QKV, RoPE, attention, MLP, dequant; benefits and the register-pressure/occupancy cost.

## IV. FlashAttention
13. `FlashAttention.md` — standard attention IO cost; the key insight that FlashAttention is
    an **IO-aware algorithm, not a faster approximation**; tiling, SRAM reuse, online
    softmax, no S×S materialization; FA1/2/3; Standard vs FA across FLOPs/traffic/capacity/
    latency/throughput; implications for long context, prefill, training, inference. ★

## V. The kernel stack
14. `Kernel-Stack.md` — the full stack from PyTorch/JAX → compiler/runtime →
    Triton/CUDA/CUTLASS → cuBLAS/cuDNN/custom → CUDA runtime → SMs/Tensor Cores → HBM, and
    where inference engines plug in.

## VI. Inference engines
15. `Inference-Engines.md` — why engines exist; limits of `Transformers.generate()`;
    vLLM / SGLang / TensorRT-LLM; plus llama.cpp, TGI, Dynamo, llm-d.
16. `vLLM.md` — PagedAttention, KV block manager, continuous batching, scheduling, prefix
    caching, chunked prefill, spec decode, TP/PP/DP/EP, one-request trace, observability.
17. `SGLang.md` — RadixAttention, prefix reuse, scheduling, structured generation, spec
    decode, cache-aware scheduling, multi-node; vs vLLM philosophy.
18. `TensorRT-LLM.md` — TRT graph/kernel optimization, build/convert process, optimized
    kernels, quant, KV, inflight batching, paged KV, spec decode, multi-GPU, the
    max-optimization vs flexibility trade.
19. `Engine-Comparison.md` — detailed vLLM vs SGLang vs TRT-LLM across install, model
    support, API, throughput/TTFT/ITL, batching, prefix cache, spec decode, quant,
    TP/PP/EP, multi-node, observability, K8s, extensibility, custom kernels, maturity.
    **No universal winner.**
20. `Load-Balancing.md` — why least-connections is insufficient; **balance remaining work,
    not requests**; routing on queue depth, prompt/output length, prefix hit, KV pressure,
    model/adapter, GPU type, P/D stage, batch state.

## VII. Multi-GPU
21. `Multi-GPU.md` — why multiple GPUs; capacity / throughput / latency / concurrency
    problems; DP/TP/PP/EP/SP/CP each with WHAT/WHY/HOW/WHEN/COMM-COST/FAILURE-MODES.
22. `Tensor-Parallelism.md` — column/row-parallel linear layers, where AllReduce/
    AllGather/ReduceScatter occur, why TP needs fast fabric; PCIe vs NVLink vs NVSwitch vs
    InfiniBand vs RoCE.
23. `Pipeline-Parallelism.md` — stage splitting, bubbles, microbatches, imbalance; why
    inference PP ≠ training PP.
24. `MoE-Expert-Parallelism.md` — router→dispatch→expert→combine; All-to-All, imbalance,
    hot experts, capacity factors; why MoE inference becomes a networking problem.
25. `NCCL.md` — ranks, communicators, collectives (AllReduce/AllGather/ReduceScatter/
    Broadcast/AllToAll/Send-Recv), ring/tree/hierarchical, NCCL ↔ NVLink/IB/RoCE.

## VIII. Multi-node & topology
26. `Multi-Node.md` — the node diagram, performance hierarchy, communication locality,
    RDMA / GPUDirect RDMA / GPUDirect Storage, topology/NUMA/NIC/GPU affinity.
27. `Scale-Up-vs-Scale-Out.md` — NVLink/NVSwitch (scale-up) vs IB/RoCE/Ethernet
    (scale-out); why an HGX/DGX node ≠ several PCIe GPUs.
28. `Topology.md` — reading `nvidia-smi topo -m`; GPU↔GPU, GPU↔NIC, NUMA, PCIe switches,
    NVLink paths; topology mistakes that kill NCCL throughput.
29. `Distributed-Architectures.md` — 11 reference architectures from single-GPU to
    TP+PP+DP+EP to P/D disaggregation, and when each makes sense.

## IX. Cross-cutting engineering
30. `Prefill-Decode-Disaggregation.md` — P/D cluster split, KV transfer, scheduling, cache
    placement, routing, failure modes; DistServe/Mooncake/research.
31. `Cross-Layer-Optimization.md` — the most important chapter: optimizing one layer
    shifts the bottleneck; find the **next limiting resource** at every level.
32. `Diagnostics.md` — the performance decision tree: CPU? GPU util? compute-bound?
    memory-bound? launch-bound? KV-limited? scheduler-limited? network? storage?
33. `Profiling.md` — what each tool answers: nvidia-smi, DCGM, Nsight Systems, Nsight
    Compute, PyTorch Profiler, nvtop, CUPTI, NCCL logs, engine metrics.
34. `GPU-Metrics.md` — SM/Tensor-Core util, bandwidth util, occupancy, warp stalls, L2 hit,
    DRAM throughput, launch rate, PCIe/NVLink/net, power, clocks; mapped to
    TTFT/ITL/TPOT/tok-s/req-s/P50-P95-P99/goodput.
35. `Case-Studies.md` — 10 architecture case studies (single-GPU dev → multi-tenant cloud).

## X. Learning & research
36. `Zero-to-Hero-Path.md` — 13 levels (L0 GPU fundamentals → L12 inference research), each
    with concepts / exercises / projects / papers / mastery criteria.
37. `Research-Lineage.md` — idea-influence maps (attention, KV, GEMM, quant, spec-decode,
    P/D, MoE), with per-paper problem/idea/result/limitation/influence/relevance.
38. `Research-Radar.md` — Production-ready / Emerging / Research / Experimental; vendor
    claims vs independently validated.
39. `Labs.md` — 20 hands-on labs (CUDA vec-add → multi-node benchmark), each with
    objective / theory / environment / commands / expected behavior / metrics /
    interpretation / common mistakes / extensions.
40. `Glossary.md` — cross-linked term index for the whole GPU-systems layer.

---

# DELIVERABLE 2 — Dependency map between chapters

```
              [existing wiki]
  Transformer · Attention · KV-Cache · Quantization · Inference/Roofline
                 │
                 ▼
   ┌──────────── Architecture.md ────────────┐
   │                │                          │
   │                ▼                          ▼
   │        Bandwidth-vs-Compute.md      Memory-Hierarchy.md
   │                │                          │
   ▼                ▼                          ▼
CUDA-From-Zero.md   GEMM.md ◄──────────────────┘
   │                │
   ▼                ▼
Kernel-Life.md   Tensor-Cores.md ◄── Quantization (existing)
   │                │
   │                ▼
   │           Custom-GEMM.md ─► Fused-Kernels.md ─► FlashAttention.md
   │                │
   ▼                ▼
Perf-Experiment   Kernel-Stack.md
-Template.md          │
                      ▼
        Inference-Engines.md
          │          │          │
          ▼          ▼          ▼
        vLLM.md  SGLang.md  TensorRT-LLM.md ─► Engine-Comparison.md
          │          │          │
          └──────────┴──────────┘
                 Load-Balancing.md
                      │
                      ▼
        Multi-GPU.md ─► Tensor/Pipeline/MoE-EP ─► NCCL.md
                      │
                      ▼
        Multi-Node.md ◄─ Scale-Up-vs-Scale-Out.md ◄─ Topology.md
                      │
                      ▼
        Distributed-Architectures.md
                      │
                      ▼
        Prefill-Decode-Disaggregation.md
                      │
   Cross-Layer-Optimization.md ◄──────────┐
                      │                    │
   Diagnostics.md ◄───┼──► Profiling.md ◄──┼──► GPU-Metrics.md
                      │                    │
                      ▼                    │
                  Case-Studies.md ◄────────┘
                      │
   Zero-to-Hero-Path.md · Research-Lineage.md · Research-Radar.md · Labs.md · Glossary.md
```

Reading rules: a chapter's dependencies are the **incoming arrows**. E.g. `GEMM.md` needs
`Bandwidth-vs-Compute.md` + `Memory-Hierarchy.md` first; `Tensor-Parallelism.md` needs
`Multi-GPU.md` + `NCCL.md`.

---

# DELIVERABLE 4 — 80/20 cheat sheet (the 20% that explains 80% of LLM inference)

| # | Concept | One-line "why it matters" | See |
|---|---|---|---|
| 1 | **Matrix multiplication** | Every Transformer op is a GEMM or GEMV; its shape decides everything. | `GEMM.md` |
| 2 | **Arithmetic intensity** | FLOPs/byte tells you which roof you're under. | `Bandwidth-vs-Compute.md` |
| 3 | **Memory bandwidth** | Decode speed ≈ BW / bytes-per-token; the #1 decode lever. | `Memory-Hierarchy.md` |
| 4 | **GPU memory hierarchy** | Move data fewer levels → fewer stalls. | `Memory-Hierarchy.md` |
| 5 | **Kernel launch overhead** | Small-batch decode is launch-bound; CUDA Graphs kill it. | `Kernel-Life.md` |
| 6 | **Kernel fusion** | Fuse to cut HBM round-trips + launches. | `Fused-Kernels.md` |
| 7 | **FlashAttention** | IO-aware attention; removes the S×S HBM traffic. | `FlashAttention.md` |
| 8 | **KV cache** | `2·L·B·h_kv·d_h·S·b` caps concurrency × context. | `../KV-Cache/README.md` |
| 9 | **Continuous batching** | Amortize weights; the GEMV→GEMM knee batch B*. | `../Inference/Continuous-Batching.md` |
| 10 | **Tensor parallelism** | Split a layer's GEMM; 2 AllReduce/layer → needs NVLink. | `Tensor-Parallelism.md` |
| 11 | **NCCL collectives** | AllReduce/AllToAll are what the network pays. | `NCCL.md` |
| 12 | **GPU/network topology** | Wrong path silently halves NCCL throughput. | `Topology.md` |
| 13 | **Prefill vs decode** | Two different bottlenecks in one model. | `Bandwidth-vs-Compute.md` |
| 14 | **Quantization** | Cuts decode bytes (and, for W8A8/W4A4, lifts compute). | `../Quantization/README.md` |
| 15 | **Profiling** | You cannot fix what you cannot measure; know which tool answers which question. | `Profiling.md` |

---

# DELIVERABLE 3 — Zero-to-Hero learning roadmap

The full version (concepts / exercises / projects / papers / mastery per level) is in
`Zero-to-Hero-Path.md` (13 levels L0–L12). Skeleton:

```
L0  GPU fundamentals          → Architecture.md
L1  CUDA basics               → CUDA-From-Zero.md + Labs L1–L5
L2  Memory hierarchy          → Memory-Hierarchy.md
L3  Profiling                 → Profiling.md, Diagnostics.md, GPU-Metrics.md
L4  GEMM                      → GEMM.md, Custom-GEMM.md
L5  Triton                    → Triton.md
L6  Attention optimization    → FlashAttention.md
L7  LLM kernels               → Fused-Kernels.md, Tensor-Cores.md, Kernel-Stack.md
L8  Inference engines         → Inference-Engines.md, vLLM.md, SGLang.md, TensorRT-LLM.md
L9  Multi-GPU                 → Multi-GPU.md, Tensor/Pipeline/MoE-EP, NCCL.md
L10 Multi-node distributed    → Multi-Node.md, Scale-Up-vs-Scale-Out.md, Topology.md
L11 Production-scale serving  → Case-Studies.md, Load-Balancing.md, Cross-Layer-Optimization.md
L12 Inference research        → Research-Radar.md, Research-Lineage.md
```
Prerequisite graph: L1 needs L0 · L4 needs L0+L2 · L6 needs L4 · L8 needs L7 · L9 needs L8 ·
L11 needs L10 · L12 needs L11. Full detail + 80/20 shortcut: `Zero-to-Hero-Path.md`, and the
older 10-level model lives at `../Learning-Path/Zero-to-Hero.md`.

---

# DELIVERABLE 7 — GPU performance troubleshooting decision tree

(Full decision tree with "how to confirm each branch" is in `Diagnostics.md`; this is the
short form.)

```
Performance problem
  │
  ├─ CPU/scheduler-bound?  (GPU idle, host CPU ~100%, long gaps between kernels)
  │     → profile host: tokenization, sampling, Python GIL, scheduler, RPC. Fix: async
  │       scheduler, CUDA Graphs, off-CPU sampling.
  │
  ├─ GPU utilization low AND kernels tiny + many launches?  → kernel-launch-bound.
  │     → CUDA Graphs, fuse ops, raise batch.
  │
  ├─ Tensor Cores busy, SMs at compute roof?  → compute-bound (usually prefill).
  │     → raise batch/context, FP8/FP4 weights, FlashAttention, more GPUs (TP).
  │
  ├─ HBM at ~peak BW, SMs mostly idle?  → memory-bandwidth-bound (usually decode).
  │     → quantize weights+KV, GQA/MLA, continuous batching to B*, speculative decoding.
  │
  ├─ KV cache full / requests queued for memory?  → KV-limited.
  │     → KV quant, evict, shrink h_kv, PagedAttention sizing, more HBM, disaggregate.
  │
  ├─ Multi-GPU: collective times ≈ compute?  → network/comm-bound.
  │     → check topology (topo -m), NVLink vs PCIe, reduce cross-node TP, SHARP, EP/PP mix.
  │
  ├─ High TTFT, low ITL?  → prefill-dominated → prefix cache, chunked prefill, P/D split.
  │
  ├─ High ITL at B=1, fine at B>8?  → per-token overhead → CUDA Graphs, spec decode, fused
  │     sampling.
  │
  └─ P99 ≫ P50 but P50 fine?  → tail latency → scheduling (rebalance remaining work),
        prefill interference (chunked prefill / P/D), hot experts (MoE capacity).
```

---

# DELIVERABLE 8 — vLLM vs SGLang vs TensorRT-LLM comparison matrix

(See `Engine-Comparison.md` for the full matrix + fairness checklist. Abbreviated: **no
universal fastest engine** — the winner depends on model, hardware, request pattern,
context length, concurrency, quantization, and SLO.)

| Dimension | vLLM | SGLang | TensorRT-LLM |
|---|---|---|---|
| Philosophy | max compatibility + pluggable kernels | program-aware, zero-overhead runtime | compiled NVIDIA-specific peak |
| Install/bring-up | easy (pip) | easy (pip) | heavier (build/convert) |
| Model coverage | widest, day-0 | wide | strong on NVIDIA models |
| API compat | OpenAI | OpenAI + programmatic | OpenAI + custom |
| Continuous batching | yes | yes | inflight batching |
| Prefix caching | hash APC | RadixAttention (structural) | config-level reuse |
| Spec decode | n-gram/EAGLE/DFlash | EAGLE/STAGE/Spec V2 | n-gram/EAGLE |
| Quant | widest | FP4/FP8/INT4/AWQ/GPTQ | FP8/INT8/INT4/NVFP4 + ModelOpt |
| TP / PP / EP | TP/PP/EP | large-scale EP | wide EP + ADP + NVL72 |
| Multi-node | yes | yes | most documented |
| Observability | Prometheus V1 | Prometheus | Prometheus + JSON |
| Extensibility / custom kernels | highest (Triton backend) | high (FlashInfer) | lower (compiled) |
| Best fit | new-model day-0, quant breadth | agentic/structured, shared-prefix, high concurrency | peak NVIDIA perf on a stable model |

**Rule:** measure on YOUR model + hardware + workload + SLO before choosing. Reproduce
benchmarks with the pinned protocol in `Perf-Experiment-Template.md`.

---

# DELIVERABLE 9 — Multi-GPU parallelism decision matrix

(Full "when to use what" is in `Multi-GPU.md` + `Distributed-Architectures.md`.)

| If your problem is… | Use | Fabric needed | Cost |
|---|---|---|---|
| Model doesn't fit one GPU | TP first, PP second | NVLink (TP), RDMA (PP) | weight ÷ N |
| Need more throughput than one node | DP replicas (+ router) | any | none (replicate) |
| MoE model, experts don't fit | EP (+ TP intra-node) | fast RDMA / NVL72 | AllToAll |
| Ultra-long context, KV won't fit | CP/SP | fast fabric | AllToAll / ring |
| Cross-node large dense model | PP + DP | RDMA | P2P, bubbles |
| Many independent requests | DP + router | any | router cost |
| Prefill & decode contend | P/D disaggregation | RDMA / NVL72 | KV transfer |
| Latency SLO on small model | spec decode + TP | NVLink | draft compute |

**Default 2025+ stack:** TP intra-node (NVLink) → EP/PP across nodes (RDMA) → DP via
router → P/D disaggregation for high-concurrency SLOs.

---

# DELIVERABLE 10 — Research Radar (topics to track next 6–12 months)

(The full, dated, source-linked radar with Production/Emerging/Research/Experimental
classification is in `Research-Radar.md`. Snapshot 2026-08-21:)

| Topic | Status | Why watch |
|---|---|---|
| FP4/NVFP4 serving | Production | default 2025–26 datacenter precision; ~3.5× decode bandwidth vs BF16 |
| FP8 KV + FP8 compute | Production | near-lossless, halves KV bytes |
| P/D disaggregation (DistServe/Mooncake/Splitwise) | Emerging→Production | SLO-driven; KV transfer is the cost |
| Speculative decoding (EAGLE, MTP, DFlash) | Production | low-batch ITL lever; acceptance-rate dependent |
| RadixAttention / program-aware scheduling | Production | agentic shared-prefix workloads |
| MoE wide-EP + NVL72 | Emerging | networking-bound; AllToAll is the bottleneck |
| Warp-specialized / async TMA kernels (FA3-class) | Emerging | Hopper/Blackwell decode + prefill |
| Grouped/skinny GEMMs for decode | Emerging | shape-specific kernels beat cuBLAS at M=1..32 |
| KV-aware routing / KV-centric serving | Emerging | "balance remaining work, not requests" |
| GPU compilers (Triton, Inductor, torch.compile) | Production | kernel generation at scale |
| Collective optimization (SHARP, hierarchical AllReduce) | Research→Emerging | multi-node AllReduce latency |
| Heterogeneous / mixed GPU serving | Research | cost vs SLO on mixed hardware |
| Sub-quadratic attention (MLA, SSM hybrids, sliding-window) | Emerging | long-context KV cost |
| Inference-time KV compression/eviction (H2O, SnapKV) | Research | long-context capacity |
| Agentic inference (multi-turn, tool loops) | Emerging | router/scheduler design for agent workloads |

**Watch for:** vendor claims that outpace independent validation (tagged `[F: vendor claim]`
in `Research-Radar.md` until measured).

---

## Maintenance protocol (living handbook)
Same as the rest of the wiki (see `../README.md` § Maintenance): discover → diff → update
only affected pages → add papers to `../Research-Papers/` → update lineage → run the
independent evaluator over major changed pages → record in `../CHANGELOG.md` with
`LAST_UPDATED` on each page. Evaluator: `deepseek-v4-flash-0731` @ 10.1.1.51:8888.

## Key Takeaways
1. One model, two bottlenecks: **prefill = compute roof**, **decode = memory roof**.
2. Everything reduces to **GEMM shape** (M/N/K) + **bytes moved** + **fabric** + **overhead**.
3. Optimize **cross-layer**: fixing one layer exposes the next; always find the next
   limiting resource.
4. **No universal winner** for engines or parallelism — match to model + hardware +
   workload + SLO, then measure with the pinned protocol.

## Related (existing wiki)
`../Inference/Roofline.md` · `../Inference/The-Life-of-a-Token.md` ·
`../Inference/Inference-Optimization.md` · `../KV-Cache/README.md` ·
`../Attention/README.md` · `../Quantization/README.md` ·
`../Serving-Engines/README.md` · `../Distributed-Inference/README.md` ·
`../Networking/README.md` · `../Hardware/README.md` · `../Learning-Path/Zero-to-Hero.md`.
