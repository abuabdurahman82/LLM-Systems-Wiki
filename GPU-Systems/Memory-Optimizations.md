# GPU Memory Optimization Techniques — PART VI
`LAST_UPDATED: 2026-08-21 · Status: core page` · Companion to `Memory-Hierarchy.md`
(that page: capacity/latency/bandwidth *per level*; this page: the *techniques* that shrink
how many levels each byte crosses). [E] arithmetic hand-derived; constants per
`../Hardware/README.md` + NVIDIA public specs.

## 30-Second Explanation
`Memory-Hierarchy.md` says where data lives and how slow each level is; this page is the toolbox
for **moving each byte as few levels down as possible, and never stranding a warp at the
bottom**. One logic, two families:
- **Fewer levels per byte:** coalescing (a warp's 32 lanes touch contiguous addresses → 1 HBM
  transaction, up to 32 if scattered), tiling (pull a chunk into shared memory, reuse it),
  shared-memory bank-conflict avoidance, register blocking, layout transformations, fusing away
  intermediate tensors (`Fused-Kernels.md`).
- **Hide the remaining latency:** double buffering, async copies (`cp.async`, HBM→shared
  bypassing registers), multi-stage pipelining — and on Hopper/Blackwell, **TMA** bulk
  transfers plus **warp-specialized** producer/consumer kernels
  (FlashAttention-3 [F: arXiv:2407.08608]).
The recurring LLM example: the **tiled GEMM that is simultaneously the QKV/MLP kernel**
(`GEMM.md`) — coalesce the loads, tile into shared, block in registers, feed with a cp.async
pipeline — and **softmax/reduction over S scores**, which is coalesced HBM loads + a
shared-memory tree reduce, no S×S materialization (the FlashAttention move
[F: arXiv:2205.14135], `FlashAttention.md`).

## Page scope + the two recurring examples
- `Memory-Hierarchy.md`: level sizes/latencies/bandwidths, cache lines, good/bad patterns.
- `Architecture.md` Concept 4 (occupancy & latency hiding) is the *why* underneath: these
  techniques raise achieved bandwidth and the ILP/TLP available to hide what remains.
- **Tiled GEMM = QKV/MLP kernel**: prefill QKV `X[S,d]·Wqkv[d,h·d_h]`, MLP `X[S,d]·W1[d,d_ff]`
  (`GEMM.md`); one tuned tiled-GEMM kernel serves all of them, S = the M dimension.
- **Softmax/reduction**: load the Q·Kᵀ row coalesced, tree-reduce in shared memory
  (`CUDA-From-Zero.md` reduction/softmax examples).

## Concept 1 — Memory coalescing (full template)
### What
A warp's 32 lanes execute one load instruction together. **Coalesced** = the 32 addresses are
contiguous → the memory unit fetches **one** HBM transaction per warp load; **uncoalesced** =
lanes scattered → the hardware splits the load into up to **32 separate transactions**
[F: CUDA programming guide]. (128 B line/sector simplification [A].)

```
Warp load of 32 × 4 B floats (128 B useful, one instruction)

COALESCED    lane t → base + 4t
 lane:  0     1     2     3   ...  31
 addr:  [A0..A3][A4..A7]...[A124..A127]
        └──────────── 1 × 128 B line ────────────┘   → 1 transaction
UNCOALESCED  lane t → base + 128t
 lane:  0            1            2         ...     31
 addr:  [L0..L31][L32..L63][L64..L95] ... [L3968..L4095]
        └─128B─┘     └─128B─┘     └─128B─┘          → 32 transactions,
                                                   only 128 B of 4096 B used
```
### Why
Each extra transaction is extra HBM round-trips *and* extra fetched bytes (whole lines/sectors
are fetched even when a lane used a few bytes of one). In the decode regime — the
bandwidth-bound one (`Bandwidth-vs-Compute.md`) — coalescing efficiency is nearly the whole
achievable bandwidth.
### How
Map `threadIdx` onto the **fastest-varying (contiguous) dimension**: for row-major A, thread t
loads `A[row][t]`, not `A[t][row]`; warp 0 of a block covers row elements 0–31. For
reductions/softmax: one warp per contiguous chunk of S, lanes 0,1,2,… inside the chunk
(`CUDA-From-Zero.md`).
### When
Always — first step of every memory-bound kernel (decode GEMVs, KV reads, norms, copies); even
compute-bound prefill GEMMs need it to feed the pipeline.
### Hardware impact
Transactions are the HBM controller's currency: coalesced warp load = 1, worst case = 32;
strided access fetches whole lines of which only a fraction is used — waste ratio =
stride/useful-bytes.
### Inference impact
Decode GEMV (d = 4096, BF16): a weight row = 4096×2 B = 8192 B streamed coalesced ≈ 8192 B
fetched. A scattered layout (each lane in its own 128 B line) → that op's HBM traffic and
exposed latency inflate up to 32× → directly into ITL.
### Example [E]
32 lanes loading 32 contiguous BF16 elements (64 B useful):
- **Coalesced**: lanes hit `base+0 … base+63`, inside one 128 B line → **1 transaction**, 100%
  of fetched bytes used.
- **Worst case**: lane t hits `base + 128·t` → 32 distinct lines → **32 transactions**, 32×128 B
  = 4096 B fetched for 64 B useful → **32× traffic and 32× exposed latency** on that
  instruction.
- **Full-row arithmetic** (4096-element BF16 row = 8192 B = 64 lines): coalesced fetch =
  8192 B (100% efficient); scattered = 32×8192 B = 256 KB for the same 8 KB of data →
  **32×** [E: 256 KB / 8 KB].
### Failure modes
- Strided/interleaved layouts (AoS, bad dequant layouts) — see the compact set below.
- Vectorized loads on misaligned pointers — compiler silently falls back to scalar loads.
- Divergent `if` changing per-lane addresses inside one load.
### How to measure it
Nsight Compute: sector-per-request counters (sectors vs useful bytes), achieved DRAM
throughput vs the 3.35 TB/s roof; coalesced ≈ minimum sectors, uncoalesced up to 32× [A].

## Concept 2 — Tiling (full template)
### What
Instead of re-reading A rows and B columns from HBM per output element, load a **[BM × BK]**
tile of A and **[BK × BN]** tile of B into shared memory *once*, compute a [BM × BN] tile of C
from them, then stream the next K-tiles. Step 3 of `GEMM.md`'s progressive optimization.
### Why
Naive GEMM reads each A element N times and each B element M times from HBM. Tiling amortizes
every HBM byte by the tile dimension: a loaded A element is **re-used BN times**, a B element
**BM times**, before the next fetch.
### How
Block = one C-tile: (a) cooperatively copy [BM×BK] + [BK×BN] into shared (coalesced warp
loads, Concept 1), (b) `__syncthreads()`, (c) each thread computes its [BR×BC] micro-tile in
registers (register blocking, compact set) over the K-tiles, (d) sync, next K-tile. This is the
prefill QKV/MLP kernel; decode is the M=B limit of the same kernel.
### When
Whenever M or N exceeds the tile: every prefill GEMM, big-batch decode. Not useful at M=1 GEMV
— nothing to amortize along M; decode wins on raw bandwidth instead (`GEMM.md`).
### Hardware impact
Shared memory (per-SM SRAM; up to 228 KB opt-in per block on sm_90 [F: CUDA programming
guide]) is the staging area: (BM·BK + BK·BN)·b × S pipeline stages must fit, and bigger
shared/block cuts blocks-per-SM → occupancy (caps in `Architecture.md` Concept 4).
### Inference impact
The tiled GEMM *is* the QKV/MLP kernel: its HBM traffic sets TTFT in prefill; at M=B (decode)
it streams weights — bandwidth-bound, tiling mostly irrelevant.
### Example [E]
d×d GEMM, M = N = K = 4096, BF16 (b = 2), square tile T = BM = BN = 64:
- Naive bytes = 2·M·N·K·b = 2·4096³·2 B ≈ **275 GB** [E].
- Tiled: each A row fetched N/BN = 4096/64 = **64 times**, each B column M/BM = **64 times** →
  bytes ≈ (M·K·N/BN + M·N·K/BM)·b = 2·4096·4096·64·2 B ≈ **4.3 GB** [E].
- Ratio = 275 / 4.3 ≈ **64× less HBM traffic**, equal to the tile side T [E:
  2·4096³·2 / (2·4096·4096·64·2) = 64]. General formula: net drop = 2·BM·BN/(BM+BN) = T for
  square tiles (the "d/BM × d/BN" re-fetch counts per operand compose to this).
### Failure modes
- Tile doesn't fit shared memory → smaller tile → more re-fetches.
- Prefill-sized tile (64×64) used at M=1 → BM waste; engines pad M to a small multiple
  instead (`Custom-GEMM.md`).
- Bank conflicts in the tile loop (below) quietly erase the win.
### How to measure it
Nsight Compute `dram__bytes` per kernel vs the Concept formula; shared-load behavior in the
L1/TEX section.

## The rest — compact set (What / Why / How / LLM use)
### Shared-memory reuse & bank conflicts
- **What**: shared memory has 32 banks (4 B wide); 32 lanes in 32 distinct banks serve in one
  cycle; two lanes in one bank serialize (32-way conflict → 32 cycles) [F: CUDA programming
  guide].
- **Why**: tiling's payoff only exists if shared memory actually beats HBM; a conflicted tile
  loop can be slower per cycle than the HBM it replaced.
- **How**: bank of `smem[r][c]` = `(c + r·(C mod 32)) mod 32`. C a multiple of 32 + reading down
  a column → one bank. Fix: pad rows to C+1, or **swizzle** `c' = c ^ f(r)` (CUTLASS-style,
  zero waste) [F: github.com/NVIDIA/cutlass].
- **[E]**: C = 32 words, warp reads column 0: unpadded → bank 0 for all 32 lanes → **32-way
  conflict, 32 cycles**; padded C' = 33 → bank = r mod 32 → **1 cycle** = **32× faster**, +3%
  shared overhead (or 0 with swizzle).
- **LLM use**: GEMM/attention tile loops read operands in two orientations; FlashAttention's
  K/V tiling uses swizzled layouts to keep the MMA feed conflict-free [F: arXiv:2205.14135].
  Measure: `l1tex__data_bank_conflicts_pipe_shared_*` in Nsight Compute.
### Register blocking
- **What**: each thread owns a **[BR × BC] micro-tile of C in registers**; the K-loop hoists
  shared operands into a few registers and issues BR×BC FMAs per load — the inner loop touches
  neither HBM nor shared memory per FMA.
- **Why**: registers are the only zero-operand-latency level, and one shared load now feeds
  BR×BC FMAs instead of 1.
- **How**: BR×BC = 4×4 or 8×8 BF16/FP16 accumulators (a 32-bit register holds 2 BF16) +
  operand + loop regs; above that, the warp feeds a Tensor Core MMA tile (`Tensor-Cores.md`).
- **Register pressure vs occupancy**: R regs/thread → 65,536/(32·R) warps per SM (cap 64) [E,
  `Architecture.md`]: **32 → 64 warps (100%)**, **64 → 32 warps (50%)** [E]. Raise BR×BC until
  `ptxas -v` shows spills or the occupancy drop outweighs the reuse gain [I].
- **Failure mode**: register spills → local-memory (HBM!) traffic — "high occupancy, collapsing
  bandwidth".
- **LLM use**: prefill GEMM (compute roof) + FlashAttention score/accumulators; decode is
  bandwidth-bound, so a high-register kernel costs little there. ~4×4 BF16 micro-tile ≈ 16
  accumulators + ~8 operand + ~8 loop ≈ 32–40 regs/thread [A].
### Vectorization / vectorized loads
- **What**: move **128 bits per instruction** (`float4`, 8×BF16) instead of 32: one warp's load
  moves 32×16 B = 512 B per instruction vs 128 B for scalar.
- **Why**: fewer load instructions (issue pressure) + full-width memory-pipe use; pairs with
  coalescing — lanes already share lines, now each lane takes 4 contiguous elements.
- **How**: per-lane addresses must be **16 B aligned** (`base % 16 == 0`, element-size ×
  lane-stride multiple of 16 B). Framework allocations are typically 256 B aligned [A] and LLM
  dims (4096, 11008) are divisible by 8 [E] → BF16 rows land 16 B aligned for free.
- **[E]**: one warp loading 512 B: scalar = 4 warp-wide instructions; vectorized = **1
  instruction, same bytes**; misaligned (base+8 B) → each 128-bit load splits → 2 instructions,
  2× issue cost on the load path [A].
- **Failure mode**: stride breaking per-lane alignment; odd tensor offsets (batch/KV chunk
  boundaries).
- **LLM use**: #1 user is the decode GEMV weight stream — coalesced + vectorized streaming of
  `W[4096,4096]` BF16 per token is what separates ~full 3.35 TB/s from a measurably worse ITL.
### Cache reuse & data-layout transformations
- **What**: the layout of tensors themselves — row- vs column-major 2D storage, AoS vs SoA;
  rule: *thread access order* must match *physical storage order*.
- **Why**: coalescing and L2 caching operate on physical order; stride ≥ cache-line size gives
  one sector per line → L2 hit rate collapses even for reused data.
- **How**: GEMM with A and B both row-major → B read column-strided; engines pre-transpose
  weights or transpose inside the shared tile (CUTLASS handles both [F: github.com/NVIDIA/
  cutlass]). LLM: KV cache `[B, h_kv, S, d_h]` — attention reads contiguously along d_h
  (coalesced); PagedAttention keeps each 16-token chunk contiguous inside a page
  [F: arXiv:2309.06180]. AoS→SoA: split `{x,y,z,w}` records into separate arrays.
- **[E]**: 32 records × 4 float fields (16 B/record), one warp reads all `.x`: AoS stride 16 B
  → 512 B fetched, 128 B useful → **4× waste**; SoA contiguous → 128 B → **4× less traffic**
  [E: 512/128].
- **LLM use**: KV layout decides attention's HBM efficiency for the whole serving lifetime;
  weight repacking (channel-last, FP8/FP4 alignment) is the load-time setup step of every
  serious engine. Watch: +1 bank-conflict padding can break 16 B row alignment — swizzle
  instead.
### Minimizing intermediate tensors (the fusion payoff)
- **What**: every intermediate tensor written by kernel i and read by kernel i+1 is a full HBM
  round-trip: 2 × S × d × b bytes. **Fusion** (`Fused-Kernels.md`) keeps it in
  registers/shared → the round-trip goes to zero.
- **Why**: elementwise/activation ops at decode are pure HBM traffic; at prefill the FLOPs are
  cheap but materialization is still real bytes, and each extra launch adds overhead
  (`Kernel-Life.md`).
- **How**: SwiGLU in one kernel (reads x, writes `silu(x)·g`); RMSNorm in one pass — load row,
  mean-of-squares in registers/shared, normalize [F: arXiv:1910.07467]; QKV as one GEMM with
  out-dim `h·d_h + 2·h_kv·d_h`; attention itself — FlashAttention *is* fusion, no S×S ever
  reaches HBM [F: arXiv:2205.14135].
- **[E]**: MLP intermediate [S, d_ff], S = 4096, d_ff = 11008, BF16: one round-trip =
  2·4096·11008·2 B ≈ **180 MB** [E] → ≈ **54 µs/layer** at 3.35 TB/s [E] → 32 layers ≈
  **1.7 ms** of pure memory traffic that fusion removes from TTFT.
- **Cost side**: register pressure (register blocking above) and one long kernel instead of
  several — the trade documented in `Fused-Kernels.md`.

## Concept 3 — Double buffering, async copies, pipelining (full template)
### What
- **Double buffering**: two shared tiles; while the block computes tile k from buffer 0,
  tile k+1 is already loading into buffer 1.
- **Async copy (`cp.async`, Ampere+)**: an HBM→shared copy that **bypasses the register file**
  — the data path is memory system → L2 → SMEM, no `ld` + `st.shared` round trip — issued per
  thread with commit groups, waited on with `cp.async.wait_group` [F: CUDA programming guide,
  Ampere whitepaper].
- **Pipelining**: S stages of cp.async in flight; the K-loop becomes "issue stage k+S−1 while
  computing stage k".
### Why
HBM latency L (~500 cycles [A]) can exceed a tile's compute time P; serial load-then-compute
leaves the SM idle L cycles *per tile*. The pipeline hides L under P, and cp.async also frees
register/staging work → more resident warps → more TLP (`Architecture.md` Concept 4).
### How
- 2 stages: load t0 → wait → during compute(t0) issue cp.async t1 → wait_group → swap buffers.
- S stages: round-robin over S buffers; commit groups (mbarriers on Hopper+) order completion.
- Shared-memory cost = S × tile bytes: a 64×64 BF16 tile = 64·64·2 B = **8 KB**; two operands
  × S = 4 stages = 64 KB/SM — feasible against the sm_90 228 KB opt-in
  [F: CUDA programming guide].
```
Single buffer (serial)                 Double buffer + cp.async (L hidden)
 SMEM: ┃load t0┃comp t0┃load t1┃comp t1┃ SMEM buf0: ┃load t0┃comp t0┃      ┃comp t2┃
 HBM:  [load t0]     [load t1]           SMEM buf1:     ┃load t1┃comp t1┃
        L|──P──|  L|──P──| ...              ┃load t2┃comp t2 ...
 HBM:   [load t0][load t1][load t2][load t3]
        L |──── P ────|──── P ────|   steady state: L ≤ P → fully hidden
```
### When
Any K-loop with L ≥ P: prefill QKV/MLP, FlashAttention's QK/AV loops. Decode GEMV: one-shot
stream, no K-loop to pipeline — double buffering doesn't apply; bandwidth is the only roof.
### Hardware impact
cp.async keeps loads off the register path (less register pressure, fewer instructions per
tile); the async-group/mbarrier mechanism tracks outstanding copies; shared memory grows with
S and competes with occupancy.
### Inference impact
The load path of every cuBLAS/CUTLASS prefill GEMM → TTFT. Without it, Hopper-class prefill
GEMMs would stall Tensor Cores on every K-tile.
### Example [E] — hiding L HBM cycles
K-loop over S_tiles = 64 tiles (4096/64), P = 512 SM cycles compute per tile, L = 512 cycles
HBM latency [A values, arithmetic shown]:
- **Single buffer**: 64 × (L + P) = 64 × 1024 = **65,536 cycles**; exposed load latency
  64 × 512 = 32,768 cycles.
- **Double buffer**: first load exposed once; load(k+1) overlaps compute(k) → total =
  L + 64 × P = 512 + 32,768 = **33,280 cycles** → **2.0× faster** [E: 65,536/33,280];
  **63 × 512 = 32,256 HBM latency cycles hidden** [E].
- **S-stage pipeline**: with L ≈ P, 2 stages hide all of L; extra stages matter when L ≫ P or
  to cover sync overhead. Bandwidth view: saturating 3.35 TB/s at L ≈ 500 ns needs
  1.67 MB in flight** [E, derived in `Architecture.md`]; S = 4 stages ×
  16 KB/stage = 64 KB/SM × 132 SMs = 8.65 MB device-wide ≥ 1.67 MB → bandwidth-saturated [E].
### Failure modes
- S too big → shared memory exceeds the SM budget → occupancy collapse (fewer blocks/SM).
- Missing `cp.async.wait_group` / mbarrier phase → race → silent data corruption.
- Double-buffering an M=1 GEMV: nothing to overlap with → complexity, no gain.
### How to measure it
Nsight Compute: `smsp__warp_issue_stalled_long_scoreboard` share should drop with the
pipeline; SMEM per block; achieved DRAM throughput vs the 3.35 TB/s roof.

## Modern concepts — Hopper/Blackwell
### TMA (Tensor Memory Accelerator)
- **What**: a Hopper/Blackwell hardware unit that moves **bulk HBM↔shared tiles** (2D/3D with
  strides) with no per-thread address math: one thread issues a copy descriptor (base, shape,
  strides, tile) tied to an **mbarrier**; TMA performs the DMA and completion arrives at the
  mbarrier — not in a register [F: CUDA programming guide, H100 whitepaper].
- **Why**: cp.async still costs one issue + address math per thread; TMA removes both, frees
  the SM's issue pressure, and lands tiles at exactly the MMA operand size.
- **How/When**: producer warp issues TMA copy + mbarrier; consumer warps phase-wait, then MMA.
  The load path of FlashAttention-3 [F: arXiv:2407.08608] and CUTLASS Hopper kernels
  [F: github.com/NVIDIA/cutlass]; use on Hopper/Blackwell prefill, cp.async pipeline is the
  Ampere fallback. Inference: TTFT at Hopper-class shapes; enables the structure below.
### Warp-specialized kernels
- **What**: split one block into **producer warps** (issue TMA/cp.async, maintain the pipeline)
  and **consumer warps** (MMA + softmax), synchronized with **mbarrier** arrive/phase waits —
  with TMA the producer `arrive.expect_tx`-announces the byte count so the barrier fires on
  actual data arrival [F: CUDA programming guide].
- **Why**: in a classic kernel every warp both loads and computes, so every warp stalls on its
  own loads; specialization lets each pipeline run continuously, and consumer warps need no
  load registers → more FLOPs per resident register.
- **How/When**: e.g. 2 producer + 4 consumer warps; FlashAttention-3 pairs this with
  warp-group MMA and "ping-pong" scheduling across two CTAs [F: arXiv:2407.08608].
  Hopper/Blackwell compute-bound prefill + long-context attention; decode kernels are usually
  too thin for the overhead [A]. Failure mode: wrong phase counts → mbarrier deadlock.
### How kernel optimization changes across GPU generations
| Generation | Kernel/memory tech added | Precision added | What it unlocked |
|---|---|---|---|
| Volta | FP16 Tensor Core MMA, WMMA | FP16 TC | first mixed-precision GEMMs |
| Turing | INT8/INT4 Tensor Cores | INT8/INT4 | low-bit quantized GEMMs |
| Ampere | **cp.async** (HBM→SMEM, bypasses registers) [F: Ampere whitepaper] | **TF32, BF16** | register-free pipelining (Concept 3) |
| Hopper | **TMA**, mbarrier, **warp-group MMA (wgmma)**, warp specialization [F: H100 whitepaper] | **FP8 (E4M3/E5M2)** | producer/consumer structure; FP8 halves GEMM bytes |
| Blackwell | 5th-gen Tensor Cores, TMA carried forward, 2-CTA MMA | **FP4 (NVFP4)**, FP8 | FP4 ~4× BF16-class FLOPs (B200: ~9 PF FP4 dense [F: vendor spec, dense=½ sparse]) — both roofs lift |
Rule of thumb [I]: on a new arch, re-check **pipeline depth S** (TMA changes what S is for),
**the dtype** (each precision tier re-sets both roofs — `Tensor-Cores.md`,
`../Quantization/README.md`), and **which warps do what** (specialization only pays at
sufficient compute density).

## How to measure these techniques (cross-cutting)
- **Coalescing/layout**: sector-per-request counters, fetched-vs-useful bytes.
- **Tiling**: `dram__bytes` vs the Concept 2 hand formula.
- **Bank conflicts**: `l1tex__data_bank_conflicts_pipe_shared_*`.
- **Pipeline**: `long_scoreboard` stall share before/after; DRAM throughput vs 3.35 TB/s.
- **Register blocking**: `ptxas -v` spills + `sm__warps_active`.
Protocol: `Perf-Experiment-Template.md`; metric→TTFT/ITL mapping: `GPU-Metrics.md`,
`Profiling.md`.

## Key Takeaways
1. Every technique here is one of two moves: **fewer levels per byte** (coalesce, tile,
   register-block, layout, fusion) or **hide the remaining latency** (double buffer, cp.async,
   pipeline, TMA, warp specialization).
2. The recurring LLM test cases: the tiled GEMM that is the QKV/MLP kernel (the classic
   techniques stack on it); softmax/reduction = coalesced loads + shared-memory tree.
3. Hopper/Blackwell rewired the load path (TMA + mbarrier + warp specialization) and each
   generation added a precision tier (TF32/BF16 → FP8 → FP4) that re-sets both roofs
   (`Tensor-Cores.md`).
4. Measure against the hand formulas: dram bytes vs ideal, sector efficiency, bank-conflict
   counters, `long_scoreboard`, occupancy — then map to TTFT/ITL (`GPU-Metrics.md`).

## Related
`Memory-Hierarchy.md` (level specs) · `Architecture.md` (occupancy & latency hiding) ·
`GEMM.md` (the operation these techniques optimize) · `Tensor-Cores.md` (MMA, FP8/FP4) ·
`Fused-Kernels.md` (intermediate-tensor payoff) · `FlashAttention.md` (tiled GEMM + online
softmax applied to attention) · `CUDA-From-Zero.md` (kernel syntax for each technique) ·
`Custom-GEMM.md` · `Bandwidth-vs-Compute.md` · `Kernel-Life.md` · `Profiling.md` ·
`GPU-Metrics.md`

## References
NVIDIA CUDA C++ Programming Guide (warp coalescing, 32-bank SMEM + conflicts, cp.async,
mbarrier, TMA, sm_90 shared-memory opt-in) [F] · NVIDIA Ampere/H100/Blackwell whitepapers
(cp.async, TMA, wgmma, FP8/FP4 rates) [F: vendor spec] · Dao et al., FlashAttention
[arXiv:2205.14135] · FlashAttention-3 [arXiv:2407.08608] · Kwon et al., PagedAttention/vLLM
[arXiv:2309.06180] · RMSNorm [arXiv:1910.07467] · CUTLASS (github.com/NVIDIA/cutlass) ·
`../Hardware/README.md` (constants cross-check).
