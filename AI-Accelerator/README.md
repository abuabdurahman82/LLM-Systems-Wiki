# AI Accelerator & Chip Architecture Engineering
`LAST_UPDATED: 2026-08-23` · Status: core section

> **From MatMul to Memory Systems to Rack-Scale AI Computers.**
> A first-principles handbook for reasoning about AI accelerator silicon — NVIDIA GPU,
> Google TPU, AMD Instinct, AWS Trainium, Cerebras WSE, Groq LPU — without vendor bias.
> Conceptual anchor: Jacob Peake, "AI Chip Architectures",
> `https://www.jacobpeake.com/ai-chip-architectures.html` (secondary source; all load-bearing
> numbers independently re-verified against primary sources — see `30-jacob-peake-ai-chip-architectures-review.md`).

## The one-sentence version
**Compute is important. Data movement is often more important.** Every architecture in this
section is a different answer to "which costs do we pay, and where?" — compute, memory,
data movement, programmability, predictability, scalability, energy, software.

## The twelve questions this section must answer
Given any chip, you should be able to answer:
1. Where does data live? (memory hierarchy, on-chip vs off-chip)
2. How does data move? (DMA, caches, scratchpads, scheduled links)
3. What actually performs the matrix multiply? (Tensor Core, MXU, Matrix Core, FMAC mesh, MXM)
4. How is non-matrix work executed? (CUDA cores, vector units, GPSIMD, VXM)
5. Who schedules execution: hardware or software? (dynamic warp scheduler vs compiler vs dataflow)
6. How is memory latency hidden or eliminated? (occupancy, prefetch, determinism, SRAM-everywhere)
7. How does one chip scale to many? (NVLink, ICI, NeuronLink, RealScale, wafer mesh)
8. How are collectives implemented? (NCCL kernels vs CC-Cores vs scheduled fabric)
9. What numerics does it optimize? (FP16/BF16 → FP8 → FP4, microscaling)
10. What software stack exposes it? (CUDA, ROCm, XLA/Neuron, Pallas, NKI, Cerebras compiler)
11. What workload is it optimized for? (training / prefill / batch-1 decode / HPC)
12. What tradeoff did the designers intentionally make? (the "bet")

## Reading order

### Foundations
- `01-why-ai-needs-specialized-chips.md` — Moore's Law, its five scalings, end of free
  single-thread scaling, the golden-age DSA argument, TPU v1 as proof point.
- `02-ai-compute-workloads.md` — the transformer as a sequence of matmuls; GEMM vs GEMV;
  training / prefill / decode arithmetic-intensity regimes.
- `03-memory-wall-and-data-movement.md` — arithmetic intensity, compute-vs-bandwidth scaling,
  the full memory hierarchy, why moving a number costs more than multiplying one.
- `04-how-to-analyze-an-ai-chip.md` — the 8-question analysis framework used for every
  architecture below.

### The six deployed architectures
- `05-nvidia-gpu-overview.md` / `06-nvidia-sm-and-tensor-cores.md` / `07-nvidia-memory-hierarchy.md` /
  `08-nvidia-gpu-scaling.md` / `09-cuda-software-stack.md` — GPU genealogy G80→Rubin, SM/warp/
  SIMT, Tensor Core evolution mma.sync→wgmma→tcgen05, HBM/TMA/warp specialization, NVLink/NVSwitch
  /scale-up vs scale-out, and the CUDA→Triton→engine stack.
- `10-google-tpu-architecture.md` — systolic arrays and the MXU, weight-stationary execution,
  software-managed scratchpads, XLA, ICI torus pods, v1→v8 genealogy.
- `11-amd-instinct-architecture.md` — GCN→CDNA genealogy, wave64 MFMA, chiplet strategy
  (XCD/IOD/Infinity Cache), ROCm/HIP stack, UALink/UEC direction.
- `12-cerebras-wafer-scale-engine.md` — wafer-scale integration, dataflow cores, SRAM-only memory,
  weight streaming for training vs SRAM-resident for inference, SwarmX.
- `13-aws-trainium-architecture.md` — NeuronCore specialized engines, SBUF/PSUM, CC-Cores
  (collectives in silicon), NeuronLink torus→NeuronSwitch, NKI.
- `14-groq-lpu-architecture.md` — deterministic functional-slice streaming, SRAM-only,
  software-scheduled Dragonfly networking, scheduled-not-routed.

### Cross-cutting analysis
- `15-ai-chip-design-philosophies.md` — six architectures, six bets (strengths/weaknesses/best-fit).
- `16-hardware-vs-software-scheduling.md` — the CPU→GPU→TPU→Groq spectrum, plus dataflow off-line.
- `17-ai-chip-memory-philosophies.md` — cache vs scratchpad vs distributed SRAM.
- `18-ai-accelerator-interconnects.md` — scale-up vs scale-out across all vendors; topologies.
- `19-ai-chip-software-stacks.md` — side-by-side software stacks and escape hatches.
- `20-ai-hardware-numerics.md` — FP32→TF32/BF16/FP16→FP8→FP6→FP4; microscaling; accumulation.
- `21-ai-accelerator-comparison.md` — the two comparison matrices (architectural + system specs).
- `22-workload-to-chip-mapping.md` — training/prefill/decode → hardware requirements; why
  tokens/s alone is not a metric.
- `23-roofline-across-ai-architectures.md` — one roofline model, six ways to move it.
- `24-the-rack-is-the-ai-computer.md` — card → server → rack → pod → AI factory.

### Strategy & selection
- `25-ai-hardware-ecosystem-strategies.md` — open vs vertically integrated; what each buys and costs.
- `26-emerging-ai-chip-architectures.md` — NPU/DPU/FPGA/ASIC, reconfigurable dataflow,
  compute-in-memory, analog, neuromorphic, photonic; and deployed non-flagship players
  (Tenstorrent, Tesla Dojo/AI5, Meta MTIA, Intel Gaudi, Etched, MatX, Taalas).
- `27-how-to-choose-ai-hardware.md` — the workload-driven decision tree.

### Practice
- `28-ai-chip-architecture-80-20.md` — the 20% of AI hardware knowledge that explains 80% of
  LLM performance (ten ideas).
- `29-ai-chip-zero-to-hero.md` — a 10-level learning path from binary arithmetic to architecture research.
- `30-jacob-peake-ai-chip-architectures-review.md` — provenance audit of the anchor article:
  claim-by-claim verification table.
- `31-the-big-idea-of-ai-chip-architecture.md` — the synthesis: one design space, eight axes,
  no universally optimal chip.

## Conventions (this section)
- SHIPPED / ANNOUNCED / PROJECTED are always separated explicitly on spec pages.
- Peaks are stated at the stated precision; dense vs sparse and per-die vs per-package vs
  per-rack vs per-pod are always distinguished.
- Memory bandwidth figures carry their tier: HBM for GPUs/TPUs/Trainium; **aggregate on-chip
  SRAM** for Cerebras/Groq. SRAM-bandwidth and HBM-bandwidth are different tiers and are
  **never** compared without saying so.
- All derived arithmetic is `[E]`-tagged with the arithmetic shown inline.
- Cross-links: `../Inference/Roofline.md`, `../GPU-Systems/GEMM.md`, `../KV-Cache/README.md`,
  `../Quantization/README.md`, `../Distributed-Inference/README.md`, siblings as bare filenames.

## Key Takeaways
1. The memory wall — not compute — is the first-order constraint for LLM inference; compute
   capacity is the first-order constraint for training/prefill.
2. "FLOPs" are meaningless without a precision, a dense/sparse basis, and a scope (die/package/rack).
3. Cache vs scratchpad vs distributed-SRAM is a philosophy choice, not an implementation detail.
4. The scale-up domain defines the largest model that behaves like one machine; everything
   beyond it pays network latency.
5. The rack — silicon + HBM + optics + switches + compiler + runtime — is increasingly the unit
   of design. Comparing bare chips is a 2022 habit.

## Related
- `../GPU-Systems/README.md` — NVIDIA-centric deep engineering (kernels, engines, multi-GPU)
- `../Hardware/README.md` — component-level silicon specs
- `../Distributed-Inference/README.md` — parallelism strategies and their communication costs
- `../Inference/Roofline.md` — the roofline model
- `../Learning-Path/Zero-to-Hero.md` — the wiki-wide path

## References
- Jacob Peake, "AI Chip Architectures", jacobpeake.com (2026) — conceptual anchor [secondary]
- Hennessy & Patterson, "A New Golden Age for Computer Architecture", ISCA 2018 Turing Lecture
- Google TPU v1 paper (arXiv:1704.04760), TPU v4 paper (arXiv:2304.01433)
- Groq ISCA 2020 ("Think Fast") & ISCA 2022 (software-defined TSP multiprocessor)
- AWS Neuron documentation (NeuronCore v2/v3/v4 architecture pages, awsdocs-neuron.readthedocs-hosted.com)
- NVIDIA architecture whitepapers (Hopper, Blackwell); AMD CDNA documentation; Cerebras public disclosures
