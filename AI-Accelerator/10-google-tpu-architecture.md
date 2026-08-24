# Google TPU Architecture
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = Google TPU papers/docs/blogs.

## 30-Second Explanation
The TPU is the inverse of the GPU: instead of *programmable hardware with dynamic
scheduling*, it is a **large matrix engine (the MXU) wrapped in just enough silicon to keep
it fed, with the *compiler* as the scheduler**. One chip is a big systolic array that reuses
operands in its own wiring, software-managed scratchpads (VMEM) that the compiler places data
into explicitly, and no hardware cache to hide mistakes — the schedule must be right, because
there is no fallback. That trade has paid off: the same philosophy has run from TPU v1 (2015,
92 TOPS INT8) to TPU v8 (2026, 9,600-chip pods), training Gemini and (announced) serving a
million-chip Anthropic deployment. [F: TPU v1 paper; Google Cloud TPU docs; Peake article
(deployment claim, [F: secondary])]

## The two philosophies, side by side
```
GPU:
  hardware is general + dynamic; a thousand SMs each run whatever the warp scheduler says
  -> latency hidden by occupancy; compiler is a helper; programmer writes kernels
TPU:
  hardware is specialized + static; ONE (or two) MXU per chip does the matmul
  -> compiler schedules the whole program (VLIW bundles); programmer writes the model,
     XLA writes the schedule; scratchpads make data movement explicit
```
The MXU (Matrix Multiply Unit, Google calls its compute unit "TensorCore") is a **systolic
array**: a grid of MACs where data *waits in place* while operands flow through the grid in
lockstep, so every MAC in every row and column reuses data already on its wires. No
register-file round-trip per multiply — **the array is its own data-reuse hierarchy**.

### Systolic array intuition (the animation)
A 4×4 array computing C = A(4×4) @ B(4×4). A enters from the left row-by-row; B from the
top column-by-column; each cell holds its partial sum and adds `a×b` when both are present:
```
t=0:  B columns enter top        A rows enter left
t=1:   b00 b01 b02 b03            -> row 0: a00 a01 a02 a03
      b10 b11 b12 b13
t=2:   .   b01 b02 b03            .
      .   b11 b12 b13
      .   .   b12 b13             <- the B values shift DOWN one cell per clock
      .   .   .   b23                  A values shift RIGHT one cell per clock
t=n:   every cell (i,j) has seen A[i,:] x B[:,j] accumulated in place
```
After ~2N clocks every output C[i,j] sits at cell (i,j). Cost: O(1) on-chip memory traffic
for O(N³) work — that *is* the systolic idea. The TPU v1's array was 256×256 8-bit MACs
(65,536 MACs, 92 TOPS INT8) [F: arXiv:1704.04760]; v2+ doubled width and precision (128×128
16-bit, then 256×256 on Trillium [F: Google Cloud docs/blog]); Trillium's 256×256 MXU is
what "4.7× v5e peak FLOPS" comes from [F: Google blog 2024].

**Weight-stationary vs streaming:** in the TPU's execution the *weight tile* is loaded into
the array and held (weight-stationary), while *activation tiles* stream through; partial
sums emerge and are read out. "Weight-stationary" is one of several dataflow schedules
(activation-stationary, output-stationary); the TPU/Trainium family uses the weight-held
variant because weights are the reused operand across the batch. [I: scheduling terminology;
per-machine behavior F]

## Genealogy (SHIPPED / ANNOUNCED)
| Gen | Year | Key facts (primary sources) |
|---|---|---|
| TPU v1 | 2015–18 | 92 TOPS INT8, 65,536 8-bit MACs (256×256), 28 MiB SRAM, inference-only. SHIPPED [F: arXiv:1704.04760] |
| TPU v2 | 2017–19 | 16-bit MXU 128×128 (two per chip on some configs); training; BF16/FP16. SHIPPED [F: Google docs] |
| TPU v3 | 2019–21 | 4× v2 compute, 1.14 TB/s ICI, 3D torus pods up to 1,024 chips. SHIPPED [F: arXiv (v3 paper, "In-Datacenter Performance Analysis of a TPU v3" — arXiv ID UNVERIFIED at authoring time; cite Google docs)] |
| TPU v4 / v4i | 2022–23 | First **reconfigurable optical circuit switches** (Palomar) in ICI; SparseCores (embedding lookup offloaded from MXU); BF16+INT8; 4,096-chip pods; peak **275 TFLOPS (BF16 or INT8)** [F: ISCA 2023 Table, arXiv:2304.01433]. SHIPPED [F: arXiv:2304.01433] |
| TPU v5e / v5p | 2023–24 | Split: v5e efficiency (inference/embeddings), v5p performance; v5p 3.3× v4 INT8 FLOPS, 2.2× HBM bandwidth, 8,960-chip pods at 4,800 Gbps/chip ICI in 3D torus. SHIPPED [F: Google Cloud blog 2023-12] |
| Trillium (v6e) | 2024–25 | First 256×256 MXU; 4.7× v5e peak FLOPS at similar power; 256-chip pods; trained Gemini 2.0; 2 SparseCores/chip. SHIPPED [F: Google blog 2024-10] |
| TPU v7 "Ironwood" | 2025–26 | Inference-focused; 4,614 TFLOPS FP8 per chip (first TPU with native FP8 at this class), 192 GB HBM, 7.2–7.4 TB/s, ICI 1.2 TB/s bidirectional; 256- or 9,216-chip pods; 42.5 ExaFLOPS FP8 at pod scale. SHIPPED/GA April 2026 [F: Google "What's new with AI Hypercomputer" + Cloud Next coverage] |
| TPU v8 (8t / 8i) | 2026 | Training (8t) + inference (8i) split, "agentic era"; adds native FP4; 8t superpod 9,600 chips, ~2 PB shared HBM, 121 ExaFLOPS; ICI doubled to 19.2 Tb/s with new **Boardfly** topology (halves max network diameter). SHIPPING/ANNOUNCED [F: Google blog 2026] |
Note: per-chip TFLOPS/HBM for v5p/Ironwood/8t are from Google announcements; where Google
quotes a pod number (42.5 ExaF, 121 ExaF) it is the vendor's own aggregate — treat as
[F: vendor claim], not an independent measurement.

## Memory: scratchpads vs caches
```
registers -> MXU internal (operands ride the array's wires)
VMEM      -> software-managed on-chip SRAM (v4 era: ~128 MB+; the "scratchpad");
             the COMPILER moves tiles HBM<->VMEM<->MXU explicitly
HBM       -> v5p: ~95 GB HBM2e @ 2.8 TB/s [F: Peake table, cross-checked];
             Ironwood: 192 GB HBM @ 7.2 TB/s [F: vendor]
```
Contrast with the GPU: the TPU has **no hardware L1/L2 eviction** — every HBM access is a
compiler decision. Benefits: deterministic latency, no cache pollution, the schedule is the
optimization. Cost: a compiler bug = a stall with *no cache to hide it*; dynamic,
data-dependent workloads (a decode loop whose shape depends on token ids, MoE routing) are
the regime where the TPU's compiler works hardest. [I: mechanism; scratchpad sizing F]

## The compiler stack (Q5/Q7 of the framework)
```
JAX / PyTorch / TensorFlow
   -> XLA (the ML compiler: HLO IR -> whole-chip / multi-chip schedule)
   -> StableHLO (the open intermediate IR, now shared with Trainium)
   -> Pallas (tile-level "kernel" language: the TPU's escape hatch;
              exposes VMEM, MXU tiles, and the inter-chip ICI to the user)
   -> the chip(s)
```
- **Hardware scheduler vs compiler scheduler:** the TPU chip has *no* dynamic thread
  scheduler in the GPU sense; execution is a VLIW-style bundle stream where the compiler
  places every op on every clock. The "scheduler" lives in XLA. (Deep: `16`.)
- **Why the compiler can win on predictable hardware:** a transformer layer is the same
  tile every step; XLA unrolls the schedule once and re-runs it. What breaks it: dynamic
  shapes, data-dependent control flow, irregular MoE dispatch — exactly where GPU kernels
  (dynamic, occupancy-hiding) still have the edge. [I]
- Pallas is the answer to "what if XLA's schedule is suboptimal for this kernel" — the
  TPU's equivalent of CUDA's escape hatch, but coarser-grained (tile level, not SASS).

## Scaling: ICI, torus, optical switches, pods
- **ICI (Inter-Chip Interconnect):** the TPU's scale-up fabric. Per-chip bandwidth has
  grown from ~400 Gbps (v2 era) to 4,800 Gbps/chip (v5p) to 19.2 Tb/s (v8) [F: vendor].
- **Topology:** 2D/3D **torus** — each chip has fixed links to its 2d neighbors, wrapped.
  Torus is cheap (point-to-point, no switch) and great for nearest-neighbor traffic
  (tensor-parallel all-reduce, pipeline stages); its cost is *diameter*: the far corner of
  a 9,216-chip 3D torus is ~120+ hops away, and all-to-all (MoE expert traffic) pays that
  on every layer. That is why v8's **Boardfly** (partially switched, high-radix) halves the
  diameter, and why TPU v4 got **reconfigurable optical circuit switches (Palomar)** — the
  torus can be *rewired* at the optical layer to fit the job. [F: arXiv:2304.01433; vendor]
- **The pod is the machine:** 4,096 (v4) → 8,960 (v5p) → 9,216 (Ironwood) → 9,600 (v8t)
  chips, one coherent ICI domain, ~40–50% of the pod's compute usable as one "logical
  accelerator" (the rest reserved for fault tolerance). [F: vendor] No other vendor's
  scale-up domain is this big — NVIDIA's is 72–576 GPUs.
- **Topology → traffic mapping:** TP all-reduce wants low-diameter/high-bandwidth
  (torus OK up to a size, then switches); MoE all-to-all wants high radix (Boardfly,
  NVSwitch, NeuronSwitch); pipeline stages want cheap point-to-point (any fabric).
  Deep: `18`.

## The six "bets" of the TPU (condensed)
1. **MAC-only silicon** — delete caches, branch predictors, reordering; power → MXU.
2. **Systolic data reuse** — the array wires *are* the cache.
3. **Compiler as scheduler** — determinism by construction (v1: "deterministic execution
   model is a better match to 99th-percentile latency" [F: arXiv:1704.04760]).
4. **SparseCores** — a purpose-built engine for embedding lookup (the one workload the
   MXU is the wrong shape for), ~5% of die area for 5–7× embedding speedup
   [F: Google docs; Peake (area/5–7× figures, secondary cross-check)].
5. **The pod as product** — sell 9k-chip domains, not chips.
6. **OpenXLA / PJRT** — share the compiler with Trainium (AWS runs XLA on Neuron) —
   the compiler, not the silicon, is the platform. [F: OpenXLA project]

## Connection to LLM inference
- **Prefill/training:** the MXU + deep VMEM tiling is compute-bound and efficient — the
  TPU's home turf (Gemini training ran on v5p/v6e/Ironwood [F: Google blog]).
- **Decode:** Ironwood's inference focus (192 GB HBM, 7.2 TB/s, FP8) targets exactly the
  bandwidth regime `02` describes; batch-1 speed per chip is competitive, *pod-level*
  aggregate throughput is the real product.
- **MoE:** the all-to-all problem is why ICI got optical reconfiguration (v4) and Boardfly
  (v8) — the topology bet is a direct response to MoE traffic
  (`../Model-Architectures/Mixture-of-Experts.md`).

## Key Takeaways
1. TPU = big systolic MXU + explicit scratchpads + compiler scheduler; the GPU's
   dynamic scheduling is *deliberately absent*.
2. The systolic array reuses operands in its own wiring — the data-reuse hierarchy is
   the interconnect, not a cache.
3. No cache fallback means the compiler *must* be right; predictable layers love this,
   dynamic workloads strain it.
4. ICI torus + optical reconfiguration + Boardfly is a topology story responding to
   all-reduce → all-to-all (MoE) traffic growth.
5. The pod (4k–9.6k chips) is the TPU's scale-up unit — the largest coherent domain in
   the industry.

## Related
- `13-aws-trainium-architecture.md` — the same philosophy rebuilt in another cloud
- `16-hardware-vs-software-scheduling.md` — the spectrum this page sits on
- `17-ai-chip-memory-philosophies.md` — VMEM vs SMEM vs HBM
- `../GPU-Systems/Tensor-Cores.md` — the counterpoint (warp-scoped, dynamic)
- `18-ai-accelerator-interconnects.md` — ICI vs NVLink vs NeuronLink

## References
- Jouppi et al., "In-Datacenter Performance Analysis of a TPU" (arXiv:1704.04760) [F]
- "TPU v4: An Optically Reconfigurable Supercomputer for ML with Hardware Support for
  Embeddings" (arXiv:2304.01433) [F]
- Google Cloud: "Introducing Cloud TPU v5p and AI Hypercomputer" (2023-12-07) [F]
- Google Cloud: "Introducing Trillium, 6th gen TPUs" (2024-10) [F]
- Google: "What's new with AI Hypercomputer" (Ironwood) [F]
- Google: "Two chips for the agentic era" (TPU 8t/8i, 2026) [F]
- Jacob Peake, "AI Chip Architectures" (secondary anchor; deployment claims cross-checked
  against the above where possible)
