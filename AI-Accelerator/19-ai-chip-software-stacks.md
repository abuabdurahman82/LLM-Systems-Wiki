# AI Chip Software Stacks — Side-by-Side and the Escape Hatches
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
A chip is only as good as the *stack* that turns a model into work it can execute. The six stacks in this section cluster into **three shapes**:
1. **The CUDA stack (NVIDIA):** a *general-purpose* stack — the *escape hatch is the stack itself*. CUDA runs *anything*; the cost is that the *compiler* (nvcc + the PTX/JIT pipeline) *speculates* (it *generates* code for a *family* of GPUs, and the *JIT* *specializes* at load time).
2. **The compiler-placed stack (TPU, Trainium, Groq, Cerebras):** the *model* is *compiled* into a *placed* dataflow (XLA → HLO, Neuron → NRIF, Groq → the SRF schedule, Cerebras → the wafer placement). The *escape hatch* is *smaller* (the model *must be static*), but the *determinism* is *higher* (page 16).
3. **The porting stack (AMD):** *ROCm* is *CUDA-compatible in intent* (hipify translates CUDA to HIP), but the *momentum* is *behind* CUDA [I]. The *escape hatch* is *real but partial*: a *CUDA* model *can* run on AMD, *with effort* [F: AMD docs].

This page maps the six stacks, *quantifies* the *escape-hatch width* (how much *generality* the *stack* preserves), and shows *why* the *stack* is *as much a bet* as the *silicon*.

## The three stack shapes

### Shape 1 — General-purpose (NVIDIA CUDA)
The CUDA stack is *general-purpose*: it runs *arbitrary* parallel code, *not just* matmuls. The *layers*:
- **The language:** CUDA C++ (a *superset* of C++ with *kernels*, *streams*, and *memory APIs*) or *Python* via *PyTorch* / *JAX* / *Triton* [F: NVIDIA].
- **The compiler:** *nvcc* (host + device compilation) + the *PTX* (Parallel Thread Execution) *virtual ISA* + the *JIT* (Just-In-Time) *SASS* (Streaming Assembler) *specialization* at *load time* [F: NVIDIA]. The *PTX* is the *stable* intermediate; the *SASS* is the *per-GPU* machine code.
- **The libraries:** *cuDNN* (convolutions, attention), *cuBLAS* (GEMMs), *NCCL* (collectives), *cutlass* (GEMM templates) [F: NVIDIA].
- **The escape hatch:** *CUDA* itself. A *CUDA* model runs on *any* NVIDIA GPU (A100 → H100 → B200) *with no recompilation* (the *PTX* *forwards-compatible* guarantee [F: NVIDIA]).

*The first-principles read:* CUDA's *escape hatch is the widest* in this section — *any* model, *any* precision, *any* topology. The *cost* is that the *compiler speculates* (the *JIT* *specializes* at load time, and the *warp scheduler* *decides* at run time) — so the *determinism* is *the lowest* (page 16).

### Shape 2 — Compiler-placed (TPU, Trainium, Groq, Cerebras)
These stacks *compile the model into a placed dataflow*. The *layers* differ, but the *shape* is the same:
- **TPU (XLA):** *JAX* / *TensorFlow* → *XLA* → *HLO* (High-Level Operations) graph → *placed* into *CMEM* slots + *MXU* schedule [F: Google]. The *escape hatch* is *XLA* itself (the *HLO* graph is *inspectable*, and *PyTorch-via-XLA* exists [F: Google]) — but the *model must be static* (the *XLA compiler* *compiles the graph*, not the *data*).
- **Trainium (Neuron):** *PyTorch* / *JAX* → *Neuron Compiler* → *NRIF* (Neuron Runtime Intermediate Format) → *placed* into *SBUF* slots + *NeuronCore* schedule [F: AWS]. The *escape hatch* is *open-source* (the *Neuron SDK* is *public*, and the *compiler* is *open-source* [F: AWS]) — but the *model must be static*, and the *runtime* is *cloud-bound* (the *Neuron* runtime *runs on AWS*, not *on-premises* [I]).
- **Groq:** *the model* → *Groq compiler* (closed) → *SRF schedule* + *lane transfers* + *inter-chip path* [F: ISCA 2022]. The *escape hatch* is *the smallest* in this section: the *model must be compiled*, and the *compiler is closed* (the *user* cannot *inspect* the *schedule*, or *re-place* a tensor) [F: ISCA 2022]. The *Groq API* (a *host-side* runtime) is the *only* interface [F: Answer Fast].
- **Cerebras:** *PyTorch* / *JAX* → *Cerebras CS-3 compiler* → *wafer placement* + *Core* schedule [F: Cerebras]. The *escape hatch* is *partial*: the *front-ends* (*PyTorch*, *JAX*) are *open*, but the *compiler* is *closed*, and the *model must fit* on the *wafer* (or *RealScale*) [F: Cerebras].

*The first-principles read:* the *compiler-placed* stacks *trade generality for determinism*. The *escape hatch width* *shrinks* as the *placement* gets *more rigid*: *XLA* (inspectable, re-compilable) → *Neuron* (open-source, cloud-bound) → *Cerebras* (closed compiler, open front-ends) → *Groq* (closed compiler, *no* general-purpose path). This is *exactly* the *inverse* of the *determinism* axis (page 16): the *narrower* the *escape hatch*, the *more deterministic* the *execution*.

### Shape 3 — Porting (AMD ROCm)
The ROCm stack is *CUDA-compatible in intent*: *hipify* (a *source-to-source* translator) converts *CUDA C++* to *HIP* (Heterogeneous-compute Interface for Portability), and *ROCm* provides the *runtime* + *libraries* (*ROCBLAS*, *MIOpen*, *RCCL*) [F: AMD]. The *escape hatch* is *real but partial*:
- *A CUDA model can run on AMD* — *with effort* (the *hipify* translation is *not always clean*, and the *kernels* may need *manual porting*) [F: AMD docs].
- *The momentum is behind CUDA* — the *ROCm* *ecosystem* is *smaller* (fewer *kernels*, fewer *third-party* *libraries*, fewer *GitHub* *issues* *resolved*) [I].

*The first-principles read:* ROCm is the *bridge* between the *general-purpose* shape (CUDA) and the *compiler-placed* shape (the *CDNA* *matrix cores* are *systolic*, like a *TPU* MXU). The *escape hatch* is *the CUDA→ROCm porting path* — *real*, but *not as wide* as *CUDA's* *PTX* *forward-compatibility* [I].

## The escape-hatch width, quantified
The *escape-hatch width* is *the fraction of the CUDA model space that the stack can run without modification*. Let's *quantify* it for the *six* stacks:

| Stack | General-purpose code? | Static-model-only? | Closed compiler? | Escape-hatch width |
|---|---|---|---|---|
| NVIDIA CUDA | **yes** (arbitrary kernels) | no | no (nvcc is closed, but the PTX is open) | **widest** [I] |
| AMD ROCm | partial (HIP kernels) | no | no (ROCm is open-source) | wide (CUDA-portable) [I] |
| Google XLA | no (HLO graph only) | **yes** | yes (XLA is closed) | medium (inspectable HLO) [I] |
| AWS Neuron | no (NRIF only) | **yes** | no (Neuron SDK is open-source) | medium (open compiler, cloud-bound) [I] |
| Cerebras CS-3 | no (wafer placement only) | **yes** | yes | narrow (open front-ends, closed compiler) [I] |
| Groq | **no** (no general-purpose path) | **yes** | **yes** | **narrowest** [I] |

The *first-principles read:* the *escape-hatch width* is *inversely correlated* with the *determinism* (page 16). The *Groq* TSP has the *narrowest* escape hatch *because* it made the *most aggressive* determinism bet (the *entire* dataflow is *scheduled*, including the *inter-chip* path). The *NVIDIA* GPU has the *widest* escape hatch *because* it made *no* determinism bet (the *warp scheduler* *decides* at run time). This is the *trade* you're *actually buying* when you *pick a stack*.

## The front-end question (PyTorch / JAX / Triton)
The *front-end* (the *framework* that *compiles* the *model*) is *the* *user-facing* interface. The *six* stacks *all* have *PyTorch* and *JAX* front-ends, but the *Triton* (a *Python-based* *GPU* programming language) *front-end* is *NVIDIA-only* [F: NVIDIA]. The *first-principles* read:
- *PyTorch* is the *default* front-end for *all* six stacks (the *torch* → *backend* compiler pass is the *user's* interface) [F: each vendor's docs].
- *JAX* is the *default* front-end for *TPU* (XLA is the *JAX* compiler) and *Trainium* (the *Neuron* *JAX* integration) [F: Google, AWS].
- *Triton* is the *NVIDIA-only* front-end (the *Triton* compiler *targets* the *NVIDIA* *PTX* / *SASS* pipeline) [F: NVIDIA].

The *escape-hatch* *implication:* a *model* written in *PyTorch* can *target* *any* of the *six* stacks (the *torch* → *backend* pass is *vendor-specific*, but the *model* is *stack-agnostic*). This is *why* the *front-end* is *the* *user's* *escape hatch*: the *model* is *portable* across *stacks*, even when the *stacks* are *not portable* across *chips* [I].

## The "CUDA is the moat" question
The *first-principles* question: *is CUDA's* *escape-hatch width* a *moat* (a *sustainable* *competitive advantage), or a *tax* (a *legacy* *constraint) that *slows* the *NVIDIA* *stack* down?

- *The moat argument:* the *CUDA* *ecosystem* (the *kernels*, the *libraries*, the *GitHub* *issues*, the *developers*) is *the* *network effect* — *switching* to *ROCm* or *XLA* costs *the* *ecosystem* [I].
- *The tax argument:* the *CUDA* *general-purpose* *bet* (the *warp* *scheduler*, the *JIT*, the *PTX*) is *a* *legacy* *constraint* — the *NVIDIA* *chip* is *designed* to *run* *arbitrary* *code*, and *that* *generality* *costs* *die area* and *power* that a *compiler-placed* *chip* (TPU, Groq) *does not pay* [I].

The *first-principles* *resolution:* *both* are *true*, and the *balance* *depends* on the *workload*. For *training* (the *general-purpose* *workload*), the *CUDA* *moat* *wins* (the *ecosystem* is *the* *product). For *inference* (the *determinism-sensitive* *workload), the *CUDA* *tax* *shows up* (the *warp* *scheduler's* *P99* is *the* *liability, and the *compiler-placed* *chips* *eliminate* it). This is *why* the *Groq* *TSP* (the *purest* *compiler-placed* *chip) *competes* on *inference* *latency*, not *on* *training* *throughput* [I].

## How to read this page against the others
- **vs. page 09 (CUDA):** page 09 is the *CUDA* *stack* in depth; this page is the *comparison* of all *six*.
- **vs. pages 05–14:** those are the *per-chip* *deep dives*; this page is the *cross-chip* *software* *comparison*.
- **vs. page 15 (philosophies):** this page is the *software* *axis* of page 15's *six-axis* *frame*.
- **vs. page 16 (scheduling):** the *compiler-placed* *stacks* are the *software* *side* of page 16's *scheduling* *spectrum*.
- **vs. page 28 (decision tree):** the *escape-hatch width* is the *software* *constraint* in page 28's *decision* *tree*.
