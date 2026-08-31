# 01 — What Is Triton (and Why It Exists)
`LAST_UPDATED: 2026-08-27 · Status: core page` · Claims tagged [F] primary source ·
[A] assumption · [I] inference · [E] measured/Python-verified this session (GB10,
Triton 3.6.0 — see `FACTS.md` context in the section README).

## 30-Second Explanation
**Triton is a Python-embedded language and compiler for writing GPU kernels.** You
write a function that says what *one program instance* does to a **block (tile) of
data** — loads, math, stores — decorate it with `@triton.jit`, and launch it with a
grid of program instances. The compiler (an MLIR-based pipeline) decides how that
block maps onto warps, shared memory, swizzled layouts, and PTX instructions
[F: triton-lang.org docs]. It was created by **Phil Tillet** as a research project
(original paper: *"Triton: an intermediate language and compiler for tiled neural
network computations"* — a PDF, not on arXiv; cite the repo), then open-sourced as
Triton 1.0 by **OpenAI on 2021-07-28** with the pitch: FP16 matmul matching cuBLAS
"in under 25 lines of code," kernels "up to 2× more efficient than equivalent Torch
implementations" [F: OpenAI blog, archived copy]. Today it is the codegen target of
`torch.compile` and the extensibility layer of vLLM and SGLang — which is why LLM
engineers are Triton users whether they chose to be or not.

## Not that Triton (the name collision)
There are two "Tritons" in the LLM stack and they have nothing in common but the name:

| | **Triton (this section)** | **NVIDIA Triton Inference Server** |
|---|---|---|
| Purpose | Write GPU kernels | Serve models over HTTP/gRPC |
| Layer | Kernel language + compiler | Serving platform |
| Form | Python DSL (`@triton.jit`) | Server binary/container |
| Replaces | CUDA C++ kernel development | ad-hoc model servers, TorchServe |
| Used for | GEMM, attention, norms, fusion, quant kernels | Deploying TensorRT/ONNX/PyTorch models |
| LLM relevance | The kernels inside the engine | One way to put the engine behind an API |

People confuse them because (a) NVIDIA named its server first and (b) searches for
"Triton LLM" mix both. Rule of thumb: if the sentence mentions `tl.load`, it's us;
if it mentions `--http-port`, it isn't.

## The gap Triton fills
PyTorch is easy but opaque — `torch.softmax(x, dim=-1)` launches whatever kernels the
framework picked; you cannot fuse your norm into it or reshape its tiling. CUDA C++
is powerful but expensive: coalescing, shared-memory bank conflicts, warp
synchronization, and Tensor-Core scheduling are all yours to get wrong. The OpenAI
blog's framing (2021) is still the sharpest [F: OpenAI blog]:

| Optimization | CUDA | Triton |
|---|---|---|
| Memory coalescing | manual | **automatic** |
| Shared-memory management | manual | **automatic** |
| Scheduling within an SM | manual | **automatic** |
| Scheduling across SMs (tiling) | manual | **manual** — you still write it |

That last row is the whole design: Triton automates the *thread-level* machinery but
leaves *algorithmic* tiling to you, because tiling is where kernel performance is
actually decided. Concretely (this section's running example): a fused softmax over
2048×2048 FP32 measured **0.265 ms in Triton vs 0.646 ms in torch eager** [E, GB10]
— the fusion is 12 lines of Python, not a C++ project.

## Where it sits in the stack
```
Python / PyTorch ops
        │
High-level tensor operations  (nn.Linear, F.softmax …)
        │
Triton kernel  (@triton.jit, tl.load/tl.dot/tl.store)
        │
Triton compiler  (MLIR: TTIR → TTGIR → backend dialects)
        │
GPU backend  (NVIDIA PTX / AMD RDNA-CDNA, via LLVM)
        │
PTX → ptxas → SASS  (NVIDIA path)
        │
GPU  (SMs, Tensor Cores, HBM)
```
Simplified — the exact pass chain per backend is on `17-compiler-internals.md`, and
it changed materially in 2022 (LLVM-only → MLIR) [F: repo, commit #1004 merge
2022-12-21]. What has **not** changed: Triton never schedules across SMs; your grid
and tile ordering (grouped ordering, persistent loops) stay your responsibility.

## Why LLM frameworks adopted it (the short version)
1. **`torch.compile` made Triton the default.** Inductor emits Triton kernels for
   fused pointwise/reduction regions — every `torch.compile` user runs them [F:
   PyTorch docs; see `16-torch-inductor.md`].
2. **Engines need custom kernels Python can iterate on.** vLLM's tree contains
   Triton decode/prefill/unified attention, fused-MoE permutation + expert kernels,
   AWQ/scaled-mm quant kernels, KV-cache reshape-and-cache, RMSNorm fusions [F:
   repo tree 2026-08-27; details in `15-kv-cache-moe-kernels.md`]. SGLang similarly
   ships Triton rotary, layernorm, activation, sampler, paged-attention kernels.
3. **Quantization is kernel-shaped.** fp8/fp4 GEMMs want dequant + GEMM + activation
   fused in one launch with block scales handled in registers (`12-blackwell-fp4.md`);
   that is a Triton-shaped problem, not a cuBLAS call.
4. **Portability of effort.** One kernel source covers NVIDIA cc 8.0–12.x and (with
   backend caveats) AMD CDNA/RDNA [F: Triton docs] — engines that must run
   everywhere keep their long-tail ops in Triton rather than in per-arch CUDA.

## What Triton is NOT
- **Not a PyTorch replacement** — it extends it; Triton kernels are called *from*
  PyTorch tensors on every page of this section.
- **Not automatically fast** — bad tiles/masks give bad numbers; our GB10 skinny-M
  GEMM lost to cuBLAS by ~2× [E] until you tune (and even then, cuBLAS kept the win).
- **Not a serving system** — that's the *other* Triton (table above).
- **Not thread-free magic** — the compiler hides warps, but registers, occupancy,
  and shared-memory pressure still bite (`08-autotuning.md`).

## Key Takeaways
1. Triton = tiled-kernel DSL + MLIR compiler; you own tiling, it owns warps.
2. Created by Phil Tillet, open-sourced by OpenAI 2021-07-28, MLIR rewrite landed
   2022-12-21, 3.x is the MLIR era [F].
3. It is load-bearing for LLM inference: Inductor codegen + vLLM/SGLang kernel fleets.
4. The name collision with NVIDIA's Inference Server is a real, recurring tax —
   correct it explicitly in docs and reviews.
5. Performance is earned, not automatic: measure per shape; expect near-CUDA for
   fused ops [A] and vendor-library wins on the hottest GEMM/attention shapes [I].

## Related
`./02-gpu-programming-model.md` (next) · `../GPU-Systems/Triton.md` (overview page) ·
`../GPU-Systems/CUDA-From-Zero.md` · `../GPU-Systems/Kernel-Stack.md` ·
`./16-torch-inductor.md` · `./17-compiler-internals.md`.

## References
- OpenAI, "Introducing Triton: Open-Source GPU Programming for Neural Networks"
  (2021-07-28; web.archive.org copy fetched 2026-08-27)
- Triton paper: P. Tillet et al., "Triton: an intermediate language and compiler for
  tiled neural network computations" (PDF; not on arXiv — cite the repo)
- github.com/triton-lang/triton (MIT; release tags API-fetched 2026-08-27)
- triton-lang.org docs — "Triton in a nutshell" / tutorials index (fetched 2026-08-27)
