# llama.cpp Architecture Deep Dive
`LAST_UPDATED: 2026-08-24 · Status: core page` · The portable-runtime engine. Unlike the
three datacenter engines in `GPU-Systems/` (vLLM, SGLang, TensorRT-LLM — all
Python/C++ servers built around continuous batching and paged KV), llama.cpp is a
dependency-free **C/C++ inference runtime** built on the `ggml` tensor library, where
*portability and constrained-memory operation* are the first-class design goals. Its claim:
"LLM (and VLM) inference with minimal setup and state-of-the-art performance on a wide
range of hardware — locally and in the cloud" [F: ggml-org/llama.cpp README, 2026-08-24].
It is **not** merely a CPU engine — it ships CUDA, Metal, Vulkan, HIP, SYCL, MUSA,
OpenCL, and WebGPU backends and runs in datacenters too — but its architecture is built
for a different device class than the engines above it.

## 30-Second Explanation
llama.cpp loads a **GGUF** file — a single-file container of quantized weights plus
metadata — and executes the model as a `ggml` computation graph over a backend
abstraction. Weights can be placed layer-by-layer across **any combination of backends**
(CPU, one or more GPUs, Apple Metal) — the "offload ratio" is a per-layer placement
decision, not an all-or-nothing choice. CPU execution is SIMD-specialized (AVX/AVX2/
AVX512/AMX on x86, ARM NEON + Accelerate + Metal on Apple Silicon, RISC-V vectors on
RISC-V) [F: README, 2026-08-24]. Prompt processing is embarrassingly parallel across
threads; token generation is a sequential memory-bandwidth-bound loop. The
`llama-server` tool wraps the runtime in an OpenAI-compatible HTTP API for service use,
but the runtime is first a *library for embedding in other programs* [F: README].

## What It Is
Plain C/C++ LLM+VLM inference with:
- **No dependencies** — single build, runs anywhere C/C++ runs [F: README].
- **Apple Silicon first-class** — ARM NEON, Accelerate, Metal [F: README].
- **x86 depth** — AVX, AVX2, AVX512, AMX [F: README].
- **RISC-V** — RVV, ZVFH, ZFH, ZICBOP, ZIHINTPAUSE [F: README].
- **1.5–8-bit integer quantization** plus mixed-precision "K-quants" [F: README].
- **Backend matrix (17 entries)**: BLAS, BLIS, CANN (Ascend NPU), CUDA, HIP (AMD),
  Hexagon (Snapdragon, in progress), IBM zDNN (IBM Z), MUSA (Moore Threads), Metal
  (Apple), OpenCL (Adreno), OpenVINO (Intel, in progress), RPC, SYCL (Intel GPU),
  VirtGPU, Vulkan, WebGPU, ZenDNN (AMD CPU) [F: README backend table, 2026-08-24].
- **CPU+GPU hybrid inference** — run models larger than total VRAM by splitting layers
  [F: README].
- **Tools**: `llama-cli` (chat), `llama-server` (OpenAI-compatible API + built-in web
  UI), GBNF grammar files for constrained generation, multimodal (VLM) subsystem
  [F: README tool list].

## Why It Was Created
The original problem (2023): run an open-weight LLM on a **laptop** — 16–32 GB of unified
memory, no datacenter GPU, no CUDA license issues, no multi-GB Python stack. Three
constraints drove the architecture [I: from the design's properties]:
1. **Memory must not exceed the device.** → weights are *quantized at export time*
   (GGUF K-quants), not dequantized into full precision in RAM; 4-bit weights use ~4 bits
   of storage per parameter instead of 16.
2. **The model may be bigger than the fastest device.** → layer-level placement across
   backends, so 10 layers run on the GPU and 20 layers on the CPU.
3. **Zero setup, many ISAs.** → C/C++ + runtime SIMD dispatch + a per-arch kernel
   library, instead of a Python+PyTorch stack pinned to one device.
Every design decision below is a consequence of these three constraints.

## Core Architecture
```
GGUF file (weights + arch metadata + quantization spec, single mmap'able file)
   │  (loaded via memory-map; page-cache friendly, no full read needed)
   ▼
llama.cpp runtime
   ├── ggml tensor graph (build the forward pass as ops on quantized tensors)
   ├── model graph → compute graph (prompt path: parallelizable; token path: sequential)
   ├── backend abstraction (one interface, many implementations)
   │    ├── CPU backend (SIMD-dispatched: AVX/AVX2/AVX512/AMX, NEON, RVV, ZenDNN, …)
   │    ├── CUDA backend (custom kernels, dequant+GEMM fused)
   │    ├── Metal backend (Apple, first-class)
   │    ├── Vulkan / SYCL / HIP / MUSA / OpenCL / WebGPU / BLAS / RPC / …
   │    └── layer placement: -ngl/--n-gpu-layers splits the graph across backends
   ├── KV cache (per-context, contiguous allocation; GPU-resident or CPU)
   ├── sampler chain (temperature, top-k, top-p, min-p, penalties, grammar)
   └── GBNF grammar engine (constrained decoding, optional)
   │
   ▼
Applications: llama-cli · llama-server (OpenAI API + web UI) · embedded libllama
```
The **backend abstraction** is the key architectural choice: each backend implements the
same small op set (matmul, dequant, norm, rope, softmax, etc.) over `ggml` tensors, and
the runtime assigns each graph op to a backend at graph-build time. This is what makes
mixed-placement (CPU+GPU hybrid) and exotic devices (IBM Z, RISC-V, WebGPU) *portable
features* rather than forks [I: structural, from the backend table].

## Request Lifecycle
1. **Load** — GGUF mmap'd; metadata (arch, n_embd, n_layers, quantization per tensor,
   rope scaling) read from the file header. Memory is page-cache on demand, so a 40 GB
   GGUF on a fast disk costs ~0 RSS until touched [I: standard mmap behavior].
2. **Tokenize** — the model's BPE/tokenizer from the GGUF.
3. **Prompt processing (prefill)** — the whole prompt is a *parallel* compute graph:
   each token position is independent given the previous position's K/V, so llama.cpp
   processes the prompt in chunks across all CPU threads (or in one GPU pass). This is
   the `llama-cli` "prompt eval" speed — typically *faster per-token than generation*
   by an order of magnitude [I: compute-parallel vs bandwidth-sequential; consistent
   with the roofline in `Inference/Roofline.md`].
4. **KV cache fill** — K/V rows for the prompt are stored in the context's KV cache
   (contiguous, sized by `n_ctx`), GPU-resident if those layers are offloaded.
5. **Decode loop** — one token at a time: run the sequential graph, read all weights +
   read/write the growing KV cache, sample, detokenize, print. This loop is
   **memory-bandwidth-bound**: at batch=1, each token's compute is trivial compared to
   the bytes it must stream (see the roofline numbers in `Inference/Roofline.md`).
6. **Stream** — `llama-server` returns tokens over the OpenAI-compatible API/SSE; the CLI
   prints as they arrive.

## KV Cache Architecture (how it differs from PagedAttention)
- The KV cache is a **contiguous, pre-allocated** tensor per context, sized to the
  configured `n_ctx` at init — *not* paged [A: check current implementation; the
  paged-block mechanism of `GPU-Systems/vLLM.md` (PagedAttention) does not exist in
  llama.cpp].
- Consequence: capacity is fixed at start (`--n-ctx`), utilization is coarse, and
  multi-request service re-uses one shared context with its own per-request slots —
  there is no server-grade block-level sharing/prefix-cache layer equivalent to APC or
  RadixAttention [A: verify current state; early `--cache-reuse` work exists].
- **Offload**: the KV cache of GPU-offloaded layers lives in GPU memory; CPU layers'
  KV lives in RAM — the hybrid split carries both [I: follows from layer placement].
- KV size obeys the same physics as everywhere else:
  `2 × layers × kv_heads × head_dim × ctx × bytes` — for a GQA model at 8k context the
  KV can be a *material fraction* of the model's own footprint, which is why `n_ctx`
  sizing is a first-order memory decision [E: same arithmetic as
  `Inference/Prefill-Decode-Disaggregation.md`].
- **No cross-request prefix reuse, no cache eviction policy, no remote KV tier** at the
  runtime level [A: as of the 2026-08-24 README; the *server* layer (llm-d) adds a
  global prefix-cache index on top of vLLM, not llama.cpp].

## CPU Execution (where it is genuinely first)
- **SIMD dispatch** — runtime selection of AVX/AVX2/AVX512/AMX kernels on x86; NEON +
  Accelerate on Apple; RVV on RISC-V [F: README]. K-quant matmul is the hot loop:
  dequantize small blocks into SIMD lanes, multiply-accumulate — the kernel design is
  tuned so the dequantize step is hidden behind the GEMM.
- **Thread pools** — prompt evaluation parallelizes over tokens × threads; generation is
  mostly single-stream (bandwidth-bound) and parallelism helps only where the batch or
  layer width allows [I].
- **Memory bandwidth is the ceiling** — at 4-bit, each token streams ~model_size/2 bytes
  through memory; on a dual-channel DDR5-5600 laptop (~89.6 GB/s [E: 2×5600 MT/s×8B,
  89.6 GB/s]) a 4-bit 8B (~4.0 GB [E: 8×10⁹ × 0.5 B]) model tops out near
  89.6/4.0 ≈ 22 tok/s, and an Apple-unified-memory Mac at ~150–273 GB/s scales
  accordingly [E: arithmetic; matches the well-known "bandwidth × precision"
  sizing rule].
- **AMX (x86)** — Intel's advanced matrix extensions add a second, wider compute path
  for CPU GEMM [F: README lists AMX support].

## GPU Execution & Layer Placement
- The CUDA backend runs custom kernels (dequantized matmul, fused RMSNorm+quant,
  Flash-attention-class attention on GPU) [F: README "custom CUDA kernels"].
- **Layer placement** (`-ngl 20` / `--n-gpu-layers`): the first N layers' weights live in
  VRAM, the rest in RAM; the graph hops backends at layer boundaries. Placement is the
  user's lever: put the *most bandwidth-hungry* layers (early attention + dense MLPs)
  on the GPU, leave the tail on CPU, and generation speed becomes a function of the
  split [I: standard practice].
- **Multi-GPU**: tensor-split a layer's matmuls across several GPUs (`-sm tensor`),
  or layer-split across GPUs plus CPU (`-sm row`) [A: verify current flags; README
  points to docs/multi-gpu.md].
- **Metal (Apple)**: not a second-class CUDA port — the first-class path for M-series,
  using the same placement model with unified memory [F: README "first-class citizen"].
- **Vulkan/SYCL/HIP/MUSA/OpenCL/WebGPU**: the same op set on other vendors' GPUs —
  the price is that per-backend kernel maturity differs; NVIDIA (CUDA) and Apple
  (Metal) are the two deepest paths [A: observed maturity ordering].

## GGUF & the Quantization Families
**GGUF** = the successor to GGML file format: a flat single-file container with
key-value metadata, tensor entries, and per-tensor quantization type [I: format
structure; verify against current docs]. Its properties are what make llama.cpp
portable:
- **Single file, mmap-friendly** — no HuggingFace directory tree, no `config.json`
  plumbing; the model *is* the file.
- **Per-tensor quantization types** — attention output projections, embeddings, and the
  final lm_head are commonly kept at higher precision (e.g. Q8_0) while the bulk of
  weights are Q4_K/Q5_K/Q6_K; this "mixed-precision" packaging is a standard
  llama.cpp technique [A: conventional packaging choice].

The quant families (all K-quant style unless noted; bit counts per README) [F: README
"1.5-bit … 8-bit integer quantization"]:
| Family | Typical bits | Use |
|---|---|---|
| Q2_K / Q3_K | 2–3 | smallest that still mostly works; big quality loss |
| Q4_0 / Q4_K | 4 | the default sweet spot for most models |
| Q5_K / Q6_K | 5–6 | quality-sensitive inference, modest memory |
| Q8_0 | 8 | near-BF16 quality; used for critical tensors |
| i-quant / Q4_0_XB etc. | ~4 effective | higher bits "implied" by importance-weighted packing — more quality per byte [I: family semantics] |
| new 1.5/5/6-bit tiers | — | finer granularity added in 2024–2025 [F: README] |

Quantization here is a **weight-only, dequant-on-the-fly** strategy: weights stay packed
in memory; kernels dequantize inside the matmul. This is different from FP8/NVFP4
(activation quantization, Tensor-Core paths) in `GPU-Systems/TensorRT-LLM.md` — llama.cpp
quantization buys *memory*, not Tensor-Core throughput.

## Batching, Scheduling, and Concurrency
- **Prompt batching**: the prompt path is chunked/parallel internally; `llama-server`
  accepts a queue of requests and evaluates them, but the runtime's request scheduler is
  **not** an iteration-level continuous-batching engine: there is no per-iteration
  admission of new sequences into a running decode batch in the vLLM sense [A: check
  current server implementation — the server does support parallel slots via
  `--parallel`, each with its own context].
- **Server mode** (`llama-server`): OpenAI-compatible `/v1/chat/completions`,
  `/v1/completions`, `/v1/models`, a built-in web UI; `--parallel N` gives N concurrent
  request slots [F: README server tool; flag semantics A: verify].
- Practical consequence: llama.cpp shines at **low concurrency** (1–8 users, one
  process) and degrades to a queueing system at hundreds of concurrent streams [I:
  consistent with the architecture — no paged KV, no iteration-level batcher].

## Speculative Decoding
llama.cpp supports draft-model speculation (`--draft` / `llama-speculative` tools: a
smaller GGUF proposes tokens, the main model verifies in one parallel pass) [A: verify
current tool names — the repo's spec-decode examples cover this]. The economics are the
same as elsewhere (`Speculative-Decoding/README.md`): the draft must be *much* faster per
token and accept-length must clear the verification overhead; on CPU, small-model
drafting is attractive because both models are bandwidth-bound.

## Structured Generation
GBNF grammars constrain the token sampler to a regular language (JSON schema, function
calls) — a grammar file + `--grammar` [F: README "GBNF grammars"]. The constraint is
applied *inside the sampler*: at each step, disallowed tokens get -inf logits. This is
heavier than vLLM/SGLang's optimized FSM-guided decoding (which precomputes allowed
token sets per state) — for tight loops it costs CPU time per token [I].

## Multimodal (VLM)
The 2026 README states "LLM (and VLM) inference" — multimodal models are supported via
a vision-encoder subsystem (image/audio decoders via single-header stb/miniaudio,
per the README acknowledgements) feeding the LLM as extra tokens [F: README]. The
architecture implication is the same as the E/P/D split in
`Distributed-Inference/NVIDIA-Dynamo.md` at miniature scale: the encoder runs once per
image (compute), then the LLM decodes — but there is no disaggregated encoder pool; it
all lives in one process [I].

## MoE Support
MoE models run through the same GGUF/`ggml` path; expert weights are quantized like all
others and the router/gate picks per-token experts [A: verify per-model]. There is no
expert-parallelism fabric story — MoE on one machine is memory-heavy (all experts
loaded), and wide-EP across nodes (the GPT-OSS/DeepSeek pattern) is *not* a llama.cpp
capability; that is the llm-d/Dynamo layer [I].

## Memory Architecture (the five budgets)
| Budget | Where | Notes |
|---|---|---|
| Weights | RAM / VRAM split by layer placement | packed in quant bits; no dequant copy |
| KV cache | per-context, RAM or VRAM | sized by `n_ctx` × parallel slots |
| Activations | scratch buffers per graph op | prompt-size dependent; the prompt path is the big one |
| Backend workspaces | per-GPU context (CUDA graph buffers, Metal command queues) | small vs weights |
| Page cache | the mmap'd GGUF itself | OS-managed; I/O on cold start |

**Pinned/paged memory**: CPU KV and weights are ordinary pageable RAM; the CPU backend
does not use pinned host memory the way CUDA transfer paths do (there is no bulk H2D
copy — weights never cross the bus after load) [I: structural].

## Performance Dimensions (the numbers that matter)
- **Prompt processing speed (tok/s)** — scales with thread count until memory/ALU bound
  on CPU; on GPU, near the device's compute roof for the prompt length.
- **Generation speed (tok/s)** — ≈ `bandwidth_effective × quantization_efficiency /
  model_bytes_effective`. The two levers: device bandwidth (unified-memory Mac > DDR5
  laptop > DDR4) and effective bits (Q4 vs Q8 halves the bytes, halves the ceiling,
  costs quality).
- **CPU memory** — quantized weights + KV + page cache; a 4-bit 8B model ≈ 4.0 GB
  weights [E: 8×10⁹ × 0.5 B] fits a laptop.
- **GPU memory / offload ratio** — `-ngl` determines the VRAM ask; below full offload,
  generation speed is set by the *slowest* layer's device.
- The roofline framing: prompt = compute roof, generation = bandwidth roof — same
  physics as `Inference/Roofline.md`, different absolute ceilings.

## Deployment Environments
| Environment | Fit | Notes |
|---|---|---|
| Apple Silicon laptop/mini | ★ best | Metal + unified memory + NEON; the canonical target |
| x86 CPU (server or laptop) | ★ strong | AVX2/AVX512/AMX; bandwidth-bound |
| NVIDIA RTX workstation | ★ strong | CUDA backend; full or partial offload |
| Edge / embedded | ★ strong | RISC-V RVV, WebGPU, Snapdragon Hexagon (in progress) [F: README] |
| RISC-V server | ○ growing | ZVFH/RVV kernels exist [F] |
| Datacenter, high concurrency | ✗ wrong tool | use vLLM/SGLang — no paged KV / iteration-level batching |
| Heterogeneous vendor GPU fleets | ○ possible | Vulkan/SYCL/HIP paths exist but maturity varies [A] |

## Strengths
1. **Device breadth** — the only mainstream runtime that treats Apple Silicon, x86
   server CPUs, RISC-V, and edge NPU-adjacent targets as first-class [F: README].
2. **Constrained memory** — K-quants + layer placement run models that no other engine
   would touch at this memory size.
3. **Zero-dependency portability** — one binary, one model file; deploy anywhere.
4. **Day-0 model support** — GGUF quants of new open models appear within days
   (community pipeline) [A: observed pattern].
5. **Embeddability** — `libllama` inside other C/C++/Rust/Go applications.

## Limitations
1. **No server-grade concurrency** — no paged KV, no iteration-level continuous
   batching, no prefix-cache sharing between requests (vs
   `GPU-Systems/vLLM.md` / `SGLang.md`) [A: check current state].
2. **No multi-node parallelism fabric** — TP/EP across machines is not a capability;
   multi-GPU is intra-host.
3. **Quantization is memory-centric** — weight-only K-quants, not FP8/NVFP4
   Tensor-Core paths; at large batch on H100-class hardware, TRT-LLM/vLLM kernel paths
   dominate on throughput [I: architectural expectation].
4. **Speculative/grammar paths are comparatively basic** vs SGLang's co-designed
   constrained+spec pipeline [I].

## When to Use / Not Use
- **Use**: local/edge inference; Apple Silicon; CPU-only; models too big for VRAM
  (hybrid split); quick experiments; embedded products; any "one user, one process"
  service.
- **Don't**: high-concurrency APIs (use vLLM/SGLang); multi-node MoE serving (use
  llm-d/Dynamo over vLLM/SGLang); FP8/NVFP4 peak-perf targets on Blackwell
  (use TRT-LLM/vLLM).
- **Alternatives at its layer**: MLC LLM (compiler-unified, mobile/JS) [F:
  `Serving-Engines/README.md`]; Hugging Face transformers for quick CPU runs; ONNX
  Runtime for cross-device inference outside the LLM domain.

## Observability
`llama-server` exposes per-request timing (prompt eval / generation speed in the CLI
telemetry), and a Prometheus `/metrics` endpoint [A: verify current flag — the
llama-server README lists metrics support]. GPU utilization is measured externally
(`nvidia-smi`, `powermetrics` on Apple) — the runtime does not instrument HBM
bandwidth.

## Key Takeaways
1. llama.cpp = **portability + constrained memory as architecture**: GGUF weights,
   `ggml` graph, 17 backends behind one op interface, per-layer device placement.
2. Its two regimes: **prompt = parallel compute** (threads/SIMD/GPU all engaged),
   **generation = bandwidth roof** (`~bandwidth × precision / model_bytes`) — the same
   roofline physics as the datacenter engines at different ceilings.
3. What it deliberately lacks (paged KV, iteration-level continuous batching,
   multi-node TP/EP, FP8 Tensor-Core paths) is exactly what vLLM/SGLang/TRT-LLM
   provide — the engines and the runtime occupy different corners of the
   device/concurrency space, and mixing them (llama.cpp for local, vLLM for the API
   tier) is a legitimate production pattern [I].
4. The quantization story (Q2_K→Q8_0 + i-quants, mixed-precision packaging) is
   independent of the engine question: GGUF is the portable-weight format, and vLLM
   can even serve GGUF-checkpointed models in some paths [A: check current vLLM GGUF
   support] — but the GGUF *ecosystem* is llama.cpp's home turf.

## Related
`Engine-Landscape.md` (layer stack) · `NVIDIA-NIM.md` · `Engine-Mega-Comparison.md` ·
`GPU-Systems/vLLM.md` · `GPU-Systems/SGLang.md` · `GPU-Systems/TensorRT-LLM.md` ·
`Inference/Roofline.md` · `Inference/The-Life-of-a-Token.md` · `KV-Cache/README.md` ·
`Quantization/README.md` · `Speculative-Decoding/README.md` ·
`Distributed-Inference/README.md` (parallelism dimensions)

## References
- ggml-org/llama.cpp — README (master, fetched 2026-08-24): goals, backends, quant
  tiers, tools, acknowledgements [F].
- ggml-org/ggml — the underlying tensor library [F: repo link in README].
- docs in-repo: `docs/build.md`, `docs/multi-gpu.md`, `docs/models.md`,
  `tools/server/README.md` [F: README references].
- No arXiv citations (repo-cited project per the citation bank).
