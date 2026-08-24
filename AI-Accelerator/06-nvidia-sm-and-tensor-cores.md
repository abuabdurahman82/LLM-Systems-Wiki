# NVIDIA SM & Tensor Core Evolution
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = NVIDIA PTX ISA / whitepapers.

## 30-Second Explanation
The Tensor Core is a small, dedicated matmul engine inside each SM that computes
**C ← A×B + C on tiles** — not scalar FMAs one at a time. Its evolution is the story of
moving the *issuing context* up the thread hierarchy and making matmul *asynchronous*:
`mma.sync` (a whole warp issues it, Volta→Ampere) → `wgmma` (a 128-thread warp-group
issues it, Hopper) → `tcgen05.mma` (a single thread issues it, it runs in the background,
accumulates into a dedicated TMEM, optionally spanning two SMs, Blackwell). Each step
trades programmer-visible control for hardware autonomy — and for a kernel that can run
softmax while the previous matmul is still in flight.

## C ← A×B + C: the tile matmul
Every Tensor Core instruction computes a *tiled* matmul with in-place accumulation:
```
D[i,j] = acc + sum_k A[i,k] * B[k,j]      (D often aliases C)
```
- **Tile:** the instruction operates on fixed operand shapes (e.g., m16n8k16 for
  `mma.sync` FP16), not arbitrary M×N×K. A real GEMM is a grid of these tiles; the K loop
  accumulates into D over chunks of K.
- **Fragments:** the SM's register file and the Tensor Core's internal operand stores have
  specific layouts. A warp's threads *together* hold the A/B/C tiles in registers, in a
  fixed distribution ("matrix fragments"). The programmer/compiler manages this layout —
  it is the source of much of a GEMM kernel's complexity (see `../GPU-Systems/GEMM.md`,
  `../GPU-Systems/Custom-GEMM.md`).
- **K loop:** the k-dimension is processed in chunks; each chunk issues one (or a few)
  MMA instructions that accumulate into the same D. This is why "deep K" pipelines so well.
- **Accumulate:** D stays in registers (or TMEM on Blackwell) in a *higher-precision*
  accumulator (FP32 for FP16/BF16/FP8 operands; FP32 for FP4), so rounding doesn't
  accumulate across the K loop. [F]

### The evolution, step by step
| Gen | Instr | Issuer | Scope | Key change |
|---|---|---|---|---|
| Volta (V100) | `mma.sync` | 1 warp (32) | warp | first dedicated FP16 matmul; A/B/C in warp registers |
| Turing (T4) | `mma.sync` | 1 warp | warp | +INT8/INT4; FP16 |
| Ampere (A100) | `mma.sync` | 1 warp | warp | +BF16/TF32; bigger tiles; async copy (cp.async) added |
| Hopper (H100) | `wgmma.mma_async` | warp-group (128) | 4 warps | warp-group scoped; A can come from SMEM (not just regs); **asynchronous** — issue and move on; FP8 |
| Blackwell (B200) | `tcgen05.mma` | 1 thread | 1 thread, + optional 2-SM cluster | single-thread issued; accumulates into **TMEM** (dedicated tensor memory); async; FP4/NVFP4; can span 2 SMs |

**Why asynchronous matters** (the whole point of the last two steps): with `mma.sync`,
the warp that issued the matmul blocks until it completes — it cannot do softmax, apply
a mask, or prefetch the next tile meanwhile. With `wgmma`/`tcgen05`, the issuer fires the
matmul and immediately continues: the Tensor Core runs in the background while the warp
(or other warps) does overlapping work. For FlashAttention-class kernels — where matmul,
softmax, and masking are interleaved *inside* the loop — this overlap is the structure of
the kernel, not an optimization on top of it. [I: mechanism; see
`../GPU-Systems/FlashAttention.md`]

## The SM in concrete terms (H100 SXM reference)
```
SM
├── 4 warp schedulers   (1 instruction issued/cycle each -> up to 4 warp-insn/cycle)
├── 128 CUDA cores      (FP32 ALUs; elementwise, control, address math)
├── 4 Tensor Cores      (4th-gen on H100; mma.sync FP16/BF16/TF32/INT8, FP8 via wgmma)
├── register file       (65,536 x 32-bit = 256 KB; max 64 warps / 2048 threads resident)
├── L1 / shared memory  (up to 228 KB, partitioned; SMEM is the tile buffer for MMA)
└── TMA (Hopper+)       (async bulk HBM<->SMEM copies, descriptor-driven, no per-element SM work)
```
- Max 64 warps / 2048 threads resident per SM [F: vendor spec] — this is the occupancy
  ceiling that latency-hiding draws on (`05`).
- The 4 schedulers let up to 4 independent warps issue in the same cycle; more resident
  warps than schedulers means the scheduler is always picking a ready warp.

## How a GEMM actually uses the SM (worked micro-view)
```
kernel:  C[M,N] = A[M,K] @ B[K,N],  M=N=K=8192,  tile 128x128,  K-chunk 32
loop:   for each 128x128 output tile (CTA):
            for k in 0..K step 32:
                TMA/cp.async: load A[128 x 32], B[32 x 128] into SMEM (async)
                wait SMEM ready
                wgmma:  C_reg += A_tile @ B_tile      (Tensor Core, FP16->FP32 acc)
            write C tile to L2/HBM
```
- The K-loop depth (8192/32 = 256 iterations) is what gives the pipeline its overlap:
  while `wgmma` #i runs, the TMA is already staging #i+1's tiles. This *software
  pipelining* (producer TMA warps, consumer MMA warps) is where `07`'s warp
  specialization comes in. [I: standard CUTLASS structure]
- **Producer/consumer warp specialization** (Hopper+): one or more warps do only TMA
  loads, the rest do only the MMA; they sync via `mbarrier` (async barriers). This
  decouples "move data" from "multiply data" so neither ever idles waiting on the other.

## Tile size, K-loop, and on-chip storage
- The **tile** must fit in SMEM + registers: bigger tiles reuse operands more (higher AI)
  but use more on-chip space. The SM's 228 KB L1/SMEM and 256 KB register file set the
  ceiling; HBM sets the floor (you must load the tile's K-chunks).
- **K-loop depth** determines how much the async machinery can overlap: deep K = long
  pipeline = the Tensor Core stays fed. Shallow K (GEMV, M=1 decode) has almost no K-loop
  to pipeline, which is exactly why decode is bandwidth-bound no matter how good the Tensor
  Core is (`02`).
- This is the *single most important reason* matmul engines differ across machines:
  TPU's MXU reuses operands in the systolic wiring (no SMEM round-trip), Cerebras assembles
  the matmul from the mesh, Groq's MXM is a fixed 320×320 plane. NVIDIA's flexibility
  (programmer picks the tile) is a strength for varied work and a cost vs a fixed-shape
  engine. [I]

## Numerics on the Tensor Core
See `20-ai-hardware-numerics.md` for the full format evolution. On the Tensor Core:
FP32 → TF32 (10-bit mantissa, FP32 range) / FP16 / BF16 (Ampere) → FP8 E4M3/E5M2 (Hopper)
→ FP6/FP4 + NVFP4 microscaling (Blackwell). FP32 accumulation is standard; block scaling
(FP8/FP4) restores accuracy by adding a per-16-element exponent.

## Connection to LLM inference
- **Prefill / training GEMMs:** fat M, deep K → Tensor Core + TMA + warp specialization
  saturate; this is where H100/B200 FLOPs get used.
- **Decode GEMV (M=B small):** no K-loop depth to pipeline; the Tensor Core is idle most of
  the time; HBM bandwidth dominates. Tensor Core FLOPs do not help decode much — the
  limiting factor is streaming weights (`02`, `../Inference/Roofline.md`).
- **Attention (FlashAttention):** matmul+softmax+mask interleaved per tile; the async
  `wgmma`/`tcgen05` overlap is what makes FA3/FA4 kernels possible (`../GPU-Systems/FlashAttention.md`).

## Key Takeaways
1. The Tensor Core computes *tiled* C←A×B+C; fragments, tiles, and the K-loop are the
   unit of a real GEMM.
2. The whole evolution (warp → warp-group → single-thread + TMEM) is one direction:
   *more async, more hardware autonomy, less per-thread overhead*.
3. Asynchronous MMA is what lets a kernel run softmax while the matmul is in flight —
   the structure of FlashAttention-class kernels.
4. Tile size is bounded by on-chip memory; K-loop depth bounds how much the pipeline can
   overlap. GEMV has neither, which is why decode is bandwidth-bound.
5. Warp specialization (producer TMA / consumer MMA + mbarrier) is the Hopper-era answer
   to feeding the Tensor Core without the issuer waiting.

## Related
- `05-nvidia-gpu-overview.md` — the machine context
- `07-nvidia-memory-hierarchy.md` — TMA, mbarrier, warp specialization in the memory context
- `../GPU-Systems/GEMM.md`, `../GPU-Systems/Tensor-Cores.md`, `../GPU-Systems/Custom-GEMM.md`
- `../GPU-Systems/FlashAttention.md` — the kernel that uses async MMA
- `20-ai-hardware-numerics.md` — the format ladder on the Tensor Core

## References
- NVIDIA PTX ISA 8.x (mma.sync, wgmma.mma_async, tcgen05.mma [F])
- NVIDIA Hopper/Blackwell architecture whitepapers (TMA, TMEM, NVLink [F: vendor spec])
- CUTLASS (open-source; GEMM tile/pipeline structure [F: repo])
- FlashAttention-3 (arXiv:2407.08608) [F: bank] — Hopper wgmma-based kernel
- `../GPU-Systems/_STYLE.md` — H100 SM constants (cross-checked)
