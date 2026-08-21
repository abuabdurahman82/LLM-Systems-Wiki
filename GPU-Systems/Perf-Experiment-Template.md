# Performance Experiment Template — How to Prove an Optimization Worked
`LAST_UPDATED: 2026-08-21 · Status: core page` · This is the **methodology** that keeps the
handbook out of "benchmark theater." Every optimization claim in this section should be
backed by an experiment shaped like this template.

## 30-Second Explanation
Most "speedups" are artifacts: cold caches, wrong clocks, un-warmed models, different
batch, different quant, different sampling. The template forces **one variable at a time,
identical everything else, repeated runs, P50/P95/P99, GPU + serving metrics, and a
mechanism explanation.** If you can't say *why* it got faster, you don't have a result —
you have a noise sample.

## The 9-step loop
```
1. Baseline      → fix model + quant + GPU + engine + version + workload + params
2. Hypothesis     → "X will cut ITL by ~N% because it reduces decode HBM bytes"
3. Change ONE variable → flip exactly one knob (quant on/off, batch, TP, kernel)
4. Benchmark      → ≥500 requests after ≥200 warm-up; closed-loop concurrency
5. Collect GPU metrics → Nsight/DCGM: BW util, SM util, occupancy, kernel time, launches
6. Collect serving metrics → TTFT, ITL/TPOT, P50/P95/P99, tok/s, req/s, goodput
7. Compare        → deltas vs baseline, same units, same concurrency
8. Explain WHY    → the roofline mechanism; if you can't, the delta is likely noise
9. Decide         → keep / revert / follow-up experiment
```

## Why each step exists (the anti-theater checklist)
- **Warm-up (≥200 req):** first requests hit cold prefix cache, cold L2, JIT/AOT kernel
  compile, CUDA-context init, clock ramp. Measure the steady state, not the ramp.
- **Repeated runs (≥5):** a single run is one sample; report mean + spread. If spread ≫
  delta, the delta is noise.
- **Controlled concurrency:** open-loop vs closed-loop give different results. Pin the
  arrival pattern. "Throughput at B=32" is undefined without the arrival model.
- **Identical model + quant:** comparing BF16 vs FP8 is only fair at the same base model
  and same quant method.
- **Identical dataset:** prompt lengths, context distribution, and shared-prefix rate
  change TTFT dramatically. Use the **same** request set for baseline and variant.
- **Identical generation params:** temperature, top-k/top-p, max_tokens,
  `seed`. Sampling changes acceptance/length → ITL.
- **P50/P95/P99 (not just mean):** tail latency is where SLOs live. A P50 win with a P99
  regression is a regression for users.
- **TTFT AND ITL AND throughput:** they trade off. Report all three; a TTFT win that
  tanks ITL is not a win.
- **Output throughput AND request throughput:** tokens/s vs req/s diverge when output
  length changes.
- **GPU memory + power:** a "faster" config that OOMs at the 5th concurrent request or
  trips power throttling (clocks drop) is not faster.
- **Clocks:** record GPU clock (boost vs sustained). Power capping and thermal throttling
  silently lower clocks between runs. `nvidia-smi --query-gpu=clocks.sm --format=csv`.

## The fairness pin (for engine/kernel comparisons)
Pin and log **all** of: model + revision, quant (+method), engine + version,
kernel backend, GPU + SKU, TP/PP/DP/EP, context limit, max-batch / max-num-seqs,
chunked-prefill on/off, CUDA-Graphs on/off, prefix-cache on/off, sampling, warm-up count,
concurrency model, dataset, and clocks. If any of these differs between two runs, the
comparison is **invalid** and must be redone. (This mirrors the fairness checklist in
`Serving-Engines/README.md` and `Labs/README.md`.)

## The metrics contract (every experiment reports these)
| Class | Metric | Where it comes from |
|---|---|---|
| Latency | TTFT (P50/P95/P99) | client-side first-token time |
| Latency | ITL / TPOT (P50/P95/P99) | client-side inter-token |
| Throughput | output tok/s, req/s | engine metrics + client |
| Util | GPU util%, SM active%, HBM BW util% | `nvidia-smi` / DCGM / Nsight |
| Util | Tensor Core util%, achieved occupancy | Nsight Compute |
| Memory | KV used, block util, peak VRAM, OOMs | engine + `nvidia-smi` |
| Power | power W, clock MHz (sustained) | `nvidia-smi` / DCGM |
| Tail | P99/P50 ratio | client |
| Quality | fixed 50-example task set / PPL | eval harness |
| Goodput | req/s at SLO met | client + SLO check |

## The "explain WHY" gate (roofline mechanism)
Before accepting a delta, name the mechanism and the roof it moves:
- "Faster because **decode bytes/token fell** (quant)" → check HBM BW util went up /
  bytes-per-token down; confirm we're **still under** the compute roof.
- "Faster because **kernel launches fell** (CUDA Graphs / fusion)" → check launch gaps in
  Nsight Systems shrank; SM idle% down.
- "Faster because **Tensor Cores used better** (FP8 GEMM)" → check `pipe_tensor` util up.
- "Faster because **less HBM traffic in attention** (FlashAttention)" → check prefill time
  down at long S, DRAM traffic down.
If the mechanism you name isn't visible in the GPU metrics, **the delta is suspect**.

## A worked mini-example [E, method]
**Hypothesis:** FP8 weights vs BF16 on a 27B, B=1 decode → ~1.8× ITL improvement.
- **Baseline:** 27B BF16, vLLM 0.25.x, 1×H100, B=1, 8k ctx, 500 req, 200 warm-up,
  T=0, max_out=128. ITL P50 = 34 ms. HBM util ~92% (bandwidth-bound, as predicted).
- **Variant:** 27B FP8 (same base, same engine), everything else identical. ITL P50 =
  19 ms. HBM util ~60% (now compute/launch leaning).
- **Compare:** 1.79×. **Explain:** bytes/token fell ~1.8× (2→1 B/weight) → decode was
  bandwidth-bound → time ∝ bytes → ITL ÷ ~1.8. The mechanism is **visible** (HBM util
  dropped, we're no longer pinned to the memory roof). **Decide:** keep, for decode-heavy
  workloads; re-check quality on the 50-example set.
(Numbers illustrative of the **method**, not a benchmark claim — run it on your hardware.)

## Common mistakes (the theater patterns)
1. **Reporting one run** → single sample, no spread. (Fix: ≥5 runs, mean + P99.)
2. **No warm-up** → cold-cache artifact reads as "speedup." (Fix: ≥200 warm-up.)
3. **Different batch/concurrency** → comparing apples vs oranges. (Fix: pin concurrency.)
4. **Mean only** → hides P99 regressions. (Fix: P50/P95/P99 always.)
5. **TTFT only** → hides ITL/throughput regressions. (Fix: all three.)
6. **No clocks logged** → power/thermal throttling between runs. (Fix: log clock + power.)
7. **No mechanism** → "it's faster" with no roofline story. (Fix: the WHY gate.)
8. **Vendor claim as [E]** → a vendor blog number is not your measurement. (Fix: tag
   `[F: vendor claim]` and reproduce locally.)

## How to measure it
The template **is** the measurement protocol. Reproducibility = the pinned fairness table
+ the metrics contract + the WHY gate, all logged in a CSV row per run (see
`Labs/README.md` conventions).

## Related
`Labs.md` (20 labs each follow this) · `Perf-Experiment-Template` is referenced by
`Engine-Comparison.md`, `Cross-Layer-Optimization.md`, `Case-Studies.md`, `Diagnostics.md` ·
`../Serving-Engines/README.md` (fairness checklist) · `../Labs/README.md` ·
`../Inference/Inference-Metrics.md`.

## Key Takeaways
1. **One variable at a time; pin everything else.** No pin → no comparison.
2. **Warm up, repeat, P50/P95/P99, TTFT+ITL+throughput, GPU+serving+power.** The full
   contract, not a single number.
3. **Explain WHY via the roofline** — if the mechanism isn't visible in GPU metrics,
   the delta is likely noise.
4. **Vendor numbers are [F: vendor claim], not [E].** Reproduce on your hardware.
