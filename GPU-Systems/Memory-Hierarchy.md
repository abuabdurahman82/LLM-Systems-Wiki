# GPU Memory Hierarchy for LLM Inference — PART IV
`LAST_UPDATED: 2026-08-21 · Status: core page` · Per-level reference: capacity / latency /
bandwidth / scope / control **per level**. Companion `Memory-Optimizations.md` owns the
*techniques* (coalescing, tiling, pipelining). Hardware constants cross-checked against
`../Hardware/README.md` and NVIDIA public specs; per-SM register/SMEM/L2 sizes are
[A: typical] unless a specific arch spec is cited; all [E] numbers hand-derived below.

## 30-Second Explanation
A GPU moves data through a stack of levels, each **larger and slower** than the one above:
`registers → shared/L1 → L2 → HBM → NVLink/PCIe → CPU RAM → NVMe`. The only fast,
per-thread store is the **register file** (a GEMM micro-tile lives there); the big, cheap
store is **HBM** (weights + KV + activations — the decode roof). Every read travels the
shortest possible path: coalesced warp loads land in one 128 B transaction, tiles stage in
shared memory, hot data rides in L2, and the rest streams from HBM at 3.35 TB/s (H100) or
~8 TB/s (B200). Two numbers set the whole game: **how many bytes cross HBM per token**
(decode: all weights + all KV) and **how many of them you avoid moving** (fusion, tiling,
KV reuse). The 20% that carries the 80%: *registers hold the tile, shared/L1 holds the
block, L2 holds the hot set, HBM is the roof; everything else is offload* —
[`Roofline`](../Inference/Roofline.md), [`GEMM`](./GEMM.md).

## The Hierarchy — one diagram, fast/small to slow/large
```
                 GPU MEMORY HIERARCHY  (latency ↑ / bandwidth ↓ as you go down)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ REGISTERS            per-thread        256 KB/SM (65,536×32b)  [A: typical]  │
 │   ~0 cyc · ALU rate   explicit (compiler) · GEMM micro-tile, accumulators    │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ SHARED MEM / L1       per-SM          ~228 KB smem (sm_90 opt-in) [A:typical]│
 │   ~20–30 cyc [A] · ~30–60 TB/s agg [A] · explicit smem / cached L1           │
 │   GEMM tiles, attention Q/K/V tiles, reduction partials · 32 banks           │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ L2 CACHE              per-GPU (whole die)   ~50 MB [A: typical H100]         │
 │   ~200 cyc [A] · ~8 TB/s effective [A] · cached, shared across all SMs       │
 │   hot weights, re-read KV, prefix-reuse, L2 residency of weight stream       │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ HBM / GDDR            per-GPU · main memory · 80 GB HBM3 (H100), 141 GB H200 │
 │   ~400–600 cyc [A] · 3.35 TB/s H100 [F] · ~8 TB/s B200 [F]                   │
 │   ALL weights + ALL KV + activations · THE DECODE ROOF                       │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ NVLINK / PCIe         GPU↔GPU / GPU↔host                                    │
 │   µs class [A] · ~900 GB/s NVLink [F] · ~64 GB/s PCIe 5.0 [F]                │
 │   TP AllReduce (2/layer), P/D KV transfer, H2D/D2H, MoE AllToAll (in-node)   │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ CPU RAM (host)        per-node · DRAM                                         │
 │   ~100–200 ns [A] · ~50–100 GB/s [A] · pinned + page-locked                  │
 │   FlexGen-class KV offload, model weights at load, pre/post-process buffers  │
 ├──────────────────────────────────────────────────────────────────────────────┤
 │ NVMe / remote         per-node / cluster · slowest                           │
 │   ~50 µs–ms [A] · ~3–7 GB/s NVMe [A] · GPUDirect Storage / RDMA              │
 │   KV offload only when KV ≫ HBM · checkpoint/weight store · P/D far tier     │
 └──────────────────────────────────────────────────────────────────────────────┘
   gradient ──►  fast / small / per-thread        slow / large / per-cluster
```

## Per-level quick reference (the WHAT)
The 9-field deep-dives are on **registers** and **HBM** (the two that matter most). Every
other level still gets its numbers here — capacity / latency / bandwidth / scope / control /
LLM-use — so the table is self-sufficient for a fast lookup.

| Level | Capacity (typ.) | Latency [A] | Bandwidth | Scope | Control | Typical LLM use |
|---|---|---|---|---|---|---|
| Registers | 256 KB / 65,536 regs per SM [A: typical] | ~0 cyc | ALU issue rate | per-thread | explicit (compiler alloc) | GEMM micro-tile, attention accumulators, loop state |
| Shared / L1 | ~228 KB smem opt-in (sm_90) [A: typical] | ~20–30 cyc | ~30–60 TB/s agg [A] | per-SM | explicit smem / cached L1 | GEMM tiles, FlashAttention Q/K/V tiles, reduce partials |
| L2 | ~50 MB [A: typical H100] | ~200 cyc | ~8 TB/s eff. [A] | per-GPU, all SMs | cached (hardware) | hot weights, re-read KV, prefix reuse, weight stream |
| HBM / GDDR | 80 GB H100 / 141 GB H200 / ~8 TB/s B200 [F] | ~400–600 cyc | 3.35 TB/s H100 [F] | per-GPU | none (DRAM) | **weights + KV + activations; the decode roof** |
| NVLink / PCIe | n/a (fabric) | µs class | ~900 / ~64 GB/s [F] | GPU↔GPU / GPU↔host | explicit (NCCL, cudaMemcpy) | TP AllReduce, P/D KV transfer, MoE AllToAll |
| CPU RAM | tens–hundreds GB | ~100–200 ns | ~50–100 GB/s [A] | per-node | explicit (pinned, DMA) | FlexGen-class KV offload, weight load, buffers |
| NVMe / remote | TB–PB | ~50 µs–ms | ~3–7 GB/s [A] | per-node/cluster | explicit (storage, RDMA) | KV offload when KV ≫ HBM; checkpoint; P/D far tier |

## Concept 1 — Registers (full 9-field template)
### What
The register file is each thread's private store: N 32-bit registers per thread, allocated at
compile time. Per-SM it is a fixed pool — H100: **65,536 × 32-bit = 256 KB per SM**
[F: H100 spec; [A: typical] per-SM figure]. It is the **only** level with zero operand latency
and is the **only** per-thread store.
### Why
The GEMM inner loop is all FMAs: hoist A/B operands and the C accumulators into registers so
the inner loop touches neither shared nor HBM (`GEMM.md` step 4 "register blocking").
Registers are also the occupancy lever — a thread's register count caps how many threads fit
on an SM (`Architecture.md` Concept 4).
### How
The compiler assigns registers; the programmer steers via `__launch_bounds__`, unrolling, and
tile sizes. `R` regs/thread → `65,536/R` threads/SM = `65,536/(32·R)` warps (cap 64).
32 regs/thread → 64 warps (100%); 64 regs/thread → 32 warps (50%) [E, `Architecture.md`].
### When
Always for GEMM/attention compute; the register budget is the binding resource in most
prefill kernels. Decode is bandwidth-bound, so a high-register kernel costs little there.
### Hardware impact
Per-SM register file is a hard occupancy cap. A GEMM that needs more registers than the pool
has **spills** values to *local memory in HBM* — hidden HBM round-trips that collapse
effective bandwidth while the occupancy metric still looks healthy.
### Inference impact
Prefill TTFT: register pressure limits tile size → limits MMA throughput. Decode ITL:
matters less (bandwidth-bound). Spills: silent bandwidth collapse — a top failure mode.
### Example [E]
H100: 65,536 regs/SM. Occupancy per `R` regs/thread = `65,536/(32·R)` warps (cap 64):
- **128 regs/thread** → `65,536/(32·128)` = **16 warps = 25%** (a fat 8×8 BF16 micro-tile).
- **64 regs/thread** → `65,536/(32·64)` = **32 warps = 50%**.
- **32 regs/thread** → `65,536/(32·32)` = **64 warps = 100%**.
Halving regs/thread (128→64→32) **doubles** occupancy each step [E] — the core GEMM/attention
tuning knob (also in `Architecture.md` Concept 4).
### Failure modes
- **Register spilling:** kernel needs more regs than available → ptxas spills to local memory
  (HBM) → "high occupancy on paper, collapsing bandwidth in practice."
- **Over-occupancy chasing:** forcing low regs to raise warp count shrinks the tile → more
  shared/HBM traffic per FMA; past the knee it's net negative.
### How to measure it
`ptxas -v` (registers per thread, spill stores/loads); Nsight Compute `sm__warps_active`
(achieved occupancy) + `l1tex`/local-memory traffic to catch spills.

## Concept 2 — HBM / GDDR, the decode roof (full 9-field template)
### What
HBM (HBM3 on H100, HBM3e on H200/B200; GDDR on consumer) is the GPU's **main memory**:
**80 GB on H100 at 3.35 TB/s** [F: H100 spec], **~8 TB/s on B200** [F: vendor spec;
[A: ~2.4× HBM3: 8.0/3.35 = 2.39]]. All weights, all KV, all activations live here.
### Why
Decode streams the **entire weight matrix + all KV per token** from HBM — it never gets to
reuse a tile. HBM bandwidth is therefore the hard ceiling on tokens/s (`Roofline.md`):
this level *is* the decode roof.
### How
Nothing to "do" — it is DRAM. You manage it by (a) cutting bytes/token (quant, GQA/MLA,
KV reuse), (b) keeping latency hidden with enough warps in flight (`Architecture.md`
Concept 4), and (c) not stranding a warp at this level with uncoalesced access
(`Memory-Optimizations.md`).
### When
Every decode step (all weights + all KV); every prefill step that exceeds L2 (activations +
weight loads). It is the floor of the hierarchy and the roof of the model.
### Hardware impact
Bandwidth is device-wide, not per-SM — all 132 SMs contend for the same 3.35 TB/s, so
"more SMs" does not raise memory-bound throughput (`Bandwidth-vs-Compute.md`). HBM3e on
H200/B200 lifts the roof ~2.4× [E: 8.0/3.35] with the same model.
### Inference impact
`tokens/s ≈ BW / bytes-per-token`. A 27B model at 50.3 GiB BF16 = 54.0 GB →
`3.35 TB/s / 54.0 GB ≈ 62 tok/s` B=1 ceiling [E] (≈ the ~65 cited in `GEMM.md`).
Every KV/weight byte you save is speed; KV also *grows* with batch × context and eats HBM
(Example below).
### Example [E]
- **Decode roof (B=1):** 50.3 GiB = 54.0 GB; `3350 GB/s ÷ 54.0 GB ≈ 62 tok/s` [E].
- **In-flight window:** saturating 3.35 TB/s at ~500 ns latency needs
  `3.35e12 B/s × 500 ns ≈ 1.68 MB` in flight device-wide [E, `Architecture.md`] — the
  arithmetic behind "modest occupancy saturates bandwidth."
- **KV vs weights (where KV lives in HBM):** GQA h_kv=8, d_h=128, FP16 → KV/token/seq =
  `2×8×128×2 B = 4096 B`. At B=64, S=8192: `524,288 × 4096 B = 2147 MB ≈ 2.0 GiB` [E] —
  already competing with the 50 GiB weight footprint for HBM at scale.
### Failure modes
- **KV pressure:** long context × high batch → KV fills HBM → eviction / OOM / degraded
  concurrency (`../KV-Cache/README.md`).
- **Uncoalesced weight stream:** a strided or misaligned GEMV kernel wastes the 3.35 TB/s →
  measured tok/s well below `BW/bytes` (`Memory-Optimizations.md` Concept 1).
- **L2 thrash at decode:** weight stream + KV reads evict each other; GQA/MQA and KV
  quantization shrink the hot set.
### How to measure it
Nsight Compute `dram__throughput` vs the 3.35 TB/s roof; `gpu_cache_utilization`; achieved
tok/s vs `BW/bytes`. `nvidia-smi` for raw HBM occupancy.

## Per-level notes (SHARED/L1, L2, NVLink/PCIe, CPU RAM, NVMe)
### Shared memory / L1 — the tiling target
Per-SM SRAM; split programmable between **explicit `smem`** and the **L1 cache** per launch
[F: CUDA programming guide]. Up to **228 KB opt-in per block on sm_90** [F: CUDA programming
guide; [A: typical] per-SM]. This is where GEMM `[BM×BK]` + `[BK×BN]` tiles and FlashAttention's
Q/K/V tiles stage so the inner loop avoids HBM (`GEMM.md` step 3, `FlashAttention.md`).
It has **32 banks (4 B wide)** — the bank-conflict story in the access-patterns section below.
A warp that misses L1/shared falls through to L2, so shared is the *fast* explicit level.
### L2 — the hot-set cache
One **whole-die, hardware-cached** level shared across all SMs; **~50 MB on H100**
[A: typical]. It holds the **hot weight stream** and **re-read KV** that fit, plus prefix
re-use. Cache-line behavior (128 B) applies: a kernel that touches one 32 B field of many
lines wastes three quarters of each fetch. At decode, L2 is where a *repeated* weight
re-fetch can hit before HBM — but the full 50 GiB weight matrix never fits, so L2 is a
partial cache, not a store. Effective bandwidth is higher than HBM when hit rates are good
[~8 TB/s aggregate; A].
### NVLink / PCIe — the fabric levels
Beyond the die. **NVLink ~900 GB/s aggregate per H100** [F: H100 spec] (intra-node GPU↔GPU)
and **PCIe 5.0 x16 ~64 GB/s** [F: spec] (GPU↔host). Two LLM uses: (1) **TP AllReduce** —
tensor parallelism does 2 AllReduces per layer, so per-layer latency adds
`2×(link latency + comm time)`; NVLink ~900 vs PCIe ~64 GB/s is a **~14×** gap [E:
`900/64`], which is why TP lives on NVLink intra-node and PP/EP/CP move to RDMA across nodes
(`Scale-Up-vs-Scale-Out.md`). (2) **P/D KV transfer** — prefill→decode KV is a bulk copy;
1 GiB at NVLink 900 GB/s ≈ 1.2 ms vs PCIe 64 GB/s ≈ 17 ms [E, `Architecture.md`].
MoE AllToAll (in-node) also rides NVLink.
### CPU RAM (host)
The node's DRAM: **~50–100 GB/s, ~100–200 ns** [A: typical DDR5 dual-channel]. Used for
**FlexGen-class KV/weight offload** (`FlexGen` [F: arXiv:2303.06865]) — move cold KV or whole
weights to host to expand capacity — and for **pinned/page-locked buffers** that make H2D/D2H
run at the full ~64 GB/s instead of pageable speed. Model loading also streams through here.
The PCIe 3.35 TB/s : 64 GB/s = **~52×** ratio [E] is why host offload is a *capacity* tool,
not a *speed* tool.
### NVMe / remote — the offload floor
Slowest level: **~3–7 GB/s (NVMe) to ~10+ GB/s (RDMA/NDR ~50 GB/s per 400G link [F: spec])**
with **~50 µs–ms** latency [A]. Only enters the picture **when KV ≫ HBM** (ultra-long context,
very high concurrency): GPUDirect Storage / RDMA pulls cold KV pages or checkpoints.
In P/D disaggregation this is the *far* tier of KV (`Prefill-Decode-Disaggregation.md`,
Mooncake [F: arXiv:2407.00079]). Never on the hot path of a decode step.

## Access patterns — what makes a level "fast"
`Memory-Optimizations.md` owns the *techniques*; here is the *why* each level rewards certain
patterns. The single most important fact: **a warp's 32 lanes issuing one load are coalesced
by the memory controller into as few HBM transactions as the addresses allow.**

### Coalesced vs strided (the 1-transaction vs 32-transaction story)
A warp = 32 lockstep threads. If the 32 lanes address **contiguous** memory, the controller
fetches **one 128 B line** (one transaction). If the lanes are **scattered across lines**,
each distinct line is its own transaction — up to **32**.

```
Warp load of 32 × 4 B floats (128 B useful, ONE instruction)

COALESCED   lane t → base + 4t
  lanes: 0     1     2     3   ...  31
  addr:  [A0..A3][A4..A7] ... [A124..A127]
          └──────── 1 × 128 B line ────────┘   → 1 transaction
STRIDED     lane t → base + 128t
  lanes: 0           1           2      ...     31
  addr:  [L0..L31] [L32..L63] [L64..L95] ... [L3968..L4095]
          └128B┘     └128B┘     └128B┘              → 32 transactions,
                                                    only 128 B of 4096 B used
```
Rule: map `threadIdx` onto the **fastest-varying (contiguous) dimension** — for row-major A,
thread t loads `A[row][t]`, not `A[t][row]` (full worked example in
`Memory-Optimizations.md` Concept 1).

### Cache locality & cache-line behavior
HBM/L2 transfer in **128 B cache lines** [A: simplification]. A "partial-line" read that wants
one 32 B field of a 128 B line still fetches the whole line → **3–4× waste**. Stride ≥ line
size makes *every* access its own line, so reuse dies even for "re-read" data. LLM KV layout
is the canonical case: `[B, h_kv, S, d_h]` is read contiguously along `d_h` (coalesced);
PagedAttention keeps each 16-token chunk contiguous inside a page
[PagedAttention [F: arXiv:2309.06180]].

### Vectorized loads (128-bit / float4) & alignment
Move **128 bits per instruction** (`float4`, 8×BF16) instead of 32-bit: one warp instruction
moves 32×16 B = **512 B** vs 128 B scalar — **4× fewer load instructions** for the same bytes
[E: 512/128]. This only works when each lane's address is **16 B aligned**
(`base % 16 == 0` and element-size × lane-stride a multiple of 16 B). Framework allocations are
typically 256 B aligned [A] and LLM dims (4096, 11008) are divisible by 8 [E] → BF16 rows land
16 B aligned for free. A misaligned base+8 B splits each 128-bit load into two → 2× issue cost
on the load path [A]. The #1 user is the **decode GEMV weight stream** — coalesced + vectorized
streaming of `W[4096,4096]` BF16 per token is what separates ~full 3.35 TB/s from a worse ITL.

### How the L1/L2/HBM controllers coalesce transactions
The **L1TEX** unit merges a warp's 32 lane requests into the minimum set of sectors/lines the
addresses span; **L2** does the same against its tags; the **HBM controllers** issue the
resulting transactions to the DRAM. A fully coalesced warp load = 1 line at each level; a
scattered one fans out to up to 32 lines per level, multiplying round-trips and fetched bytes
at every stage. This is why "transactions" are the HBM controller's currency and why the
sector-per-request counters in Nsight Compute are the first thing to check.

### Shared-memory bank conflicts
Shared memory has **32 banks, 4 B wide**; 32 lanes in 32 distinct banks serve in **one cycle**;
two lanes in one bank **serialize** — a 32-way conflict takes **32 cycles = 32×** a conflict-free
access [E: 32/1] [F: CUDA programming guide]. It happens when a warp reads **down a column** of
a 2D array whose rows aren't bank-rotated: `smem[r][c]` with C a multiple of 32 and c fixed →
bank = `(c + r·(C mod 32)) mod 32` = constant for all r → all 32 lanes on one bank. Fix: pad
rows to C+1, or **swizzle** `c' = c ^ f(r)` (CUTLASS-style, zero waste)
[F: github.com/NVIDIA/cutlass]. GEMM/attention tile loops read operands in two orientations, so
FlashAttention uses swizzled layouts to keep the MMA feed conflict-free
[F: arXiv:2205.14135].

## Good vs bad access patterns (the table)
Relative HBM cost is vs a fully coalesced, aligned, 100%-efficient reference. Transaction
counts are [E] (32-lane warp, 128 B line, 4 B element) unless noted.

| Pattern | Transactions | Relative HBM cost | LLM example |
|---|---|---|---|
| Coalesced contiguous (32 lanes, 1 line) | **1** [E] | 1× | decode GEMV weight row |
| Vectorized float4 (32 lanes, 16 B/lane) | 1–2 [E] | ~1× (fewer instrs) | vectorized weight stream |
| Strided (lane stride = 1 line, 32 lines) | **32** [E] | **32×** | AoS field read, `A[t][row]` |
| Scattered random (each lane own line) | **32** [E] | **32×** | bad dequant layout |
| Partial-line (32 B of a 128 B line) | 1 [E] | **4×** [E: 128/32] | one field of many records |
| AoS → SoA field extraction | up to 32 [E] | up to **4×** [E: 512/128] | `{x,y,z,w}` records |
| GEMM B column-strided (no transpose) | N× [E, per K-tile] | high | naive GEMM (pre-tile) |
| 32-way shared-memory bank conflict | 1 (shared) | **32× cycles** [E: 32/1] | column read of 32-wide row |

The pattern is the whole story: the difference between a kernel that hits ~full 3.35 TB/s and
one that stalls is *which row of this table its inner loop is on* (`Memory-Optimizations.md`).

## Key Takeaways
1. The hierarchy is a **latency/bandwidth gradient**: registers (fast, per-thread) → shared/L1
   (per-SM) → L2 (per-GPU) → HBM (per-GPU, the roof) → NVLink/PCIe → CPU RAM → NVMe.
2. **Registers hold the GEMM micro-tile**; **shared/L1 holds the block tile**; **L2 holds the
   hot set**; **HBM holds everything else** and *is* the decode roof (`Roofline.md`).
3. **HBM bandwidth (3.35 TB/s H100, ~8 TB/s B200) sets tokens/s ≈ BW / bytes-per-token**; the
   27B B=1 ceiling ≈ 62 tok/s [E] and KV at B=64/S=8192 already ≈ 2 GiB [E] in HBM.
4. **One warp load = 1 transaction if coalesced, up to 32 if strided/scattered** [E] — the
   single biggest per-kernel lever; vectorization cuts instructions ~4× [E] when aligned.
5. **Bank conflicts** (32 banks) and **register spills** are the two "looks fine, actually
   slow" failures — check `l1tex` bank counters and `ptxas -v` spills, not just occupancy.

## Related
`./Architecture.md` (occupancy & latency hiding — the WHY) · `./Memory-Optimizations.md`
(the HOW: coalescing/tiling/pipelining) · `./GEMM.md` (the operation the hierarchy serves) ·
`./Fused-Kernels.md` (cut HBM round-trips by not writing intermediates) · `./FlashAttention.md`
(IO-aware tiling that keeps S×S off HBM) · `../Inference/Roofline.md` (BW × AI = the roof) ·
`../KV-Cache/README.md` (where KV lives and why it caps concurrency) ·
`../Inference/The-Life-of-a-Token.md` · `./Bandwidth-vs-Compute.md` · `./Profiling.md`

## References
NVIDIA CUDA C++ Programming Guide (warp coalescing, 32-bank SMEM + conflicts, sm_90 smem
opt-in, cp.async, L1/shared split) [F] · NVIDIA H100 Datasheet/whitepaper (132 SMs, 65,536
regs/SM = 256 KB, 80 GB HBM3 @ 3.35 TB/s, ~900 GB/s NVLink, ~64 GB/s PCIe 5.0, 4 warp
schedulers/SM) [F: vendor spec] · NVIDIA H200/B200/NVL72 announcements (HBM3e 141 GB,
~8 TB/s HBM3e, 72-GPU NVLink domain) [F: vendor spec] · Dao et al., FlashAttention
[arXiv:2205.14135] · Kwon et al., PagedAttention/vLLM [arXiv:2309.06180] · Sheng et al.,
FlexGen [arXiv:2303.06865] · Mooncake [arXiv:2407.00079] · CUTLASS
(github.com/NVIDIA/cutlass) · `../Hardware/README.md` (constants cross-check).
