# Hardware vs. Software Scheduling — The CPU → GPU → TPU → Groq Spectrum
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
"Who schedules the next operation?" is the single deepest architectural question in this section, because it decides *where latency comes from* and *whether latency is knowable before the program runs*. The spectrum runs: **CPU** (in-order / OOO hardware pipeline, nanosecond-scale decisions) → **GPU** (hardware warp scheduler, hardware hides latency by context-switching thousands of warps) → **TPU** (XLA compiler places tensors in CMEM; hardware executes the placed plan) → **Groq** (the compiler places the *entire* dataflow, including the *inter-chip* path; the hardware has essentially nothing left to decide). Every step rightward trades **flexibility** for **determinism**. This page maps the spectrum, quantifies what "hiding" vs. "eliminating" latency actually buys, and shows why the two ends (GPU and Groq) are *not* comparable on a single metric.

The key insight: **a hardware scheduler buys *expected* latency via occupancy; a software scheduler buys *maximum* latency via placement.** Those are different numbers, and confusing them is how you end up picking the wrong chip.

## The four scheduling regimes

### 1. CPU — in-order / out-of-order pipeline
A modern CPU core has a fetch → decode → dispatch → execute → retire pipeline. The *out-of-order* (OOO) window (tens-to-hundreds of instructions, e.g. 200–400 ROB entries on a server core [I]) lets the core *reorder* independent instructions to keep the functional units busy while a load misses. The "scheduler" is the **reorder buffer + issue logic**, operating at nanosecond scale, per-core.

- **What it hides:** individual cache misses (L1/L2/L3) via the OOO window.
- **What it can't hide:** a DRAM miss (hundreds of cycles) unless you have *another* independent instruction ready — which is exactly the OOO window's job.
- **Why it's not enough for AI matmuls:** a matmul is a *dense, regular, dependent* dataflow. The OOO window can't reorder the 409,600 MACs of a 320×320 tile because they are *dependent* (each output depends on the full dot product). The OOO window hides *irregular* latency (loads); it cannot hide *regular* dependency chains. That is why you need a systolic array (page 10) or a tensor core (page 06) to do matmuls at all.

### 2. GPU — hardware warp scheduler, latency-hiding via occupancy
A GPU SM has a hardware **warp scheduler** that picks, every cycle, *which warp issues next*. A warp is 32 (NVIDIA) or 64/32 (AMD wavefront) lanes executing in lockstep (SIMT). When a warp's load misses, the scheduler **swaps in another ready warp** — the miss is hidden by *context-switching*, not by reordering. This is **occupancy**: the fraction of the SM's available warps that are actually resident.

- **What it hides:** HBM misses (hundreds of cycles) *if there are enough other warps to switch to*.
- **The trade:** occupancy requires *many* independent threads. A batch-1 GEMV (decode) has very few independent threads, so occupancy is low, and the HBM miss is *not* hidden — it shows up directly in the token latency. This is the single most important fact in this section: **batch-1 decode is the regime where the GPU's latency-hiding mechanism stops working** (page 03's memory wall bites hardest exactly here).
- **Determinism:** the warp scheduler is *hardware* and *dynamic*, so the *tail* latency is *not known in advance*. The P99 can be 2× the P50 when a warp gets stuck on a contended HBM bank (page 14's BERT-base example: GPU P99 jumps 25% over P50 due to cache-contention [F: Answer Fast]).

### 3. TPU — XLA compiler places tensors; hardware executes the plan
XLA (Accelerated Linear Algebra) compiles the model into a HLO (High-Level Operations) graph, then *places* each tensor into a specific CMEM (Common Memory) slot and schedules the MXU (Matrix Multiply Unit) operations in a fixed order. The hardware executes that *placed plan*; the MXU is a systolic array that runs the placed matmul in a deterministic, pipelined fashion.

- **What the compiler does:** decides *where each tensor lives* and *in what order the MXUs run*. The hardware does not re-decide this at runtime.
- **What the hardware still does:** routes data through the ICI (Inter-Core Interconnect) torus between chips, and manages the HBM<->CMEM streaming. The *inter-chip* path is hardware-routed (torus), not compiler-scheduled.
- **Determinism:** *intra-chip* latency is deterministic (the CMEM placement + MXU pipeline is fixed). *Inter-chip* latency is *mostly* deterministic but still subject to the torus routing (a hop to a neighbor is fixed, but a multi-hop path can vary). So TPU is *deterministic at the chip, near-deterministic at the pod*.
- **The escape hatch:** XLA is open, and the HLO graph is inspectable — so you can see *why* a model is slow. This is a big advantage over Groq (page 19).

### 4. Groq — the compiler places the *entire* dataflow, including inter-chip
Groq's TSP takes the TPU's thesis and extends it: the compiler places *not just the intra-chip tensors* but the *entire inter-chip dataflow* into the 45 SRFs and the 64 streaming lanes. The Dragonfly interconnect is *scheduled by the compiler*, not routed by hardware routers (page 14). There is no hardware warp scheduler, no warp, no SIMT — the *program is the schedule*.

- **What the compiler does:** decides every SRF allocation, every lane transfer, every MAC, and every *inter-chip* hop. The hardware has *nothing left to decide*.
- **What the hardware still does:** physically move the data. But the *time* it takes is fixed at compile time (the < 3 µs worst-case end-to-end [F: ISCA 2022]).
- **Determinism:** *total*. The P99 is *known at compile time*, to within 2% (the 24,240-run BERT-Large histogram [F: ISCA 2022]).
- **The cost:** the model *must be compiled*. You cannot run an arbitrary workload; you cannot add a new layer at runtime. The escape hatch is essentially closed (page 19).

## The spectrum, quantified
The four regimes are on a single axis: **fraction of the schedule decided at compile time vs. run time.**

| Regime | Compile-time decisions | Run-time decisions | Latency knowable? | Tail latency (P99/P50) |
|---|---|---|---|---|
| CPU OOO | none (the compiler emits instructions) | per-instruction reorder | no | n/a (OOO window reorders dependent work) [I] |
| GPU SIMT | kernel launch order | per-cycle warp pick | no | P99 ≈ +25% over mean (SOTA GPU BERT-base: 630 → 790 µs) [F: Answer Fast] |
| TPU + XLA | tensor placement, MXU order | ICI torus routing, HBM streaming | mostly | n/a (no published tail histogram in the ISCA 2023 v4 paper) [UNVERIFIED] |
| Groq TSP | *entire* dataflow (intra + inter chip) | nothing | **yes** | P99 = +0.4% over mean (TSP BERT-base [F]); P99 < 1,225 µs over P100 = 1,300 µs on BERT-Large, within 2% of the compiler prediction over 24,240 runs [F: ISCA 2022] |

The table is the whole argument: **as you move right, the P99/P50 ratio collapses toward 1.** That is the *measurable* signature of "software scheduling" — the tail disappears.

## Why "hiding" and "eliminating" are not the same
A GPU *hides* latency: a 400-cycle HBM miss is hidden *if* there is another warp to run during those 400 cycles. The miss *still happens*; it just doesn't show up in the critical path. The cost of hiding is **occupancy** (you need enough warps) and **power** (you keep the warps' state in the registers).

A TPU/Groq *eliminates* latency: the tensor is *already in the right SRAM slot* when the MXU/MXM needs it. There is no miss, no prefetch, no snoop. The cost of eliminating is **placement** (the compiler must know the model in advance) and **SRAM capacity** (the model must fit).

The first-principles difference: **hiding is a *statistical* guarantee (the miss is hidden *on average*); eliminating is a *deterministic* guarantee (the miss *never happens*).** For a batch-1 service where the P99 is the product, the deterministic guarantee is worth more — and that is exactly the bet Groq makes.

## The workload → regime map
| Workload | Right regime | Why |
|---|---|---|
| Training (large batch) | GPU / TPU | High occupancy hides HBM; the P99 is irrelevant (you optimize throughput) |
| Prefill (long prompt, batch-N) | GPU / TPU | High arithmetic intensity (GEMM), high occupancy, HBM is fine |
| Batch-1 decode (latency-critical) | **Groq** (or Cerebras) | Occupancy is ~0; the GPU's hiding fails; the SRAM regime wins |
| Batch-1 decode (cost-critical) | GPU / TPU / Trainium | The P99 is less important than the $/token; HBM is cheaper than SRAM |
| HPC / scientific | GPU | Generality + the CUDA ecosystem; the latency tail is not the product |
| Real-time (voice, search, translation) | **Groq** | The P99 *is* the product; the compile-time guarantee is worth the closed stack |

The map is the payoff of the spectrum: **you pick the regime that matches the workload's latency sensitivity, not the regime with the highest FLOPs.**

## The CPU limit (page 01's first-principles)
Page 01 establishes that the CPU's single-thread performance grew ~52%/yr in 1990 and ~3%/yr by 2018 [F: anchor]. The OOO window is the *last* CPU trick: it hides latency, but it cannot eliminate it. The CPU is the *left end* of the spectrum — the regime where *all* scheduling is run-time and *no* latency is eliminated. Every AI accelerator in this section is a move *right* along the spectrum: GPU (hide more, via occupancy), TPU (eliminate more, via placement), Groq (eliminate *all*, via a scheduled dataflow). The CPU is not a competitor in AI — it is the *reference point* against which every accelerator's determinism is measured.

## The "dataflow off-line" point
The Groq TSP is sometimes described as "offline dataflow" — the dataflow is *fixed at compile time*, not at runtime. This is a *stronger* claim than "the model is static": even the *inter-chip* path is fixed. A TPU's ICI torus is *hardware-routed* — the torus can route a packet around a congested link. A Groq Dragonfly is *compiler-scheduled* — the path is *the* path, and it is *known*. This is why the Groq worst-case latency is a *scheduled* time (< 3 µs), not a *measured* tail: the scheduler *chose* the path, and the path *is* the latency.

The practical consequence: **a Groq system's latency is *design-time-fixed*, not *runtime-measured*.** You can *know* the P99 before the system is built. No GPU or TPU system offers that. (The 24,240-run histogram is a *verification* that the design-time prediction holds, not a *measurement* of the latency [F: ISCA 2022].)

## How to read this page against the others
- **vs. page 04:** page 04's question #5 ("Who schedules execution: hardware or software?") is answered here, in depth.
- **vs. pages 05–14:** those are the per-chip deep dives; this is the cross-chip scheduling comparison.
- **vs. page 15 (philosophies):** this page's "workload → regime map" is the *scheduling* axis of page 15's six-axis frame.
- **vs. page 23 (roofline):** the roofline shows *why* batch-1 decode is bandwidth-bound (the GPU's hiding fails); this page shows *what* the alternatives (TPU/Groq) do instead.
- **vs. page 30 (fact-check):** the "GPU P99 jumps 25% over P50" figure is from the Answer Fast paper [F]; page 30 verifies it.
