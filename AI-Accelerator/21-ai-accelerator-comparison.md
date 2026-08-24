# AI Accelerator Comparison — The Two Matrices
`LAST_UPDATED: 2026-08-24` · Status: reference page · `[F]` = primary source cited inline (or a verified per-page value from this section); `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
Two matrices, two questions:
- **Matrix A (architectural):** *per-chip* — the compute ceiling, the on-chip SRAM, the off-chip HBM, the interconnect, the numerics, the scheduler. This is the *chip's identity*.
- **Matrix B (system):** *per-domain* — the scale-up domain size, the scale-out fabric, the aggregate memory, the worst-case latency, the software escape hatch. This is the *system's identity*.

The *rule*: **compare chips on Matrix A, compare systems on Matrix B, and never mix the two.** A *chip* comparison (Matrix A) tells you *the ceiling per die*; a *system* comparison (Matrix B) tells you *the largest model that behaves like one machine*. The *two matrices disagree* on the *ranking* — that disagreement is the *point* (a *low-peak* *chip* like the *Groq TSP* *wins* the *system* *comparison* on *batch-1 latency*, because *Matrix B* is where the *scheduled* *fabric* *lives*).

*Source note:* every value below is either `[F]` (a primary source or a value already verified on this section's per-chip pages 05–14) or `[E]` (computed from `[F]` data, with the formula in the page). Where a value is `UNVERIFIED`, it is flagged and *not* used in any `[E]` computation.

## Matrix A — Per-chip (architectural)
| Chip | Process | Peak (stated precision, dense) | On-chip SRAM | Off-chip HBM | HBM bandwidth | Scheduler | Optimized numerics |
|---|---|---|---|---|---|---|---|
| NVIDIA H100 (SXM5) | 4 nm TSMC [F] | 989 TFLOPS BF16; 1,979 TFLOPS FP8 [F] | 50 MB L2 + per-SM L1 [F: p05/07] | 80 GB HBM3 [F] | 3.35 TB/s [F: p05] | HW warp scheduler [F] | FP8 / BF16, FP32 accum [F] |
| NVIDIA H200 (SXM5) | 4 nm TSMC [F] | 1,979 TFLOPS FP8 [F] | 50 MB L2 [F: p07] | 141 GB HBM3e [F] | 4.8 TB/s [F] | HW warp scheduler [F] | FP8 / BF16 [F] |
| NVIDIA B200 | 4 nm TSMC (Blackwell) [F] | ~4,500 TFLOPS FP8 dense; ~9,000 TFLOPS FP4 dense / GPU [E/F: secondary] | L2 [F] | 192 GB HBM3e [F] | 8.0 TB/s [F] | HW warp scheduler [F] | NVFP4 (MX) / FP8 [F: NVIDIA] |
| Google TPU v4 | 7 nm [F: ISCA 2023] | ~275 TFLOPS BF16/chip [F: p10] | 128 MiB CMEM + 16 MiB VMEM/core [F: arXiv:2304.01433] | 32 GiB HBM2e [F] | 1.2 TB/s [F] | XLA (compiler) + ICI torus [F] | BF16 / INT8, FP32/INT32 accum [F] |
| Google TPU v5p | (announced) [F] | ~459 TFLOPS BF16/chip [UNVERIFIED: secondary] | CMEM [F: p10] | ~95 GB HBM2e [F: p10] | ~2.8 TB/s [F: p10] | XLA [F] | FP8 [F: Google] |
| Google TPU v7 Ironwood | (announced) [F] | 4,614 TFLOPS FP8/chip [F: p10] | CMEM [F] | 192 GB HBM [F: p10] | 7.2–7.4 TB/s [F: p10] | XLA [F] | FP8 [F: Google] |
| AMD MI300X | CDNA 3, 5/6 nm chiplets [F: p11] | ~1,307 TFLOPS FP16/BF16 dense/package [F: AMD spec] | 256 MB Infinity Cache [F: p11] | 192 GB HBM3 [F: p11] | 5.3 TB/s [F: p11] | HW warp (wavefront) scheduler [F] | FP8 / BF16 [F] |
| Cerebras WSE-2 | 5 nm [F: p12] | ~750 TFLOPS FP16/wafer [F: p12] | 40 GB on-wafer SRAM [F: p12] | none [F] | on-wafer (21 PB/s aggregate, not point-to-point [F: p12]) | Compiler-placed dataflow [F] | FP16/BF16 [F: p12] |
| Groq TSP (2022) | 14 nm GF [F: p14] | ~737 TOPS INT8 [E] (deck ~750); ~184–188 TFLOPS FP16 [E] | 220 MiB distributed [F: p14] | none [F] | on-chip streaming 20 TiB/s aggregate [F: p14] | Compiler-scheduled dataflow (intra + inter chip) [F: p14] | INT8 / FP16, INT32/FP32 accum [F] |
| AWS Trainium2 | (NeuronCore-v3) [F: p13] | 158 TFLOPS cFP8 dense/chip (316 sparse) [F: p13] | 224 MiB SBUF/core [F: p13] | 96 GiB HBM3e [F: p13] | 2.9 TB/s [F: p13] | Neuron compiler (offline) [F] | cFP8 (MX) [F: p13] |

*Reading Matrix A:* the *columns* are the *six axes* of *page 15* (compute, SRAM, HBM, bandwidth, scheduler, numerics). The *Groq TSP* row is the *outlier* in *two columns* (*SRAM* *per chip* *relative* to *peak*, and *scheduler* *rigidity*) — that *outlierness* is the *design bet*. The *H200* row is the *outlier* in *HBM capacity* (141 GB vs. 80 GB) — that is the *inference* *bet* (more *KV cache* per *chip).

## Matrix B — Per-system (the scale-up domain)
| System | Scale-up domain | Domain mechanism | Domain aggregate memory | Scale-out fabric | Worst-case E2E latency | Software escape hatch |
|---|---|---|---|---|---|---|
| NVIDIA DGX H100 | 8 GPUs (NVLink 4, 900 GB/s total/GPU [F]) | NVLink switch (NVL72: 72 GPUs [F]) | 8×80 = 640 GB HBM3 [E] | InfiniBand NDR / Ethernet (RoCE) [F] | n/a (routed; P99 variable) [I] | CUDA (widest) [F] |
| Google TPU v4 pod | 4,096 chips (ICI torus) [F: ISCA 2023] | ICI torus + OCS (Palomar) [F] | 4,096×32 GiB = 128 TiB [E/F: ISCA 2023 "128 TiB"] | ICI (the same fabric scales out) [F] | n/a (compiler-scheduled) [I] | XLA (open HLO) [F] |
| Google Ironwood pod | 9,216 chips [F: p10] | ICI torus [F] | 9,216×192 GB ≈ 1,769 TB ≈ 1,660 TiB [E] | ICI [F] | n/a [I] | XLA [F] |
| AMD MI300X-8 | 8 GPUs (XGMI) [F: p11] | Infinity Fabric [F] | 8×192 = 1,536 GB [E/F: p11] | InfiniBand NDR / Ethernet [F] | n/a [I] | ROCm (CUDA-portable) [F] |
| Cerebras CS-3 | 1 wafer (WSE-2) [F: p12] | RealScale (multi-wafer) [F: p12] | 40 GB on-wafer SRAM/wafer [F: p12] | RealScale [F] | n/a [I] | Cerebras compiler (closed; open front-ends) [F] |
| Groq GroqNode | 8 TSPs (C2C, 240 GB/s bisection [F: p14]) | Dragonfly (9 nodes/rack, 145 racks max [F: p14]) | 8×220 MiB = 1.75 GiB/node [E]; 10,440 TSPs ≈ 2.19 TiB [E] | Scheduled Dragonfly (not routed) [F: p14] | **< 3 µs worst-case E2E [F: ISCA 2022]** | Groq compiler (closed; no general-purpose path) [F] |
| AWS Trainium2 UltraServer | 64 chips (3D torus, 1,280 GB/s/chip [F: p13]) | NeuronLink [F] | 64×96 GiB = 6 TiB HBM3e [E] | EFA (400 Gb/s) [F: p13] | n/a [I] | Neuron SDK (open-source; cloud-bound) [F] |

*Reading Matrix B:* the *Groq* row is the *only* row with a *stated* *worst-case* *E2E latency* (*< 3 µs*) — *that* *is* the *determinism bet* (page 16, 18). The *NVIDIA* *row* is the *only* *row* with *the widest escape hatch* (CUDA). The *two columns* that *disagree* with *Matrix A* are *the domain size* and *the latency* — *a* *low-peak* *chip* (*Groq*) *can win* the *system* *comparison* *on latency*, and a *high-capacity* *chip* (*H200, MI300X*) *can* *win* it *on* *model fit*.

## The two-matrices disagreement (the point)
The *same* *six chips* *rank* *differently* on *Matrix A* vs *Matrix B*:

| Rank | Matrix A (per-chip peak) | Matrix B (system batch-1 latency) |
|---|---|---|
| 1 (best) | B200 (FP4) / MI300X (FP16) / H100 (FP8) | **Groq TSP** (< 3 µs worst-case) [F] |
| last | Groq TSP (FP16 ~187 TFLOPS) | H100 / MI300X (routed; P99 variable) [I] |

*The* *disagreement* *is* the *first-principles lesson*: **the per-chip peak (Matrix A) is necessary but not sufficient; the system's latency guarantee and model fit (Matrix B) decide the workload.** A *Groq* *TSP* *loses* *Matrix A* on *FP16* *peak* and *wins* *Matrix B* on *batch-1* *latency* — *that* *disagreement* *is* the *reason* *the* *two matrices exist* [I].

## How to read this page against the others
- **vs. pages 05–14:** those *provide* the *per-chip values*; this page *assembles* them into *two matrices*.
- **vs. page 15 (philosophies):** page 15 is the *six axes* in *prose*; this page is the *six axes* in *two matrices*.
- **vs. page 18 (interconnects):** this page's *Matrix B* *scale-up* *columns* *are* page 18's *domain* *table*.
- **vs. page 22 (workload mapping):** page 22 *uses* these matrices to *map* *workloads* to *chips*.
- **vs. page 23 (roofline):** page 23 *places* these matrices' *chips* *on* the *roofline* (the *compute ceiling* and the *bandwidth floor*).
