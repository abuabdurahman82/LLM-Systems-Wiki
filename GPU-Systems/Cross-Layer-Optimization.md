# Cross-Layer LLM Inference Optimization
`LAST_UPDATED: 2026-08-21 · Status: core page` · The most important conceptual chapter in
the section. Companion to `Kernel-Stack.md` (the map) and `Diagnostics.md` (the
decision tree).

## 30-Second Explanation
Optimizing **one layer** of the stack is never enough, because the layers are
**cascaded**: the output of one optimization becomes the input condition of the next.
Speed up the GEMM and the GPU finishes sooner → now the **NCCL AllReduce** is the
bottleneck. Quantize to INT4 and the weight traffic halves → now the **scheduler or
kernel-launch overhead** is the bottleneck. Every real performance investigation is a
hunt for the **next limiting resource**. This chapter teaches the method: optimize a
layer, re-measure, find what is now limiting, repeat — down the stack until the SLO is
met or you run out of levers.

## The full layer chain (from `Kernel-Stack.md`, restated)
```
Model architecture ─► Precision ─► Kernel ─► Memory hierarchy ─► Inference engine
   ─► Scheduler ─► Parallelism ─► Network ─► Cluster scheduler ─► Request router
   ─► Application
```
Each arrow is a **handoff**: the left side's output becomes the right side's input
constraint. The bottleneck can sit at **any** of these, and it **moves** as you fix
the others.

## Why single-layer optimization is insufficient (the core argument)
A system's throughput is limited by its **slowest link** (the classic pipeline /
waterfall view). But LLM inference is worse than a simple pipeline, because:
1. **The links are coupled by shared resources** (HBM, fabric, SMs). Fixing one link
   shifts load onto a shared resource that another link also uses.
2. **The regime changes** (compute-bound ↔ memory-bound ↔ latency-bound ↔ comm-bound)
   as you fix things — the *bottleneck's nature* changes, not just its magnitude.
3. **SLOs are per-percentile** (P99 ITL), so a fix that helps the mean can hurt the tail.

Therefore: **measure → fix one layer → re-measure → find the next limiter → repeat.**

## Worked examples (the "faster X exposes Y" patterns)

### Example 1: Faster kernel → NCCL becomes the bottleneck
- **Situation:** 27B model, TP=8, B=1 decode. ITL is ~55 ms.
- **Optimization:** swap the GEMV kernels for bandwidth-optimal FP8 skinny GEMMs →
  each GPU's local compute time drops ~40%.
- **Result:** ITL only drops to ~50 ms, not 33 ms. **Why:** with TP=8, **2 AllReduce per
  layer** run over NVLink every token; when the local GEMM shrank, the AllReduce time
  (which was hidden under the GEMM) is now a larger *visible* fraction. The bottleneck
  moved from **compute (GEMM)** to **communication (AllReduce)**.
- **Next lever:** reduce TP (TP=4, more work per GPU but fewer AllReduce), or
  overlapping (run the AllReduce concurrently with the next layer's GEMM), or move to
  a faster fabric. **Re-measure.**

### Example 2: INT4 → scheduler becomes the bottleneck
- **Situation:** 70B model, BF16, B=1, single GPU, ITL ~110 ms (bandwidth-bound: 140 GiB
  of weights streamed per token).
- **Optimization:** quantize weights to INT4 (W4A16) → weight bytes ÷ 4 → ITL drops to
  ~40 ms.
- **Result:** ITL is now ~40 ms but the **theoretical** INT4 ceiling is ~30 ms. The gap
  is **kernel-launch + scheduler overhead**: at B=1, each of the ~80 kernels/step
  (QKV, attn, O, 3×MLP, norms ×2, etc.) has ~0.3–0.5 ms launch latency, and the Python
  scheduler adds gaps.
- **Next lever:** **CUDA Graphs** (capture the launch sequence → one graph replay) +
  **kernel fusion** (norm+residual, QKV into one kernel). **Re-measure.**

### Example 3: FlashAttention → prefill scheduler becomes the bottleneck
- **Situation:** long-context service, S=32k, TTFT too high.
- **Optimization:** adopt FlashAttention-3 → prefill attention HBM traffic drops →
  prefill compute time drops ~2×.
- **Result:** TTFT drops, but **not** 2×. **Why:** at S=32k the attention is only ~8–15%
  of the prefill FLOPs (the GEMMs dominate, see `../Inference/The-Life-of-a-Token.md`);
  AND the **scheduler's chunked-prefill decision** (how many prompt tokens to admit per
  step, how to co-schedule with decodes) now limits how fast the prefill *stream*
  completes.
- **Next lever:** tune chunked-prefill size; or **P/D disaggregation** to isolate the
  prefill pool. **Re-measure.**

### Example 4: Batching to B* → HBM capacity becomes the bottleneck
- **Situation:** decode throughput low at B=8.
- **Optimization:** raise continuous-batching to B=64 (toward the knee batch B*) →
  weights amortized → tok/s up ~5×.
- **Result:** throughput up, but **KV cache fills** → requests queue, P99 ITL spikes,
  some OOM. **Why:** B=64 × 8k ctx × KV-per-token exceeds HBM capacity after weights.
- **Next lever:** **KV quantization** (FP8 KV halves capacity need), **GQA/MLA** (shrink
  h_kv), **eviction** (H2O/SnapKV), or **more HBM** (H200/B200). **Re-measure.**

### Example 5: P/D disaggregation → fabric becomes the bottleneck
- **Situation:** co-located serving, prefill stalls decodes (P99 ITL bad).
- **Optimization:** P/D split → decode ITL P99 improves.
- **Result:** TTFT on the decode pool rises (KV transfer latency), and the **fabric**
  now carries bulk KV transfers that compete with the decode pool's own AllReduce.
- **Next lever:** GPUDirect RDMA, hierarchical KV (transfer only the delta), KV-aware
  routing (place the decode on the GPU closest to the prefill). **Re-measure.**

## The method (make it a habit)
1. **Pick the SLO** that matters (P99 ITL? TTFT? goodput?).
2. **Profile the whole stack** (`Diagnostics.md`, `Profiling.md`) → name the *current*
   limiting resource and its layer.
3. **Apply ONE optimization** at that layer (change one variable, `Perf-Experiment-Template.md`).
4. **Re-measure the SLO + GPU metrics** (the roofline regime: compute/memory/latency/comm).
5. **Ask: what is now limiting?** The regime likely shifted.
6. **Repeat** until the SLO is met or no levers remain.
7. **Document the path** (which layer you fixed in which order, and why) — this is the
   reusable knowledge (`Case-Studies.md`).

## The "regime shift" table (what a fix at layer X typically exposes)
| You fix (layer) | Typical next limiter (layer) | Why |
|---|---|---|
| GEMM kernel (kernel) | NCCL / scheduler | compute shrank; comm/overhead now visible |
| Precision to INT4/FP4 (precision) | kernel-launch / scheduler | bytes down; overhead now dominates |
| FlashAttention (kernel) | prefill scheduler / GEMM | attention was small; GEMMs + scheduling dominate |
| Continuous batching (scheduler) | HBM capacity (KV) | more seqs → KV fills |
| P/D split (parallelism) | fabric (KV transfer) | bulk KV competes with collectives |
| TP up (parallelism) | AllReduce (fabric) | more collectives per token |
| Router fix (router) | KV pressure / hot experts | work redistributed, local capacity binds |
| More replicas (cluster) | router / SLO tail | scale-out exposes tail + imbalance |

## Hardware impact
Every cross-layer move re-balances the **three-number model** (`../Hardware/README.md`):
peak FLOPS, HBM BW, fabric BW. You are constantly deciding *which of the three numbers
your workload is actually using*, and shifting load between them.

## Inference impact
- The SLOs (TTFT, ITL/TPOT, P99, goodput) are the **output** of the whole stack; no
  single-layer metric captures them.
- A cross-layer win is **multiplicative** only if you fix the *right* layer in the
  *right* order; fixing a non-bottleneck layer buys ~nothing (and can regress the tail).

## Failure modes (the anti-patterns)
- **Fixing a non-bottleneck layer:** you optimize the GEMM when the scheduler is the
  limiter → no SLO gain, maybe a P99 regression. (Fix: profile first.)
- **Optimizing the mean, hurting the tail:** a fix that lowers P50 but raises P99
  (e.g. a bigger batch that increases variance). (Fix: track P99, not just mean.)
- **Regime-blind:** applying a memory-bound fix (quant) to a compute-bound workload
  (large prefill) → no gain. (Fix: name the regime from the roofline.)
- **Stale profiler:** profiling config A, optimizing for config B. (Fix: profile the
  config you'll ship.)

## How to measure it
- **The SLO deltas** (P50/P95/P99 TTFT/ITL, goodput) before/after each layer fix —
  the only numbers that matter.
- **The regime** (compute/memory/latency/comm) from GPU metrics after each fix — to
  confirm the bottleneck *moved* as predicted.
- **The "next limiter" log:** for each step, record which layer you fixed and what the
  profiler shows as the new bottleneck. This log **is** the cross-layer story.

## Related
`Kernel-Stack.md` (the map) · `Diagnostics.md` (the decision tree) · `Profiling.md`
(the tools) · `Perf-Experiment-Template.md` (one variable at a time) · `Case-Studies.md`
(10 worked cross-layer stories) · `GEMM.md` · `NCCL.md` · `Load-Balancing.md` ·
`../Inference/Inference-Optimization.md`.

## Key Takeaways
1. **Layers cascade:** fix one, and the bottleneck *moves* to the next limiting resource.
2. **The regime changes** (compute/memory/latency/comm) as you fix things — re-name it
   after every fix.
3. **Method:** profile → fix one layer → re-measure → find the next limiter → repeat,
   all the way down the stack.
4. **Fix the bottleneck layer, not a random one** — and watch the P99, not just the mean.
