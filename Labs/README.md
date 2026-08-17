# Hands-On Research Labs
`LAST_UPDATED: 2026-08-16` · 12 labs. Each: hypothesis / setup / commands / metrics /
expected observations / interpretation. All runnable on a single GPU + one serving
engine (vLLM shown; SGLang equivalents noted). Keep every lab's output in a
reproducible folder; tag claims [E] (measured) vs [I] (inferred).

Common setup (assume a 24–96GB GPU):
- `pip install vllm torch` · model: a 7B-class open model (Qwen/Llama-class, BF16 or
  FP8). For 27B use NVFP4/FP8 if HBM allows.
- Timing: client-side (aiohttp, keep-alive); report P50/P95/P99 at fixed concurrency.
- Always: warm up (≥200 requests) before measuring; log engine version + GPU + clocks.

## Lab 1 — Measure TTFT and ITL
- **Hypothesis:** TTFT ∝ prefill length (compute-bound); ITL flat vs prefill length
  (decode-bound) until KV-read dominates.
- **Setup:** single request, S ∈ {512, 4k, 32k}, out=128, B=1.
- **Commands:** `vllm serve ... --enable-chunked-prefill`; client records first-token
  time (TTFT) and inter-token times (ITL).
- **Metrics:** TTFT, mean/P95 ITL, tok/s.
- **Expected:** TTFT rises ~linearly with S (until chunking/kernel effects); ITL
  roughly flat, rising slightly at 32k (KV read).
- **Interpretation:** confirms the prefill/decode split; the point where ITL starts
  rising marks KV-read becoming significant.

## Lab 2 — Observe KV-cache growth
- **Hypothesis:** KV bytes = `2·L·B·h_kv·d_h·S·b`; engine reports utilization.
- **Setup:** B=1, vary S; read `gpu_cache_utilization` / `kv_cache` metric.
- **Commands:** curl the engine's metrics endpoint; plot util vs S.
- **Metrics:** reported KV used vs your hand-computed equation.
- **Expected:** measured ≈ hand-computed (within block-size rounding).
- **Interpretation:** validates the budget equation; the gap = block overhead.

## Lab 3 — Compare MHA vs GQA
- **Hypothesis:** at equal context, GQA (h_kv<h_q) uses less KV → higher max
  concurrency.
- **Setup:** two models of similar size, one MHA-era, one GQA; fix S; raise B until KV
  OOM.
- **Metrics:** max B before OOM; KV bytes/req; ITL at a common B.
- **Expected:** GQA holds ~2–4× more concurrent sequences.
- **Interpretation:** h_kv is the KV-budget dial (confirm
  `Model-Architectures/Attention-Head-Designs.md`).

## Lab 4 — Benchmark FP16 vs FP8 vs INT4
- **Hypothesis:** lower precision → fewer bytes/token → higher decode tok/s (until
  compute ridge or quality cliff); prefill mostly unaffected (weight-only).
- **Setup:** same 7B at BF16 / FP8 / INT4 (AWQ/GPTQ); same workload, B=1 and B=8.
- **Metrics:** tok/s, ITL P95, VRAM, plus a fixed 50-example quality check (perplexity
  or a short task set).
- **Expected:** decode tok/s up ~1.5–2× (BF16→FP8→INT4); quality: FP8 ≈ lossless, INT4
  small drop.
- **Interpretation:** separates the bandwidth win from the accuracy cost.

## Lab 5 — Test continuous batching
- **Hypothesis:** at fixed B, throughput rises with B up to the roofline knee;
  P99 ITL stable under continuous (vs static) batching.
- **Setup:** closed-loop B ∈ {1, 8, 32, 128}; out=256 fixed.
- **Metrics:** total tok/s, P50/P95/P99 ITL, GPU util, goodput.
- **Expected:** tok/s ↑ with B; ITL P99 ↑ near the knee; static batching (if available)
  wastes slots.
- **Interpretation:** the GEMV→GEMM amortization; find your knee batch.

## Lab 6 — Test prefix caching
- **Hypothesis:** shared prefix → lower TTFT on repeat.
- **Setup:** 32 requests sharing a 4k system prompt; first batch cold, later warm.
  Compare `--enable-prefix-caching` on/off.
- **Metrics:** TTFT P50/P95 (cold vs warm), KV util.
- **Expected:** warm TTFT drops sharply; caching off → no drop.
- **Interpretation:** prefix caching is a TTFT tool; measure the hit-rate effect.

## Lab 7 — Benchmark speculative decoding
- **Hypothesis:** EAGLE/n-gram spec decode lowers ITL at B=1–8, ~unchanged at high B.
- **Setup:** B=1, 8, 32; spec on/off; log acceptance rate if exposed.
- **Metrics:** ITL P50/P95, tok/s, acceptance rate.
- **Expected:** big ITL win at low B; little at high B.
- **Interpretation:** spec decode is a latency (not throughput) tool.

## Lab 8 — Compare vLLM and SGLang
- **Hypothesis:** engine choice matters; differences show most at high B / shared-
  prefix / long-context.
- **Setup:** same model+quant, both engines, B=1/8/64, S=1k/32k, prefix on/off.
  Pin: kernel backend, sampling, context limit, chunked-prefill, CUDA graphs, versions.
- **Metrics:** TTFT/ITL P50/P95/P99, tok/s, goodput.
- **Expected:** winner varies by cell (that's the point); log which kernel each used.
- **Interpretation:** no global winner (the fairness checklist is the method; see
  `Serving-Engines/README.md`).

## Lab 9 — Profile inference with Nsight
- **Hypothesis:** decode steps are HBM-bandwidth-bound; Nsight shows memory throughput
  near peak, SMs idle.
- **Setup:** Nsight Systems on a B=1 decode run; capture a 10s window.
- **Metrics:** memory throughput vs peak, SM occupancy, kernel launch gaps.
- **Expected:** high DRAM bandwidth, low SM active %.
- **Interpretation:** visual confirmation of the roofline regime.

## Lab 10 — Build a model router
- **Hypothesis:** routing easy→small, hard→large cuts cost at equal quality.
- **Setup:** a 1B + a 7B; a classifier (LLM-judge or embedding) assigns each query.
- **Metrics:** $/token, accuracy on a fixed set vs always-large.
- **Expected:** 30–60% cost cut, small accuracy dip (tune the threshold).
- **Interpretation:** routing is a cost/quality dial; the router itself is an LLM cost.

## Lab 11 — Experiment with KV eviction
- **Hypothesis:** at 25–50% KV budget, a good eviction (H2O/SnapKV-style) beats
  random but degrades vs full.
- **Setup:** long-context QA (32k doc, 5 Qs); KV budget ∈ {100%, 50%, 25%}; policy ∈
  {none, sliding, attention-score top-k}.
- **Metrics:** answer accuracy, ITL, KV used.
- **Expected:** accuracy holds at 50%, drops at 25%; ITL improves with budget cut.
- **Interpretation:** the quality-vs-memory frontier; heuristics vs learned (open).

## Lab 12 — Build a two-model agent/evaluator system
- **Hypothesis:** an independent evaluator improves agent output quality; measure the
  model-vs-harness split.
- **Setup:** worker model + a separate evaluator model (different family) that critiques
  and requests revision; run a task set (a) bare worker, (b) worker+evaluator loop,
  (c) worker+better harness (retries, tools).
- **Metrics:** task success, revision count, tokens/cost.
- **Expected:** (b) > (a) on correctness; (c) varies; record the deltas.
- **Interpretation:** a data point for the model-vs-harness question
  (`Harness-Engineering/README.md`).

## Conventions
- Log: engine+model+quant version, GPU, clocks, concurrency, warm-up, sampling,
  kernel backend. One run = one CSV row.
- Report P50/P95/P99 + mean. Tag [E]/[I]. Never present a vendor number as [E].
- Keep scripts in `/tmp` (or the lab folder) for re-runs.

## Related
`Inference/Inference-Metrics.md` · `Inference/Roofline.md` · `Serving-Engines/README.md`.
