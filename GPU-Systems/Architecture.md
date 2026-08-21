# GPU Computing for LLM Engineers — PART I
`LAST_UPDATED: 2026-08-21 · Status: core page` · Hardware constants cross-checked against
`../Hardware/README.md` and NVIDIA public specs; all [E] numbers hand-derived from those
constants. Tags: **[F]** verified primary source · **[A]** engineering assumption ·
**[I]** inference · **[E]** verified by computation this session.

## 30-Second Explanation
A neural-net layer is mostly **matrix multiply**: thousands of independent dot products that a
CPU chews on with a handful of cores, but that a GPU executes with thousands of threads at once.
The GPU trades *single-thread latency* for *throughput* — exactly what a 4096-wide GEMM or a
27B-parameter decode step wants. Its layout: many **Streaming Multiprocessors (SMs)**, each with
scalar FP/INT ALUs ("**CUDA cores**"), **Tensor Cores** for mixed-precision
matrix-multiply-accumulate (MMA), **warp schedulers** that issue instructions to groups of 32
lockstep threads ("**warps**", SIMT), plus registers, shared memory/L1, L2, and HBM. The program
model is **Grid → Block → Warp → Thread**: the grid is launched, blocks are scheduled onto SMs
(a block never spans two SMs), and inside an SM every 32 threads form a warp driven by one
scheduler. The single most important trick: **a warp stalling on HBM does not stall the SM** —
the scheduler switches to another ready warp; with enough warps resident, outstanding loads keep
the HBM pipeline saturated, so *slow* memory *behaves* like fast memory. Prefill (big dense
GEMMs) lives on Tensor Cores with high occupancy; decode (streaming weights, one token at a time)
lives on latency hiding — see [Roofline](../Inference/Roofline.md) and
[The Life of a Token](../Inference/The-Life-of-a-Token.md).

## Why Neural-Network Workloads Map to GPUs
Two properties of LLM math fit the GPU's strengths [I]:
1. **Massive parallelism.** A `[S,d]×[d,d]` GEMM at S=8192, d=4096 is 4096 independent dot
   products of length 8192×4096 — embarrassingly parallel, no inter-element dependencies.
   Attention adds S×S×h independent head computations.
2. **Latency-vs-throughput.** We never care about *one* element's latency, only the whole
   matrix's throughput. A latency-oriented CPU wastes pipeline on per-element latency; a
   throughput-oriented GPU hides it by running thousands of independent chains at once.
The flip side: a GPU is a *poor* general-purpose CPU (slow per-thread control flow, big branch
penalties). LLM inference is ~90% GEMM/GEMV + elementwise ops (`GEMM.md`), so it lands exactly in
the GPU's sweet spot [I].

## GPU Hardware — What an SM Actually Is
A datacenter GPU is a wall of SMs (H100 SXM: **132 SMs** [F: NVIDIA H100 spec]). Each SM contains:
- **CUDA cores** — scalar FP32/BF16/FP16/INT32 ALUs; one element per clock each
  [F: CUDA programming guide]. "CUDA core" = a scalar ALU.
- **Tensor Cores** — mixed-precision **MMA** units: one instruction multiplies-accumulates small
  tiles (e.g. 16×8×16) in FP16/BF16/FP8/FP4. All of the "989 TFLOP BF16 dense" peak comes from
  here, not the CUDA cores [F: H100 spec]. See `Tensor-Cores.md`.
- **Warp schedulers** — 4 per SM [F: H100 whitepaper]; each issues one instruction per clock to
  a resident warp.
- **Register file** — 256 KB per SM = **65,536 × 32-bit registers** [F: H100 spec]; the biggest
  occupancy lever.
- **Shared memory / L1** — per-SM SRAM, programmable split between shared mem and L1 per launch
  [F: CUDA programming guide].
- **L2 cache** — one shared across the whole die, in front of HBM.
- **HBM** — main memory (HBM3 on H100 @ 3.35 TB/s [F: spec]; HBM3e on H200/B200; GDDR7 on
  RTX 50). Bandwidth is a device-wide property, not per-SM.

```
┌────────────────────────────────────────────────────────────────────────────────┐
│ H100-class GPU (simplified)                                                   │
│  ┌── GPC (GPU Processing Cluster, groups SMs) ───────────────┐ × 132 SMs [F]  │
│  │ ┌─ SM ────────────────────────────────────────────────────┐ │               │
│  │ │  warp schedulers (4) — pick ready warp, issue 1 instr/c│ │               │
│  │ │  ┌─ CUDA cores (scalar FP/INT ALUs) ──────────────────┐│ │               │
│  │ │  ├─ Tensor Cores (mixed-precision MMA) ───────────────┤│ │ ← 989 TF BF16 │
│  │ │  ├─ register file (256 KB, per-SM)                    ││ │               │
│  │ │  ├─ shared memory / L1 (per-SM SRAM)                  ││ │               │
│  │ │  └─ LSU, FIFOs, per-SM pipeline ──────────────────────┘│ │               │
│  │ └─────────────────────────────────────────────────────────┘ │               │
│  └──────────────────────────────────────────────────────────────┘               │
│   L2 cache (shared, whole die)                                                 │
│   └─ memory controllers ── HBM3 (3.35 TB/s aggregate) [F]                     │
│   └─ PCIe 5.0 x16 (~64 GB/s to host) [F]                                      │
│   └─ NVLink (~900 GB/s aggregate to peer GPUs) [F]                           │
└────────────────────────────────────────────────────────────────────────────────┘
```

## Concept 1 — CPU vs GPU
### What
A **CPU**: a few wide, out-of-order, latency-optimized cores with big L3 cache and branch
prediction. A **GPU**: hundreds of narrow, mostly in-order, throughput-optimized cores with
less per-core intelligence but far more on-chip scratch and much wider memory bandwidth.
### Why
Same silicon, opposite bets: the CPU makes *your thread* fast (deep pipelines, speculation,
out-of-order issue); the GPU runs *lots of threads* — when one thread mispredicts or its load
stalls, switch to another ready warp instead of flushing a deep pipeline [F: CUDA programming
guide, SIMT model]. Neural nets are the mainstream workload where "lots of threads" beats "few
fast threads" by orders of magnitude [I].
### How
CPU hides latency via **ILP** — speculative/out-of-order issue within a ~few-hundred-instruction
window. GPU hides latency via **TLP** — the warp scheduler swaps between ready warps with no
speculation. Both exist on a GPU, but TLP is the dominant mechanism; see Concept 4.
### When
CPU wins: serial/branchy code, runtime work, kernel-launch orchestration. GPU wins: dense math at
large shape — every prefill GEMM, every decode weight stream, every attention block.
### Hardware impact
A CPU die spends a large fraction of its area on cache + branch hardware [A]; a GPU die spends
most of its area on SMs (ALUs, Tensor Cores, register files, schedulers). H100: 132 SMs [F] vs a
server CPU's ~16–32 cores.
### Inference impact
All LLM math is GPU-resident; the CPU is only the *orchestrator*. Any host-side stall (Python,
GIL, in-loop sampling) adds directly to ITL — a slow scheduler shows up as GPU idle time, not a
GPU problem (`Diagnostics.md`).
### Example [E]
One 4096×4096 GEMM = 2·4096³ ≈ **137 GFLOP**. 16-core server CPU, AVX-512, no AMX-class BF16
speedup, ~27 GFLOP/s sustained: 137e9/27e9 ≈ **5.1 s**. H100 at a conservative 30% of its 989
TFLOP BF16-dense peak (≈297 TFLOP/s): 137e9/297e12 ≈ **0.46 ms**. ~4 orders of magnitude on one
layer's dominant op.
### Failure modes
- **CPU-bound serving:** host can't feed the GPU → utilization dips between kernels (the classic
  small-batch decode symptom).
- **PCIe fallback:** host RAM ↔ HBM at ~64 GB/s is ~50× slower than HBM's 3.35 TB/s for the same
  tensor [E: 3350/64 ≈ 52].
### How to measure it
`nvidia-smi --query-gpu=utilization.gpu` alongside host CPU %; Nsight Systems shows the
inter-kernel gaps. Oscillating GPU util tracking host CPU spikes = CPU-bound.

## Concept 2 — SIMT and the Warp
### What
Threads are not independent: hardware groups every **32 consecutive threads of a block into a
warp**, and the warp scheduler executes **one instruction at a time for all 32 lanes in lockstep**
— SIMT, single instruction multiple threads. Warp size 32 is fixed hardware, not a launch
parameter [F: CUDA programming guide].
### Why
SIMT gives SIMD throughput (one ALU op feeds 32 lanes) *without* explicit vectors: you write
ordinary per-thread code; the compiler maps threads to lanes. It also removes branch prediction:
on a divergent branch the warp executes **both** paths in sequence with a per-lane active mask —
no mispredict, no pipeline flush; you just pay issue slots for the masked path
[F: CUDA programming guide].
### How
All 32 lanes of a warp execute `fma(r0,a,b,c)` in the same clock — "32 CUDA cores, one FMA, one
cycle." **Divergence**: `if (lane < 16) A else B` → the warp runs A with lanes 0–15 active, then
B with 16–31; both paths are issued → up to 2× issue slots for that region.
### When
Always — SIMT is the model; you can't opt out. You *can* avoid *paying* for it by aligning control
flow with warp structure: branch on `blockIdx` or `threadIdx.x / 32`, not on `threadIdx.x % 3`
[A: kernel-writing convention].
### Hardware impact
The warp scheduler is the heart of the SM: 4 schedulers × 1 issue/clock [F]. The instruction mix
(memory vs ALU vs Tensor MMA) determines which SM sub-unit saturates — this is what "warps
stalled on memory" metrics measure.
### Inference impact
- **Prefill GEMMs** are branch-free FMA/MMA floods: no divergence, high occupancy, Tensor Cores
  saturated — why prefill reaches ~50–70% of peak MFU with good kernels [A].
- **Decode** GEMVs spread work over few threads per output; engines keep control flow warp-aligned,
  so the decode cost is *latency* (memory stalls), not divergence.
### Example [E]
Grid of **8 blocks × 256 threads = 2048 threads = 64 warps** (2048/32). Each block's 256 threads
form 8 warps. If an SM hosts 2 blocks (16 warps) and each warp issues one 32-wide FMA/cycle:
16 FMA/cycle = 16×32 = **512 FLOP/cycle from scalar ALUs alone** — before any Tensor Core
instructions.
### Failure modes
- **Warp-wide divergence:** data-dependent `if` on a per-thread value doubles issue slots in that
  region (classic mistake in naive masking/attention kernels).
- **Assuming independent threads:** two lanes of a warp *must* run the same instruction stream;
  per-thread control flow pays the mask.
- **Divergent memory access:** two lanes reading distant addresses split one warp load into
  multiple transactions (`Memory-Hierarchy.md`).
### How to measure it
Nsight Compute: branch-instruction and warp-branch-divergence reports; issue-slot utilization
(warps issued / warps eligible).

## The Execution Hierarchy — Grid → Block → Warp → Thread
The CUDA program model is a 4-level tree that maps 1:1 onto hardware:

```
Program (host)
└── GRID              one kernel launch; many blocks
    └── BLOCK         e.g. 256 threads; SCHEDULED onto ONE SM as a unit [F]
        └── WARP      32 consecutive threads; the EXECUTION unit (hardware)
            └── THREAD one program counter + one register set

Physical mapping:
  grid launched ──► block scheduler hands each BLOCK to one SM (never spans two SMs)
  inside an SM ──► 32 consecutive threads auto-group into warps;
                   warp scheduler issues each warp's instructions
```
- **Thread** — `threadIdx` + registers; that's all it privately owns.
- **Warp (32)** — unit of execution; scheduler granularity.
- **Block** — unit of *scheduling* onto SMs and of *cooperation*: block threads share the SM's
  shared memory and sync with `__syncthreads()`; a block lives on exactly one SM its whole life
  [F: CUDA programming guide].
- **Grid** — unit of a kernel launch; blocks may run in **any order**, so kernels must be
  order-independent (reductions use two-pass/atomics, not ordering).

Occupancy ties the levels together: with a 256 KB (65,536-register) register file [F] and R
registers/thread, one SM holds at most 65,536/R threads = 65,536/(32·R) warps — worked out in
Concept 4.

## Concept 3 — Memory Hierarchy Overview
Full treatment: `Memory-Hierarchy.md`. The 30-second version:

| Level | Where | Latency (typical) | Bandwidth | Notes |
|---|---|---|---|---|
| Registers | per-thread, in SM | 0 (ALU operand) | ALU rate | free; costs occupancy |
| Shared mem / L1 | per-SM SRAM | ~20–30 cycles [A] | ~TB/s aggregate | tiles land here |
| L2 | whole-die SRAM | ~200 cycles [A] | ~8 TB/s [A] | in front of HBM |
| HBM | off-die | ~400–600 cycles [A] | 3.35 TB/s H100 [F] | main memory |
| NVLink / PCIe | peer GPU / host | µs-class [A] | ~900 / ~64 GB/s [F] | cross-device |

### What
Every read goes register ← (shared/L1) ← L2 ← HBM; each level is slower and larger. Kernel
engineering = moving each byte **as few levels down as possible** and never stranding a warp at
the bottom.
### Why
HBM latency (~hundreds of ns) is structurally ~30–100× an L1 hit [A]. No caching makes HBM fast
— so the GPU doesn't try to make it fast; it makes latency *invisible* (Concept 4).
### How
HBM → (coalesced warp-wide load) → L1/L2 → shared memory → registers → ALU/Tensor Core. Tiling
turns O(N·K) HBM reads per output into O(N·K/BM): load a 64×64 tile once, reuse it 64 times
(`GEMM.md`).
### When
Registers: GEMM inner loop, activation math. Shared: GEMM/attention tiles, reduction partials.
L2: KV re-reads that fit, weight prefetch. HBM: everything else — and at decode, *all* weights +
*all* KV, every token.
### Hardware impact
Shared memory is per-SM: a block on SM7 cannot read SM3's shared memory. HBM bandwidth is
device-wide — all SMs contend for the same 3.35 TB/s, so "more SMs" does not raise memory-bound
throughput (`Bandwidth-vs-Compute.md`).
### Inference impact
Prefill attention's S×S score matrix at S=32k, h=64 = 32768²×64×2 B ≈ **137 GB = 128 GiB** [E] —
it must never reach HBM; FlashAttention keeps it in shared memory [F: arXiv:2205.14135]. Decode
streams the whole weight matrix from HBM each token; bytes/token is the ITL denominator
(`../Inference/The-Life-of-a-Token.md`).
### Example [E]
Same 4096×4096 GEMM: naive (one thread per C[i,j], reading A row + B column from HBM) moves
2·4096³·2 B ≈ **275 GB**. 64×64 tiling reuses each 64-wide strip 64× → ~4.3 GB: **~64× less HBM
traffic** — most of the gap between a naive and a decent GEMM is *levels traversed*.
### Failure modes
- **Uncoalesced warp access:** 32 lanes in 32 different 128B lines = 32 transactions where 1
  would do.
- **Bank conflicts:** 32 lanes hitting one shared-memory bank serialize.
- **L2 thrash at decode:** weight stream + KV reads evict each other; GQA/MQA shrinks KV.
### How to measure it
Nsight Compute memory table: `dram__throughput` vs `l1tex__throughput`, sector hit rates.
Bandwidth-bound kernel → push `dram__throughput` toward the 3.35 TB/s roof.

## Concept 4 — Occupancy & Latency Hiding (THE KEY QUESTION)
**"Why can thousands of GPU threads make slow memory appear faster?"**
Because a warp stalling on HBM does not stall the SM. The SM's warp schedulers keep many warps
resident (each in its registers); when the current warp issues a load and stalls, the scheduler
**switches to another ready warp in one cycle** and keeps issuing. With enough warps, the
*aggregate* stream of outstanding loads stays full, the HBM pipeline never drains, and **achieved
bandwidth approaches peak** — memory *looks* fast even though each individual load still takes
~500 ns [I: standard throughput-architecture argument; latency values are engineering estimates].
Two distinct hiding mechanisms:
- **ILP** — one warp has multiple independent instructions in flight (CPU-style; bounded by the
  compiler's scheduling window).
- **TLP** — many *warps* provide independent work (the GPU's dominant mechanism; bounded only by
  the register file and warp slots → this is where **occupancy** comes in).

### What
**Occupancy** = resident warps on an SM ÷ the SM's maximum resident warps (64 warps / 2048 threads
on H100 [F: H100 spec]). It caps how much latency you can hide: more resident warps ⇒ more bytes
in flight ⇒ closer to peak HBM bandwidth.
### Why
HBM at ~500 ns [A] and 3.35 TB/s [F] needs 3.35e12 × 500e-9 ≈ **1.67 MB in flight** device-wide
to stay saturated [E]. One warp-wide 128B load moves 128 B → ~**13,000 in-flight warp-loads**
(1.67 MB / 128 B) [E]. Spread over 132 SMs that is ~**99 outstanding loads per SM** [E] —
trivially covered by e.g. 64 resident warps/SM × ~1.5 loads each. So even *modest* per-SM
occupancy saturates bandwidth; 100% occupancy is sufficient, not necessary [I].
### How
Register-file arithmetic (H100: 65,536 regs/SM [F], cap 64 warps/SM [F]):
- Kernel using **32 regs/thread**: 65,536/32 = 2,048 threads = **64 warps = 100%** of the
  64-warp cap [E].
- Kernel using **64 regs/thread**: 65,536/64 = 1,024 threads = **32 warps = 50% occupancy** [E].
  Halving registers/thread doubles occupancy — the core GEMM/attention tuning knob. (Other caps:
  shared memory/block, blocks-per-SM; the compiler reports which resource binds.)
### When
- **Prefill:** dense, many warps; Tensor Core MMA is issued per warp, so occupancy also scales
  MMA issue rate — prefill lives on Tensor Cores + high occupancy.
- **Decode: this is where hiding lives.** Per SM the active work is thin (small M); the engine's
  batch is the TLP source. Batch B=64 gives 64× the warps of B=1 for the same weights — the same
  3.35 TB/s now feeds 64 sequences. That is exactly the roofline's knee
  B* ≈ ridge·b_w/2 ≈ 295·2/2 ≈ **295 (BF16, H100)** [E; `../Inference/Roofline.md`].
### Hardware impact
Register file + warp slots + shared memory are the three occupancy caps. Tensor Cores amplify
occupancy: one warp's MMA covers 16×8×16 elements, so GEMM can be FLOP-saturated at ~50%
occupancy while a copy kernel is bandwidth-starved at 50% [I].
### Inference impact
- **Decode B=1:** few active warps per SM → HBM not fully utilized → measured tok/s well below
  `BW/bytes`. Continuous batching (`../Inference/Continuous-Batching.md`) is literally the act of
  adding resident warps to fill the memory pipeline [I].
- **Speculative decoding** adds draft+verify parallelism inside one step — TLP for thin request
  streams (`../Speculative-Decoding/README.md`).
### Example [E]
H100 at 50% occupancy: 132 SMs × 32 warps × 128 B in flight ≈ **540 KB** — roughly half the
1.67 MB saturation window *with one load per warp*; at full 64-warp occupancy with ~1.5
loads/warp: 132×64×1.5×128 B ≈ **1.61 MB ≈ peak window** [E]. At B=1 decode, an SM may have <2
useful warps active per instruction stream → achieved BW drops to a fraction of peak; that gap
is your ITL.
### Failure modes
- **Low occupancy + memory-bound kernel:** #1 decode inefficiency; check `occupancy` + warp-stall
  breakdown in Nsight Compute.
- **Register spills:** chasing occupancy with few regs spills to local memory (HBM) — bandwidth
  collapses even though the metric says "high occupancy".
- **High occupancy, low ILP:** all warps stall on the *same* dependency (one L2 line) — switching
  doesn't help; coalescing fixes it, occupancy doesn't.
### How to measure it
- Nsight Compute: `sm__warps_active` (achieved occupancy); `smsp__warp_issue_stalled_*`
  breakdown — `long_scoreboard` = HBM wait, `short_scoreboard` = L1, `wait`/`barrier` = sync.
- Rule: memory-bound + `long_scoreboard` dominant + occupancy < 50% → add warps (bigger batch,
  fewer regs/thread, more blocks). Nsight Systems: kernel durations + `dram__throughput` vs roof.

## Concept 5 — Interconnects: PCIe, NVLink, NVSwitch
The on-chip hierarchy ends at the die. Beyond it:

| Link | Scope | Bandwidth (H100-gen) | Role |
|---|---|---|---|
| **PCIe 5.0 x16** | GPU ↔ host | ~64 GB/s/direction [F: spec] | weight load, H2D/D2H, fallback peer path |
| **NVLink** | GPU ↔ GPU, intra-node | ~900 GB/s aggregate per H100 [F: spec] | TP allreduce, P2P, in-node KV |
| **NVSwitch** | all-to-all node fabric | every GPU pair first-class [A] | 8-GPU node; NVL72: 72-GPU NVLink domain [F] |
| IB/RoCE | inter-node | ~50 GB/s per 400G NDR link [F: spec] | scale-out; `../Networking/README.md` |

### What
PCIe is the **host bridge**; NVLink is **GPU peer fabric**; NVSwitch is the **crossbar** that
connects all NVLinks so any GPU reaches any other in one hop. Different fabrics for different
distances — not faster versions of each other [I].
### Why
Multi-GPU inference is a fabric problem: tensor parallelism does 2 AllRecommends per layer, so
per-layer latency adds `2×(link latency + comm time)`. NVLink's ~900 GB/s vs PCIe's ~64 GB/s is a
**~14×** gap [E: 900/64] — that is why TP lives intra-node on NVLink while PP/EP/CP move to RDMA
across nodes (`Scale-Up-vs-Scale-Out.md`, `Topology.md`).
### How
PCIe: driver posts DMA; `cudaMemcpy` moves ~64 GB/s. NVLink: direct GPU↔GPU, bypassing the host;
NCCL's AllReduce/AllGather and P2P copies run over it. NVSwitch: an on-node switch chip wiring
all 8 GPUs' NVLinks into a full crossbar — an HGX node becomes one machine instead of 8 PCIe
islands [I].
### When
PCIe: single-GPU boxes, dev rigs, model loading. NVLink: any TP, in-node P/D KV transfer,
intra-node MoE AllToAll. NVSwitch/NVL72: 72-GPU domains for frontier MoE (DeepSeek-class) EP/CP
[F: NVIDIA NVL72].
### Hardware impact
Fabric bandwidth bounds communication-parallelism: AllReduce time scales with payload/BW;
NVSwitch makes every AllReduce uniform, while PCIe-only topologies produce near/far pairs where
NCCL routes through the host — ~14× slower on that path [I].
### Inference impact
- **TP=8 on NVLink:** 32 MB allreduce ≈ 2×32 MB/900 GB/s ≈ **0.07 ms** [E] → ~2 ms over 32
  layers ≈ <0.1% of a decode step. Same on PCIe: ≈ 1 ms/layer → ~32 ms → ~50% of a 65 ms ITL
  step [E]. The fabric *is* the parallelism strategy.
- **P/D disaggregation:** prefill→decode KV transfer is bulk copy. 1 GiB at NVLink 900 GB/s ≈
  **1.2 ms** [E]; at PCIe 64 GB/s ≈ **17 ms** [E] — a full ITL by itself
  (`Prefill-Decode-Disaggregation.md`).
### Example [E]
27B model (50.3 GiB BF16) loading onto one H100 over PCIe 5.0: 54.0 GB ÷ 64 GB/s ≈ **0.85 s** —
model load is PCIe-bound, not CPU-bound. Contrast with the same tensor in HBM: 54.0 GB ÷ 3.35
TB/s ≈ **16 ms** [E].
### Failure modes
- **PCIe-only node running TP=8:** collective time ≈ compute time → "GPU utilization high but
  throughput low"; run `nccl-tests` + `nvidia-smi topo -m` first.
- **Topology/NUMA assumptions wrong:** one GPU pair routes through host → that pair's NCCL
  traffic ~14× slower; P99 blows up, P50 looks fine (`Topology.md`).
- **NVSwitch domain shared across jobs:** a 72-GPU domain split between tenants halves effective
  AllToAll BW (MoE EP is most sensitive) [I].
### How to measure it
`nccl-tests` (all_reduce_perf, alltoall_perf) on the *real* topology — never trust datasheet BW;
`nvidia-smi topo -m` for actual GPU↔GPU links; Nsight Systems + NCCL debug logs for per-collective
timing; NVLink throughput counters vs peak.

## Connecting It All to LLM Inference — the Two Regimes
| Resource | Prefill (compute-bound) | Decode (memory-bound) |
|---|---|---|
| Tensor Cores | saturated via big-M GEMMs + high occupancy | idle (M too small; GEMV) |
| CUDA cores | elementwise/softmax assist | attention, norms, sampling |
| HBM | weights once + S×d activations | **all weights + all KV, every token** |
| Occupancy/TLP | high by shape | *the* lever: batch → warps → bandwidth |
| Fabric | rarely (prefill fits one node) | P/D KV transfer, TP allreduces |

Chain: **GEMM shape decides the roof** (`GEMM.md`) → **roof decides which resource is hot**
(`Bandwidth-vs-Compute.md`) → **hierarchy decides achievable BW** (`Memory-Hierarchy.md`) →
**warp/occupancy arithmetic decides whether you get it** (Concept 4) → **fabric decides whether
parallelism helps** (Concept 5). Kernel-level detail: `CUDA-From-Zero.md`, `Kernel-Life.md`;
measurement: `Profiling.md`, `GPU-Metrics.md`.

## Key Takeaways
1. A GPU = 132 SMs × (scalar ALUs + Tensor Cores + warp schedulers) fed by one device-wide HBM
   pool; it is a *throughput* machine, not a *latency* machine.
2. Warps (32 threads, lockstep SIMT) are the execution unit; blocks are the scheduling unit; a
   block never spans two SMs. Divergence costs issue slots, not correctness.
3. "Why does slow memory look fast?" → **TLP via warp switching**: enough resident warps keep
   HBM's ~1.67 MB in-flight window full, so achieved BW ≈ peak; occupancy is the arithmetic that
   guarantees enough warps.
4. Prefill buys FLOPs (Tensor Cores + occupancy); decode buys bandwidth (batching = adding
   warps). The switch happens at the roofline ridge ≈ 295 FLOP/byte (H100 BF16).
5. Fabric is a first-class resource: ~64 GB/s PCIe vs ~900 GB/s NVLink is a ~14× gap that
   determines whether TP, P/D, and MoE-EP are viable on your topology.

## Related
`CUDA-From-Zero.md` · `GEMM.md` · `Memory-Hierarchy.md` · `Bandwidth-vs-Compute.md` ·
`Tensor-Cores.md` · `../Inference/Roofline.md` · `../Inference/The-Life-of-a-Token.md` ·
`../Hardware/README.md` · `../Networking/README.md` · `../Inference/Inference-Metrics.md`

## References
NVIDIA CUDA C++ Programming Guide (warp = 32, SIMT semantics, block/SM mapping, shared mem + L1
split) [F] · NVIDIA H100 Datasheet/whitepaper (132 SMs, 989 TFLOP BF16 dense, 3.35 TB/s HBM3,
65,536 regs/SM, 64 warps/SM, ~900 GB/s NVLink, 4 warp schedulers/SM) [F: vendor spec] · NVIDIA
H200/B200/NVL72 announcements (HBM3e 141 GB, ~8 TB/s HBM3e, FP4/FP8 rates, 72-GPU NVLink
domain) [F: vendor spec] · Dao et al. 2022, FlashAttention [F: arXiv:2205.14135] ·
Williams/Waterman/Patterson 2009 (roofline) [F] · `../Hardware/README.md` (constants cross-check).
