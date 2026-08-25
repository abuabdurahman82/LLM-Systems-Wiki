# NVIDIA GPU Architecture — Overview
`LAST_UPDATED: 2026-08-23` · Status: core page · Specs tagged `[F: vendor spec]` unless noted.
NVIDIA is the "generalist" of this section: one architecture that must serve HPC, training,
prefill, and decode simultaneously, priced accordingly.

## 30-Second Explanation
An NVIDIA GPU is a **hierarchy of programmable, dynamically-scheduled parallel machines**:
thousands of CUDA cores plus dedicated Tensor Cores, organized into SMs, scheduled in
32-thread *warps*, fed by an explicit on-chip memory system (registers, shared memory/L1,
L2, HBM) and scaled out over NVLink/NVSwitch into 72- (and now 144-)GPU coherent domains.
The bet: **programmability + dynamic scheduling + a software ecosystem (CUDA) beat any
more specialized machine on general-purpose AI work** — at the price of more silicon spent
on the machinery that specialized chips delete.

## Genealogy (SHIPPED / ANNOUNCED / PROJECTED)
```
G80 "Tesla" (2006-08)   first CUDA GPU: SIMT cores, no dedicated matmul unit. SHIPPED.
Fermi (2010)             warp scheduling matured; PCIe; compute-class GPUs. SHIPPED.
Kepler (2012)            ECC HPC focus; K40. SHIPPED.
Maxwell (2014)           consumer + Pascal-bridge generation. SHIPPED.
Pascal (2016)            first GPU FP16; HPC P100. SHIPPED.
Volta (2017-18)          FIRST TENSOR CORES (FP16 mma.sync, warp-scoped); async global->shared
                         copy (cp.async). SHIPPED.
Turing (2018-19)         INT8/INT4 Tensor Cores; RT cores. SHIPPED.
Ampere (2020)            BF16 + TF32 Tensor Cores; mma.sync still warp-scoped; A100 80GB. SHIPPED.
Hopper (2022-23)         FP8; warp- GROUP- scoped wgmma (128 threads); TMA bulk async copy;
                         NVLink 4 (900 GB/s/GPU); H100 80GB HBM3. SHIPPED.
Blackwell (2024-25)      B200/GB200 NVL72: 2 reticle-limit dies/package (CoWoS-L),
                         tcgen05.mma (single-thread issued, async, TMEM accumulate),
                         FP4/NVFP4, HBM3e 192GB @ 8 TB/s, NVLink5 1.8 TB/s/GPU, NVSwitch
                         rack domain NVL72. SHIPPED.
Blackwell Ultra (2025)   B300: 288 GB HBM3e, 7.5 PF FP8 dense / 15 PF FP4 dense,
                         1,400 W. SHIPPED.
Rubin (2026)             R200/R300 class: HBM4 ~288 GB @ ~13 TB/s, ~17 PF FP8 / ~50 PF FP4
                         dense, NVL144 (144-GPU domain, 260 TB/s). SHIPPED/launching.
Rubin Ultra (2027)       NVL576 "Kyber": 576 GPUs, HBM4e ~1 TB/package, ~33 PF FP8 dense
                         per GPU (projected), ~600 kW/rack. ANNOUNCED (GTC 2025 roadmap
                         [F: vendor spec]).
```
[Provenance note: Hopper/Blackwell/Ultra/Rubin figures are from NVIDIA official datasheets
and GTC keynotes [F: vendor spec]; "dense" = with sparsity disabled; 2:4 structured
sparsity doubles quoted peaks where marketed.]

## The machine as a hierarchy
```
GPU (one or two reticle-limit dies on Blackwell+, one HBM pool, one L2)
└── GPC (graphics processing cluster: 4-10 SMs + raster)
    └── SM (streaming multiprocessor, the unit of scheduling)
        ├── 4 warp schedulers (each issues 1 warp instruction/cycle)
        ├── CUDA cores (FP32/INT32 ALUs, 128/SM on H100, 128 on Blackwell-class)
        ├── Tensor Cores (FP16/BF16/FP8/FP4 MMA; 4th-gen on Ampere, 5th on Hopper+,
        │    tcgen05-class on Blackwell)
        ├── register file (65,536 × 32-bit/SM = 256 KB [E]; max 64 warps/2048 threads resident [E])
        ├── unified L1 / shared memory (up to 228 KB on Hopper SM; partitioned between
        │    L1 cache and programmer-visible SMEM)
        └── TMA (Hopper+: bulk async tensor copies HBM <-> SMEM, no SM instruction cost
             per element; Blackwell adds more autonomous copy features [F: vendor spec])
└── L2 cache (shared across SMs; H100: 50 MB; Blackwell: 126 MB per die [F: vendor spec])
└── HBM (HBM3/HBM3e/HBM4; the weights + activations + KV live here)
└── NVLink/NVSwitch (scale-up; PCIe (host)); NIC + IB/Spectrum-X (scale-out)
```
H100 SXM concrete numbers (the wiki's standard constant set, [F: vendor spec]):
132 SMs, 989 TFLOP BF16 dense, 3.35 TB/s HBM3, 80 GB, ~900 GB/s NVLink aggregate,
700 W; max 64 warps / 2048 threads resident per SM; 4 warp schedulers per SM.

## SIMT, warp, CTA, occupancy, latency hiding — the scheduling story
- **SIMT (single-instruction, multiple-threads):** the SM issues one instruction to a *warp*
  (32 threads, a "warp" = 32 consecutive lanes). Divergent branches execute serially with
  masking — the classic GPU tax, why kernels avoid per-thread control flow.
- **Thread block / CTA (cooperative thread array):** a block of threads (e.g. 128–1024) that
  must run on *one* SM; they share the SM's registers/SMEM and can synchronize with a
  barrier. Blocks are the unit the GPU *schedules across* SMs.
- **Warp scheduling:** 4 schedulers/SM, each picking one ready warp each cycle (round-robin
  among eligible warps). A warp is "ready" when its next instruction's operands/dependencies
  are satisfied.
- **Occupancy:** how many of the SM's 64-warp register/scheduler slots are filled with
  resident warps. High occupancy = more independent warps to switch between.
- **Latency hiding (the GPU's answer to the memory wall):** an HBM access takes ~600+
  cycles [A]. With ~32–64 warps resident per SM, the scheduler switches to a warp whose data
  is ready while the HBM request for another is in flight. Compute does not wait for
  memory — *other warps fill the gap*. This is the fundamental GPU mechanism and the reason
  occupancy matters: too few resident warps and the HBM latency shows up as bubbles.
  [I: mechanism; cycle counts approximate on H100, varies by L1/L2 hit]
- **Why it matters for LLMs:** decode kernels (GEMV at M=B) have *little* arithmetic to
  overlap per weight-read; the win comes from many concurrent CTAs keeping HBM saturated
  (batching across requests). Prefill kernels (fat GEMMs) have deep K-loops to pipeline.
  The same scheduler serves both — that flexibility is the GPU's bet.

## The SM's dual population: CUDA cores vs Tensor Cores
- **CUDA cores** do FP32/INT32/FP64 scalar-ish work: elementwise ops (softmax, activations,
  residual adds, RoPE, routing for MoE), address arithmetic, and any op with no dedicated
  engine.
- **Tensor Cores** do the matmuls: C ← A×B + C on tiles, in FP16/BF16/FP8/FP4. Deep dive:
  `06-nvidia-sm-and-tensor-cores.md`.
The split mirrors every other machine in this section (AMD Matrix Core vs SIMDs, Trainium
Tensor vs Vector/Scalar/GPSIMD, Groq MXM vs VXM); the NVIDIA-specific part is that the
*issuing context* for Tensor Cores has moved across generations: warp (Volta–Ampere) →
warp-group (Hopper wgmma) → single-thread async + TMEM + 2-SM cluster (Blackwell
tcgen05). [F: vendor PTX/ISA docs]

## The 8-question framework, answered for NVIDIA (quick pass)
```
Q1 lives:      HBM (weights/KV/activations); SMEM/L1 tiles; registers; TMEM accumulators
Q2 moves:      caches + explicit SMEM tiling + cp.async/TMA bulk copies; NVLink; PCIe
Q3 compute:    CUDA cores (FP32/INT) + Tensor Cores (MMA, tile, async on Blackwell)
Q4 scale:      NVLink domain (8/72/144 GPUs) over NVSwitch; IB or Spectrum-X beyond
Q5 schedule:   HARDWARE — warp schedulers + occupancy (fully dynamic)
Q6 numerics:   FP64/32/TF32/BF16/FP16/FP8/FP6/FP4(+NVFP4); FP32 accumulate
Q7 program:    CUDA (C++/Python) -> PTX -> SASS; cuBLAS/cuDNN/CUTLASS; Triton;
               vLLM/SGLang/TensorRT-LLM
Q8 bet:        the generalist — every regime, all workloads; priced on the CUDA moat
```

## What makes NVIDIA different from the other five (one paragraph each)
- **vs TPU:** NVIDIA schedules in hardware, TPU in compiler; NVIDIA caches, TPU scratchpads;
  NVIDIA is programmable to SASS, TPU to XLA/Pallas. (Deep: `10`, `16`, `17`.)
- **vs AMD:** both are SIMT GPU-class; AMD's innovation is *outside* the CU — chiplets,
  Infinity Cache, HBM capacity, open interconnects — while NVIDIA's is *inside* the SM —
  tensor primitives, TMA, async MMA. (Deep: `11`.)
- **vs Trainium:** both have dedicated engines; Trainium adds CC-Cores (collectives in
  silicon) and is compiler-first (OpenXLA); NVIDIA's collectives are NCCL kernels on the
  same SMs. (Deep: `13`.)
- **vs Cerebras:** NVIDIA hides the wall with occupancy+caches; Cerebras deletes the wall
  with SRAM-everywhere and no caches. (Deep: `12`.)
- **vs Groq:** NVIDIA tolerates uncertainty dynamically; Groq removes it statically.
  (Deep: `14`.)

## Connection to LLM inference
- **TTFT** is set by prefill GEMM throughput → Tensor Core FLOPs + HBM for prompt/KV.
- **ITL** is set by decode weight+KV bandwidth → HBM bandwidth and batching
  (`../Inference/Continuous-Batching.md`).
- **KV cache** capacity → HBM capacity (80→288 GB across Hopper→Blackwell).
- **Multi-GPU tensor parallelism** → NVLink bandwidth (900 GB/s → 1.8 → 3.6 TB/s)
  (`../GPU-Systems/Tensor-Parallelism.md`, `08`).

## Key Takeaways
1. The GPU's core bet is *dynamic* scheduling: occupancy hides memory latency; the cost is
   the silicon that specialized chips delete.
2. Blackwell's move (2 dies, async single-thread MMA, TMEM) is the GPU walking *toward*
   the compiler-side of the design space — more autonomy per matmul instruction, less
   per-thread overhead.
3. NVLink domains (72→144→576) are the largest "one machine" in the industry; scale-out
   jumps 10–100× in latency past the domain.
4. CUDA is an architectural feature: the stack (PTX/SASS/cuBLAS/CUTLASS/Triton/engines)
   is part of why the silicon wins, not just a delivery vehicle (`09`).
5. "Fastest FLOPS" understates the GPU; "most flexible" overstates it — the GPU is the
   machine you buy when you don't yet know which regime you're paying for.

## Related
- `06-nvidia-sm-and-tensor-cores.md` — the SM and MMA internals
- `07-nvidia-memory-hierarchy.md` — HBM/L2/SMEM/TMA/warp specialization
- `08-nvidia-gpu-scaling.md` — NVLink/NVSwitch, scale-up vs scale-out
- `09-cuda-software-stack.md` — the software moat
- `../GPU-Systems/Architecture.md` — SIMT/kernel-level engineering
- `15-ai-chip-design-philosophies.md` — the six-bet map

## References
- NVIDIA H100/H200/B200/B300 datasheets (specs cited [F: vendor spec])
- NVIDIA Hopper/Blackwell architecture whitepapers; GTC 2024/2025 keynotes (Rubin, NVL576
  roadmap [F: vendor spec])
- PTX ISA documentation (mma.sync / wgmma / tcgen05 [F])
- `../GPU-Systems/_STYLE.md` — the wiki's H100/B200 constant set (cross-checked)
