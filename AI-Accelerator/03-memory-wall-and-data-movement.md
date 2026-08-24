# The Memory Wall and Data Movement
`LAST_UPDATED: 2026-08-23` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
AI chip architecture is, at bottom, a data-movement problem. Compute throughput has been
scaling ~4–5× per generation on leading nodes; DRAM-based memory bandwidth has been scaling
~1.5–2× per generation. The gap between the two — the **memory wall** — is the single
reason every architecture in this section exists in the shape it does. The tool that makes
this quantitative is **arithmetic intensity**: FLOPs performed per byte moved. If your
intensity is below the machine's "roofline ridge" (peak FLOPs / peak bandwidth), no amount
 of compute silicon helps — you are bandwidth-bound, and only moving bytes faster works.

## Arithmetic intensity
```
AI = Operations / Bytes Moved        [FLOP/byte]

GEMM(M,N,K), b bytes/operand:
  FLOPs = 2*M*N*K
  Bytes ≈ (M*K + K*N + M*N) * b      (read A, read B, touch C)
  AI    ≈ 2*M*N*K / ((M*K + K*N + M*N)*b)
  M=N=K large:  AI ≈ 2*K/b           -> hundreds to thousands
  M=1 (GEMV):   AI ≈ 2K/( (K + N + K)*b ) -> ~ 1-2, independent of N,K
```
[E: verified in python this session — see `02` for the full M-curve on the example model:
M=1 → 1.0, M=8 → 8.0, M=128 → 120.5, M=1024 → 682.7 FLOP/byte at K=N=4096, BF16.]

The machine has a fixed ratio of FLOPs to bandwidth; the workload has its own AI. The
performance you get is `min(peak FLOPs, AI × peak bandwidth)` — the roofline
(`../Inference/Roofline.md`). The **ridge point** is where the two rooflines meet:
- H100 SXM BF16: 989 TFLOP / 3.35 TB/s ≈ **295 FLOP/byte** [E: matches `../GPU-Systems/_STYLE.md`]
- B200 FP8: ~4.5 PFLOP / 8 TB/s ≈ 562 FLOP/byte [E, vendor spec basis]
- Groq LPU: 187 TFLOP FP16 / 80 TB/s on-chip SRAM ≈ 2.3 FLOP/byte [E: from `14` — note this
  is *SRAM* bandwidth, a different tier; the "ridge" is nearly meaningless there because
  almost nothing misses SRAM]

## Compute scaling vs bandwidth scaling
| Resource | Typical growth per generation (2019→2026) | Notes |
|---|---|---|
| Peak dense FLOPs (per chip, leading edge) | ~10× (H100→B200 FP8: 2→4.5 PF; →B300 7.5 PF; Rubin ~17 PF [F: vendor specs]) | transistor scaling + precision halving |
| HBM bandwidth (per chip) | ~2.4× (3.35 → 8 → ~13 TB/s on Rubin [F: vendor specs]) | HBM3→HBM3e→HBM4, more stacks/wider buses |
| HBM capacity (per chip) | ~5× (80 → 192 → 288 GB → 1 TB Rubin Ultra [F: vendor specs]) | 8→12→16 HBM stacks |
| SRAM (per chip) | ~flat (process shrink stopped buying SRAM density: 6T cell doesn't shrink logic-style [I: Cerebras WSE-2→WSE-3 evidence: +10% SRAM on 54% more transistors]) | the structural ceiling for SRAM-only machines |
| Inter-chip bandwidth | ~2×/gen (NVLink 900 GB/s → 1.8 TB/s → 3.6 TB/s; UALink 800 Gbps/lane [F: vendor specs]) | scale-up domain expansion |

The structural asymmetry: **FLOPs grow ~5× faster than HBM bandwidth does**, so the ridge
point drifts right — workloads that were compute-bound in 2022 need bigger batches in 2026
to be compute-bound again. Meanwhile capacity grows faster than bandwidth, so *which models
fit* is improving faster than *how fast they stream*. [I: synthesis of the table above]

## The memory hierarchy (all tiers, all machines)
```
            bandwidth/byte      latency        capacity
registers     highest          ~0 cycles       KB
accumulator   (TMEM, PSUM,     ~1 cycle        KB
  specialized)
scratchpad    (SMEM/LDS/SBUF/  1 cycle         32 KB - 28 MB
  VMEM, local
  SRAM per core)
L1 / L2       (GPU cache;      few-10s cycles  KB-MB
 AMD Infinity
 Cache ~256MB LLC)
HBM           ~1-3 TB/s        ~400-600 cycles ~80-288 GB
host DRAM     ~0.1-0.4 TB/s    ~us             TB
remote acc.   (NVLink/ICI/     tens of us      ~rack/pod
 NeuronLink/
 RealScale)
network       (IB/RoCE/UEC     ~10-100 us      unlimited
 Ethernet)
```
Four properties per tier — **latency, bandwidth, capacity, energy per access** — and the
architecture is the *shape* of this curve on that machine. The two philosophies:
- **Cache hierarchy (NVIDIA, AMD):** hardware decides placement (L1/L2 tags, eviction).
  The programmer sees one address space; the machine hides latency with many in-flight
  requests and occupancy. Cost: tags, eviction logic, coherence, variable latency.
- **Scratchpad / explicit (TPU VMEM, Trainium SBUF/PSUM, Cerebras local SRAM, Groq MEM
  slices):** software/compiler decides placement. No tags, no eviction, deterministic
  latency. Cost: the compiler gets it wrong and there is *no fallback* — no cache to paper
  over the mistake. [I: synthesis; per-machine detail in `10`–`14`]

## Why moving a number costs more than multiplying one
Quantitatively, from the public data:
- An H100 can do **989 TFLOP BF16** but moves only **3.35 TB/s** from HBM: the FLOP:byte
  ratio is 295:1. A single FP32 multiply-accumulate on an SM costs a fraction of a cycle of
  power; a 32-byte HBM read costs a full DRAM-row access on the stack side. [E: ratio; F: specs]
- On-chip SRAM is ~5–10× the bandwidth density of HBM per die edge, at ~10–100× the $/bit
  [I: standard HBM vs SRAM cost analysis]. Cerebras's bet is literally "pay 100×/bit to
  never leave SRAM"; Groq pays it per-chip and then pays it again in chip count.
- Inter-chip links are another 20–100× slower than HBM (NVLink ~1.8–3.6 TB/s per chip vs
  8–13 TB/s HBM on the same chips [F: vendor specs]).
So the energy/latency/cost ordering is always: **multiply < on-chip move < HBM access <
inter-chip move < cross-node network move**. The entire design space of this section is
"which moves do we make, and how many?"

## The five data-movement strategies (preview)
| Machine | What it does with the wall |
|---|---|
| NVIDIA GPU | hide it: occupancy + hardware caches + explicit SMEM tiling + TMA bulk copy; data movement is a *pipeline* alongside compute (`07`) |
| Google TPU | shrink it: huge MXU reuses operands in-register across the systolic array; one HBM round-trip feeds a whole 128×128×128 tile (`10`) |
| AMD | hide + enlarge: caches plus a 256 MB Infinity Cache LLC that sits between L2 and HBM (`11`) |
| Cerebras | delete it: no HBM at all; 21 PB/s aggregate SRAM; matmul is assembled *from* the mesh (`12`) |
| Trainium | shrink + dedicate: software-managed SBUF/PSUM, 128 DMA engines, and *collective traffic in its own silicon* (`13`) |
| Groq | delete + schedule: SRAM only, and the network itself is statically scheduled, so no move has variable latency (`14`) |

## Connection to LLM inference
- **Decode (M=1):** AI≈1 → the ceiling is bandwidth/weights (`02`). Every HBM TB/s or SRAM
  TB/s buys ~1× tokens/s at batch 1; every FLOP upgrade buys ~0×.
- **Prefill (M large):** AI in the hundreds → FLOPs matter; HBM capacity matters for KV
  writes. This is the regime where TPU MXUs and Blackwell Tensor Cores shine.
- **Long context:** the KV cache (128 KiB/token on the GQA-8 example model [E: 2·32·8·128·2B])
  grows out of HBM into… nowhere, on most machines. Cerebras/Groq have no "nowhere" tier:
  long context steals weight capacity from the same SRAM (`../KV-Cache/README.md`).
- **Continuous batching:** raises decode AI by sharing weight reads across requests — the
  software-side workaround for the memory wall (`../Inference/Continuous-Batching.md`).

## Key Takeaways
1. Arithmetic intensity (FLOP/byte) is the invariant that separates "my chip is slow because
   of FLOPs" from "my chip is slow because of bytes".
2. FLOPs have been outpacing HBM bandwidth ~5:1 per generation; the ridge point keeps
   moving right.
3. Caches and scratchpads are two different answers to one problem — placement by hardware
   (with a fallback) vs placement by compiler (without one).
4. The cost ordering multiply < on-chip move < HBM < inter-chip < network is why
   "data movement is more important than compute" for inference.
5. SRAM density stopped scaling with process nodes — the scarcest resource for SRAM-only
   architectures is the one node shrinks no longer buy.

## Related
- `04-how-to-analyze-an-ai-chip.md` — how to turn this into a checklist
- `../Inference/Roofline.md` — the roofline model, fully derived
- `../GPU-Systems/Memory-Hierarchy.md` — the GPU hierarchy in engineering detail
- `17-ai-chip-memory-philosophies.md` — cache vs scratchpad vs distributed SRAM, deep dive

## References
- Jouppi et al. "In-Datacenter Performance Analysis of a TPU" (arXiv:1704.04760) — 28 MiB
  software-managed SRAM as a design principle [F]
- "In-Datacenter Performance Analysis of a Tensor Processing Unit v2" and TPU v4
  (arXiv:2304.01433) — VMEM scratchpad scaling [F]
- NVIDIA H100/B200 architecture whitepapers (specs cited as [F: vendor spec])
- AMD MI300X/MI355X product pages (Infinity Cache 256 MB [F: vendor spec])
- Cerebras WSE-2/WSE-3 public disclosures (40/44 GB SRAM, 20/21 PB/s aggregate [F: vendor])
- Groq ISCA 2020/2022 papers (230 MB on-chip SRAM, scheduled networking [F])
