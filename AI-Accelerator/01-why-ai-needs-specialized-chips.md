# Why AI Needs Specialized Chips
`LAST_UPDATED: 2026-08-23` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
For 30 years, a single processor core got ~2× faster per year with no effort: transistors
shrank, frequencies rose, and the same clock consumed roughly the same power (Dennard scaling).
That free lunch ended around 2004–2010. Performance kept growing only by adding *more*
processors — and each one needed more software engineering to use well. AI, whose core
workload is a handful of repetitive, highly parallel operations, was the first application
class that could accept a *completely different* machine shape instead of a bigger CPU.
The result: domain-specific architectures (DSAs) — TPUs, GPUs-as-AI-engines, Trainium,
Cerebras, Groq — and the "Cambrian explosion of novel computer architectures" that
Hennessy & Patterson predicted at their 2018 ISCA Turing Lecture [F: iscaconf.org ISCA'18
Turing Lecture PDF].

## The five scalings (do not conflate "Moore's Law")
"Moore's Law" is used to mean five different things, and they ended at different times:

| Scaling | What it is | Status |
|---|---|---|
| **Transistor scaling** | ~2× transistor density per node | Still alive (node-to-node, 2026: N3→N2 [F: TSMC public roadmaps]) |
| **Frequency scaling** | ~2× clock speed per generation | **Dead ~2004** (3.5–4 GHz ceiling on leading nodes) |
| **Energy (Dennard) scaling** | power constant as density doubles (volts scale down with density) | **Dead ~2004–2007**; now power grows ~linearly with density at fixed voltage headroom [I: standard microarchitecture analysis] |
| **Architectural scaling** | better cores, wider superscalar, deeper pipelines | Stalled ~2010: out-of-order cores are expensive and power-hungry |
| **System scaling** | more cores, more chips, more datacenters | **Alive and dominant** — this is where all performance growth now comes from |

Consequence: a modern phone SoC or server CPU buys its performance from *many small cores*
plus memory hierarchy tricks. A single core in 2026 delivers only marginally more single-thread
performance than one in 2010 [I: SPECint single-thread history, e.g. Intel/AMD/Apple public
benchmarks].

The Hennessy–Patterson numbers quantify this: in the 1980s single-thread performance grew
~52%/year; by 2018 it was ~3%/year [F: ISCA 2018 Turing Lecture, slide "SPECint 2001–2018",
reprinted in "A New Golden Age for Computer Architecture", CACM 2018].

## What a CPU core actually costs
A modern out-of-order core spends most of its transistors on machinery that has *nothing to
do with the arithmetic*: branch predictors, reorder buffers, register renaming, load-store
units, speculative execution [I: any modern microarchitecture, e.g. Intel/Sunburst or
AMD/Zen documentation]. That machinery exists because CPU workloads are irregular: the
processor must handle *any* program. For an AI workload — "multiply these 1,000,000×1,000,000
matrices" repeated a million times — almost all of that machinery is waste. The DSA bet:
**delete the irregular-workload machinery, and spend those transistors on MACs and data
movement.** The TPU v1 paper is the canonical statement: "The TPU's deterministic execution
model is a better match to the 99th-percentile response-time requirement... than are the
time-varying optimizations of CPUs and GPUs (caches, out-of-order execution, multithreading,
multiprocessing, prefetching...)" [F: arXiv:1704.04760, §2].

## Why AI, specifically, unlocked DSAs
Four workload properties make neural nets unusually DSA-friendly:

1. **Fixed, repetitive operation mix.** A transformer is ~95%+ matrix multiplies and
   elementwise ops (see `02-ai-compute-workloads.md`). The hardware only needs to be good at
   a handful of things.
2. **Massive data parallelism.** Each MAC in a 128×128 or 256×256 array operates on
   independent elements — no branch, no data-dependent control flow between elements [I].
3. **Tolerant numerics.** Small rounding error does not crash an NN; it degrades accuracy
   smoothly. This is why FP16/BF16/FP8/FP4 all work — a luxury CPUs never had.
4. **Cost of inference scales with volume, not correctness.** A 10% speedup on a trillion
   queries is worth billions; the engineering can be specialized aggressively [I: standard
   inference-cost economics].

The proof point was the TPU v1: deployed at Google datacenters from 2015, 29× CPU throughput
and ~80× CPU energy-efficiency on NN inference (at INT8 precision, per the paper's comparison
methodology) [F: arXiv:1704.04760, §6; Peake article cites the same figures]. The 2018 Turing
Lecture's closing prediction — "the next decade will see a Cambrian explosion of novel
computer architectures" [F: ISCA 2018] — is now a list of shipped products: NVIDIA GPUs,
AMD Instinct, Google TPUs, AWS Trainium/Inferentia, Cerebras WSE, Groq LPU, plus Meta MTIA,
Intel Gaudi, Tesla Dojo/AI5, Tenstorrent, Etched, and more (see
`26-emerging-ai-chip-architectures.md`).

## The DSA design axes
Every specialized chip makes explicit choices on axes a CPU blurs together:

```
axis            general-purpose CPU          DSA
--------------- --------------------------  --------------------------------
control flow    unpredictable, OoO spec      predictable / statically scheduled
registers       renamed, huge                small / descriptor-based / none
memory          caches, prefetch, ECC        explicit scratchpads / SRAM-only / HBM
data movement   implicit (L1/L2 misses)      explicit DMA / compiler-scheduled
scheduling      hardware (issue queues)      compiler (TPU/Groq) or dataflow (WSE)
precision       FP32/FP64                    INT8/FP16/BF16/FP8/FP4 + block scaling
scaling         NUMA, PCIe, socket           purpose-built fabrics (NVLink, ICI, ...)
```

None of these axes is "better" in the abstract. The rest of this section shows the same six
deployed architectures making six different points in this space.

## Where performance growth goes now
With frequency and architectural scaling dead, a DSA gets performance from:
1. **More compute units per wafer** (transistor scaling still works for the MAC arrays).
2. **Better precision-per-FLOP** (halve the operand width, double the FLOPs, recover accuracy
   with block scaling — see `20-ai-hardware-numerics.md`).
3. **Better data movement** (this section's thesis — see `03-memory-wall-and-data-movement.md`).
4. **System scaling** (bigger HBM stacks, faster interconnects, bigger pods — see `18`, `24`).

Item 3 is where the six architectures diverge most, and it is why "peak FLOPS" is the worst
single number to compare chips (see `21-ai-accelerator-comparison.md`).

## Connection to LLM inference
- **TTFT (time-to-first-token)** is dominated by prefill: compute-bound large GEMMs — a DSA
  with strong matrix engines wins.
- **ITL (inter-token latency)** is dominated by decode: one GEMV per layer per token —
  bandwidth-bound, so HBM capacity/bandwidth or SRAM bandwidth decides who wins batch-1 speed.
- **Throughput** (aggregate tokens/s) is dominated by batching: arithmetic intensity climbs
  with batch size until the machine is compute-bound — the roofline ridge (see
  `../Inference/Roofline.md` and `23-roofline-across-ai-architectures.md`).

A DSA that is "the fastest" at one of these three regimes can be the worst at another; the
"bet" of each architecture in this section is a bet on which regime its customers pay for.

## Key Takeaways
1. Moore's Law didn't die — *frequency* and *Dennard* scaling did; system scaling replaced them.
2. CPUs pay ~50%+ of their transistor budget for irregular-workload machinery that AI
   workloads never use; DSAs delete it and reinvest in MACs and data movement [I: architectural
   analysis].
3. The TPU v1 (92 TOPS INT8, 28 MiB software-managed SRAM, deterministic execution) was the
   first proof that a domain-specific machine could beat a CPU by 29× on its domain
   [F: arXiv:1704.04760].
4. AI's four properties — fixed op mix, data parallelism, tolerant numerics, volume economics
   — are what make DSAs viable at all.
5. All post-2010 performance growth is system-level: more chips, more memory, faster links.

## Related
- `02-ai-compute-workloads.md` — the transformer's matmul breakdown
- `../GPU-Systems/Architecture.md` — SIMT as a *general-purpose* parallel philosophy
- `../Inference/The-Life-of-a-Token.md` — prefill/decode from the token's perspective
- `../Inference/Roofline.md` — the model that turns "fast FLOPs" into "useful performance"

## References
- Hennessy, J., Patterson, D. "A New Golden Age for Computer Architecture: Empowering the
  Machine-Learning Revolution". CACM 2018; Turing Lecture at ISCA 2018
  (`https://iscaconf.org/isca2018/docs/HennessyPattersonTuringLectureISCA4June2018.pdf`)
- Jouppi et al. "In-Datacenter Performance Analysis of a Tensor Processing Unit". ISCA 2018,
  arXiv:1704.04760 — TPU v1: 92 TOPS INT8 peak, 28 MiB SRAM, 29×/80× CPU figures [F]
- Jacob Peake "AI Chip Architectures" (2026) — secondary conceptual anchor
- TSMC public node roadmap (for the "transistor scaling still alive" claim [F])
