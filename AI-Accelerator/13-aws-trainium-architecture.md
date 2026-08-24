# AWS Trainium / Inferentia Architecture
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = AWS Neuron docs (fetched 2026-08-23) / AWS press; [F: secondary] = press.

## 30-Second Explanation
Trainium is best read as **the TPU's thesis rebuilt inside a different cloud**: a 128×128
weight-stationary systolic array fed from software-managed scratchpads, scheduled ahead of
time by a compiler — down to sharing Google's OpenXLA. What is genuinely Amazon's is narrow
and deliberate: **dedicated collective-communication silicon (CC-Cores) bolted onto the
borrowed core**, plus the vertical integration to price a chip that only has to beat NVIDIA
*inside AWS*. The anchor tenant is Anthropic — Claude runs on over a million Trainium
chips (Project Rainier, ~500k Trn2 at late-2025 launch, grown past 1M by early 2026)
[F: AWS/press; Peake (secondary cross-check)].

## Genealogy
| Year | Chip | Core | Key facts |
|---|---|---|---|
| 2015 | (Annapurna Labs acquired ~$350M) | — | Amazon's in-house silicon team (Nitro, Graviton) [F: press] |
| 2019 | Inferentia (inf1) | NeuronCore-v1 | inference-only: 4 NC-v1, 8 GB DRAM, three fixed engines [F: AWS] |
| 2022 | Trainium1 (trn1) | NeuronCore-v2 | first training chip: 2 NC-v2, GPSIMD, 32 GB HBM2e @ 0.8 TB/s, NeuronLink 2D torus (16-chip instance) [F: AWS] |
| 2023 | Inferentia2 (inf2) | NeuronCore-v2 | inference line converges on the v2 microarchitecture [F: AWS] |
| 2024 | Trainium2 (trn2) | NeuronCore-v3 | 8 NC-v3, first real FP8 (2× over BF16), 96 GB HBM3 @ 2.9 TB/s, SBUF 224 MiB/chip, 64-chip UltraServer (4×4×4 3D torus, 1,280 GB/s/chip); powers Project Rainier [F: AWS docs] |
| 2025–26 | Trainium3 (trn3) | NeuronCore-v4 | first 3 nm AWS chip (TSMC N3P); OCP MXFP8/MXFP4; 144 GB HBM3e @ 4.9 TB/s, SBUF 256 MiB; **NeuronSwitch** all-to-all replaces the torus; 144-chip UltraServer [F: AWS docs] |

## Architecture: specialized engines working concurrently
A Trainium chip carries a small number of NeuronCores (2 on trn1, 8 on trn2/trn3). Each
NeuronCore is **not one monolithic matmul engine but a cluster of decoupled, specialized
engines**:
```
NeuronCore
├── Tensor Engine   (the 128×128 systolic array; GEMM/CONV; the matmul FLOPs)
├── Vector Engine   (cross-element reductions: layernorm, softmax, pooling)
├── Scalar Engine   (pointwise: activations, GELU — one-in/one-out)
├── GPSIMD Engine   (8 × fully-programmable 512-bit vector processors running C;
│                    the escape hatch for "fits none of the other three")
├── 128 DMA engines (HBM<->SBUF data movement, overlapped with compute)
├── Sync Engine     (sequences the transfers)
└── CC-Cores (from trn2)  (dedicated collective-communication units)
```
AWS's own docs: "The Tensor engines are based on a power-optimized systolic array... A
NeuronCore-v3 Tensor Engine delivers 158 cFP8 TFLOPS, and 79 BF16/FP16/TF32 TFLOPS"; the
Vector Engine delivers 1 TFLOPS FP32, the Scalar Engine 1.2 TFLOPS FP32, and the GPSIMD is
"eight fully-programmable 512-bit wide vector processors" [F: AWS Neuron docs, NC-v3 page
(fetched 2026-08-23)]. There are no warps or wavefronts: the engines run as a
**statically-scheduled dataflow pipeline**, and the load-bearing decisions are about what
*surrounds* the systolic array.

A well-compiled step overlaps all four engines: the Tensor Engine grinds a matmul while the
Vector Engine runs the previous tile's softmax and the DMA engines stage the next — the same
producer/consumer overlap that makes TPU and GPU attention kernels efficient, expressed as
**separate physical engines rather than separate warps or VLIW slots**. [F: AWS; I: mechanism]
The tax at the edges: an operator that fits none of the specialized engines falls to the
GPSIMD path (slower) — Trainium's version of the long-tail cost every non-GPU accelerator
carries.

## The matrix engine: SBUF / PSUM data path
```
HBM
  -> SBUF (State Buffer: the main scratchpad; software-managed;
       24 MiB/NC on v2 -> 28 MiB on v3 -> 32 MiB on v4 [F: AWS];
       chip-level: 224 MiB trn2, 256 MiB trn3 [F: AWS spec table])
  -> Tensor Engine (128×128 weight-stationary array:
       LoadStationary: one operand tile held in the array
       MultiplyMoving: the other streams through it)
  -> PSUM (Partial-SUM: ~2 MiB accumulator SRAM the engine can read-add-write,
       so a contraction longer than K=128 folds along the K axis)
  -> SBUF (result)
Every hop issued by the compiler; nothing is prefetched or evicted by hardware.
```
AWS's own contrast with a CPU/GPU: the NeuronCore "has no cache" and "all memory movement
is explicit in the program itself" [F: AWS]. **This is exactly Google's VMEM bet** — an
explicit scratchpad the compiler must schedule perfectly, with no cache to paper over a
mistake. When the schedule is right the engines never stall; when it is wrong there is no
fallback path. [F: AWS; I: characterization]

**Array scaling trick:** the physical array is fixed at 128×128 across all three
generations; what changes is how many products it packs per cell. trn1 ran BF16/FP16 with
FP32 accumulate (FP8 at the BF16 rate — no speedup). trn2's v3 double-pumps FP8 to present
an *effective* 256×128 (the first real 2× on 8-bit). trn3's v4 packs microscaling operands
to present an effective 512×128 at 4× the BF16 rate. The count of physical MAC cells never
moves; the datapath feeds them narrower numbers. [F: AWS; Peake (secondary, consistent)]

The design runs a **generous HBM budget against modest peak FLOPs** — more memory per unit
of compute than a comparable NVIDIA part. But on *absolute* capacity it trails: trn2's 96 GB
sits below H200/B200; trn3's 144 GB below B200's 192 / B300's 288. So the lever AWS pulls
when arguing large-model economics is **price, not memory leadership**: cost per unit of
compute and HBM on silicon it builds and rents itself. [F: capacity specs; I: read]

## Numerics (and the one figure to distrust)
Trainium tracks the same precision-halving curve (FP32 → BF16 → FP8 → FP4) with two
wrinkles:
1. **Configurable FP8:** rather than fixed E4M3/E5M2 like Hopper, the Tensor Engine takes an
   adjustable exponent bias and supports E5M2, E4M3, E3M4 — the compiler trades range for
   precision per tensor. [F: AWS NC-v3 doc: "adjustable exponent biasing for the cFP8 data
   type"]
2. **Trn3's FP4 buys memory, not FLOPs:** OCP MXFP4 operands are up-converted to MXFP8
   before the array, so FP4 runs at the FP8 rate — it saves memory/bandwidth, not compute.
   [F: AWS; Peake (secondary, consistent)]
Both generations use microscaling block exponents (from trn3) and hardware stochastic
rounding (every generation). **The one figure to distrust is the sparse peak:** AWS
headlines a "4× FP8" number that its own architecture pages put at **2× over dense FP8**
(the 4× is relative to dense BF16) — "the marketed acceleration and the datapath do not
quite agree." [F: AWS; Peake flag]

## Collectives in silicon (dedicated subsection)
The block with no clean GPU analogue is the **collective-communication core**. Distributed
training and inference spend a large fraction of wall-clock in collectives: every gradient
step is an all-reduce, every MoE layer an all-to-all. **On a GPU those collectives run as
NCCL kernels on the same SMs doing the math** — communication and compute contend for the
same silicon, and overlap has to be won in software. Trainium carves the function out into
**dedicated hardware**: 20 CC-Cores per trn2 chip, wired straight to the NeuronLink ports,
executing all-reduce, all-gather, reduce-scatter, and all-to-all *while the Tensor and
Vector engines keep running* [F: AWS]. It is the same move Google made with SparseCore and
Cerebras with its off-core zero filter: find the workload the main engine is the wrong shape
for, and spend a little area on a purpose-built block beside it. **Communication becomes
something the chip does concurrently, not something it pauses to do.** Why this justifies
silicon: TP/DP all-reduce every step and MoE all-to-all every layer are on the *critical
path* of LLM serving/training; stealing SMs for them directly taxes the FLOPs that pay for
the chip. [I: the "why" is analysis; the CC-Core existence/count F: AWS]

## Scaling: NeuronLink, NeuronSwitch, EFA/SRD
- **Scale-up (NeuronLink):** through trn2, a torus — a trn2 instance is 16 chips in a 4×4 2D
  torus at ~1.28 TB/s (1,280 GB/s) per chip; the 64-chip UltraServer joins four instances
  into a 4×4×4 3D torus (the thin third axis, ~256 GB/s/instance, is the torus's
  characteristic trade: cheap wiring, huge nearest-neighbor bandwidth, many hops across the
  diameter). **Trn3 replaces the torus with NeuronSwitch** — a switched all-to-all fabric
  that roughly doubles inter-chip bandwidth (2,560 GB/s/chip) and flattens the diameter to
  one switched hop; the 144-chip UltraServer gives 362 dense FP8 PFLOPS and 20.7 TB HBM3e.
  The motivation: MoE expert routing is all-to-all — the worst case for a torus; a switch
  turns the longest-hop pair into a single crossing. [F: AWS; Peake (topology, secondary)]
  The scale-up domain is *message-passing*, not coherent shared memory — closer in spirit to
  the TPU's ICI than to an NVSwitch crossbar.
- **Scale-out (EFA over Ethernet):** every instance carries an Elastic Fabric Adapter NIC
  (3.2 Tbps per trn2 instance); the transport is **SRD (Scalable Reliable Datagram)**,
  offloaded to Nitro cards — AWS's clean-sheet answer to RDMA: instead of one ordered flow,
  it sprays each message across up to 64 parallel paths and delivers reliably but
  out-of-order, pushing reassembly to the collective library and sidestepping head-of-line
  blocking. No InfiniBand.
- **UltraCluster:** stitched by the "10p10u" network (~10 petabits/s at under 10 µs
  datacenter latency), scaling to hundreds of thousands of chips. Proof point: Project
  Rainier (~500k Trn2 for Anthropic, late 2025; past 1M by early 2026). AWS claims Trn2
  delivers 30–40% better price-performance than its Hopper-class GPU instances [F: AWS
  (vendor figure, vs last-gen NVIDIA, not Blackwell); F: press].

## Software: XLA-first, NKI as the escape hatch
```
PyTorch (torch-neuronx, via PyTorch/XLA LazyTensor) / JAX (jax-neuronx, via StableHLO)
   -> XLA HLO (the SAME OpenXLA IR as the TPU; Trainium is a first-class PJRT device)
   -> neuronx-cc (the Neuron compiler; lowers HLO -> a NEFF binary)
   -> NKI (Neuron Kernel Interface): a Python, tile-level kernel language exposing the
     four engines and the SBUF/PSUM scratchpads directly — Trainium's Pallas/Triton
   -> NeuronX Distributed (sharded training) + a collective library mapped onto the CC-Cores
```
The gap to CUDA (and even to the TPU stack) is **maturity, not design**: NKI, the JAX path,
and the distributed library were all still beta through late 2024; a ported model runs only
on AWS (no cross-vendor fallback). The clearest tell: Anthropic does not simply target
Trainium through PyTorch — it embeds with Annapurna, writes its own low-level NKI kernels,
and upstreams fixes. **Trainium is production-viable at the frontier, but at the frontier it
is co-engineered, not turnkey.** [F: AWS; Peake (secondary)]

## The five Trainium bets
1. **The cloud is the product, the chip a component** — win on price-performance inside AWS, never on a merchant spec sheet.
2. **Borrow the compute thesis** — reuse the TPU's systolic/scratchpad/compiler bets (down to OpenXLA); spend the saved effort on network and rack.
3. **Collectives belong in silicon** — CC-Cores overlap all-reduce/all-to-all with compute in hardware.
4. **Reuse the cloud's own network** — EFA + SRD, no InfiniBand.
5. **Move the topology to the workload** — torus while traffic is nearest-neighbor (trn1/2), switched all-to-all when MoE outgrows it (trn3).

## Key Takeaways
1. Trainium = TPU thesis + Amazon cloud: 128×128 systolic array, software-managed SBUF/PSUM,
   whole-program XLA compilation, no caches.
2. Four specialized engines (Tensor/Vector/Scalar/GPSIMD) run concurrently — the
   producer/consumer overlap is expressed as *physical engines*, not warps.
3. CC-Cores are the genuinely novel block: collectives as dedicated silicon, decoupled from
   the matmul units — a direct answer to NCCL stealing SMs.
4. The torus→NeuronSwitch move is the same industry pattern: switch to a crossbar when
   all-to-all (MoE) traffic outgrows nearest-neighbor.
5. Economically, Trainium competes on price (vertical integration), not spec-sheet FLOPs;
   frontier use is co-engineered (Anthropic/NKI), not turnkey.

## Related
- `10-google-tpu-architecture.md` — the borrowed thesis
- `13` companion; `16-hardware-vs-software-scheduling.md` — compiler-scheduled dataflow
- `17-ai-chip-memory-philosophies.md` — SBUF/PSUM vs VMEM vs SMEM
- `../GPU-Systems/NCCL.md` — the counterpoint: collectives as kernels
- `../Distributed-Inference/README.md` — why MoE all-to-all drives the topology bet

## References
- AWS Neuron docs: NeuronCore-v3/v4, Trainium2/Trainium3 architecture & spec tables
  (awsdocs-neuron.readthedocs-hosted.com — fetched 2026-08-23) [F]
- AWS: Project Rainier / Anthropic deployment announcements [F: press]
- OCP MX microscaling spec [F]
- Jacob Peake "AI Chip Architectures" (secondary anchor; topology/economics cross-checked
  to AWS docs and press)
