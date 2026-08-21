# GEMM — The Core Operation Behind LLMs
`LAST_UPDATED: 2026-08-21 · Status: core page` · All [E] arithmetic is hand-derived;
hardware constants cross-checked against `../Hardware/README.md` and NVIDIA specs.

## 30-Second Explanation
A Transformer layer is ~90% **matrix multiplications**. In prefill the matrices are big
(`[S,d] × [d,d]`, S = prompt length) → dense, compute-bound, Tensor-Core-happy. In decode
the matrices are skinny (`[B,d] × [d,d]`, B = batch, often 1) → they degenerate into
**GEMVs** that stream the whole weight matrix per token → memory-bandwidth-bound. GEMM
performance depends **heavily on shape**: an `8192×4096×4096` GEMM and a
`1×4096×4096` GEMV use the same weights but sit on opposite roofs of the
[Roofline](../Inference/Roofline.md). This page walks GEMM from the naive triple loop to
Tensor Cores, and maps every Transformer operation to a GEMM.

## What
A General Matrix Multiply:
```
C[M,N] = A[M,K] · B[K,N]      (each C[i,j] = Σ_k A[i,k]·B[k,j])
FLOPs  = 2·M·N·K              (one MAC = 2 FLOPs)
```
**M** = rows of A (in LLMs: number of tokens in flight), **N** = cols of B (out dim),
**K** = shared dim (in dim). The three numbers determine the entire performance profile.

### Map every Transformer op to a GEMM
(Shapes for a standard decoder layer, d = hidden, S = seq len in a step, h·d_h = QKV out,
d_ff = FFN width. See `../Inference/The-Life-of-a-Token.md`.)

| Op | GEMM shape | Role |
|---|---|---|
| Q proj | `X[S,d] · Wq[d, h·d_h]` | what to look for |
| K proj | `X[S,d] · Wk[d, h_kv·d_h]` | what to be found by |
| V proj | `X[S,d] · Wv[d, h_kv·d_h]` | what to carry |
| Attention | `QKᵀ` + `·V` (per head) | the S×S core |
| O proj | `A[S, h·d_h] · Wo[h·d_h, d]` | back to d |
| MLP up | `X[S,d] · W1[d, d_ff]` (SwiGLU: 3 of these) | expand |
| MLP down | `H[S,d_ff] · W3[d_ff, d]` | shrink back |

The **MLP is where most parameters live** (~⅔ of a layer); QKV is ~⅓. Total linear
FLOPs/token ≈ **~12·d²** (3·d² QKV + 1·d² O + ~8·d² SwiGLU MLP) [E, derived].

## Why
GEMM is the single dominant cost of inference. Optimize it and you optimize the model.
The roofline tells you which lever to pull **based on M**:
- **M = S (prefill, large):** AI ≈ d/b_w (≈ 2048 @ d=4096, BF16) ≫ ridge → **compute-bound**.
  Tensor Cores + big K → near-peak. FlashAttention handles the S×S part.
- **M = B (decode, small):** AI ≈ 2·B·d / (2·B·b + b_w·d) → ≈ 1–4 at B=1,2 →
  **memory-bound**. You're just streaming `d×d` weights. Batch to B* to amortize.

## How — progressive optimization
Each step moves data fewer levels down the hierarchy (see `Memory-Hierarchy.md`):

1. **Naive GEMM** — one thread per `C[i,j]`, each reads a full row of A + col of B from
   HBM → O(N·K) HBM reads per output element. Re-reads A N times, B M times. Catastrophic.
2. **Coalescing** — reorder so a warp's N threads touch N contiguous addresses (32-wide
   128B transaction). Halves HBM transactions vs random.
3. **Tiling into shared memory** — load a `[BM × BK]` tile of A and `[BK × BN]` tile of B
   once into shared memory; each thread computes a `[BM×BN]` sub-tile of C. Reuse goes
   from O(1) to O(tile). HBM traffic drops ~`d/BM` × `d/BN`.
4. **Register blocking** — each thread holds a `[BR × BC]` micro-tile in **registers**;
   inner FMA loop stays in registers (no HBM, no shared). Register pressure vs occupancy
   trade-off.
5. **Warp-level tiling** — split the shared-memory tile across the 32 lanes of a warp so
   the FMA issue rate saturates the SM.
6. **Tensor Cores** — swap the scalar FMA for a mixed-precision **MMA** (matrix
   multiply-accumulate) on `m×n×k` tiles (e.g. 16×8×16). The whole warp issues one MMA
   covering 16×8 outputs × K in one instruction → 8–16× the FLOP/issue rate.

```
Naive                          Tiled (shared mem)            Register-blocked
C[i,j]                         tile [BM×BN] of C            [BR×BC] in regs
│  reads A row + B col         │                              │
│  from HBM, O(NK) each       load tiles once → SRAM         FMA loop in regs
└  re-reads A N times         reuse = BM or BN               no HBM in inner loop
```

## When
- **Large M (prefill, training, big-batch decode):** use cuBLAS/cuBLASLt or CUTLASS
  kernels tuned for your shape; Tensor Cores in the best dtype.
- **Small M (decode):** cuBLASLt has skinny-M kernels, but **custom grouped/batched/
  quantized GEMM** often wins (`Custom-GEMM.md`). This is where engines differentiate.
- **MoE:** grouped GEMM (many small, different-M GEMMs, one per expert) — cuBLAS
  batched/grouped or custom.

## Hardware impact
- Prefill GEMM → **Tensor Core** utilization high; HBM read = weights once + activations.
- Decode GEMV → **HBM bandwidth** saturated; Tensor Cores mostly idle (M too small).
- Quantized GEMM (W8A8/W4A4) → Tensor Core FLOP rate rises (FP8 = 2× BF16, FP4 = 4× on
  Blackwell) **and** bytes drop → both roofs lift.

## Inference impact
- **TTFT** ∝ prefill GEMM time → FP8/FP4 weights, FlashAttention, more GPUs (TP) help.
- **ITL** ∝ decode bytes/token → quantize, batch to B*, GQA/MLA shrink KV.
- A 6.5B-class layer's MLP is a `B×4096 → 11008 → 4096` GEMM; at B=1 that's
  3·4096·11008 ≈ **136M MACs** but streams **~269 MB** of weights → bandwidth-bound,
  not FLOP-bound (33.5M MACs is trivial; 269 MB of HBM is the cost).

## Example [E, hand-derived]
Take a 6.5B-class decoder (d=4096, 32 layers, d_ff=11008, GQA), BF16 (b=2). Per-layer
linear weight bytes:
- QKV + O ≈ 4 · 4096 · 4096 · 2 = **128 MB** (taking Q,K,V,O out-dims ≈ d in aggregate).
- MLP (SwiGLU, 3 matrices): 3 · 4096 · 11008 · 2 = **269 MB**.
- Per layer ≈ **397 MB**; × 32 layers ≈ **12.7 GB** of linear weights (≈ the model's
  ~6.5B-param BF16 size; embedding adds a little).
Decode B=1 ceiling on H100 (3.35 TB/s): 3.35 TB/s ÷ 12.7 GB ≈ **~260 tok/s** (theoretical,
ignoring KV reads + kernel overhead). A real 27B model (50.3 GiB BF16, see
`../Inference/Roofline.md`) scales the bytes up → **~65 tok/s** B=1 ceiling. Both **halve**
if the GEMV kernel isn't bandwidth-optimal (strided/unaligned access, or a large-M
cuBLAS kernel picked for M=1).

## Failure modes
- **M too small for the kernel:** cuBLAS default may pick a large-M kernel → poor
  decode. Use cuBLASLt's algo selection or a custom skinny GEMM.
- **Unaligned / strided inputs:** breaks coalescing + vectorization → HBM efficiency
  collapses. (Layout matters: see `Memory-Hierarchy.md`.)
- **Wrong dtype path:** a BF16 GEMM on FP8-capable HW with no `compute type` set →
  TF32/FP32 fallback, ~½–¼ the peak.
- **Shape mismatch with block sizes:** M,N,K not multiples of the MMA tile → padding
  waste; engines pad to a multiple.

## How to measure it
- **NVIDIA Nsight Compute** → per-kernel `sm__inst_executed_pipe_tensor`,
  `dram__throughput`, `compute__throughput`; the achieved FLOP/s vs peak is your GEMM
  efficiency. [F: Nsight Compute docs]
- **`cublas` benchmark** (`cublasLtMatmulAlgoGetHeuristic`) → best algo per shape.
- **Roofline position:** compute AI = 2MNK / bytes, plot on the [Roofline](../Inference/Roofline.md).
  Below ridge → bandwidth; above → compute.
- **vLLM/SGLang metrics:** prefill vs decode tok/s, `gpu_cache_utilization`, kernel time
  from `torch.profiler` / Nsight Systems.

## Why GEMM performance depends heavily on shape
The **M** dimension (tokens) is the pivot:
- M large → K-reuse → compute roof, Tensor Cores shine.
- M small → K is streamed once → memory roof, only bandwidth matters.
The same weight matrix, the same GPU, two opposite regimes. This is why a single
"GEMM kernel" cannot be optimal for both, and why inference engines run **different
kernels for prefill vs decode** and pick by M, N, K, dtype, and architecture.

## Example: prefill vs decode, same model, same layer
| | Prefill (S=4096) | Decode (B=1) |
|---|---|---|
| GEMM shape | `[4096,4096]×[4096,4096]` | `[1,4096]×[4096,4096]` |
| FLOPs | 137 GFLOP | 33.5 MFLOP |
| Weight bytes | 32 MB | 32 MB (streamed once) |
| AI (FLOP/byte) | 4096 (≈ d/b) | **1.0** |
| Roof | compute | **memory** |
| What limits | Tensor Cores | HBM bandwidth |
| Best lever | FP8/FP4, big-K pipelining | quantize + batch |

## Related
`../Inference/Roofline.md` · `GEMM` is the spine of `Tensor-Cores.md`,
`Custom-GEMM.md`, `Fused-Kernels.md`, `FlashAttention.md` · `../Inference/The-Life-of-a-Token.md` ·
`../Quantization/README.md` · `Memory-Hierarchy.md` · `../Hardware/README.md`.

## Key Takeaways
1. Every Transformer op is a GEMM; **M (tokens) is the regime-switch**.
2. Prefill GEMM = compute roof (Tensor Cores); decode GEMV = memory roof (bandwidth).
3. Optimize by moving data up the hierarchy: coalesce → tile → register → Tensor Cores.
4. Engines run **different GEMM kernels** for prefill vs decode and by shape/dtype/arch.
