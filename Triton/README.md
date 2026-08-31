# Triton — From Python Kernels to High-Performance LLM Inference
`LAST_UPDATED: 2026-08-27 · Status: first-class section` · Zero-to-hero handbook for
**Triton, the GPU kernel language and compiler** — not NVIDIA Triton Inference Server
(§02 untangles that name collision). Claims tagged [F] primary source (Triton
repo/docs, OpenAI blog, PyTorch/NVIDIA/AMD docs, vLLM/SGLang source trees) · [A]
engineering assumption · [I] inference · [E] measured or Python-verified this session
on the local **GB10 (cc 12.1, Triton 3.6.0)** unless another box is named.

## 30-Second Explanation
Triton is a Python-embedded DSL + compiler for writing GPU kernels at the granularity
of a **block (tile) of data** instead of a thread: you write what *one program* does
with a tile (`tl.load` → compute → `tl.store`), and the compiler decides warps,
coalescing, shared-memory layout, swizzling, and (on Hopper+) pipelining for you
[F: triton-lang.org docs]. It exists because PyTorch gives you tensors but not
kernels, and CUDA C++ gives you kernels at the price of thread-level engineering:
Triton is the middle layer where almost every LLM custom op actually wants to live.
Three forces made it the default kernel language of the LLM era: **`torch.compile`'s
Inductor emits Triton** for every fused op [F: PyTorch docs], **vLLM and SGLang ship
dozens of hand-written Triton kernels** (decode/prefill attention, fused MoE, quant
GEMMs, norms, KV-cache ops — verified in both source trees), and **fp8/fp4 kernels
need shape-specific fused epilogues** that vendor libraries don't cover. The ceiling
is still hand-written CUDA/CUTLASS on the few hottest kernels — Triton's value is
that the *rest* of the kernel fleet becomes writable, readable, and fusable in Python.

## Who this is for and how to read it
- **PyTorch engineer, no kernel background:** pages 01 → 02 → 03 → 05 → 06 → 20.
- **Inference engineer who needs to modify engine kernels:** 03 → 04 → 13 → 14 → 15.
- **CUDA programmer evaluating Triton:** 02 → 08 → 10 → 12 → 18 → 19.
- **Performance engineer:** 07 (roofline) → 17 (debugging) → 18 (methodology) → 19.

| Page | What it covers |
|---|---|
| `01-what-is-triton.md` | What Triton is/isn't, why it exists, the history timeline |
| `02-gpu-programming-model.md` | Programs vs threads, grids, the block mental model |
| `03-triton-fundamentals.md` | First kernel line-by-line, masks, dtypes, broadcasting, tl ops |
| `04-memory-and-tiling.md` | Memory hierarchy, coalescing, the GB10 numbers behind them |
| `05-kernel-fusion.md` | Fusion: the flagship pattern, fused softmax walkthrough |
| `06-reductions-softmax.md` | Reductions, numerically-stable softmax, first benchmarks |
| `07-gemm.md` | GEMM from scratch: naive → tiled → grouped ordering → autotune |
| `08-autotuning.md` | `@triton.autotune`, num_warps, num_stages, register pressure, occupancy |
| `09-tensor-cores.md` | How `tl.dot` reaches Tensor Cores; per-architecture mapping |
| `10-tma-descriptors.md` | TMA + tensor descriptors on Hopper/Blackwell |
| `11-persistent-kernels.md` | Persistent kernels, persistent matmul, warp specialization, pipelining |
| `12-blackwell-fp4.md` | Blackwell (SM100 vs SM121!), block-scaled NVFP4/MXFP4 matmul |
| `13-flash-attention.md` | FlashAttention in Triton, online softmax, prefill vs decode |
| `14-llm-kernels.md` | RMSNorm/LayerNorm/RoPE/activations — the fused-epilogue zoo |
| `15-kv-cache-moe-kernels.md` | Paged KV access, KV ops, MoE fused kernels, grouped GEMM |
| `16-torch-inductor.md` | Dynamo → Inductor → Triton; generated vs handwritten kernels |
| `17-compiler-internals.md` | MLIR pipeline, TTIR/TTGIR, PTX/SASS, reading generated code |
| `18-debugging-profiling.md` | Interpreter, device_print, Nsight, benchmarking correctly |
| `19-performance-engineering.md` | Optimization methodology, common mistakes, comparisons (CUDA/CUTLASS/cuBLAS) |
| `20-practical-labs.md` | 18 progressive labs + 30-day learning path + "how to read any kernel" |

## The one-paragraph mental model
A Triton kernel is a Python function that describes the **work done by one program
instance on one tile of data**; the launch grid says how many programs cover the
whole tensor; the compiler lowers each program to warps, shared-memory staging, and
PTX — automatically. Program 0 handles elements 0–1023, program 1 handles
1024–2047, and so on. You own tiling, masks, and memory movement between
hardware layers; the compiler owns everything warp-level. That split is why a fused
softmax is ~15 lines instead of a week of CUDA, and why the same source covers
NVIDIA (cc 8–12) and AMD (CDNA/RDNA) backends — while still exposing the
performance knobs that matter (`BLOCK_*`, `num_warps`, `num_stages`,
`warp_specialize`, tensor descriptors).

## Key Takeaways
1. Triton = Python DSL + MLIR-based compiler: **you own the tile, the compiler owns
   the warp** — the inverse emphasis of CUDA C++.
2. It is the codegen target of `torch.compile` and the extensibility layer of vLLM
   and SGLang: LLM engineers are already Triton users whether they know it or not.
3. Measure before believing: our GB10 [E] runs show Triton beating torch-eager by
   ~2.4× (softmax) and ~10× (RMSNorm, unfused ref), beating cuBLAS on 2048³ FP16
   GEMM — and *losing* to cuBLAS on skinny M=1 decode GEMMs. Real rankings are
   shape- and box-specific.
4. Hopper/Blackwell features (TMA, warp specialization, tcgen05, block-scaled FP4)
   are where current Triton development is concentrated — and where datacenter
   SM100 and consumer/edge SM121 diverge sharply.
5. The ceiling claim survives: near-CUDA for most fused ops [A]; hand-written
   CUDA/CUTLASS/FlashInfer keeps the hottest kernels — Triton is for the long tail
   and the fusion wins.

## Related
`../GPU-Systems/Triton.md` (single-page overview) · `../GPU-Systems/CUDA-From-Zero.md`
(the thread-level story) · `../GPU-Systems/Kernel-Stack.md` (where Triton sits) ·
`../Inference/Roofline.md` · `../KV-Cache/README.md` · `../Quantization/README.md` ·
`../Serving-Engines/README.md` · `../GPU-Communication/README.md` (NCCL — the layer
above kernels).

## References
- Triton repo & docs: github.com/triton-lang/triton · triton-lang.org (fetched 2026-08-27)
- OpenAI blog, "Introducing Triton" (2021-07-28; archived copy fetched this session)
- Triton releases v2.0.0 (2023-03-02), v3.0.0 (2024-07-19), v3.4.0–v3.7.1 (API-fetched tag dates)
- PyTorch blog, "Warp Specialization in Triton: Design and Roadmap" (2026-01-08)
- Tutorials 01–11 + gluon/ (current main); persistent-matmul + block-scaled-matmul pages
- vLLM and SGLang source trees (GitHub API tree listings, 2026-08-27)
- Measured [E] baseline: GB10 cc 12.1, Triton 3.6.0, torch 2.11.0+cu130 (this session)
