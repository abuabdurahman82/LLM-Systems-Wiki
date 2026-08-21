# Tensor Cores for LLM Engineers
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART VIII — continues the GEMM→kernel
ladder from `GEMM.md` (step 6 of its optimization sequence). Hardware constants per
`../Hardware/README.md` and NVIDIA specs; vendor peaks tagged `[F: vendor spec]`.

## 30-Second Explanation
A **Tensor Core** is a mixed-precision matrix multiply-accumulate (MMA) unit inside each
SM. One warp-level instruction computes an `m×n` tile of a matrix product
(`D[m,n] += A[m,k]·B[k,n]`, e.g. 16×8×16) — 2048 MACs in one issue — where CUDA cores do
one scalar FMA per thread per issue. Prefill GEMMs (large M) live under the **compute
roof** and are only as fast as the Tensor Cores allow; decode GEMVs (M ≈ 1) live under
the **memory roof** and barely use them. Modern Tensor Cores accept **FP16/BF16, FP8
(E4M3/E5M2), INT8/INT4, and FP4/NVFP4**, each with a higher peak: on H100 FP8 dense is
2× BF16 dense (1,979 vs 989 TFLOP [F: vendor spec]); on B200 FP4 dense is ~4× BF16-class
(~9 PF vs ~2.25 PF [F: vendor spec]). So quantization helps inference by **two
independent routes**: fewer weight bytes (bandwidth) *and* a higher MMA peak (compute) —
and only weight+activation formats (W8A8, W4A4) engage the second route. The rest of
this page: the MMA tile, the SM data path, the format table, and the
precision↔throughput trade.

## What — Tensor Cores (the unit)

*9-field concept.*

### What
A Tensor Core executes `D[m,n] = A[m,k] · B[k,n] + D[m,n]` on small tiles **per
instruction**, with A/B/D in different (mixed) precisions. First shipped on Volta (V100,
2017; vendor whitepaper) [F: NVIDIA V100 whitepaper]; generations: Volta (fp16),
Turing (fp16/int8), Ampere (+bf16, tf32), Hopper (+fp8 e4m3/e5m2, sparsity), Blackwell
(+fp4/nvfp4) [I: generation timeline from vendor docs]. It is **warp-collective**: one
thread issues `mma.sync`, all 32 lanes supply/hold fragments of A, B, and D, and the
unit computes the whole tile.

### Why
FMA throughput per issue scales with tile size, not with thread count: a `16×8×16`
tile is 2,048 MACs = 4,096 FLOP in **one warp instruction**, vs a scalar warp issuing
32 independent FMAs (64 FLOP) per instruction [E: 16·8·16·2 = 4096; 32·2 = 64;
4096/64 = 64×]. NVIDIA could therefore place far more FLOP in an SM than a scalar-FMA
design at comparable power — which is exactly the compute roof you need for prefill
(`GEMM.md`, `Bandwidth-vs-Compute.md`).

### How
- **Issue:** a warp issues `mma.sync` with its A/B operand fragments in registers;
  result D lands back in the warps' registers. Data path: registers in, registers out
  (see diagram below) — no memory access inside the MMA.
- **PTX family (shapes, not recipes):** `m16n8k16` (FP16/BF16), `m16n8k8` (TF32),
  `m8n8k4`/`m8n8k16` (INT8), `m8n8k32` (INT4), `m16n8k32` (FP8 e4m3/e5m2, Hopper)
  [F: NVIDIA PTX ISA]. Hopper adds `wgmma.mma_async` (warp-group-wide, async) that
  Blackwell-era kernels still use for large GEMMs; you don't need to write PTX —
  cuBLAS/CUTLASS/Triton emit it (`Triton.md`, `Custom-GEMM.md`).
- **CUDA C++ WMMA:** the `nvmath::wmma` API wraps the same idea: create
  `fragment<matrix_a, m16n8k16, half, row_major>`, `load_matrix_sync` from shared
  memory, `mma_sync(a, b, d)` accumulating into the D fragment,
  `store_matrix_sync` back. "Fragment" = how the m×n tile's elements are scattered
  across the warp's 32 registers [F: CUDA C++ Programming Guide, WMMA].

### When
- **Always**, for the big GEMMs: prefill, training, batched decode — any M ≫ knee
  (knee batch B* ≈ 295–345 on H100, `Bandwidth-vs-Compute.md` E3).
- **Rarely binding**, for B=1 decode GEMVs: AI ≈ 1–4 ≪ ridge, HBM limits the token
  rate; Tensor Cores wait on data.
- **Only if the kernel's dtype path actually uses them** — a "FP8 model" served with a
  BF16 compute path gets zero MMA benefit (failure mode below; `Custom-GEMM.md`).

### Hardware impact
Vendor whitepapers enumerate the units, e.g. V100: 640 Tensor Cores across 80 SMs;
A100: 432 across 108 SMs (= 4/SM) [F: NVIDIA whitepapers]. Modern SMs partition into
4 processing blocks (warp scheduler + FP/INT pipes + a Tensor Core path each) [A:
architectural description consistent with whitepapers] — the exact per-SM count varies
by generation and is not the number that matters: one warp can feed one MMA pipe per
issue, and MMA latency is amortized by the register→pipe→register loop. What *does*
matter: the **peak FLOP/s per precision** (table below) and that MMA operands come from
**registers**, so the GEMM pipeline is HBM → L2/SMEM → registers → Tensor Core →
registers → epilogue (`Memory-Hierarchy.md`).

### Inference impact
- **TTFT** (prefill, compute roof): set by the Tensor Core peak of the GEMM dtype.
  FP8 prefill on H100 is 2× BF16; FP4 on B200 ~4× BF16-class (`../Inference/Roofline.md`).
- **ITL** (decode, memory roof): Tensor Cores are mostly idle; only the *bytes* matter
  — but a kernel that dequantizes to BF16/FP16 in-register still runs the 16-bit MMA,
  so "weight-only 4-bit" ≠ "4-bit compute" (see trade-off section).
- **Attention:** FlashAttention's S×S GEMMs also run on Tensor Cores (FA2/FA3 target
  them; FA3 on Hopper uses TMA + wgmma) — see `FlashAttention.md`.

### Example
One `m16n8k16` FP16 MMA: A is `16×16` FP16, B is `16×8` FP16, D is `16×8` FP32 (or
FP16). MACs per instruction: `16·8·16 = 2,048` → 4,096 FLOP [E]. The same tile done
with scalar CUDA-core FMAs needs 2,048 FMA *issues by one thread*, or 2,048/32 = 64
issue-iterations across a 32-lane warp [E] — and each scalar issue only does 2 FLOP,
vs 4,096 for the MMA. This 64× issue-rate ratio is why GEMM kernels "swap the FMA loop
for the MMA loop" (`GEMM.md` step 6).

### Failure modes
- **Wrong dtype path:** FP8 weights but the GEMM issued as BF16/TF32 → you paid
  accuracy risk for no speedup. Check the kernel (Nsight: `sm__inst_executed_pipe_tensor`
  + achieved FLOP/s vs the *right* peak — `Profiling.md`).
- **M not a multiple of the tile:** padding waste; engines pad or fall back to a
  different tile (`GEMM.md`).
- **Register pressure:** D fragments live in registers; too many simultaneous tiles or
  too-long K-pipelining drops occupancy (`Memory-Hierarchy.md`).
- **Assuming decode benefits:** B=1 decode is bandwidth-bound; the Tensor Core peak is
  irrelevant there (`Bandwidth-vs-Compute.md`).

### How to measure it
- Nsight Compute: `sm__inst_executed_pipe_tensor` (MMA issue activity), achieved FLOP/s
  vs the dtype's peak, `dram__throughput` to confirm which roof binds
  [F: Nsight Compute docs] → `Profiling.md`, `GPU-Metrics.md`.
- Sanity check: prefill tok/s should scale ~2× going BF16→FP8 on H100 (compute roof,
  same MFU); decode B=1 tok/s should scale ~1× on bytes-only, not on FLOPS [I].

## Where the Tensor Cores sit — the SM data path
```
 HBM (3.35 TB/s on H100 SXM [F: vendor spec])
  │  coalesced / cp.async / TMA (Hopper+)
  ▼
 L2 ──► SMEM: tiles [BM×BK] of A, [BK×BN] of B  (shared-memory tiling, GEMM.md step 3)
  │        │  ld.shared → per-lane register fragments (A, B, D)
  ▼        ▼
 ┌────────────────────────────────────────────────────────────────┐
 │ SM = 4 processing blocks, each ≈ {scheduler + FP/INT pipe + TC}│
 │                                                                │
 │   registers ────►  Tensor Core  ────►  registers               │
 │   (A frag, B frag)  mma.sync m16n8k16:   (D frag, 16×8)        │
 │                       D[16,8] += A[16,16]·B[16,8]              │
 │                                                                │
 │   CUDA cores (scalar FMA) handle: dequant, scales, softmax,    │
 │   elementwise, epilogue — not the bulk GEMM                    │
 └────────────────────────────────────────────────────────────────┘
  │  epilogue: D regs → SMEM → (L2) → HBM
  ▼
 HBM
```
Key points [I: synthesis of `GEMM.md` + vendor docs]:
1. **Registers → Tensor Core → registers.** MMA operands never come from memory
   directly; the whole register-blocking/tile pipeline (`GEMM.md` steps 3–5) exists to
   keep feeding fragments.
2. **CUDA cores and Tensor Cores coexist in the SM.** Low-bit dequantization (W4→FP16
   in-register), scaling, attention softmax, and epilogues run on the scalar pipes —
   this is why weight-only quantization still spends time on CUDA cores even when the
   MMA itself is fast.
3. **The pipeline is producer/consumer:** while one warp group's MMAs execute, async
   copies (Hopper `cp.async.bulk`/TMA, warp-specialized kernels) load the next K-tile
   (`Memory-Optimizations.md`, `FlashAttention.md` uses the same overlap for QKV/O tiles).

## Supported formats, bit-widths, and relative peaks
**Convention:** vendor "sparse" peaks use 2:4 structured sparsity; **dense = ½ sparse**
on the architectures below [F: NVIDIA spec convention]. All peaks: tensor-core, dense.

| Format | Bits/param | H100 SXM dense | Ratio vs BF16 | B200 (Blackwell) | Use in LLMs |
|---|---|---|---|---|---|
| FP32 (CUDA cores) | 32 | 67 TFLOP (non-TC) [F: vendor spec] | ~0.07× | — | training fallback; never the LLM serving path |
| TF32 | 19 (10b mantissa) | ~495 TFLOP [F: vendor spec] | 0.5× | — | legacy GEMM default on Ampere/Hopper if unset |
| FP16 | 16 | 989 TFLOP [F: vendor spec] | 1× | — | fine-tuning, legacy inference |
| BF16 | 16 | **989 TFLOP** [F: vendor spec] | 1× | ~2.25 PF [F: vendor spec] | LLM training/serving default |
| FP8 E4M3 / E5M2 | 8 | **~1,979 TFLOP** [F: vendor spec] | **2×** | **~4.5 PF** [F: vendor spec] | 2024–25 Hopper datacenter default (W8A8, KV FP8) |
| INT8 | 8 | ~3,958 TOPS [F: vendor spec] | 4× | — | CPU/edge, SmoothQuant-class GEMM |
| INT4 | 4 | (m8n8k32 MMA) [F: PTX ISA] | 8× [I: ratio] | — | mostly weight-only territory |
| FP4 / NVFP4 (e2m1 + block scales) | ~4.5 eff. | n/a (no FP4 on Hopper) | — | **~9 PF** [F: vendor spec] | 2025–26 datacenter default (W4A4/W4A16) |

Reading the table: going 16→8 bits doubles the MMA peak (H100), 16→4 quadruples it
(B200); the ratio FP4/BF16 on B200 ≈ 9/2.25 = **4×** [E: 9e15 ÷ 2.25e15 = 4] [F: vendor
spec for both peaks]. INT8 on H100 is 4× BF16 because 8-bit MACs are 2× 16-bit MACs and
INT8 adds no dynamic range [I]. The *effective* ratio is what feeds the roofline ridge:
H100 ridge jumps 295 → 591 FLOP/byte in FP8 (989/3.35 → 1979/3.35 [E]); B200 FP8 ridge
= 4.5e15/8e12 = 562.5 [E, matches `Bandwidth-vs-Compute.md`].

## The central trade — precision ↔ memory ↔ bandwidth ↔ Tensor Core throughput ↔ quality

*9-field concept — the precision↔throughput trade.*

### What
One knob (bits/param for weights and/or activations) moves **four** things at once:
(1) weight/KV **bytes** in HBM, (2) **bandwidth cost** per token (decode ceiling
∝ 1/bytes), (3) **MMA peak** (lower-precision formats have higher FLOP/s), (4) **model
quality** (quantization error). The two performance routes are *independent*:
- **Route 1 — bandwidth:** fewer bytes/weight → decode streams more tokens/s (works at
  B=1 where FLOPS don't matter).
- **Route 2 — compute:** lower-precision MMA → higher prefill/throughput FLOP/s (works
  at large M where bytes don't matter).

### Why
Tensor Cores are designed with more datapath width per half-FLOP as precision drops
(2× MACs at 8-bit, 4× at 4-bit — see table), while HBM capacity/bytes scale linearly
with bit-width. So every bit you remove buys bytes **and** FLOPs — but only if the
kernel actually executes the lower-precision MMA.

### How
Pick the format per tensor, then verify the kernel path:
- **W4A16 / W8A16 (weight-only):** weights packed in HBM/SMEM, **dequantized in
  registers to 16-bit**, then a 16-bit MMA. Route 1 only: bytes ↓, compute unchanged
  (activations are 16-bit; the MMA is still BF16/FP16). This is the GPTQ/AWQ classic
  (`../Quantization/README.md`).
- **W8A8 (FP8 E4M3, Hopper+):** both operands 8-bit → the GEMM issues `m16n8k32` FP8
  MMAs: Route 1 + Route 2 both. Needs per-tensor/per-block scales (calibration or
  runtime).
- **W4A4 (NVFP4, Blackwell):** 4-bit weights *and* 4-bit activations, block-scaled →
  `mma` FP4 path: ~4× the BF16-class peak **and** ~3.5× fewer weight bytes
  (`../Quantization/README.md`).
- **KV quant (FP8/INT8):** halves KV bytes — a decode lever independent of the GEMM
  dtype (`../KV-Cache/README.md`).

### When
- **B=1 latency:** weight-only W4/W8 (bandwidth route). Tensor Cores barely engage.
- **High-throughput serving / prefill-heavy:** W8A8 or W4A4 (both routes compound).
- **Quality-critical:** stay BF16 or FP8 (near-lossless); INT4/FP4 weight-only is where
  quality risk concentrates (`../Quantization/README.md`).

### Hardware impact
Both roofs move: memory roof = BW/bytes (up as bytes fall); compute roof = MMA peak
(up as precision drops); the ridge P/BW moves too (H100: 295 → 591 FLOP/byte in FP8
[E]) — so the knee batch B* stays ~fixed while the *rate on each side* rises
(`Bandwidth-vs-Compute.md` E3, dtype invariance of B* ≈ 295).

### Inference impact
- **TTFT:** FP8 prefill ≈ 2× BF16 on H100 at equal MFU [I: roofline + table].
- **ITL:** scales with bytes only at small B; quantizing the *compute* path doesn't
  speed up B=1 decode (it's HBM-bound, `../Inference/Roofline.md`).
- **Capacity:** bytes/param → VRAM headroom → more concurrent KV
  (`../KV-Cache/README.md`).

### Example
[Worked example below](#worked-example-e-fp8-doubles-peak-and-halves-bytes) —
H100, 27B model, BF16 vs FP8 ceilings.

### Failure modes
- **Assuming speedup ∝ bit reduction:** W4A16 on a compute-bound prefill gives ~0
  compute benefit (MMA still 16-bit); the "4-bit is 4× faster" claim only applies to
  the 4-bit *MMA* path on FP4-capable HW [I].
- **Two-route double counting:** if you halve bytes *and* double peak, the compound
  gain appears **only** where both roofs matter (batched decode past B*, big prefill);
  at B=1 the FLOP doubling is irrelevant [I].
- **Quality compounding:** W4 + FP8-KV + FP4-activations simultaneously is where errors
  stack; benchmark the end task, not a perplexity toy [I: `../Quantization/README.md`].
- **Kernel regression:** a quantized stack whose GEMM picks a dequant-heavy custom
  kernel can lose to a plain cuBLAS BF16 GEMM at large M — measure, don't assume
  (`Custom-GEMM.md`).

### How to measure it
- **Decode:** tok/s at B=1 before/after (should track bytes ratio, `Bandwidth-vs-Compute.md`).
- **Prefill:** TTFT or prefill FLOP/s at equal MFU (should track peak ratio of the
  *actually-issued* MMA dtype).
- **Kernel path:** Nsight Compute `sm__inst_executed_pipe_tensor` + achieved FLOP/s
  vs the correct dtype peak [F: Nsight Compute docs]; engine logs for the GEMM kernel
  name (`vLLM.md`, `TensorRT-LLM.md`).
- **Quality:** task-level regression, not just perplexity [I].

## NVFP4 / FP4: the ~4.5-bit datacenter default
- **NVFP4** = FP4 e2m1 payload (4 bits: 1 sign, 2 exp, 1 mantissa — 6 distinct values,
  0, ±0.5, ±1, ±2, ±4, ±6) with a **per-block FP8 (E4M3) scale every 16 elements**
  [F: NVIDIA docs]. Effective cost per param: 4 + 8/16 = **4.5 bits** [E: 4 + 0.5] —
  the "4.5" used in `../Inference/Roofline.md` (27B → 27e9 × 4.5/8 = 14.1 GiB [E]).
- Activations can be NVFP4 too (W4A4) on Blackwell → the FP4 MMA path: ~9 PF dense
  [F: vendor spec], the 4× BF16-class peak in the table above.
- **Why the 2025–26 default:** it compounds *both* routes (~3.5× fewer weight bytes
  **and** ~4× MMA peak), keeps quality near-lossless with runtime block scales (minimal
  calibration, `../Quantization/README.md`), and B200/GB200 NVL72 serve at this
  precision by default in major engines (SGLang FP4, TensorRT-LLM NVFP4, vLLM FP4
  kernels) [F: vendor/engine docs].
- The block-scale overhead is why it's "~4.5" not "4": at 16-element blocks the scale
  costs 8/16 = 0.5 bits/param; larger blocks would amortize the scale but lose
  per-block range headroom [I].

## Worked example [E] — FP8 doubles peak AND halves bytes (H100, 27B)
Reference point (Python-verified in `../Inference/Roofline.md` and
`Bandwidth-vs-Compute.md` — numbers referenced, not re-derived): 27B BF16 model,
H100 SXM (3.35 TB/s HBM3 [F: vendor spec]), 8192 ctx, GQA h_kv=8 → per-token decode
traffic = 5.4e10 B weights + 1.07e9 B KV = **5.507e10 B** → **60.8 tok/s** ceiling
[there: 3.35e12 ÷ 5.507e10].

**Route 1 — bytes (decode, W8A8 weights, KV stays BF16):**
- FP8 weights: 27e9 × 1 B = **2.7e10 B**; total per token = 2.7e10 + 1.07e9 =
  **2.807e10 B**.
- Ceiling: `3.35e12 ÷ 2.807e10 ≈ 119 tok/s` [E] → **1.96×** [E: 119/60.8].
- Near the full 2× weight-halving because weights are 98% of the traffic
  [E: 5.4e10/5.507e10 = 0.981]. (NVFP4: 1.519e10 B → 1.626e10 total → 206 tok/s
  [E] — quoted in `Bandwidth-vs-Compute.md`.)

**Route 2 — peak (prefill, same model, S = 8192):**
- Prefill FLOP ≈ 2·27e9·8192 = **4.42e14** [E, `The-Life-of-a-Token.md`].
- BF16 peak 989 TFLOP; FP8 peak 1,979 TFLOP [F: vendor spec] → at equal 60% MFU [A]:
  `4.42e14 ÷ (0.6·989e12) ≈ 0.75 s` vs `4.42e14 ÷ (0.6·1979e12) ≈ 0.37 s` [E] →
  exactly **2×** [E: 1979/989 = 1.99].
- The compute ridge moves 295 → 591 FLOP/byte [E: 1979e12/3.35e12], so the knee batch
  B* stays ≈ 295 (`Bandwidth-vs-Compute.md` E3) — quantization lifts the *rate*, not
  the *knee*.

**Why it is not "4-bit → 4× everywhere":** at B=1 the decode ceiling is BW÷bytes, so
the FLOP doubling is worth ~0%; a W4A16 weight-only kernel dequantizes to 16-bit and
issues 16-bit MMAs, so it gets Route 1 only; W4A4 on B200 gets both (bytes ÷ ~3.5 and
peak × 4) — and even then the *observed* gain per bit is set by which roof your
workload sits under, not by the bit-width ratio alone [I].

## Related
- [`GEMM`](./GEMM.md) — the optimization ladder this page continues (step 6: swap FMA
  for MMA).
- [`Bandwidth-vs-Compute`](./Bandwidth-vs-Compute.md) — roofline, ridge, B*; the 27B
  ceilings referenced above.
- [`Custom-GEMM`](./Custom-GEMM.md) — where engines pick quantized/skinny GEMM
  kernels; kernel-path risk.
- [`FlashAttention`](./FlashAttention.md) — attention's S×S GEMMs on Tensor Cores;
  FA3 wgmma/TMA on Hopper.
- [Quantization](../Quantization/README.md) — W4A16/W8A8/W4A4, GPTQ/AWQ, NVFP4 formats
  and quality.
- [Roofline](../Inference/Roofline.md) — the one-page roofline; the 4.5-bit NVFP4
  convention.
- [`Memory-Hierarchy`](./Memory-Hierarchy.md), [`Memory-Optimizations`](./Memory-Optimizations.md)
  — the HBM→SMEM→regs pipeline.
- [`Profiling`](./Profiling.md), [`GPU-Metrics`](./GPU-Metrics.md) — Tensor Core
  utilization metrics.

## Key Takeaways
1. **One warp instruction, a whole tile:** MMA does `D[m,n] += A[m,k]·B[k,n]` on
   e.g. 16×8×16 (4,096 FLOP/issue) vs 64 FLOP/issue for a scalar warp [E].
2. **Data path: registers → Tensor Core → registers** — MMA operands never touch
   memory directly; the tiling pipeline exists to feed it.
3. **Two independent quantization routes:** bytes (bandwidth, decode) + MMA peak
   (compute, prefill); W4A16 engages only the first, W8A8/W4A4 engage both.
4. **Speedup ≠ bit-width ratio:** it's set by which roof your workload sits under;
   at B=1 the FLOP doubling is worth ~0%.
5. **NVFP4 ≈ 4.5 bits/param** (4-bit payload + FP8 block scale ÷16) is the 2025–26
   datacenter default because it compounds both routes on ~4×-peak FP4 MMAs.
