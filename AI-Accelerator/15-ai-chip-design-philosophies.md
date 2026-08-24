# AI Chip Design Philosophies — Six Architectures, Six Bets
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference.

## 30-Second Explanation
Every major AI accelerator is a *bet*: a deliberate trade of one scarce resource (generality, power, latency, memory capacity, bandwidth, software momentum) for another. A GPU bets on **generality + ecosystem**. A TPU bets on **per-flop efficiency + a closed, compiler-driven system**. Cerebras bets on **putting the whole memory on one wafer**. Groq bets on **a scheduled, deterministic dataflow with zero on-chip DRAM**. Trainium bets on **cost-per-token with an open, cloud-owned system**. AMD bets on **HBM bandwidth and ROCm parity**. This page is the comparison frame: six bets, each scored on the axes that actually decide a workload fit (pages 04's twelve questions, compressed to six), with a worked roofline example (page 23) and a decision tree (page 28).

The single most important insight: **the six chips are not on one line of "better/worse." They are on different axes.** A Groq TSP is not "worse than an H100" — it is answering a *different question* (deterministic batch-1 latency vs. aggregate throughput). The rest of this page makes that concrete.

## The six bets
| Chip | The bet (one line) | What it gives up |
|---|---|---|
| **NVIDIA GPU** | Maximum generality + the CUDA ecosystem; hardware-scheduled SIMT [F: NVIDIA] | Per-flop efficiency, deterministic latency, a fixed power envelope you can't beat |
| **Google TPU** | Per-flop efficiency via systolic MXU + HBM + ICI torus, all driven by XLA [F: Google ISCA 2023] | Generality, open ISA, out-of-Google availability |
| **AMD Instinct** | HBM3e/4 bandwidth + CDNA matrix cores, ROCm-compatible with CUDA workloads [F: AMD] | Software momentum (ROCm < CUDA), some per-flop efficiency |
| **Cerebras WSE** | One wafer = one machine; 40 GB on-wafer SRAM, no off-chip memory, RealScale scale-out [F: Cerebras] | Yield, cost, generality, a single huge die you can't patch |
| **Groq TSP** | Software-scheduled dataflow, deterministic latency, zero on-chip DRAM [F: ISCA 2022] | Generality, a fixed model (must be compiled), scale-up ceiling |
| **AWS Trainium** | Cost-per-token via cFP8 + HBM3e + NeuronLink, open to any cloud customer [F: AWS] | Per-flop peak, software maturity, a closed cloud dependency |

## The six axes (a compressed page-04 framework)
Page 04 gives the full twelve-question framework. For a six-way comparison, six axes capture 90% of the variance:

1. **Compute ceiling** — peak FLOPs at the working precision, dense (not sparse), die/package/rack scope stated.
2. **Memory architecture** — on-chip SRAM size, off-chip HBM capacity and bandwidth, and *where the model weights live*.
3. **Scheduling** — hardware (warp scheduler), software (compiler-placed scratchpads), or dataflow (compile-time graph).
4. **Scale-up domain** — the largest N of chips that behaves like one machine (NVLink domain, ICI pod, RealScale, NeuronLink group).
5. **Numerics** — FP16/BF16 → FP8 → FP4, and whether microscaling (MX) is supported.
6. **The escape hatch** — the software path that lets you run a workload the chip wasn't designed for (CUDA, ROCm, XLA, Pallas, NKI, Cerebras compiler).

Each axis is scored below per chip. Tags: `[F]` = cited, `[E]` = computed, `[I]` = inferred, `UNVERIFIED` = not primary-source-confirmed.

## Axis 1 — Compute ceiling
Peak values are at the chip's **stated working precision**, **dense** (not 2:4-sparse), and **per-chip** unless noted. This is the number to compare; the "sparse" or "exaFLOPS" marketing numbers are different questions.

| Chip | Precision | Peak (dense, per chip) | Tag |
|---|---|---|---|
| NVIDIA H100 | BF16 | ~989 TFLOPS (HBM3, SXM5) | [F: NVIDIA, page 05] |
| NVIDIA H100 | FP8 | ~1,979 TFLOPS | [F: NVIDIA] |
| NVIDIA H200 | FP8 | ~1,979 TFLOPS | [F: NVIDIA] |
| Google TPU v4 | BF16 | ~275 TFLOPS/chip | [F: ISCA 2023, arXiv:2304.01433] |
| Google TPU v5p | BF16 | ~459 TFLOPS/chip (≈3.3× v4) — secondary-source estimate; no primary per-chip BF16 figure in the verified sources | [F/UNVERIFIED] |
| AMD MI300X | FP16/BF16 | ~1,307 TFLOPS (dense, package) [F: AMD spec] | [F: AMD] |
| Cerebras WSE-2 | FP16 | ~750 TFLOPS (wafer) | [F: Cerebras] |
| Groq TSP | INT8 (Acc32) | ~737 TOPS/chip [E] (deck ~750) | [F/E] |
| Groq TSP | FP16 | ~184–188 TFLOPS/chip [E] | [F/E] |
| AWS Trainium2 | cFP8 | 158 TFLOPS/chip (dense; 316 with sparsity) | [F: AWS, page 13] |
| AWS Trainium3 | cFP8 | (next-gen; peak not yet primary-source-published) | UNVERIFIED |

**The first-principles read:** the compute ceiling is *necessary but not sufficient*. A Groq TSP at ~187 TFLOPS FP16 looks weak next to a MI300X at ~1,307 TFLOPS FP16 — but the Groq TSP is not trying to win the FP16-throughput race. It is trying to win the *batch-1-latency* race, where the compute ceiling is irrelevant and the *SRAM bandwidth + scheduling* is everything (page 23's roofline makes this precise).

## Axis 2 — Memory architecture
This is where the bets diverge most. The question is not "how much memory?" but **"where do the model weights live, and how fast can a single token's decode stream them?"**

| Chip | On-chip SRAM | Off-chip (HBM) | Model weights live in |
|---|---|---|---|
| NVIDIA H100 | 50 MB L2 (per SM ~288 KB L1) | 80 GB HBM3, 3.35 TB/s | HBM (weights), SRAM (activations) |
| Google TPU v4 | 128 MiB CMEM + 16 MiB VMEM/core | 32 GiB HBM2e, 1.2 TB/s per chip (v4 [F: ISCA 2023]) | HBM, streamed to CMEM |
| AMD MI300X | 256 MB L2 + per-GCD cache | 192 GB HBM3, 5.3 TB/s | HBM |
| Cerebras WSE-2 | 40 GB on-wafer SRAM | none | on-wafer SRAM (the whole model, small ones) |
| Groq TSP | 220 MiB distributed | none | on-chip SRAM (the whole model, must fit) |
| AWS Trainium2 | 224 MiB SBUF/core | 96 GiB HBM3e, 2.9 TB/s | HBM, streamed to SBUF |

**The two regimes:**
- **HBM regime (NVIDIA, AMD, TPU, Trainium):** the model is too big for on-chip SRAM, so it lives in HBM and is *streamed* to SRAM by the memory hierarchy. The cost is the HBM bandwidth (the "memory wall," page 03). A batch-1 decode is bandwidth-bound: token rate ≈ HBM-bandwidth / (model-size × bytes-per-param).
- **SRAM regime (Cerebras, Groq):** the model *must fit* in on-chip SRAM, so there is no HBM at all. The cost is that the model is bounded in size (Groq: 220 MiB/TSP × N TSPs; Cerebras: 40 GB/wafer). But the payoff is that a batch-1 decode is *compute-bound or schedule-bound*, not bandwidth-bound — because the weights are already in the fastest memory on the chip.

This is the entire design philosophy in one table. Everything else (scheduling, interconnect, software) is a consequence of which regime you're in.

## Axis 3 — Scheduling
| Chip | Scheduler | What it means |
|---|---|---|
| NVIDIA GPU | Hardware warp scheduler (dynamic) | Max latency hiding via occupancy; tail latency is variable |
| AMD GPU | Hardware warp scheduler (dynamic) | Same as NVIDIA, with AMD-specific warp (wavefront) size |
| Google TPU | XLA (compiler, offline) | Placed into CMEM; deterministic *if* the model is static |
| Cerebras | Compiler-placed dataflow (offline) | Whole-wafer placement; deterministic, but the model is fixed |
| Groq TSP | Compiler-placed dataflow (offline) | Most deterministic: *inter-chip* path is also scheduled |
| AWS Trainium | Neuron compiler (offline) | Placed into SBUF; deterministic, but less rigid than Groq |

The CPU→GPU→TPU→Groq spectrum is the theme of page 16. The short version: **hardware schedulers buy latency-hiding (occupancy); software schedulers buy determinism (known latency).** You cannot have both for free — the Groq TSP gives up latency-hiding to get a *known* latency, which is the right trade only for batch-1, latency-sensitive workloads.

## Axis 4 — Scale-up domain
The largest N of chips that behaves like *one machine* (shared memory / scheduled fabric, no PCIe hop). This is the single most important number for "what's the biggest model I can run without a PCIe/NIC penalty?"

| Chip | Scale-up domain | Mechanism |
|---|---|---|
| NVIDIA | 8 GPUs (NVLink 5) / 72 (NVLink switch, NVL72) | NVLink 5, 1.8 TB/s/GPU [F: NVIDIA] |
| Google TPU | 9,216 chips (Ironwood pod) / 9,600 (v8 superpod) | ICI torus / Boardfly [F: Google] |
| AMD | 8 GPUs (Infinity Fabric) | MI300X XGMI [F: AMD] |
| Cerebras | 1 wafer (WSE-2), RealScale to 256+ | on-wafer + RealScale [F: Cerebras] |
| Groq | 8 TSPs (node) / 264 (33-node Dragonfly) / 10,440 (145-rack) | scheduled Dragonfly [F: ISCA 2022] |
| AWS Trainium | 8 (NeuronLink) / 64 (Trn2) / 128 (Trn3) | NeuronLink [F: AWS] |

**The first-principles read:** the scale-up domain defines the largest model that *behaves like one machine*. A 70B model at FP16 (135.6 GB) fits in one H100-8 (80 GB × 8 = 640 GB) with room for KV cache — so an H100-8 is the natural unit. A 70B model at FP16 does *not* fit in one Groq TSP (220 MiB), so it must be spread across ~576 TSPs (page 14) — and the *scheduled Dragonfly* is what makes that 576-chip spread feel like one machine. The scale-up domain is the load-bearing constraint for any multi-chip model.

## Axis 5 — Numerics
The precision ladder is FP32 → TF32/BF16/FP16 → FP8 → FP6 → FP4, with microscaling (MX) for the low-precision formats. Which format a chip optimizes for is a *bet* about where the accuracy/quality tradeoff lives for the target workload.

| Chip | Optimized precision | Microscaling (MX)? | Tag |
|---|---|---|---|
| NVIDIA H100/H200 | FP8 (E4M3/E5M2) | no (MX is H100+ via FP8) | [F: NVIDIA] |
| Google TPU v5p | FP8 (E5M2/E4M3) | no | [F: Google] |
| AMD MI300X | FP8 (E5M2/E4M3) | no | [F: AMD] |
| Cerebras WSE-2 | FP16/BF16 (FP8 on WSE-3) | no | [F: Cerebras] |
| Groq TSP (2022) | INT8 / FP16 | no (FP8 on TSP v2) | [F: ISCA 2022] |
| AWS Trainium2 | cFP8 | yes (cFP8 is AWS's microscaling) | [F: AWS] |

**The first-principles read:** FP8 halves the bytes-per-param vs FP16, so it halves the memory wall for the same model. But it costs accuracy — which is why the *microscaling* formats (FP8, FP4, MX) matter: they keep the *dynamic range* of FP16 in a lower-precision container by scaling per-block. Trainium's cFP8 and NVIDIA's FP4/MX are both bets that "the model is fine at FP8/FP4 if you scale per-block." Page 20 (numerics) develops this.

## Axis 6 — The escape hatch
The software path that lets you run a workload the chip wasn't designed for. This is the *option value* of the platform: how much can you lose if the chip's native workload doesn't fit?

| Chip | Native stack | Escape hatch |
|---|---|---|
| NVIDIA | CUDA + cuDNN + NCCL | CUDA is *the* escape hatch — every other chip chases it |
| Google TPU | XLA + JAX/TF | PyTorch-via-XLA, but the compiler is closed |
| AMD | ROCm | CUDA→ROCm porting (hipify); improving but not CUDA |
| Cerebras | Cerebras CS-3 compiler | PyTorch/JAX front-ends, but the compiler is closed |
| Groq | Groq compiler (closed) | limited — the model *must* be compiled to the TSP |
| AWS Trainium | Neuron SDK | PyTorch/JAX front-ends, open-source compiler |

**The first-principles read:** the escape hatch is *inverse* to the determinism bet. A Groq TSP has the smallest escape hatch (you must compile the model, no general-purpose path) *because* it made the most aggressive determinism bet. An NVIDIA GPU has the largest escape hatch (CUDA runs anything) *because* it made no determinism bet. This is the trade you're actually buying when you pick a chip.

## Worked example: where does a 70B model fit?
A concrete application of the six axes. Llama-2 70B: 67.8 B params [F: Meta HF].

**At FP16 (135.6 GB weights [E]):**
- **H100-8 (640 GB HBM):** fits with ~500 GB headroom for KV cache. Batch-1 decode is HBM-bandwidth-bound. Under tensor-parallelism each H100 holds [E] 135.6 / 8 = **16.95 GB** of weights, so one decode step streams 16.95 GB at 3.35 TB/s = [E] **5.06 ms/token → ~198 tok/s at 100% HBM efficiency** for the 8-GPU system (all chips stream their shard in parallel; the AllReduce on each layer adds a small overhead [I]). At a realistic ~30–50% HBM utilization for a decode-bound kernel [I], that is **~60–100 tok/s**, which matches published batch-1 numbers for Llama-2-70B on 8×H100 [I].
- **Groq 576-TSP (132.5 GB aggregate SRAM):** does *not* fit at FP16 (135.6 GB > 132.5 GB) — so it must run at INT8 (67.8 GB), which fits with ~64 GB headroom for KV cache [I]. This is exactly what Next Platform reports (INT8, 512-in/1024-out, > 300 tok/s) [F].
- **Cerebras WSE-2 (40 GB on-wafer):** does *not* fit at FP16 or INT8 (67.8 GB > 40 GB) — so Cerebras runs 70B models across multiple WSEs in RealScale, or at a lower precision [I].

**At FP8 (67.8 GB weights [E]):**
- **H100-8:** fits with ~570 GB headroom; ~2× the FP16 token rate [E].
- **Groq 576-TSP:** fits at FP8 with ~64 GB headroom, same as INT8 [E].
- **Cerebras WSE-2:** *just* fits at FP8 (67.8 GB > 40 GB, still no) — needs RealScale [I].

The example shows the six axes working together: the *compute ceiling* (axis 1) is irrelevant for the Groq TSP at batch-1; the *memory architecture* (axis 2) is the deciding factor; the *scale-up domain* (axis 4) determines how many TSPs you need; and the *numerics* (axis 5) determine whether the model fits at all.

## The decision frame (preview of page 28)
The six axes compress to a three-question decision:
1. **What's my batch size?** Batch-1 → Groq/Cerebras (SRAM regime). Batch-N → NVIDIA/AMD/TPU/Trainium (HBM regime).
2. **What's my latency budget?** P99 must be *known* → Groq. P50 is fine → GPU/TPU.
3. **What's my model size?** Must fit in on-chip SRAM → Groq/Cerebras. Fits in HBM → everything else.

Page 28 turns this into a full decision tree.

## How to read this page against the others
- **vs. page 04:** this is the *application* of the twelve-question framework to the six chips; page 04 is the *framework*.
- **vs. pages 05–14:** those are the per-chip deep dives; this is the cross-chip comparison.
- **vs. page 16 (scheduling):** this page's axis 3 is a one-line summary; page 16 is the full CPU→GPU→TPU→Groq spectrum.
- **vs. page 17 (memory):** this page's axis 2 is a one-line summary; page 17 is the cache-vs-scratchpad-vs-distributed-SRAM deep dive.
- **vs. page 18 (interconnects):** this page's axis 4 is a one-line summary; page 18 is the scale-up/scale-out topology comparison.
- **vs. page 19 (software):** this page's axis 6 is a one-line summary; page 19 is the side-by-side software-stack comparison.
- **vs. page 23 (roofline):** this page's "worked example" is a *memory* example; page 23 is the *compute* roofline that makes the bandwidth-vs-FLOPS trade precise.
- **vs. page 28 (decision tree):** this page's "decision frame" is the preview; page 28 is the full tree.
