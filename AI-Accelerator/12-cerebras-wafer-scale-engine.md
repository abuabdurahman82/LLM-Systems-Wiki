# Cerebras Wafer-Scale Engine
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = Cerebras public disclosures / Hot Chips; [F: secondary] = analyst (SemiAnalysis) / press.

## 30-Second Explanation
Cerebras's thesis: **the die boundary is the problem.** The industry prints dozens of dies
on a 300 mm wafer, saws them apart, then spends its most exotic engineering (HBM, NVLink,
CoWoS, thousands of copper cables) wiring the pieces back together at a fraction of on-die
bandwidth. Cerebras *skips the saw*: the Wafer-Scale Engine is one piece of silicon — 84
reticle fields, 46,225 mm², ~900,000 dataflow cores — with every byte of on-chip memory in
SRAM, one cycle from a compute unit. The consequence: the highest-bandwidth "interconnect"
in the industry does not exist at all, and the machine is a **bandwidth machine, not a
FLOPs machine** — its FLOPs exist to keep up with the SRAM.

## Genealogy
| Gen | Year | Facts |
|---|---|---|
| WSE-1 | 2019 | CS-1: first shipped wafer-scale processor; 1.2T transistors, 400,000 cores, 18 GB on-wafer SRAM. SHIPPED [F: Cerebras] |
| WSE-2 | 2021 | 7 nm; 850,000 cores, 40 GB SRAM; weight streaming moves weights off-wafer into MemoryX. SHIPPED [F: Cerebras] |
| Galaxy CG-1 | 2023 | 64-system cluster with G42; trained the Jais Arabic LLM family. SHIPPED [F: G42/Cerebras] |
| WSE-3 | 2024–25 | 5 nm; 4T transistors, 900,000 cores, 44 GB SRAM; per-core FP16 SIMD doubled to 8-wide; clusters specified to 2,048 systems (never built). SHIPPED [F: Cerebras/Hot Chips] |
| Inference pivot | 2024–25 | Weights *parked* in SRAM instead of streamed: fastest independently measured decode in the industry — the pivot that now defines the company [F: Artificial Analysis measurements] |

## The radical thesis, in one figure
The reticle (stepper field) is ~850 mm² — why every conventional chip is under that ceiling,
and why B200 became two dies the moment NVIDIA pressed against it. Cerebras prints the same
~550 mm² die 84 times in a 12×7 grid, then (in a process co-developed with TSMC) lays extra
high-level metal across the <1 mm scribe lines where the saw would run. The mesh crosses
each seam on a source-synchronous interface (2,880 GB/s per die on WSE-3); the entire
inter-die layer costs ~97 W. **To software the seams do not exist: one uniform mesh, one
chip.** [F: Cerebras/Hot Chips]

## Yield: how you make a 46,000 mm² chip survive defects
Wafer-scale was tried in the 1980s and failed on yield — one defect kills the whole wafer.
Cerebras's answer is **granularity**: a defect on an H100 disables a ~6 mm² SM; the same
defect on a WSE disables one 0.05 mm² core. WSE-3 fabricates ~970,000 cores and ships
900,000 — the ~7% spare pool plus redundant fabric links lets the hardware remap around
every defect and restore a full logical mesh. [F: Cerebras]

## The core: dataflow, not a matrix unit
A WSE core is tiny (~38,000 µm² on WSE-2, ~half SRAM, ~half logic, peaking ~30 mW):
48 kB local SRAM, 16 general-purpose registers, a six-stage pipeline, a 4-wide FP16 FMAC
SIMD (8-wide on WSE-3), and a five-port router into the fabric. Execution is **dataflow**:
the core sits idle until a *wavelet* arrives; control bits select which handler fires; eight
hardware microthreads switch cycle-by-cycle as tensor operands arrive and drain. No warps,
no warp schedulers, no caches to miss, no reorder buffer — **the arrival of data is the
schedule.** (This is why Cerebras does not sit on the static-vs-dynamic scheduling line;
see `16`.) [F: Cerebras]

The unusual part is the *instruction*. Alongside the 16 GPRs sit **44 data-structure
registers (DSRs)**, each holding a tensor descriptor (base, extent, stride, up to 4-D). An
instruction names operands by DSR, so one FMAC says "multiply the arriving stream against
this resident tensor, accumulate into that one" — the hardware streams elements for as long
as the tensor lasts. **The loop lives in the descriptor**, not in software. "NVIDIA spent
five Tensor Core generations walking the matmul toward a single descriptor-driven command;
on a WSE core, a tensor instruction has no other form." [F: Cerebras]

## There is no matrix unit on the wafer
NVIDIA/Google/AMD concentrate FLOPs in a dedicated matmul engine. Cerebras **assembles the
matmul out of the fabric**: a GEMM runs as a wafer-wide choreography — each arriving weight
is broadcast along a row of cores holding activations, every core fires a multiply-accumulate
against its resident slice (an AXPY per weight), and partial sums reduce across the mesh.
The data reuse a Tensor Core gets from a register tile and an MXU from its wiring, the WSE
gets from **geometry**: activations never move, so the only operand in flight is the one
being multiplied. [F: Cerebras]

### The FLOPs ledger (read carefully)
WSE-3's headline **125 PFLOPS is *sparse* FP16** (assumes ~8× zero-skipping on ideally sparse
tensors). **Dense ≈ 15.8 PFLOPS FP16** [E: 900,000 cores × 8-wide × 2 × 1.1 GHz, derived;
Cerebras publishes no official dense figure]. Per-watt, dense FLOPs lose to every
contemporary GPU. The wafer was never a FLOPs machine — it is a **bandwidth machine**.

## Memory: one tier, and a cliff at the edge
```
44 GB SRAM in 48 kB slices inside the cores, one cycle from an FMAC.
No HBM, no L2, no eviction policy.
Quoted bandwidth: 21 PB/s aggregate = the SUM of 900,000 local SRAM ports.
```
That 21 PB/s is an **on-wafer aggregate, not a point-to-point link, and not comparable to an
HBM figure** (the whole point of `03`/`17`). The honest comparison is **bytes per FLOP**:
the wafer feeds ~1.3 bytes per dense FP16 FLOP, where a B200 gets ~0.002 from HBM [E:
21e15/15.8e15 = 1.33; 8e12/4.5e15 = 0.0018; ratio ~748×]. On that axis every GPU/TPU is
starved; the WSE is the only machine in balance. Decode — the pure-bandwidth phase — is the
phase the wafer is shaped for.

The other side of the tier is the **edge of the wafer**: 12×100 GbE (1.2 Tb/s) to everything
else — barely more than one ConnectX-8 NIC. Between on-wafer SRAM and off-wafer Ethernet sit
**five orders of magnitude**. NVIDIA's hierarchy descends gradually; the WSE has two tiers
with a cliff between them. **The wafer is an island, and the island's superpower and its cage
are the same fact.** And the island is not growing: SRAM density has effectively stopped
scaling — WSE-3 carries just ~10% more SRAM than WSE-2 despite a node shrink and a 54%
transistor jump. The scarcest resource is the one the next node no longer buys. [F: Cerebras]

## Two different memory strategies: training vs inference
- **Training inverts the flow:** on a GPU/TPU weights are resident and activations stream;
  on a WSE **activations are resident and weights stream**. Master weights live in MemoryX
  (a DRAM+flash appliance beside the cluster); layer by layer, weights stream across the
  wafer, trigger MACs against activations pinned in SRAM, and leave; gradients stream back,
  and the optimizer step runs inside MemoryX on CPUs. The wafer "never stores weights, not
  even temporarily" (Cerebras's phrase). Model size is bounded by MemoryX, not the 44 GB;
  the 44 GB bounds activations and batch. **One wafer holds a full layer's activations, so
  there is no tensor/pipeline parallelism, no FSDP sharding — a 70B model is written as a
  single-device program**, and multi-system scaling is *pure data parallelism* through
  SwarmX. [F: Cerebras]
- **Inference parks the weights in SRAM** and shards the model across wafers at layer
  boundaries (pipeline-parallel over Ethernet). Streaming a 70B model's ~136 GB from
  MemoryX per decoded token over ~150 GB/s would cost ~a second per token — fatal. So
  Llama-70B runs on "as few as four" CS-3s, each wafer contributing 44 GB of weight+KV and
  ~23 kW. [E: 67.8e9×2 = 135.6 GB / ~35 GB effective per wafer ≈ 4 wafers, consistent]

The speeds are real and independently measured: Artificial Analysis clocked 1,850 tok/s on
Llama 3.1 8B and 446 on 70B at the 2024 launch, 969 on Llama 405B, 2,522 on Llama 4 Maverick
in 2025 (~2.4× the best published Blackwell number of the time). Vendor-quoted peaks run
higher (2,100 on 70B with speculative decoding; 3,000 on GPT-OSS-120B, where live
independent measurement sits nearer 2,000). **No GPU provider comes close on per-user
decode speed.** [F: Artificial Analysis (independent); vendor peaks [F: Cerebras]]

## The economics (the sharp edge)
44 GB/wafer means a frontier model consumes fleets: ~24 CS-3s for a 1.6T-class model that
fits in a handful of GPU racks, each system ~$450k BOM selling at ~$2–3M list
[F: SemiAnalysis (analyst estimate); never officially disclosed]. During decode the wafer's
enormous FLOPs mostly idle; per-token API pricing runs ~3–5× GPU providers for the same open
models; long contexts steal SRAM from weights (KV lives in the same 44 GB), so the API caps
at 131K tokens while frontier providers serve 256K–1M. MoE is served but is the format's
worst case: a huge parameter footprint, a few experts at a time, in the most expensive
memory. The market has priced it: Mistral Le Chat, Perplexity Sonar, and Meta's Llama API
pay for the latency; **OpenAI signed for 750 MW of CS-3 capacity through 2028** (reported
>$10B at signing, grown past $20B) — the largest endorsement wafer-scale has received. [F:
press/SemiAnalysis, secondary]

## Software: compiler-driven, no kernel escape hatch
The Cerebras compiler is a **kernel matcher, not a general code generator**:
`cerebras.pytorch` traces the training step through lazy tensors into Torch-MLIR and a graph
IR, then matches subgraphs against a library of hand-written kernels, falling back to slower
auto-generated ops. Documented constraints: **static graphs only, no dynamic shapes, no
data-dependent control flow, no eager tensor access mid-step**, PyTorch version pinned.
The best independent practitioner account (SURF, Dutch national compute centre) reports
unsupported layer types and no 1:1 porting path. **There is no user kernel path**: when the
matcher misses badly, the fix is a Cerebras engineer. A separate SDK language, CSL, exposes
the raw machine (tasks, wavelets, colors) and has produced striking HPC results, but it is
a separate world from the PyTorch flow. Every flagship model (Jais, BTLM, Med42) was
co-developed with embedded Cerebras staff. [F: Cerebras; SURF (secondary)]

The "immunity": FlashAttention is a scheme for tiling attention *through a memory
hierarchy* — the WSE has no hierarchy to tile against, so the optimization class that costs
AMD years of porting lag simply does not apply. But the immunity and the poverty are the
same fact: the third-party kernel ecosystem that compounds on CUDA has no surface to attach
to. [I]

## Scaling: the wafer is the scale-up domain
- **Scale-up = the wafer.** 900,000 cores on one 2D mesh: 32-bit links, single-cycle hops,
  statically routed over 24 colors, native broadcast, ~214 Pbit/s aggregate fabric. Fixed at
  46,225 mm² by a 300 mm wafer — NVIDIA's scale-up domain grows every generation; the wafer
  has been the same size since 2019.
- **Scale-out = Ethernet, immediately.** 12×100 GbE per system. Training scales via SwarmX
  (data-parallel broadcast/reduce over RoCE); inference shards at layer boundaries
  (pipeline-parallel over Ethernet).
- **Constraints of a fixed wafer domain:** no more area to be had (450 mm wafers died a
  decade ago), so the scale-up roadmap is whatever the next node yields in density.

## The five Cerebras bets
1. **Don't cut the wafer** — stitch 84 reticle fields; the highest-bandwidth boundary doesn't exist.
2. **SRAM is the only memory** — 44 GB at 21 PB/s aggregate; balance the machine.
3. **Dataflow cores, no matrix unit** — matmul from broadcast+FMAC+mesh reduction; skipping a zero is free.
4. **Weights move, activations stay** (training) — decouple model size (MemoryX) from wafer memory.
5. **Sell latency, not throughput** — re-read a whole model per token faster than any HBM machine.

## Key Takeaways
1. The WSE deletes the die boundary; its "interconnect" is lithography, not SerDes.
2. It is a bandwidth machine (1.3 B/dense-FLOP) — FLOPs exist to keep up with SRAM, not the reverse.
3. Training streams weights through resident activations (no TP/PP/FSDP); inference parks
   weights in SRAM and pipeline-shards across wafers — *two different memory strategies*.
4. The 21 PB/s is an aggregate of 900k SRAM ports — never compare it to HBM bandwidth directly.
5. No kernel escape hatch: the compiler matcher + embedded engineers is the system; the
   wafer's niche (batch-1 decode) is real but priced 3–5× and capacity-limited.

## Related
- `12` companion; `14-groq-lpu-architecture.md` — the opposite SRAM bet (many small chips vs one big)
- `17-ai-chip-memory-philosophies.md` — distributed-SRAM philosophy
- `../GPU-Systems/GEMM.md` — the counterpoint: matmul in a register tile
- `24-the-rack-is-the-ai-computer.md` — why the wafer's fixed domain both helps and limits

## References
- Cerebras WSE-2/WSE-3 public disclosures & Hot Chips talks [F]
- Cerebras MemoryX / weight-streaming documentation [F]
- Artificial Analysis speed measurements (independent) [F: secondary]
- SemiAnalysis cost/economics analysis [F: secondary (analyst)]
- Jacob Peake "AI Chip Architectures" (secondary anchor; core geometry cross-checked to Cerebras)
