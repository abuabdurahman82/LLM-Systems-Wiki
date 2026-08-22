# TensorRT-LLM Architecture — Compiling the Model, Not Just the Code
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART XVII of the GPU-systems handbook.
The GPU-systems view of TensorRT-LLM: the base compiler, the build/convert process,
compiled kernels, inflight batching, and the max-optimization vs flexibility trade.
Architecture claims [F] from the repo (github.com/NVIDIA/TensorRT-LLM) and NVIDIA
documentation, tagged `[F: TRT-LLM docs]` / `[F: NVIDIA docs]`. No version numbers
asserted — check current docs. Performance statements are hypotheses [I]; verify with
`Perf-Experiment-Template.md` before choosing an engine.

## 30-Second Explanation
TensorRT-LLM inverts the usual order of operations: instead of *interpreting* a PyTorch
model at runtime (vLLM, SGLang), it **compiles** a model+precision+shape+GPU-architecture+
parallelism config into a **serialized engine** ahead of time, and a C++ runtime replays
that engine with custom-tuned kernels [F: TRT-LLM docs]. The compiler (TensorRT lineage)
fuses layers, specializes GEMM/attention/MoE kernels for the target SM architecture, and
captures CUDA Graphs — so the runtime pays near-zero launch overhead [F: TRT-LLM docs].
The cost is the build step: every change to model, quantization, batch/shape settings,
GPU arch, or TP degree can require a re-build, and new-model day-0 support lags the
interpreter engines [I]. The honest framing: TRT-LLM is the *peak-stable-model-on-NVIDIA*
bet; vLLM/SGLang are the *flexibility + model-breadth* bets. Neither is "the fastest
engine" — the winner is workload-dependent (see `./Engine-Comparison.md`). The engine-level
page is `../Serving-Engines/TensorRT-LLM.md`; the why-engines-exist framing is
`./Inference-Engines.md`.

## Two Layers: TensorRT and TensorRT-LLM
### The base compiler: TensorRT
TensorRT is NVIDIA's general-purpose DNN inference optimizer: it takes a computational
graph (ONNX-class inputs), rewrites it, and emits tuned kernels for a specific GPU
architecture [F: NVIDIA docs]. Its core moves, which LLM inference inherited:
- **Graph optimization:** rewrite and contract op sequences so intermediate tensors stop
  round-tripping through HBM (e.g. collapse a GEMM+bias+activation into one op).
- **Layer fusion:** merge adjacent elementwise/pointwise ops into a single kernel so one
  launch reads/writes each value once — the LLM version of this is QKV-fusion,
  RMSNorm+residual fusion, RoPE-in-attention (`./Fused-Kernels.md`, `./Cross-Layer-Optimization.md`).
- **Kernel auto-tuning:** pick the best tiling/split-K/cluster configuration *per shape,
  per SM generation* — a GEMM tuned for Hopper is not the GEMM tuned for Blackwell.
That is "compile-time" work: the decisions are baked in before serving starts. [A:
general compiler framing]
### The LLM stack on top: TensorRT-LLM
TensorRT-LLM is a purpose-built LLM engine around that compiler philosophy, because LLMs
break naive DNN-compiler assumptions:
- **Unbounded, variable-length state** (the KV cache grows every token) — a static graph
  can't encode "sequence length = whatever this request has done so far." [I]
- **Iteration-level scheduling** (a batch changes membership every decode step) — a
  serialized engine must be *re-enterable* with a different batch each iteration. [I]
- **MoE routing** (data-dependent expert dispatch, grouped GEMMs) and speculative
  verification (variable-width token blocks per request). [F: TRT-LLM docs]
So TensorRT-LLM is not "TensorRT with an LLM plugin"; it is a C++ runtime whose kernels
are *generated/tuned at build time* by the compiler, then re-entered at every step. [I]
## Build/Convert: From Checkpoint to Engine
### What
The pipeline: a PyTorch/HuggingFace checkpoint (or an already-quantized checkpoint from
ModelOpt) is **converted and built** into a **serialized engine** — a binary artifact
encoding the fused graph, tuned kernel selections, weight layouts, and CUDA-Graph
captures for that config. At serve time the runtime loads the engine; it does not
re-interpret the model [F: TRT-LLM docs].
### Why
Peak performance requires shape- and architecture-specific code. An interpreter engine
picks kernels generically at runtime; a compiled engine bakes in *the* best
kernel/tiling/quant-layout for this model at this precision at this batch range on this
GPU arch — and the runtime can then assume fixed layouts, pre-captured CUDA Graphs, and
no host-side graph dispatch. That is where "peak" comes from — and where the cost lives
too: the build is what you pay for it. [I]
### How
```
 BUILD PIPELINE
 ┌──────────────┐    ┌────────────────────────────────────────────┐    ┌─────────────────┐
 │ HF/PyTorch   │    │  trtllm build (offline, compile-time)      │    │  runtime (C++)  │
 │ checkpoint   │───►│  1. load weights, re-lay out (quant layout) │   │  load engine    │
 │ (+ optional  │    │  2. graph construction + fusion decisions  │───►│  inflight batch │
 │    ModelOpt  │    │  3. kernel selection/auto-tune for SM arch │    │  paged KV mgmt  │
 │    quant)    │    │  4. CUDA-Graph capture for shape buckets   │    │  replay graphs  │
 └──────────────┘    └────────────────────────────────────────────┘    └─────────────────┘
        ▲                        │  emits
        │                        ▼
        │               ┌────────────────────────────────────────────┐
        └──────────────  │  SERIALIZED ENGINE (binary artifact)       │
   one build per:        │  fuses + tuned kernels + graphs + layout   │
   (model, quant,       └────────────────────────────────────────────┘
    shape buckets,
    GPU arch, TP)
```
The key structural fact: the engine is **per (model, quant, shape config, GPU arch, TP)**.
Change any one axis — switch BF16→FP8, TP=4→TP=8, H100→B200, raise max-batch — and you
generally re-build. Worked example of the combinatorics [E]: one team running 2
quantizations (BF16, FP8), 2 parallelisms (TP=1, TP=8), 2 shape configs (max-context
16k, 64k), on 2 GPU archs = 2×2×2×2 = **16 engine builds** [E, arithmetic]. A
flexibility-first workflow would run one interpreter binary for all 16; the compiled
workflow produces 16 artifacts (and the build time for all of them). [E]
### When
When the model is stable, the hardware is fixed (or a small set of SKUs), the SLOs are
known, and you can afford build latency in the release process. Wrong when the model
flips weekly or you need day-0 support for a new architecture. [I]
### Hardware impact
The engine is arch-specific: kernel selections assume a concrete SM generation (Tensor
Core dtype support, TMA/warp-specialization availability on Hopper/Blackwell) and a
concrete interconnect (TP=8 assumes intra-node NVLink-class fabric — `./Multi-GPU.md`,
`./Topology.md`). An engine built for one arch does not transfer to another. [I]
### Inference impact
At runtime: no graph dispatch, no per-op kernel lookup — the step is a pre-planned
sequence of tuned kernel launches (CUDA-Graph-replayed where shape is in a captured
bucket). That is the low-overhead path small-batch decode lives or dies on
(`./Kernel-Life.md`); the trade is that out-of-bucket shapes fall to slower paths. [I]
### Example
Llama-class 70B on 8×H100: BF16 → engine A; FP8 (ModelOpt-calibrated) → engine B; same
weights, same shape config, TP=8 in both. Engine B is not "A with a quant flag" — it is a
separate build whose GEMM kernels run 8-bit Tensor Core paths with a different weight
layout (see the quantization section). One checkpoint, two artifacts, two serve times;
expect B's decode to be bandwidth-favored and prefill compute-favored — the *amount* is
workload- and arch-dependent [I], not a fixed multiple.
### Failure modes
- **Stale engine:** weights or config changed but the engine wasn't rebuilt — silent
  behavior/precision mismatch between what you test and what you serve.
- **Build fragility:** a new model arch or a shape-config edge case that the builder
  doesn't cover → build failure, not runtime degradation.
- **Shape-bucket misses:** runtime batch/context outside the captured buckets →
  non-Graph path, higher overhead [I].
- **Long rebuilds blocking release:** the build step is on the critical path of every
  model/config change. [I]
### How to measure it
- Build wall-time per config (CI metric).
- Runtime: compare kernel time per step with/without CUDA-Graph replay (Nsight,
  `Profiling.md`); launch-gap metrics.
- Serve-level: TTFT/ITL P50/P99 per engine vs the interpreter baseline at identical
  model+quant+batch (`Perf-Experiment-Template.md`).
## Graph and Kernel Optimization: What Actually Gets Fused
### Fusion at build time
The builder decides the fused op sequence; typical fusions in a Transformer block:
- QKV projection into one GEMM; RoPE applied *inside* the attention kernel (no separate
  rotate kernel).
- Attention + bias/scale into one paged-attention kernel that reads KV through block
  tables.
- RMSNorm (+residual) into one elementwise kernel (`./Fused-Kernels.md`, RMSNorm:
  arXiv:1910.07467 [F]).
- Dequant fused into the GEMM prologue so 4/8-bit weights never materialize as 16-bit in
  HBM (`./Custom-GEMM.md`).
The fused sequence is *fixed in the engine* — which is both the win (no host-side
decision per step) and the rigidity (a new op pattern means a new build). [I]
### Specialized kernels
- **Custom GEMM:** shape-bucketed, SM-arch-tuned GEMM kernels (decode GEMMs are skinny
  M×K GEMVs; prefill GEMMs are fat). The compiler picks tiling/split-K per bucket
  (`./GEMM.md`, `./Tensor-Cores.md`).
- **Attention:** TRT-LLM compiles its *own* attention kernels per model/paged-KV layout,
  distinct from FlashAttention/FlashInfer families — benchmark fairness requires pinning
  which attention kernel ran in each test (arXiv:2307.08691 for the FA family reference).
  [F: TRT-LLM docs; I: fairness note]
- **MoE:** grouped/batched GEMMs for expert dispatch with a wide-expert-parallelism
  optimization series across the fabric (`./MoE-Expert-Parallelism.md`). [F: TRT-LLM docs]
### CUDA Graphs
For decode, the per-step kernel sequence is captured into a CUDA Graph per shape bucket
(batch-size range, context length): replaying the graph costs one launch instead of
hundreds, killing small-batch launch overhead (`./Kernel-Life.md`). Chunked context is
designed to coexist with graph capture, so prefill chunks don't permanently invalidate
the decode graphs. [F: TRT-LLM docs]
## Quantization in TRT-LLM
Supported formats: **FP8, INT8, INT4, NVFP4**, plus the **NVIDIA ModelOpt** path for
producing the quantized checkpoint [F: TRT-LLM docs]. The structure:
- **ModelOpt** produces the quantized weights (calibration, scales, block-scaled NVFP4
  layouts); **the builder** then compiles GEMMs for that precision — e.g. FP8 W8A8 runs
  8-bit Tensor Core paths, NVFP4/INT4 weight-only paths fuse dequant into the GEMM.
- **KV-cache quantization** (FP8/INT8 KV) halves KV bytes → more sequences per GPU at
  long context; a separate runtime capability (`../KV-Cache/README.md`).
- Full format/accuracy/method landscape: `../Quantization/README.md`. The one-truth
  reminder from there: quantization is a **bandwidth/capacity tool first, compute tool
  second** — weight-only W4 barely changes prefill FLOPs but cuts decode bytes. [F]
## KV Cache: Paged Blocks in the Compiled Runtime
The KV manager is paged: a fixed pool of uniform blocks (configurable block size),
per-request block tables, attention kernels that index KV through the tables [F: TRT-LLM
docs] — the same mechanism class as PagedAttention (arXiv:2309.06180 [F]); sizing
arithmetic in `../KV-Cache/README.md`. TRT-LLM-specific capabilities:
- **KV cache quantization** (FP8/INT8) as a build/runtime config.
- **KV cache reuse** (config-level prefix reuse) — shared prefixes point at shared
  blocks rather than re-prefilling. [F: TRT-LLM docs]
- Paged layout is what makes the CUDA-Graph story tractable: the attention kernel shape
  is stable across batch membership changes; only the block-table contents change. [I]
The paged design raises the capacity ceiling (effective KV utilization approaches the
pool), so the inflight batch can run at a larger B and decode GEMMs stay near the
roofline knee (`../Inference/Roofline.md`, `./Bandwidth-vs-Compute.md`).
## Inflight Batching
### What
**Inflight batching** = iteration-level continuous batching in a C++ scheduler [F:
TRT-LLM docs]: the batch is rebuilt every model step — a request finishing frees its
slot in the *next* iteration, a new prompt is admitted mid-stream, and **chunked
context** lets prefill chunks ride in the same batch as decodes (prefill/decode
overlap). The Orca paper (arXiv:2211.05102) is the reference for iteration-level
scheduling; deep treatment: `../Inference/Continuous-Batching.md`.
### Why
Two independent wastes die:
1. **Slot waste** — static batches sit idle while the shortest request finishes first.
2. **Prefill/decode interference** — without chunking, one long prefill stalls every
   decode in the batch, spiking P99 ITL. Chunked context bounds each chunk so a
   prefill can't monopolize a step. [F: TRT-LLM docs; I: framing]
Because the scheduler is C++ (not a Python event loop), per-iteration overhead is
engineered out of the hot path — the same class of bet SGLang makes on the Python side
and vLLM makes async; which is best at very high batch is a hypothesis, not a fact
[ I]. (`./vLLM.md`, `./SGLang.md`.)
### How
Each step the scheduler: (1) appends new K/V for admitted requests into their block
tables; (2) admits up to capacity from the waiting queue (prompt first or priority
order, config-dependent); (3) packs remaining budget into prefill chunks alongside
running decodes; (4) hands the step to the model runner, which replays the matching
CUDA-Graph bucket (or the non-Graph path if out of bucket). At multi-instance scale,
**ADP Balance** routes requests across instances to equalize *remaining work*, not
request counts [F: TRT-LLM docs] — the routing principle from `./Load-Balancing.md`.
### When
Always in production serving; the relevant knobs are max batch size, chunked-context
size, and max requested max-tokens (over-reserving KV capacity to the max kills the
paged pool — size it against real workload context, `../KV-Cache/README.md`). [I]
### Hardware impact
Bigger effective batch → decode GEMMs at larger M → higher Tensor Core utilization up
to the roofline knee, then the marginal token starts to cost more than it returns
(`../Inference/Roofline.md`). The C++ scheduler also removes a host-side latency term
from small-batch decode, where launch overhead dominates (`./Kernel-Life.md`). [I]
### Inference impact
- **Throughput:** slots never sit dead; batch stays near B\*.
- **P99 ITL:** chunked prefill bounds prefill interference.
- **TTFT:** prefill chunk interleaving trades TTFT against ITL — the chunk size is the
  knob (`./Prefill-Decode-Disaggregation.md` for the disaggregated version).
### Example
Batch of 256 decode sequences + 1 new 4096-token prompt. No chunking: the next step
prefills 4096 tokens while 256 decodes wait → one P99-ITL spike. With chunked context
(e.g. 1024 tokens/chunk — a config choice, not a spec number [A]): the prompt takes ~4
steps of 1024-token chunks interleaved with decodes; each step's ITL stays close to the
decode-only ITL, and the prompt's TTFT grows by ~4 chunks worth. The arithmetic is
pure scheduling: TTFT_prompt ≈ prompt_len/chunk × step_time [E, algebraic].
### Failure modes
- **Over-sized max-tokens:** KV reserved for the cap instead of reality → capacity
  collapse, early preemption.
- **Chunk too small:** prefill takes many steps → TTFT up; chunk too large: ITL spikes.
- **Batch pinned too low:** under-utilized Tensor Cores (the batch never reaches B\*).
- **Instance imbalance (multi-instance):** without ADP-style balancing, one instance
  absorbs the long-prompt tail → global P99 driven by one node. [I]
### How to measure it
Engine Prometheus: batch size over time, queued requests, preemption counts; TTFT/ITL
P50/P99 at fixed concurrency; prefill-chunk share of each step (`GPU-Metrics.md`,
`Perf-Experiment-Template.md`).
## Speculative Decoding
TRT-LLM ships **n-gram (self-draft) and EAGLE**-class speculative decoding, plus
Llama-draft [F: TRT-LLM docs]. The distinctive implementation note from the docs:
**guided decoding and speculative decoding run cooperatively across CPU and GPU** —
constraint checking (structured-output masks) is done in parallel on the CPU side
instead of serializing it on the GPU, which matters when both constrained sampling and
speculation are active. [F: TRT-LLM docs; I: significance]
Mechanism recap: the draft path proposes K candidate tokens, the target model verifies
them in one forward pass, and the accepted prefix is emitted in one step — a latency
tool (ITL) that preserves the target's distribution; acceptance is workload-dependent,
so speedup is per-workload, never assumed. Reference: EAGLE arXiv:2401.15077 [F];
deep treatment: `../Speculative-Decoding/README.md`.
## Multi-GPU Execution: The Most Documented Stack
TP, PP, EP, DP are the same primitives as in `./Multi-GPU.md`; what makes TRT-LLM
distinctive is the *depth of public documentation* on the hard cases [F: TRT-LLM docs]:
- **TP:** intra-node tensor parallelism over NVLink; the engine is built per TP degree
  (TP=8 is a different engine than TP=4 — weight sharding is baked in at build).
- **Wide Expert Parallelism (EP):** a multi-part optimization series for MoE expert
  dispatch across nodes; AllToAll is the bottleneck, and the series targets it
  (`./MoE-Expert-Parallelism.md`, `./NCCL.md`). [F: TRT-LLM docs]
- **ADP (attention data parallelism) + ADP Balance:** replicate the attention/dense
  stages, shard experts, and balance by remaining work across instances — a
  hybrid-parallelism knob the docs treat in depth. [F: TRT-LLM docs]
- **DWDP (distributed-weight data parallelism):** weight sharding across data-parallel
  replicas to spread large MoE weights. [F: TRT-LLM docs]
- **NVL72:** optimization for the 72-GPU NVLink domain (72 GPUs, one NVSwitch fabric,
  ~900 GB/s-class H100 links [A: per `../Hardware/README.md` constants]); P/D
  disaggregation and wide EP both get NVL72-specific treatment. [F: TRT-LLM docs]
"Most documented" is a statement about *public documentation volume*, not measured
maturity or guaranteed win — the other engines also scale multi-node; verify per
deployment (`./Multi-Node.md`, `./Scale-Up-vs-Scale-Out.md`).
## Why It's Peak-on-NVIDIA (and Less Portable)
- **Kernel specialization assumes NVIDIA:** Tensor Core dtypes (FP8/NVFP4), TMA and
  warp-specialized patterns, SM-arch auto-tuning — all compiled for a concrete NVIDIA
  arch. Porting to AMD/Intel/other GPUs is not a re-build; it is a different kernel
  ecosystem. [I]
- **The build ties config to arch:** engine = f(model, quant, shape, arch, TP). The
  specialization that makes peak perf possible is exactly what makes each artifact
  single-target. [I]
- **Ecosystem gravity:** quant (ModelOpt), orchestration (Dynamo), and the NVL72-class
  deployments all assume NVIDIA fabric/SDKs. The portability penalty grows with every
  one you adopt. [I]
The honest statement: TRT-LLM buys peak stable-model performance *on the NVIDIA GPUs it
was built for*, at the price of build friction, slower day-0 model coverage, and a
thinner custom-kernel plugin ecosystem than vLLM's Triton-backed stack
(`./Engine-Comparison.md`).
## The Relationship, and the Trade
```
PyTorch model ──► TensorRT-LLM conversion/build (compile-time) ──► optimized runtime ──► kernels
                 · weight re-layout        · C++ engine replay        · fused attention/GEMM
                 · graph + fusions         · inflight batching        · CUDA-Graph buckets
                 · kernel auto-tuning      · paged KV mgmt            · arch-tuned MoE
                 · CUDA-Graph capture      · TP/wide-EP/ADP placement
```
Compile-time decisions (left box) become runtime guarantees (right box): no dispatch,
no generic fallback on the hot path — but also no flexibility without a rebuild.

```
           MAX OPTIMIZATION                          FLEXIBILITY / VELOCITY
  ┌──────────────────────────────────┐    ┌──────────────────────────────────┐
  │ build per (model,quant,shape,    │    │ one interpreter binary; kernels  │
  │  arch, TP) → serialized engine   │    │  picked at runtime; plugin-able  │
  │ arch-tuned kernels, CUDA Graphs  │    │  (Triton backends); day-0 new   │
  │  · peak stable-model NVIDIA perf │◄──►│  models; widest quant coverage   │
  │  · peak multi-node NVL72-class   │    │  · re-tune without re-build      │
  │  · low host overhead on replay   │    │  · release = config, not build   │
  └──────────────────────────────────┘    └──────────────────────────────────┘
         rebuild on every config change ◄──►  no build step, some peak cost
   representative: TRT-LLM                    representative: vLLM, SGLang
   (peak on a stable model+HW you control)     (breadth + developer velocity)
```
Neither pole dominates: the "winner" is the workload. Stable model + fixed NVIDIA HW +
known SLO → the compile-time side pays. Rotating models, new arch day-0, custom kernels,
mixed hardware → the interpreter side pays. The comparison matrix and fairness
checklist: `./Engine-Comparison.md`; engine-fit one-pagers: `../Serving-Engines/README.md`.

## Failure Modes (engine-level)
- **Wrong philosophy for the workload:** TRT-LLM on a model that changes weekly → build
  treadmill; vLLM when you need the last 10% of stable-model NVIDIA perf and can afford
  the build (`./Inference-Engines.md` § failure modes).
- **Benchmark misread:** comparing TRT-LLM vs vLLM without pinning attention kernel
  family, quant, batch, graphs → you measured the kernel stack, not the engine
  (`./Engine-Comparison.md` fairness checklist).
- **Engine drift:** weights/config updated, engine not rebuilt → served behavior ≠
  tested behavior.
- **Arch assumption leak:** an engine or kernel tuned on Hopper behaving differently on
  Blackwell — always re-build, never carry. [I]

## How to Measure This Page's Claims
- Build wall-time × config matrix (the [E] combinatorics above, measured).
- Per-step kernel time with vs. without CUDA-Graph replay; launch gaps
  (`Profiling.md`, Nsight Systems).
- TTFT/ITL P50/P99 + goodput at SLO, TRT-LLM vs vLLM vs SGLang at pinned model/quant/
  batch (`Perf-Experiment-Template.md`).
- Multi-GPU: AllToAll time under wide EP; ADP balance effect on P99 across instances.

## Related
`./Inference-Engines.md` (why engines exist) · `./vLLM.md` · `./SGLang.md` ·
`./Engine-Comparison.md` · `./Multi-GPU.md` · `./Kernel-Life.md` ·
`./Fused-Kernels.md` · `./Prefill-Decode-Disaggregation.md` ·
`../Serving-Engines/TensorRT-LLM.md` (engine-fit page) ·
`../Serving-Engines/README.md` · `../Quantization/README.md` ·
`../KV-Cache/README.md` · `../Speculative-Decoding/README.md` ·
`../Inference/Continuous-Batching.md` · `../Inference/Roofline.md` ·
`../Hardware/README.md`

## Key Takeaways
1. TRT-LLM compiles (model, quant, shape, arch, TP) into a serialized engine; the
   runtime replays tuned kernels + CUDA Graphs — peak perf is the *consequence* of the
   build step, and so is its cost.
2. Inflight batching = C++ iteration-level continuous batching with chunked context and
   ADP Balance: prefill/decode overlap with bounded P99 interference.
3. The distinctive multi-GPU depth (wide EP, ADP, DWDP, NVL72) is *documentation*
   advantage, not a universal performance verdict.
4. The trade is structural: max-optimization (stable model + fixed NVIDIA HW) vs
   flexibility/velocity (vLLM/SGLang). Choose by workload; measure before claiming.
