# Groq LPU (Tensor Streaming Processor)
`LAST_UPDATED: 2026-08-24` · Status: core page · `[F]` = Groq ISCA 2022 paper (fetched 2026-08-24), Groq "Answer Fast" arXiv 2206.11062, Groq 2020 ML-Hardware workshop deck, Next Platform 2023-11-27; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
Groq's chip is **the TPU's thesis carried one step further in the direction of determinism**. Both use a systolic-style matmul engine fed from a single, software-managed SRAM level and scheduled ahead of time by a compiler. But where TPU still routes data through a hardware-defined torus and (in v4+) relies on a DRAM-backed hierarchy at scale, Groq's TSP (Tensor Streaming Processor) **replaces the hardware router with a software-scheduled, application-defined dataflow**: every transfer, every MAC, every activation is placed on the chip's 45 streaming register files by an offline compiler at build time. The result is a chip whose latency is *fixed to within a few percent of the compiler's prediction* — the strongest determinism claim of any accelerator in this section. The trade-off is flexibility: a TSP is not a general-purpose device, and a model has to be *compiled to it* before it runs. That's also why Groq has always sold inference as a service (LPU-as-a-service), not silicon: the value is the deterministic end-to-end token, and the value scales with the number of TSPs you can wire together with a scheduled — not routed — network.

The chip itself is modest on paper: **~750 INT8 TOPS / ~187 FP16 TFLOPS [E]** at 900 MHz from four 320×320 Matrix Execution Modules (409,600 int8 MACs/cycle total [F]), **~220 MiB of distributed SRAM per TSP [F]** — about 1.7× the on-chip CMEM scratchpad of a TPU v4 chip (128 MiB [F: Google v4 paper]) and, per Groq's Answer Fast paper, 4–10× the last-level cache of a modern GPU [F] — and *no DRAM on the chip at all*. The system that makes it interesting is the Dragonfly-interconnected rack scale: ISCA 2022 specifies a **145-rack, 10,440-TSP** maximum system with a **5-hop diameter and < 3 µs end-to-end worst-case latency [F]**.

## Genealogy
| Year | Milestone | Notes |
|---|---|---|
| 2016 | Groq founded (Menlo Park) | Ross, Abts, Bitar, and others; core team from Google TPU [F: press] |
| 2020 | ISCA ML-HW Workshop: "From Chips to Systems" | Dennis Abts; first public TSP microarchitecture: 4 × 320×320 MXM, 45 SRFs, 64 streaming lanes @ 20 TiB/s aggregate, 14 nm GF [F: workshop deck] |
| 2022 | "Answer Fast: Accelerating BERT on the TSP" (arXiv 2206.11062) | 130 µs P99 for BERT-base batch-1, ~6× state-of-the-art at the time [F] |
| 2022 | ISCA 2022: "A Software-defined Tensor Streaming Multiprocessor for Large-scale Machine Learning" | 24,240 BERT-Large runs on 4 TSPs; P99 < 1,225 µs, P100 = 1,300 µs; 145-rack / 10,440-TSP system spec [F] |
| 2023 (Aug) | GroqCloud commercial launch | 500+ TSPs on 14 nm (GlobalFoundries) in 3 switched pods [F: Groq PR] |
| 2023 (Nov) | Next Platform on-site | 574–576 TSPs running Llama-2 70B across 8–9 racks; 14 nm → 4 nm Samsung roadmap [F: Next Platform 2023-11-27] |
| 2024–25 | 4 nm Samsung TSP (TSP v2) | Next-gen node; details not public [UNVERIFIED] |
| 2025 (Dec 24) | **NVIDIA–Groq licensing deal ~$20.6 B** | Non-exclusive perpetual license; Ross & Maddera move to NVIDIA; GroqCloud continues as an independent service [F: press] |

## Chip-level architecture (per TSP)
A single TSP is a **single-clock-domain, 900 MHz** chip on 14 nm (GlobalFoundries, 2022 generation; 4 nm Samsung for the successor, announced 2023). The chip is split into four quadrants, each holding one **320×320 Matrix Execution Module (MXM)**; a central **VXM (Vector Execution Module)** handles everything that isn't a matmul. There are **45 Streaming Register Files (SRFs)** placed between the quadrants, and **64 streaming lanes** (32 eastward + 32 westward) carry 320-byte vectors between SRFs at **20 TiB/s aggregate [F]**.

```
TSP (per chip, 14 nm GF, 900 MHz)
┌──────────────────────────────────────────────────────────────────┐
│                        45 Streaming Register Files (SRFs)        │
│                  64 streaming lanes @ 20 TiB/s aggregate         │
│              (32 eastward + 32 westward; 320 B / lane / cycle)   │
│                                                                  │
│   ┌───┐   ┌───┐   ┌───┐   ┌───┐                                 │
│   │MXM│──▶│MXM│──▶│MXM│──▶│MXM│   4 × 320×320 = 409,600 MACs   │
│   │320│   │320│   │320│   │320│   (~750 TOPS INT8Acc32 [E])     │
│   │   │   │   │   │   │   │   │   (~187 TFLOPS FP16 [E])        │
│   └───┘   └───┘   └───┘   └───┘                                 │
│                                                                  │
│                    ┌───────────┐                                │
│                    │   VXM     │   16 PEs / lane × 20 superlanes│
│                    │  (vector) │   5,120 32-bit / cycle;        │
│                    │           │   20k INT8 ops / cycle [F]     │
│                    └───────────┘                                │
└──────────────────────────────────────────────────────────────────┘
  On-chip SRAM: 220 MiB distributed (≈ 230 MB in decimal) [F]
  No on-chip DRAM; no cache hierarchy; single-level, fixed-latency
```

**Why it looks like a TPU and isn't.** The MXM is a systolic array just like a TPU MXU: 320 lanes × 320 features, storing 409,600 "weights" (i.e., one MAC tile per cycle, INT8×INT8→INT32 or FP16×FP16→FP32 accumulation [F: 2020 workshop]). The 409,600-MAC number that circulates in secondary coverage is the **total MAC count across all four MXMs, not a per-cycle figure** — and the two formats do *not* run at the same rate. ISCA 2022 states the MXM decomposes a matmul into `[1×K]×[K×320]` sub-operations and that "a TSP can run **two FP16 or four int8** sub-operations each cycle" [F: ISCA 2022] — so int8 (K=320) delivers 4 × 320 × 320 = 409,600 MACs/cycle and FP16 (K=160) delivers 2 × 160 × 320 = 102,400 MACs/cycle, i.e. **FP16 throughput is exactly ¼ of INT8**. Hence [E] **INT8 ≈ 409,600 × 2 × 0.9 GHz ≈ 737 TOPS** (the 2020 deck rounds to "~750 Tops Int8Acc32" [F]) and [E] **FP16 ≈ 102,400 × 2 × 0.9 GHz ≈ 184 TFLOPS**, matching the deck's "1.5 PetaFlops FP16" for an **8-TSP** node (1.5e15 / 8 = 187.5 TFLOPS/chip [F: 2020 workshop]). The deck's "**> 1 TeraOps/s/mm²**" compute-density claim [F: 2020 workshop] is reported here as a deck figure, not recomputed: the TSP die area is not stated in the sources I verified (die size: UNVERIFIED), so a per-mm² cross-check would be fabricated.

**What makes it "deterministic" — and what that word actually means.**
The single most important sentence in the Groq microarchitecture literature is:
> "The TSP simplifies data flow through **Stream Programming**: a large, single-level scratchpad SRAM — fixed, deterministic latency; explicitly allocate tensors in space and time, unlocking massive memory concurrency" [F: 2020 workshop, slide on stream programming].

Every tensor, every activation, every intermediate is *placed* by an offline compiler into a specific SRF at a specific cycle. There is no cache, no memory controller, no DRAM prefetcher, no miss, no snoop. The chip has no hardware-defined execution order — the order is *the program*. This is the same philosophical bet as TPU (software-managed scratchpads, XLA) and Cerebras (dataflow cores), but carried further: even the *inter-chip* data path is a scheduled dataflow, not a routed one (next section).

**Memory: 220 MiB distributed SRAM, no DRAM on chip.**
The ISCA 2022 paper is explicit that each TSP has **220 MiB of on-chip SRAM** (decimal ≈ 230 MB [F]) and *no DRAM on the chip* [F: ISCA 2022]. This is ~1.7× the on-chip CMEM scratchpad of a TPU v4 chip (128 MiB CMEM shared by its two cores [F: Google v4 paper]) and, per the Answer Fast paper, 4–10× the last-level cache of a modern GPU [F: Answer Fast]. The consequence is that *any model that doesn't fit in the aggregate SRAM of the system has to be split across TSPs* — which is exactly where the scheduled-network design earns its keep.

**VXM and numerics.**
The VXM handles everything the MXM doesn't: elementwise ops, reductions (layernorm, softmax), activation functions, attention's Q·Kᵀ/V·attn matmuls *are* MXM work, but the softmax + mask + scale are VXM work. The MXM supports **INT8, UINT8, and FP16** inputs with **INT32 or FP32 accumulation** [F: 2020 workshop]. There is no native FP8 / BF16 / FP4 path in the 2022-generation TSP [F] — a meaningful gap versus TPU v5p (FP8) or Trainium2 (cFP8) [F: AWS], and one of the reasons the 2024–25 4 nm generation (TSP v2) matters: it was reported to add FP8 support, but the details are not public [UNVERIFIED].

## System: the Dragonfly cluster
The TSP is not sold as a single chip. Groq's ISCA 2022 paper describes a system that scales to **145 racks, 10,440 TSPs**, interconnected with a **Dragonfly topology** [F]. The numbers that matter:

| Parameter | Value (ISCA 2022) |
|---|---|
| Max system size | 145 racks, 10,440 TSPs [F] |
| Interconnect | Dragonfly [F] |
| Diameter | ≤ 5 hops [F] |
| Worst-case end-to-end latency | < 3 µs [F] |
| Bisection bandwidth | 240 GB/s per 8-TSP node; 50 GB/s between nodes (minibatch) [F: 2020 workshop] |
| Per-TSP SRAM | 220 MiB distributed [F] |
| Node SRAM | [E] 8 × 220 MiB = 1.72 GiB (≈ 1.85 GB decimal) |
| Aggregate SRAM (max system) | [E] 10,440 × 220 MiB ≈ 2.19 TiB (≈ 2.4 TB decimal) |

**"Scheduled, not routed."** The Dragonfly is a *topology* — a fixed, non-blocking, 5-hop graph. What makes Groq's use of it distinctive is that the **routing is done by the compiler, not by hardware routers**. Every TSP-to-TSP transfer in a given model is a known, fixed, compile-time edge. There is no adaptive routing, no congestion control, no retransmission, no per-packet header processing in the datapath. The interconnect behaves like an extension of the on-chip SRFs: you write to a remote TSP's SRAM the same way you write to a local one, and the *time* it takes is fixed at compile time. This is the load-bearing claim behind the < 3 µs worst-case end-to-end latency [F] — it is the *scheduled* time for the longest data path in the system, not a measured tail.

**Rack scale (2020 workshop numbers).**
The 2020 workshop deck gives a per-node, per-rack, and per-system view [F: 2020 workshop]:
- **Node**: 8 TSPs (an 8-way SMP "GroqBox"/node — the deck describes a 4U chassis "containing 8 Groq TSP 100 Cards"), 6 PetaOps INT8 / 1.5 PetaFlops FP16, 240 GB/s bisection — i.e., 750 TOPS / 187.5 TFLOPS per TSP [F].
- **Rack**: up to 64 TSPs, 48 PetaOps INT8 / 12 PetaFlops FP16, two 200 Gbps InfiniBand HDR links to ToR 40-port switches, 50 GB/s bisection between nodes (minibatch parallelism).
- **System**: "100s of nodes"; example: **320 TSPs → 240 PetaOps INT8 / 60 PetaFlops FP16**; worst-case system latency 2.5 µs [F].

Note the internal consistency: every scale point divides to the same per-TSP figures (6/8 = 48/64 = 240/320 = 750 TOPS INT8; 1.5/8 = 12/64 = 60/320 = 187.5 TFLOPS FP16 [E]) — so the per-TSP peak is unambiguous even where the deck rounds.

The ISCA 2022 paper then extends this to the 145-rack / 10,440-TSP maximum, with the Dragonfly and the < 3 µs worst-case [F]. The 2023 commercial deployment (574–576 TSPs running Llama-2 70B across 8–9 racks [F: Next Platform 2023-11-27]) is *inside* the ISCA 2022 system spec — it is not a new architecture, it is a *commercial realization* of the 2022 paper's design point.

**Llama-2 70B on 576 TSPs — a [E] check.**
Llama-2 70B has 68.98 B parameters (actual, not the marketing "70 B") [F: HF checkpoint index]. Next Platform reports the 576-chip system ran Llama-2 70B **at INT8** (512-token inputs / 1,024-token outputs) [F: Next Platform 2023-11-27]. Two first-principles consistency checks follow from that:
1. **Weight footprint at INT8**: [E] 68.98 × 1 byte ≈ **68.98 GB of weights**. Divided by the per-TSP 220 MiB (≈ 230 MB decimal) gives [E] 68.98 GB / 230 MB ≈ **~300 TSPs** of pure weight storage. The 576-chip deployment is roughly **2× that**, so about half of the aggregate SRAM ([E] 576 × 220 MiB ≈ 123.75 GiB ≈ 132.5 GB) holds weights and the rest holds KV cache, activations, and buffers [I] — plausible for a 1,024-token decode with a large KV context.
2. **FP16 is ruled out by the SRAM budget alone**: at FP16 the weights are [E] 68.98 × 2 = **137.95 GB**, which *exceeds* the ~132.5 GB aggregate SRAM of the whole 576-TSP system. So this deployment **could not have been run in FP16** — the SRAM budget alone pins the working precision to INT8 (or lower). This matches Next Platform's "INT8 processing" report exactly, and it is a cleaner consistency check than any per-chip speed claim.

## BERT-Large latency: the discrepancy you must know about
The anchor article (Peake, 2025) claims that Groq ran BERT-Large "24,240 times in a ~75 µs band." **This is not what the primary source says.** The ISCA 2022 paper, §5.4, reports (paraphrasing the extracted text): the team "execute[s] a single inference of BERT-Large running on four TSPs within a GroqNode 24,240 times, using SQuAD 1.1 dev Dataset," and "the results show that **99% of inferences return in under 1225 µs, with all of them returning by 1300 µs**; the dotted line at 100% highlights the estimated latency returned by our compiler, and shows that it is within 2% of the actual measured latency in the majority of cases" [F: ISCA 2022 §5.4].

So the **24,240** number is correct — it is the *count of BERT-Large inferences*, not a MAC count or a latency figure. But the latency is **P99 < 1,225 µs / P100 = 1,300 µs**, not "~75 µs." The 75 µs figure appears to be a conflation with the **130 µs P99 for BERT-base batch-1** reported in the "Answer Fast" paper (arXiv 2206.11062) [F] — which is a *different model* (BERT-base, ~110 M params vs. BERT-Large, ~340 M params) and a *different* result. BERT-Large is ~3× the parameters of BERT-base, and the ISCA 2022 P99 of ~1.2 ms is ~9× the BERT-base 130 µs figure, consistent with the ~3× model-size ratio plus the additional inter-TSP communication and the PCIe input/output transfer time for the larger embedding/FFN layers [I].

**This matters for two reasons.**
1. **The anchor article's "~75 µs" is a primary-source error.** It understates the BERT-Large tail latency by a factor of ~16 (75 µs vs. 1,225 µs P99). Page 30 of this section flags it in the fact-check table.
2. **The *correct* number is still the strongest determinism claim in this section.** P99 < 1,225 µs and P100 = 1,300 µs on a *multi-chip* system, within 2% of the compiler's prediction, is not a marketing figure — it is a measured histogram over 24,240 runs binned at 5 µs [F]. No GPU or TPU system in this section has a comparable published tail-latency guarantee.

## Why deterministic, and what it costs
The TSP's design is a deliberate bet on **batch-1 inference for latency-sensitive workloads** [F: 2020 workshop: "Focus on batch-size 1 performance — drives technology and implementation decisions"]. The reasoning:

- **Batch-1 is the regime where the memory wall bites hardest.** A single token's decode is a GEMV (arithmetic intensity ~1 FLOP/byte), not a GEMM. The only way to make it fast is to keep the weights in the fastest possible memory and to *not* pay a single cache miss, DRAM latency, or interconnect hop that the hardware scheduler might have hidden in a batch-N run.
- **Determinism is a product feature, not an implementation detail.** For a real-time service (machine translation, search, voice), a P99 that is *known at compile time* is worth more than a P50 that is fast but variable. The compiler's prediction *is* the latency guarantee — the hardware is designed to make the prediction true.
- **The cost is generality.** A TSP is not a general-purpose processor. You cannot run arbitrary code on it; you can only run a model that the compiler has placed. This is the same constraint as a TPU (you need XLA) or Cerebras (you need their compiler), but more severe: the TSP has *no* general-purpose compute path outside the MXM/VXM dataflow.

**What the TSP is not.**
- Not a general-purpose GPU. No SIMT, no warp scheduler, no CUDA-compatible ISA.
- Not a TPU. No DRAM, no torus, no XLA (Groq uses its own compiler).
- Not a Cerebras WSE. The WSE is one giant chip with on-wafer SRAM; the TSP is many small chips with a scheduled inter-chip network.
- Not an FPGA. The dataflow is fixed at compile time, not at runtime.

## The 2025 NVIDIA deal and what it means for the architecture
On **2025-12-24**, NVIDIA announced a **~$20.6 B** non-exclusive perpetual license to Groq's TSP technology, with **Jonathan Ross and Ross Maddera** moving to NVIDIA; **GroqCloud continues as an independent service** [F: press]. The deal is a licensing agreement, not an acquisition: Groq keeps the cloud, NVIDIA gets the architecture. The strategic read [I]:

- **NVIDIA is buying the determinism claim, not the silicon.** The TSP's ~750 TOPS / 220 MiB SRAM per chip is not competitive with an H200 on raw throughput. What is competitive is the *scheduled, not routed* system design and the batch-1 latency guarantee — a feature NVIDIA's own GPU stack does not offer (CUDA's scheduler is hardware-driven, not software-scheduled).
- **Groq keeps the service, NVIDIA keeps the design.** GroqCloud continues to sell LPU-as-a-service; NVIDIA integrates the TSP design into a future accelerator (rumored to be a "low-latency inference" variant of the Rubin generation [UNVERIFIED]). The TSP architecture in this section describes the *pre-deal* 2022-generation chip (14 nm, 4 MXM, 220 MiB SRAM); the post-deal successor (4 nm Samsung, TSP v2, FP8) is not yet public [UNVERIFIED].
- **The deal does not invalidate the ISCA 2022 paper.** The paper describes a real, shipped, measured system. The 145-rack / 10,440-TSP spec, the 24,240-run BERT-Large histogram, and the < 3 µs worst-case latency are all primary-source facts [F] that remain true regardless of who now owns the IP.

## How to read this page against the others
- **vs. TPU (page 10):** same systolic-array + scratchpad + compiler thesis; TPU keeps DRAM + torus + XLA, Groq drops all three and replaces them with a scheduled Dragonfly.
- **vs. Cerebras (page 12):** Cerebras puts the whole memory on one wafer; Groq puts the memory on many small chips and schedules the inter-chip path.
- **vs. Trainium (page 13):** Trainium keeps DRAM (HBM3e) and a hardware-routed torus; Groq has neither.
- **vs. GPU (pages 05–09):** the TSP is the *anti-GPU* in this section: no cache, no DRAM, no hardware scheduler, no general-purpose compute. It is the purest expression of the "compile the dataflow" philosophy.
- **Roofline (page 23):** the TSP sits at the *right edge* of the roofline — it is not trying to raise the compute ceiling, it is trying to make the *latency floor* (the P99) as low and as *known* as possible.
- **Fact-check (page 30):** the anchor article's BERT-Large "~75 µs" claim is corrected here and flagged in the verification table.

## Key numbers (quick reference)
| Parameter | Value | Tag |
|---|---|---|
| Process (2022 gen) | 14 nm GlobalFoundries | [F] |
| Process (next gen) | 4 nm Samsung (announced 2023; details UNVERIFIED) | [F/UNVERIFIED] |
| Clock | 900 MHz | [F] |
| MXMs | 4 × 320×320 = 409,600 int8 MACs/cyc | [F] |
| INT8 peak (Acc32) | [E] ~737 TOPS (deck rounds to ~750) | [E/F] |
| FP16 peak | [E] ~184–188 TFLOPS/chip (¼ of INT8; deck: 1.5 PetaFlops per 8-TSP node) | [E] |
| VXM | 16 PEs/lane × 20 superlanes; 5,120 32-bit / cycle; 20k INT8 / cycle | [F] |
| SRFs | 45 | [F] |
| Streaming lanes | 64 (32 E + 32 W) @ 20 TiB/s aggregate | [F] |
| On-chip SRAM | 220 MiB distributed (≈ 230 MB decimal) | [F] |
| On-chip DRAM | None | [F] |
| Node | 8 TSPs, 6 PetaOps INT8 / 1.5 PetaFlops FP16, 240 GB/s bisection | [F: 2020 workshop] |
| Max system | 145 racks / 10,440 TSPs | [F] |
| Interconnect | Dragonfly, ≤ 5-hop | [F] |
| Worst-case E2E latency | < 3 µs | [F] |
| BERT-Large (4 TSPs) | P99 < 1,225 µs; P100 = 1,300 µs; 24,240 runs; within 2% of compiler prediction | [F] |
| BERT-base batch-1 | P99 = 130 µs (6× SOTA at time of publication) | [F] |
| Llama-2 70B deployment | 574–576 TSPs across 8–9 racks, INT8, 512-in/1024-out, > 300 tok/s (2023) | [F: Next Platform] |
| NVIDIA deal | ~$20.6 B licensing, 2025-12-24; Ross & Maddera → NVIDIA; GroqCloud continues | [F: press] |
