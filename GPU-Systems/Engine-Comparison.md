# Inference-Engine Comparison — vLLM vs SGLang vs TensorRT-LLM vs Others
`LAST_UPDATED: 2026-08-22 · Status: core page` · Deliverable 8 — the decision matrix. Architecture
claims [F] come from `./vLLM.md`, `./SGLang.md`, `./TensorRT-LLM.md` and each engine's docs; fit
judgments are [A] assumptions or [I] inferences. **No benchmark numbers appear in this page, by
design**: every "fastest/best" claim is a hypothesis to test on your own workload with
`./Perf-Experiment-Template.md`.

## 30-Second Explanation
The three production engines — **vLLM**, **SGLang**, **TensorRT-LLM** — differ along a few real
dimensions, not along a hidden speed ranking:
- **Flexibility vs peak-perf**: interpreter engines pick kernels at runtime and support new models
  day-0 (vLLM, SGLang); TRT-LLM compiles a per-(model, quant, shape, arch, TP) engine for peak
  performance on a stable model, at the cost of a rebuild on every config change [I: structural].
- **Host language & scheduler**: vLLM runs a Python async scheduler; SGLang runs a Python
  scheduler designed around a low-host-overhead goal (vendor term "zero-overhead"); TRT-LLM runs a
  C++ inflight-batching scheduler [F].
- **Model coverage vs peak-perf depth**: vLLM has the widest model/quant/kernel coverage; TRT-LLM
  has the deepest per-model multi-GPU optimization documentation [A].
- **How prefix sharing is decided**: hash-discovered (vLLM APC) vs program-declared
  (SGLang RadixAttention) vs config-level reuse (TRT-LLM) [F].
"Best" is workload-dependent: model, GPU SKU, request pattern, context length, concurrency,
quantization, and SLO all change the answer. This page gives the **dimensions, the tradeoffs, and
the method to compare fairly** — not a leaderboard. The only perf numbers that matter are the ones
you measure on your workload (`../Inference/Inference-Metrics.md`).

## The Comparison Matrix
The centerpiece. Columns: dimension × engine; TGI and llama.cpp are included as **context**
(different class: HF-native serving and edge/CPU respectively) — treat their cells as rougher
estimates. **No benchmark numbers anywhere in this table** — the "Performance profile" row is
deliberately qualitative ("tends to be", [I]) and must be replaced by your own measured [E]
numbers via the fair-comparison protocol below. Deep dives: `./vLLM.md`, `./SGLang.md`,
`./TensorRT-LLM.md`; kernel-stack detail: `./Kernel-Stack.md`.

| Dimension | **vLLM** | **SGLang** | **TensorRT-LLM** | **TGI / llama.cpp (context)** |
|---|---|---|---|---|
| **Kernel stack** | Pluggable backends: FlashAttention, FlashInfer, TRTLLM-GEN, FlashMLA, Triton attention; GEMM via CUTLASS / TRTLLM-GEN / CuTeDSL / FusedMoE; CUDA-Graph decode [F: vLLM docs] | FlashInfer-centric: paged + ragged attention JIT per (shape, arch); CUTLASS/Triton GEMM; CUDA Graphs [F: SGLang docs; FlashInfer arXiv:2501.01005] | Self-compiled: attention kernels generated per model/layout; GEMMs tuned per shape-bucket + SM arch; grouped GEMM for MoE; CUDA-Graph buckets [F: TRT-LLM docs] | TGI: FlashAttention + paged KV [F: repo]; llama.cpp: own CUDA/CPU kernels, GGUF layout [F: repo] |
| **Scheduling** | Python async, iteration-level continuous batching; chunked prefill co-scheduled; preemption (recompute/swap) [F: vLLM docs; Orca arXiv:2211.05102] | Continuous batching + chunked prefill in Python; low-host-overhead design goal ("zero-overhead", vendor term); program-aware admission [F: SGLang] | C++ inflight batching; chunked context; ADP Balance routes by remaining work [F: TRT-LLM docs] | TGI: continuous batching + paged KV [F: repo]; llama.cpp: server-mode batching, not an iteration-level research-grade scheduler [A] |
| **Prefix-cache approach** | Hash-based **APC**: per-block hash chain, refcount-shared paged blocks; sharing *discovered* at cache time [F: vLLM docs; arXiv:2309.06180] | **RadixAttention**: radix tree over token prefixes; sharing *defined structurally by the program* [F: arXiv:2312.07104] | Config-level KV-cache reuse: shared prefixes point at shared blocks [F: TRT-LLM docs] | TGI: prefix caching (check current docs) [A]; llama.cpp: prompt/context reuse, not a server prefix cache [A] |
| **Speculative decoding** | n-gram, suffix, EAGLE, DFlash drafters [F: vLLM docs] | n-gram, EAGLE, STAGE, DFlash, Spec V2; co-designed with grammar-constrained output [F: SGLang docs] | n-gram, EAGLE, Llama-draft; guided + spec decoding cooperate across CPU/GPU [F: TRT-LLM docs] | TGI: draft-model spec decode [A: check docs]; llama.cpp: draft-model spec decode [F: repo] |
| **P/D disaggregation** | Disaggregated prefill/decode/encode over shared memory, NIXL, or RDMA [F: vLLM docs] | P/D disaggregation supported; program-aware scheduler knows sibling requests [F: SGLang] | P/D gets NVL72-specific treatment; Dynamo is the orchestration layer [F: TRT-LLM docs; NVIDIA Dynamo] | No native P/D disaggregation [I] |
| **Multi-GPU / parallelism** | TP / PP / DP / EP [F: vLLM docs; `./Multi-GPU.md`] | TP intra-node; large-scale EP demonstrated at 96×H100 [F: SGLang blog]; multi-node via NCCL [F: SGLang docs] | TP / PP / EP / ADP / DWDP + NVL72 — deepest public multi-GPU documentation [F: TRT-LLM docs] | TGI: TP [F: repo]; llama.cpp: tensor split across GPUs + CPU offload [F: repo] |
| **MoE support** | FusedMoE kernels + expert parallelism [F: vLLM docs] | MoE with large-scale EP [F: SGLang docs] | Wide-EP optimization series; grouped/batched expert GEMMs [F: TRT-LLM docs] | llama.cpp: MoE runs via GGUF, EP limited [A]; TGI: MoE models supported [A] |
| **Quantization coverage** | Widest of the big three: FP8, NVFP4/MXFP4, INT8/INT4, GPTQ, AWQ, GGUF, compressed-tensors, ModelOpt [F: vLLM docs] | FP4-class, FP8, INT4, AWQ, GPTQ [F: SGLang docs] | FP8 / INT8 / INT4 / NVFP4 + ModelOpt checkpoint path; KV-cache quant [F: TRT-LLM docs] | llama.cpp: GGUF Q2–Q8 + i-quant, the edge reference [F: repo]; TGI: GPTQ/AWQ/bnb [A] |
| **Model coverage / new-model speed** | Tends to be the day-0 default; widest architecture coverage [A: observed release pattern] | Broad; tends to trail vLLM by a little on brand-new architectures [I] | Strong on supported models; new architectures lag behind interpreter engines because of the build pipeline [I] | llama.cpp: day-0 for nearly any model via GGUF [A]; TGI: tracks the HF ecosystem [A] |
| **Performance profile (qualitative — NO numbers here)** | Tends to be strong for general high-throughput serving; whether the Python event loop holds at very high batch is an open hypothesis [I] — workload-dependent | Tends to be strong at high concurrency with shared prefixes: structural sharing + low host overhead target the two dominant agentic costs [I: consistent with the vendor design goal] | Tends to be peak for a stable model on fixed NVIDIA hardware, especially multi-node NVL72-class; pays it in per-model build cost [I] | Tends to be the CPU/edge/heterogeneous choice; not a datacenter-throughput contender [I] |
| **Maturity / ecosystem** | Largest community; widest kernel plugins; Prometheus V1 [A] | LMSYS-backed, research-adjacent, fast-moving [A] | NVIDIA first-party; ModelOpt + Dynamo gravity; deepest multi-GPU docs [A] | TGI: HF-maintained [A]; llama.cpp: largest open C/C++ LLM repo [A] |
| **When to pick it (a hypothesis, not a verdict)** | Default general-purpose start point — test H1 on your workload | Agentic / structured / shared-prefix traffic — test H2 on your measured prefix hit rate | Stable model + fixed NVIDIA HW + build friction you can absorb — test H3 at your SLO | Edge / CPU / heterogeneous, or HF-native serving — test H4 on your device |

**How to read this matrix.** Rows 1–9 and 11 are architectural facts or stated assumptions —
they are stable and you can trust them for planning. Row 10 is deliberately worded as "tends to
be": it is a *fit* judgment [I], not a measurement, and it inverts on some workloads. Row 12 is a
hypothesis to verify, not a recommendation to follow.

## The Dimensions That Actually Matter (Why This Matrix, Not a Speed Table)
A speed table would be fiction: it would fix one workload and claim universality. The real
decision space is:

**1. The flexibility ↔ peak-perf spectrum.** One pole is the interpreter engine: kernels chosen
at runtime, one binary for every model, day-0 support, custom-kernel plugins; the other pole is
the compiled engine: kernels tuned at build time for one (model, quant, shape, arch, TP),
peak on a stable model, rebuild on every change.

```
  FLEXIBILITY + BREADTH                        PEAK SINGLE-MODEL PERF
 ┌────────────────────────────────┐    ┌────────────────────────────────┐
 │ interpreter engine             │    │ compiled engine                │
 │ · kernels picked at runtime    │    │ · kernels tuned at build       │
 │ · day-0 new models             │    │ · peak on stable model + arch  │
 │ · widest quant coverage        │    │ · rebuild per (model,quant,    │
 │ · custom-kernel plugins        │    │   shape, arch, TP)             │
 │ · release = config change      │    │ · release = build + re-capture │
 │ representatives: vLLM, SGLang  │    │ representative: TRT-LLM        │
 └────────────────────────────────┘    └────────────────────────────────┘
```
Within the interpreter pole the two engines still differ: **vLLM** = breadth + pluggable kernel
ecosystem; **SGLang** = program-aware, prefix-strong, low-host-overhead by design goal [F].
Neither pole dominates: the workload does.

**2. "How fast does a new model land."** A real differentiator that speed tables hide. A new
architecture ships; vLLM or llama.cpp tends to serve it the same week, SGLang shortly after,
TRT-LLM after its builder adds support and you re-build [A: observed pattern; verify per
release]. If your model rotation is monthly or faster, day-0 speed can beat any stable-model
peak [I].

**3. "How much do I have to write vs configure."** llama.cpp: you write little — GGUF + flags.
vLLM: mostly configuration (`--max-num-seqs`, chunked-prefill flags, backend pinning) [F: vLLM
docs]; you only *write* kernels when you add Triton backends. SGLang: you declare program
structure (DSL) once and the scheduler exploits it. TRT-LLM: you write/maintain a build pipeline
and one engine artifact per config — the 2×2×2×2 = 16-engine combinatorics worked through in
`./TensorRT-LLM.md`. The engine that minimizes your engineering time is as valuable as the one
that minimizes your ITL [I].

**4. P/D disaggregation + KV-aware routing — the forward-looking axis.** Prefill (compute roof)
and decode (memory roof) are different bottleneck regimes; splitting them onto different GPUs
(`./Prefill-Decode-Disaggregation.md`) and routing requests to replicas whose prefix cache is
warm ("balance remaining work, not requests", `./Load-Balancing.md`) is where multi-replica
serving is heading. All three engines have pieces of this; the engine whose disaggregation +
routing story fits your cluster topology will matter more at scale than any single-GPU speed
difference [I].

## How to Run a FAIR Comparison (Method, No Fake Numbers)
The matrix above tells you *what* to compare; this tells you *how* to make the comparison valid.
Full protocol: `./Perf-Experiment-Template.md`; metric definitions:
`../Inference/Inference-Metrics.md`.

- **Fix everything except the engine**: model + revision, quant (+ method, + calibration),
  GPU SKU + count, clocks (logged, throttling ruled out), TP/PP/EP, context limit,
  max-batch / max-num-seqs, chunked-prefill on/off, CUDA-Graphs on/off, prefix-cache on/off,
  attention backend (vLLM) / kernel selection, sampling (temp/top-p/max_tokens/seed).
  Any pin that differs between two runs invalidates the comparison.
- **Fix the workload**: prompt-length distribution, output-length distribution,
  prefill/decode mix, and — critical — the **shared-prefix rate**. A 60% prefix-overlap
  workload rewards RadixAttention and APC; a 0% overlap workload does not. "B=32" is
  undefined without the arrival model (closed vs open loop).
- **Measure the full contract**: TTFT P50/P95/P99, ITL/TPOT P50/P95/P99, output tok/s,
  req/s, P99/P50 ratio, KV block utilization, prefix hit rate, HBM BW util, power/clocks.
  Never report one number; TTFT/ITL/throughput trade against each other.
- **Warm up and repeat**: ≥200 warm-up requests discarded; ≥5 runs per config, interleaved
  across engines so drift (thermal, clock) affects everyone.
- **Explain WHY**: a delta you can't tie to a roofline mechanism (bytes/token, launch
  count, prefix hit rate, KV capacity) is noise, not a result.
- **The matrix cell becomes [E] for YOUR workload.** After one pinned run, "vLLM tends to
  be strong for general throughput" is replaced by "vLLM at P50 ITL = X ms on my model,
  my S, my B" — a measured number [E] that is true *for that workload only*, not a
  universal claim. Sizing reference for P/D discussions: the handbook's example model
  (L=32, h_kv=8, d_h=128, BF16) has KV/token = 2·32·8·128·2 = 131,072 B = **128 KiB/token**
  [E, example model — same arithmetic as `./vLLM.md`], so a 32k-context sequence carries
  ~4 GiB of KV that P/D transfer must move.

**Worked example: a comparison protocol** (20 lines — fill in, do not run blindly):

```
Engine comparison protocol (template; pin every line)
model:      <org/model @ revision>                      # identical for all engines
quant:      BF16 (or FP8 + method + calibration set)
hardware:   1x H100-SXM; log clocks + power every run
parallel:   TP=1 (or pin TP=N for all engines; TRT-LLM: build engine for this TP)
engine A:   vLLM <ver>; pin attention backend; APC on; chunked prefill on; max-num-seqs=128
engine B:   SGLang <ver>; radix cache on; same effective max concurrency
engine C:   TRT-LLM <ver>; engine pre-built for (model, quant, shapes, arch, TP)
workload:   500 requests; S ~ {prompt dist}; out ~ {dist}; shared-prefix rate {p%}
concurrency: closed-loop B in {1, 32, 128}
warm-up:    200 requests, discarded
repeats:    5 runs/engine, interleaved; report P50/P95/P99 per metric
record:     TTFT, ITL/TPOT, out tok/s, req/s, P99/P50 ratio, KV block util,
            prefix hit rate, HBM BW util, CUDA-graph hit fraction
gate:       if ANY pin differs between two runs -> redo those runs
decide:     overwrite the matrix perf-row with your [E] numbers; name the WHY per delta
```

## Decision Guide — Hypotheses, Not Winners
Each entry is a hypothesis to test, not a declared winner. Every one ends the same way:
**verify on your workload** with the pinned protocol above.

- **H1 — Default general-purpose: start from vLLM.** Broadest model/quant/kernel coverage,
  largest community, day-0 support, OpenAI-compatible API [A: common default]. If your traffic
  is general serving with modest prefix overlap, it is the lowest-risk first candidate.
  Verify on your workload.
- **H2 — Structured / multi-turn traffic with strong prefix reuse: SGLang.** RadixAttention +
  program-aware scheduling + native grammar-constrained decoding target exactly the agentic
  cost structure: shared system prompts, multi-turn history, schema outputs, high concurrency
  [A]. Strongest when your measured prefix overlap is high; test the hit rate first.
  Verify on your workload.
- **H3 — Peak single-model perf on stable hardware: TensorRT-LLM.** You are willing to own a
  build pipeline, the model is stable, the NVIDIA SKU is fixed, and you need the last
  increment of stable-model performance — often multi-node NVL72-class [A]. The hypothesis
  breaks the moment the model rotates weekly. Verify on your workload at your SLO.
- **H4 — Edge / CPU / heterogeneous: llama.cpp (or TGI).** No-GPU, low-precision GGUF,
  CPU+GPU hybrid, or HF-native serving are different device classes where the three
  datacenter engines are simply not the right tool [A]. Verify on your workload (device,
  precision, latency budget).
- **H5 — Long-horizon / P/D / agentic at scale: the disaggregated + KV-aware route.**
  High-concurrency SLOs where TTFT and ITL both matter, long shared contexts, multi-replica
  clusters: P/D disaggregation + prefix-aware routing (Dynamo-class, llm-d-class, or
  native) may dominate single-GPU engine choice entirely [I]. The engine question becomes a
  cluster-topology question; test both layers. Verify on your workload and your topology.

Choosing between H1 and H2, or between H1/H2 and H3, is a measured question. Run the protocol;
the matrix's qualitative perf row gets replaced by your [E] numbers; the decision is yours.

## Key Takeaways
1. The engines differ along real dimensions — flexibility vs peak-perf, host language,
   model-coverage speed, prefix-cache mechanism, P/D + routing — not along a universal
   speed ranking; this page deliberately contains no benchmark numbers.
2. vLLM = breadth + pluggable kernels; SGLang = program-aware + structural prefix sharing;
   TRT-LLM = compiled peak on stable NVIDIA models. Each is the right first hypothesis for
   a different workload class; none is "the fastest."
3. "How fast does a new model land" and "how much do I have to write vs configure" decide
   as much as performance does — speed tables hide both.
4. A fair comparison pins model/quant/GPU/workload/arrival/concurrency/backend/params,
   measures TTFT + ITL + throughput + P95/P99 + utilization, warm-ups, repeats, and names
   the mechanism (`./Perf-Experiment-Template.md`).
5. After one pinned run, the matrix's perf row becomes your own [E] numbers for that
   workload only — the engine decision is then a measurement, not a faith claim.

## Related
`./vLLM.md` · `./SGLang.md` · `./TensorRT-LLM.md` (deep dives) · `./Inference-Engines.md`
(why engines exist) · `./Kernel-Stack.md` (where engines plug into the kernel stack) ·
`./Perf-Experiment-Template.md` (the pinned protocol) · `./Load-Balancing.md` (KV-aware
routing) · `./Prefill-Decode-Disaggregation.md` · `./Multi-GPU.md` ·
`../Inference/Inference-Metrics.md` (TTFT/ITL/throughput definitions) ·
`../Inference/Continuous-Batching.md` · `../Speculative-Decoding/README.md` ·
`../KV-Cache/README.md` · `../Serving-Engines/README.md` (engine-fit one-pagers + fairness
checklist).

## References
- Kwon et al., "Efficient Memory Management for LLM Serving with PagedAttention", SOSP'23,
  arXiv:2309.06180 [F].
- Zheng et al., "SGLang: Efficient Execution of Structured Language Model Programs",
  arXiv:2312.07104 [F].
- Yu et al., "FlashInfer: Efficient LLM Serving with Custom Attention Kernels",
  arXiv:2501.01005 [F].
- Yu et al., "Orca: A Distributed Serving System for Transformer-Based Generative Models",
  OSDI'22, arXiv:2211.05102 [F].
- Li et al., "EAGLE: Speculative Decoding with Embedding-Level Augments", arXiv:2401.15077 [F].
- Engine docs (architecture claims, current feature availability — check current docs):
  github.com/vllm-project/vllm · github.com/sgl-project/sglang ·
  github.com/NVIDIA/TensorRT-LLM · github.com/huggingface/text-generation-inference ·
  github.com/ggml-org/llama.cpp [F: repos].
- Vendor claims ("zero-overhead" term, 96×H100 EP deployment, class-of-speedup blog
  numbers) — [F: vendor claim] in `./SGLang.md`; never presented as independent results here.
