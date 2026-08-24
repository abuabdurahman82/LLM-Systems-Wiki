# How to Analyze an AI Chip (the 8-Question Framework)
`LAST_UPDATED: 2026-08-23` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
You do not need to memorize six architectures. You need one checklist. For *any*
accelerator, answer these eight questions and you can predict its behavior on your
workload:

```
Q1  Where does data live?          (memory hierarchy; what's on-chip; what's off-chip)
Q2  How does data move?            (caches? DMA? compiler? scheduled links?)
Q3  What do the compute units look like? (one engine? many cores? a mesh? slices?)
Q4  How do chips communicate at scale?  (fabric; topology; scale-up domain size)
Q5  Who schedules execution?       (hardware scheduler, compiler, or dataflow arrival)
Q6  What numerics does it optimize? (FP16/BF16/FP8/FP4/INT8; block scaling; accumulate type)
Q7  How is the machine programmed?  (ISA/compiler; kernel escape hatch; model-level stack)
Q8  What workload is the design betting on? (training / prefill / batch-1 decode / HPC / edge)
```

Q1–Q4 are the hardware; Q5 is the soul (the scheduling philosophy); Q6–Q7 are the
interfaces; Q8 is the bet. Pages `05`–`14` walk the six deployed machines through this
exact checklist, so you can verify your own answers against worked examples.

## Question 1 — Where does data live?
The hierarchy list, in order of proximity to compute, and what each tier holds in steady
state:
- **Registers / accumulators:** in-flight tile fragments (A, B, C). On NVIDIA, registers
  plus TMEM (Blackwell); on Trainium, PSUM; on TPU, the MXU's internal routing; on Cerebras,
  16 GPRs + 44 DSRs per core; on Groq, stream registers (64/lane).
- **On-chip scratch:** the tile that the matmul engine works on — SMEM/LDS (32–160 KB per
  SM/CU), VMEM (TPU, up to ~128 MB+), SBUF (Trainium, 24–32 MiB per NeuronCore [F: AWS docs]),
  local SRAM (Cerebras 48 KB/core × 900k = 44 GB/wafer [F: vendor]), MEM slices (Groq 230 MB
  per chip [F: ISCA papers]).
- **Off-chip DRAM:** HBM (80–288 GB per package on current flagships) or *nothing*
  (Cerebras, Groq: the model must fit in aggregate SRAM, or weights stream from MemoryX).
- **Beyond:** host memory, peer chips, remote nodes.
*What to extract:* total on-chip bytes, off-chip bytes, and which layer of the model
(weights vs activations vs KV) lives where in your deployment.

## Question 2 — How does data move?
- Hardware cache (NVIDIA L1/L2, AMD Infinity Cache): automatic, variable latency.
- Explicit scratchpad management (TPU VMEM, Trainium SBUF): compiler issues the loads;
  128 DMA engines on Trainium overlap with compute [F: AWS docs].
- Bulk-copy engines (NVIDIA TMA since Hopper): a dedicated unit moves tiles while the SM
  computes; cp.async on Ampere; both reduce the *programmer's* burden but stay
  hardware-scheduled.
- Scheduled point-to-point links (Groq RealScale): every byte arrives on a cycle the
  compiler chose; "scheduled, not routed" [F: ISCA 2022 paper].
- Mesh with per-core routers (Cerebras): five-port router per core; wavelets are the
  packets; broadcast is a fabric primitive.
*What to extract:* who decides the placement (HW vs SW), what the latency is (fixed vs
variable), and whether communication can overlap compute or steals from it (NCCL kernels on
GPUs steal SMs; CC-Cores on Trainium do not [F: AWS docs]).

## Question 3 — What do the compute units look like?
- **Dense matrix engines:** Tensor Core (warp/warp-group/scoped), MXU (128×128, growing to
  256×256), Matrix Core (wavefront-scoped MFMA), NeuronCore Tensor Engine (128×128 systolic,
  [F: AWS docs]).
- **Distributed matmul:** Cerebras has *no* matrix unit — GEMM is assembled from a row of
  cores each doing an AXPY against a resident slice, reduced over the mesh [F: Cerebras
  public disclosures].
- **Sliced SIMD:** Groq's MXM (4× 320×320 planes, 409,600 multipliers [F: ISCA papers]) plus
  VXM/SXM slices.
- **The non-matmul half:** CUDA cores / vector units / GPSIMD / VXM / Cerebras FMAC. This
  half decides how fast the machine can feed and finish around the matmul — and how badly
  it does address-irregular work (MoE dispatch, paged attention, speculative verify).
*What to extract:* the engine's tile shape (128×128? 256×256? descriptor-driven?), its
native formats, and whether the matmul is *asynchronous* from the issuing context
(NVIDIA: yes, since Hopper; AMD wavefront MFMA: no — the wave waits [I: kernel-engineer
consensus]; Groq/Cerebras: n/a — no "issuing context" in the GPU sense).

## Question 4 — How do chips communicate at scale?
- The **scale-up domain**: how many chips behave as one machine (NVLink domain: 8 → 72 →
  up to 576 planned; ICI pod: 4k–9.6k chips; NeuronSwitch UltraServer: 144; Groq rack:
  72; Cerebras: 1 wafer, always).
- **Topology:** full crossbar (NVSwitch), torus (TPU ICI, Trn1/Trn2 NeuronLink),
  switched all-to-all (NeuronSwitch, NVLink 6 switch layers), Dragonfly (Groq), 2D mesh
  (Cerebras). Topology decides the cost of the two traffic shapes that matter:
  nearest-neighbour (TP/adjacent-PP) vs all-to-all (MoE expert routing).
- **Scale-out:** beyond the domain — InfiniBand/Spectrum-X (NVIDIA), Ethernet/UEC (AMD,
  Groq-adjacent), EFA/SRD (AWS), plain Ethernet (Cerebras, Gaudi). Latency jumps 10–100×
  here, which is why the domain boundary is the most expensive line on the architecture.
*What to extract:* the per-chip scale-up bandwidth, the hop diameter, and whether
collectives run on dedicated silicon or share the compute fabric.

## Question 5 — Who schedules execution?
The spectrum, from fully dynamic to fully static (deep dive: `16-hardware-vs-software-scheduling.md`):
```
CPU (OoO, speculative) → GPU (hardware warp scheduler, occupancy)
  → TPU/Trainium (VLIW bundle / compiler-scheduled engines)
    → Groq (static cycle-level schedule, chip and network)
Cerebras is off this axis: dataflow — execution is triggered by operand arrival.
```
Consequences: determinism (Groq: BERT-Large latency measured within a ~75 µs band over
24,240 runs [F: Groq public results, cited in ISCA-adjacent material]); adaptability (GPU
wins on data-dependent control flow); compiler burden (moves to the compiler as you go
right). [I: framing]

## Question 6 — What numerics does it optimize?
- Format ladder: FP32 → TF32/BF16/FP16 → FP8 (E4M3/E5M2 or Trainium's configurable bias)
  → FP6/FP4 (OCP MX block-scale, shared across AMD/TPU v8/Blackwell; NVIDIA's NVFP4 is
  its proprietary variant).
- Accumulation precision: FP32 accumulate is near-universal on BF16/FP16 paths; FP8
  accumulates to FP32 in practice.
- What to extract: *which* low-precision formats are native (not just "FP8 support"),
  whether mixed-precision A/B (e.g., FP8×FP4 on CDNA4) is allowed in one instruction,
  and whether FP4 buys *compute* speed or only *memory/bandwidth* savings (Trainium Trn3:
  FP4 up-converts to FP8 in the array — memory savings, no FLOP gain [F: AWS docs]).

## Question 7 — How is the machine programmed?
- **Kernel-level escape hatches:** CUDA (SASS/PTX), HIP/Triton-ROCm, Pallas (TPU), NKI
  (Trainium), CSL (Cerebras, raw machine), Groq compiler (no user kernels at all).
- **Model-level stacks:** PyTorch/JAX + XLA + PJRT (TPU, Trainium), PyTorch + torch.compile
  + Triton (NVIDIA, AMD), Cerebras PyTorch matcher (static graphs only [F: SURF
  practitioner report, cited secondary]), GroqCloud (bring a model, not a kernel).
- What to extract: how fast a *new* operator lands (months? engineer-embedded?), whether
  dynamic control flow is supported, and whether the stack is open-source or a closed
  compiler. Ecosystem maturity is an architectural property — a chip without a kernel
  escape hatch is a closed system even if the ISA is open [I].

## Question 8 — What workload is the design betting on?
Map the answers above to regimes (`02`):
- Compute-rich, big-batch, HBM-heavy → **training / prefill** (H100/B200, TPU v5p/Ironwood,
  Trn2/Trn3).
- Bandwidth-rich, small-batch, SRAM-heavy → **batch-1 decode latency** (Groq, Cerebras,
  MTIA-style small-chip fleets).
- Capacity-rich (288 GB+ HBM) → **large models / long context** (MI300X/MI355X, B200/B300).
- Both, balanced, with a software moat → **the generalist** (NVIDIA's actual market
  position: no single regime, all of them, priced accordingly).
The honest question is never "which chip is fastest" but "which regime does *this*
deployment pay for, and does the bet match the bill?" — see `22-workload-to-chip-mapping.md`
and `27-how-to-choose-ai-hardware.md`.

## Using the framework: a worked mini-example (NVIDIA B200)
```
Q1  lives: weights+KV in 192-288 GB HBM; tiles in TMEM/SMEM/regs (~KBs); activations in HBM
Q2  moves: L1/L2 + SMEM explicit tiling + TMA bulk copy; NVLink for peers; PCIe for host
Q3  engine: 5th-gen Tensor Cores, tile-MMA, async, up to 2-SM cluster; CUDA cores for the rest
Q4  scale: NVLink5 domain up to 72 (NVL72), 130 TB/s aggregate; IB/Spectrum-X beyond
Q5  schedule: hardware (warp schedulers, occupancy) — fully dynamic
Q6  numerics: FP64/FP32/TF32/BF16/FP16/FP8/FP6/FP4 + NVFP4; FP32 accumulate
Q7  program: CUDA → PTX → SASS; cuBLAS/cuDNN/CUTLASS; Triton; TRT-LLM/vLLM/SGLang
Q8  bet: the generalist — every regime, all workloads, priced on the moat
```
Run the same eight lines for each of the other five machines (done in full in `05`–`14`)
and the "six architectures, six bets" picture of `15` assembles itself.

## Key Takeaways
1. Eight questions, asked in order, turn any datasheet into a predictable machine.
2. Q1+Q2 (where data lives / how it moves) determine the inference ceiling more than
   any FLOP number.
3. Q4's scale-up domain is the largest model that feels like one machine; its size is a
   design constant, not a knob.
4. Q5 (scheduling) and Q7 (programming) are two sides of one coin: every cycle of
   determinism you buy from the hardware is a cycle you pay for in compiler complexity.
5. Q8 is where analysis becomes decision: the chip that matches your regime is the right
   chip; "fastest overall" is not a category.

## Related
- `05`–`14` — the framework applied to each machine
- `15-ai-chip-design-philosophies.md` — the six-bet synthesis
- `../GPU-Systems/Glossary.md` — term definitions
- `21-ai-accelerator-comparison.md` — the framework rendered as two matrices

## References
- (Framework is author synthesis [I]; per-machine facts in `05`–`14` carry their own tags.)
