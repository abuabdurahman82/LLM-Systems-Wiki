# The GPU Systems Lab — a Hands-On Roadmap
`LAST_UPDATED: 2026-08-22 · Status: core page` · The **DO** page: 12 ordered, hands-on labs that
turn the reading path (`Zero-to-Hero-Path.md`) into executed experiments. Part XXXV of the
GPU-Systems section. Every lab enforces the `Perf-Experiment-Template.md` discipline:
fix the variables, control the environment, report numbers, reproduce.

## 30-Second Explanation
Reading rooflines is not the same as *having* a roofline of your own. This page is a
dependency-ordered lab bench: **Lab 1 measures your machine's real ridge**, Labs 2–4 take a
GEMM from "wrong" to "within 30% of cuBLAS" to "Tensor-Core peak", Lab 5 shows the
FlashAttention IO win as a number, Labs 6–7 derive the decode roof and the KV concurrency
ceiling, Lab 8 puts quantization on the bandwidth curve, Lab 9 kills launch overhead,
Labs 10–11 put the fabric under a probe (NCCL, then TP on a real 7B), and Lab 12 runs one
full serving system end-to-end with the diagnostics tree. Each lab's output is an input to
the next: your ridge (L1) frames every roofline question, your BW number (L1/L6) frames
every decode number, your AllReduce curve (L10) frames every TP result (L11).
**No fabricated results here** — every "expect" is a hypothesis to *measure and confirm* on
your hardware; your logged number is the [E] result.

Hardware base (from `_STYLE.md`; cross-check `../Hardware/README.md`):
- H100 SXM [F: vendor spec]: 989 TFLOP BF16 dense · 3.35 TB/s HBM3 · ~900 GB/s NVLink
  aggregate · 132 SMs · 80 GB HBM3 (H200: 141 GB HBM3e).
- Theoretical H100 BF16 ridge ≈ 989/3.35 ≈ **295 FLOP/byte** [E, arithmetic: 989/3.35 = 295.2].
  Your *achieved* ridge (Lab 1) will be lower — that is the point of measuring it.
- The **example model** for all hand arithmetic: 6.5B-class dense (d=4096, L=32, d_ff≈11008,
  GQA h_kv=8, d_h=128); 13 GB in BF16; KV/token = 128 KiB [E, example model].

## Lab dependency map

```
 L1 roofline ──► L2 GEMM+coalesce ──► L3 tiling+smem ──► L9 fusion/graphs
    │   │            │                       │              │
    │   │            └────────► L4 TC-GEMM ──┼──► L5 FlashAttention
    │   └────────────► L6 GEMV ──────────────┼──► L8 quant GEMM
    │                                        │
    └──────────────► L7 KV math ─────────────┤
                                             │
 L10 NCCL ──► L11 TP@7B ──┐                  │
                          ▼                  ▼
                       L12 e2e serving system ◄────── (L2..L9, L11 feed L12)
```

Ordered list (build strictly in this order; skip L7/L8/L10–L11 only if you lack the
resource, never out of order):

```
L1 → L2 → L3 → L4 → L5 → L6 → L7 → L8 → L9 → L10 → L11 → L12
```

## The discipline every lab shares (from Perf-Experiment-Template.md)
- **Pin the variables:** GPU SKU, clocks (`nvidia-smi --query-gpu=clocks.sm --format=csv`),
  driver/CUDA version, dtype, shapes, warm-up count. One variable at a time.
- **Control the environment:** exclusive GPU (`CUDA_MPS_PIPE_DIRECTORY` off, no co-tenants),
  logged power/clock, same kernel for baseline and variant.
- **Report numbers:** ≥5 runs, mean + spread, P50/P95/P99 where it matters; one CSV row
  per run (the "How to log a lab" template below).
- **Reproduce:** script + seed + shapes in the lab folder; re-run after a reboot.
- **Tag claims:** [F] sourced · [A] assumption · [I] inference · [E] measured this session.

---

## Lab 1 — Measure your roofline
- **Goal:** replace every "H100 is ~3.35 TB/s / 989 TFLOP" recitation with *your* machine's
  numbers: achieved BW, achieved TFLOP, your own ridge.
- **Build:** (a) a copy kernel (vectorized global copy, e.g. float4, large buffer ≥1 GiB);
  (b) a large GEMM at a compute-dominant shape (e.g. M=N=K=8192, BF16, cuBLAS via
  PyTorch `torch.mm` and/or your Lab-3 kernel).
- **Measure:** achieved BW = 2·bytes_moved / time (read+write); achieved TFLOP = 2·M·N·K /
  time. Plot the roofline (BW roof ∝ FLOP/byte, compute roof flat). Ridge = TFLOP_peak_achieved
  ÷ (BW_achieved·10⁶) [E, your session].
- **Expect:** achieved copy BW in the 80–95% of 3.35 TB/s band [A, typical for vectorized
  HBM streams]; large GEMM TFLOP well above 3.35 × 295 ≈ 10⁸ FLOP/byte territory, i.e.
  comfortably compute-bound; your measured ridge **below** the theoretical 295 [I].
- **Done-when:** you can state "my ridge is ~X FLOP/byte on <GPU, measured copy BW ~Y TB/s,
  GEMM ~Z TFLOP" with ≥5 runs each and both numbers stable across re-runs.

## Lab 2 — Your first GEMM, then coalescing
- **Goal:** internalize that **coalescing is the #1 lever**: the same algorithm, re-indexed,
  moves the same data in fewer transactions.
- **Build:** a naive CUDA GEMM (one thread per C element, B row-major with strided B reads)
  and a coalesced version (consecutive threads read consecutive addresses; swap roles /
  adjust indexing so the inner loop is contiguous along the fast dimension).
- **Measure:** kernel time + DRAM throughput and DRAM utilization % from Nsight Compute
  (`ncu --section MemoryWorkloadAnalysis`); report BW-util as % of the Lab-1 achieved BW.
- **Expect:** the coalesced version at ≥2× the DRAM utilization of the naive one and a
  matching drop in kernel time [I]; L2 hit rate is the mechanism — confirm it in the
  section report, not just the clock time.
- **Done-when:** you can point at two Nsight screenshots (naive vs coalesced) and say which
  metric moved and why, with the time delta matching the BW-util delta. See
  `GEMM.md` § mapping and `Memory-Hierarchy.md` § coalescing.

## Lab 3 — Tiling + shared memory
- **Goal:** move the bottleneck from "DRAM per element" to "compute per tile" and watch the
  BW-vs-compute shift happen on your profiler.
- **Build:** a tiled GEMM: CTA tile T×T, A/B tiles staged through shared memory, register
  accumulation; add double buffering once the basic tile runs. Tune T ∈ {32, 64, 128}.
- **Measure:** time vs naive (Lab 2 coalesced) vs cuBLAS at a fixed small shape
  (M=N=K=1024, BF16) [A, "small" here means small relative to H100's cuBLAS sweet spot];
  Nsight Compute: DRAM utilization, SM busy %, achieved occupancy per tile size.
- **Expect:** tiled ≫ coalesced > naive; as T grows, DRAM utilization should fall and SM
  busy % rise — the kernel crosses from memory-bound toward compute-bound [I];
  **within ~30% of cuBLAS at 1024³** is the target [A].
- **Done-when:** your best tile is within ~30% of cuBLAS at the pinned shape, and your log
  row shows the DRAM-util drop that proves *why* tiling won. `GEMM.md` and
  `Memory-Optimizations.md` are the theory side.

## Lab 4 — Tensor-Core GEMM
- **Goal:** get onto the Tensor-Core roof and map the precision → TFLOP curve.
- **Build:** cuBLASLt GEMM (BF16, FP8 E4M3) and/or CUTLASS templates (TF32/BF16/FP8) at
  M=N=K=8192; one call per precision, otherwise identical.
- **Measure:** achieved TFLOP per precision; `pipe_tensor` utilization + DRAM utilization
  from Nsight Compute. H100 [F: vendor spec]: 989 TFLOP BF16 dense; FP8 dense ≈ 2× BF16.
- **Expect:** at large M, BF16 in the 70–90% of 989 band, FP32 an order of magnitude below
  it, TF32 between, FP8 ≈ 2× BF16 at the same shape [I]; DRAM util drops as precision
  drops at fixed M (less traffic per FLOP) [I].
- **Done-when:** you have a 4-row table (FP32/TF32/BF16/FP8 × TFLOP) on *your* GPU with the
  tensor-pipe util column attached; the FP8 row confirms the ~2× step. `Tensor-Cores.md`
  explains the MMA tile math behind each row.

## Lab 5 — FlashAttention (or a Triton attention)
- **Goal:** turn "FlashAttention is IO-aware, not a faster approximation"
  (`FlashAttention.md`) into a measured number at S=4096.
- **Build:** (a) a naive attention that materializes the S×S scores in HBM (the O(S²)
  round-trip version); (b) FlashAttention (a library call) or a Triton flash-style kernel,
  same B/H/d (use d=128, h=32 — the example-model geometry).
- **Measure:** kernel time at S=4096, B=1 (≥5 runs), plus DRAM bytes moved (Nsight Compute
  `dram__bytes.sum`) for each version. Naive traffic scales as S²·d per head batch [I];
  FlashAttention traffic is O(S·d·(h+1)-ish, sub-quadratic) [F, 2205.14135].
- **Expect:** the naive-vs-FA time gap to grow fast with S; at S=4096 the DRAM-byte ratio
  should be roughly the S²/(S·const) band, and the time ratio visibly smaller than the
  FLOP ratio (same FLOPs, fewer bytes) [I, 2205.14135 §3].
- **Done-when:** you can report "naive S=4096: X ms, Y GiB DRAM; FA: X′ ms, Y′ GiB" and
  the byte drop is the explanation you give in the log's WHY field.

## Lab 6 — The decode GEMV
- **Goal:** derive and *measure* your B=1 decode ceiling: tok/s ≈ BW ÷ weight-bytes.
- **Build:** skinny GEMMs at M=1 across the weight shapes of the 6.5B example model
  (QKV/O: 4096×4096-class; MLP: 4096×11008-class), BF16.
- **Measure:** achieved tok/s = 1 / (sum of per-layer GEMV times, ×32 layers); DRAM
  utilization per GEMV from Nsight Compute.
- **Expect [E, example model]:** 6.5B BF16 = 6.5e9 × 2 B ≈ **13 GB/token**; ceiling =
  3.35e12 / 13e9 ≈ **~257 tok/s** on an ideal H100. Your measured M=1 rate will sit
  *below* that (launch overhead, low parallelism at M=1, imperfect BW) [I] — the ratio of
  ceiling to measured is your "distance from the decode roof" number.
- **Done-when:** you have ceiling, measured, and the ratio logged; Nsight shows you are
  memory-bound but DRAM util < 90%, explaining the gap. This lab is the foundation of
  `Bandwidth-vs-Compute.md`'s decode side.

## Lab 7 — KV-cache math
- **Goal:** compute the concurrency ceiling your HBM imposes at two context lengths.
- **Build:** arithmetic (a script is fine) + an empirical check: fill KV blocks via an
  engine (vLLM `--max-num-seqs` sweep until OOM) or raw cudaMalloc of KV tensors.
- **Measure:** KV bytes/req = 128 KiB/token [E, example model] × S; concurrent requests
  that fit in your HBM minus weights.
- **Expect [E, example model, H100 80 GB]:** S=4096 → 4096 × 128 KiB = **512 MiB/req**;
  (80 GiB − ~13 GB weights − activations) ≈ 64 GiB → **~125 concurrent reqs**.
  S=128k (131072) → 131072 × 128 KiB = **16 GiB/req** → **~3–4 concurrent reqs** on 80 GB
  (~7–8 on H200's 141 GiB). The context length is the concurrency killer [I].
- **Done-when:** hand-computed bytes match the engine's reported KV usage within block
  rounding, and you can state your two concurrency ceilings as numbers. `../KV-Cache/README.md`
  has the full formula; `../Labs/README.md` Lab 2 runs the engine-side check.

## Lab 8 — A quantized GEMM
- **Goal:** put quantization on the bandwidth curve and see why speedup < bit-ratio.
- **Build:** W8A8 (e.g. FP8 or INT8 weights + activations) and W4A16 (4-bit weights, 16-bit
  activations, e.g. Marlin-class kernel) at the Lab-6 GEMV shapes and a large-M prefill
  shape (M=8192).
- **Measure:** achieved effective bandwidth (bytes actually moved ÷ time) and speedup vs
  BF16 for each quant, at M=1 and M=8192; quality on a fixed 50-example set or short
  perplexity suite (`Perf-Experiment-Template.md` § quality).
- **Expect:** W8A8 decode speedup ≈ 1.8–2× and W4A16 ≈ 2.5–3× — **below the 2×/4× bit
  ratio** — because of dequant/compute overhead and activation staying wide [I, A];
  prefill (M=8192) barely moves for weight-only quant (weights amortized over M rows)
  [I, 2306.00978, 2210.17323].
- **Done-when:** the quant → bandwidth → speedup table is filled with measured columns,
  the "why < bit-ratio" row cites the visible mechanism (dequant pipe / SM busy % up),
  and the quality row exists. `../Quantization/README.md` is the theory side.

## Lab 9 — Kernel fusion / CUDA Graphs
- **Goal:** make launch overhead visible, then kill it: launch-bound → compute-bound.
- **Build:** a 10-op decode step pipeline (RMSNorm → QKV GEMM → RoPE → attention → O-proj
  → residual → RMSNorm → MLP GEMM → activation → residual) un-fused; then (a) fused
  variants where the architecture allows (RMSNorm+residual, bias+act) and/or (b) the whole
  pipeline captured as a CUDA Graph.
- **Measure:** Nsight Systems timelines: total step time, kernel launch count, host-side
  gaps between kernels, SM idle % — for un-fused, fused, and graphed variants, B=1.
- **Expect:** un-fused B=1 shows host-visible gaps between small kernels (each kernel is
  ~µs-scale, launch ~5–10 µs [A]); after fusion/graphs the gaps shrink and total step
  time drops commensurate with the launch count cut [I]; at B=64 the same change is
  nearly invisible — batch is also a launch-overhead dial [I].
- **Done-when:** the three timelines are side by side in the log and the step-time delta
  matches (launches removed × avg launch cost) within spread. `Kernel-Life.md` and
  `Fused-Kernels.md` are the theory.

## Lab 10 — NCCL collectives
- **Goal:** characterize your fabric with the tool that TP will use: AllReduce bus
  bandwidth vs message size, 2/4/8 GPUs.
- **Build:** `nccl-tests` (`all_reduce_perf`) on 2, 4, 8 GPUs (intra-node NVLink; note the
  topology from `nvidia-smi topo -m`).
- **Measure:** bus bandwidth (GB/s) across message sizes (8 B → 8 GiB) per rank count;
  H100 NVLink aggregate ≈ ~900 GB/s [F: vendor spec].
- **Expect:** each curve is latency-bound at small messages (BW flat/low, time ≈ latency)
  and approaches the fabric peak at large messages; the knee location and the
  large-message plateau differ by rank count (more hops, more traffic) [I, `NCCL.md`
  ring: time ≈ 2(N−1)/N · size/BW].
- **Done-when:** you have 3 curves (2/4/8-rank), can name your knee size and large-message
  plateau, and say whether your plateau is NVLink-limited or lower [E, your session].
  `Multi-GPU.md` § why TP needs fast fabric and `../Networking/README.md` frame the next
  two labs.

## Lab 11 — TP on a small model
- **Goal:** see where the fabric bites on a real model: run a 7B-class model at TP=1/2/4.
- **Build:** vLLM (or SGLang) serving a 7B-class open model at `--tensor-parallel-size`
  1, 2, 4; same workload: S=2048 prompt, out=256, B=1 and B=8 (closed-loop), ≥200 warm-up,
  ≥500 requests [Perf-Experiment-Template].
- **Measure:** TTFT/ITL P50/P95/P99 + total tok/s per TP; AllReduce fraction = NCCL time ÷
  step time (Nsight Systems or the engine's profiling hooks).
- **Expect:** TP=1 baseline; TP=2/4 improve B=1 ITL (weights split across GPUs → fewer
  bytes/GPU/token, see Lab 6) until AllReduce time eats the gain [I]; the AllReduce
  fraction should track your Lab-10 latency/plateau behavior; at B=8 prefill/decode GEMMs
  stay compute-bound and TP helps less [I].
- **Done-when:** the TP scaling curve (1→2→4) is plotted with TTFT/ITL/tok-s and the
  AllReduce % per point, and the "fabric bites" point is labeled with the Lab-10 numbers
  that predict it. `Tensor-Parallelism.md` has the per-layer AllReduce layout.

## Lab 12 — End-to-end: one serving system
- **Goal:** the whole machine under a pinned workload; produce a real benchmark and apply
  the diagnostics tree to *your* bottleneck.
- **Build:** vLLM or SGLang (pin engine + version + model + quant exactly), a closed-loop
  workload (e.g. 512 prompt / 128 output, B=32, 500 requests after 200 warm-up), DCGM or
  Nsight sampling in the background.
- **Measure:** TTFT P50/P95/P99, ITL P50/P95/P99, output tok/s, req/s, GPU util, HBM BW
  util %, SM active %, KV used, clock + power (the full metrics contract from
  `Perf-Experiment-Template.md`).
- **Expect:** you will find *a* bottleneck — use the `Diagnostics.md` tree to name it
  (launch-bound? memory-bound? KV-limited? comm-bound?) and verify the branch with the
  metric the tree asks for [I]; at B=32 on one H100 with a 6.5–7B model, memory-bound
  decode or KV pressure are the common answers [I].
- **Done-when:** the benchmark row is logged per the template, the bottleneck is named
  with its confirming metric, and a one-paragraph "next experiment" follows the template's
  step 9. This lab is the capstone: every earlier lab's number should be citable in the
  interpretation. `../Labs/README.md` holds the serving-side lab set that runs in parallel.

---

## How to log a lab
One CSV row per run — the minimum that makes a result reproducible:

```
lab, date, gpu_sku, clocks, driver_cuda, dtype, shape_or_workload, kernel_or_engine,
warmup, runs, measured_bw_or_tflop, %_of_peak_or_ref, p50_p95_p99, ncu_or_nsys_note,
why_gate (mechanism), notes
```

Rules (from `Perf-Experiment-Template.md` + `../Labs/README.md` conventions):
- One run = one row; ≥5 runs per configuration; report mean + spread, P50/P95/P99 where
  latency matters.
- The `% of peak or reference` column is where your Lab-1 ridge and Lab-4 peaks live;
  every later lab's % should be readable against them.
- The `why_gate` column is mandatory: if the mechanism isn't visible in the profiler,
  mark the row UNVERIFIED and don't cite it as [E].
- Keep scripts + seeds in the lab folder; a lab that can't be re-run in 30 minutes is not
  logged, it's performed.

## The 80/20
If time is short, do **Labs 1, 2, 6, 10, 12** — they give ~80% of practical GPU-systems
skill:
1. **L1** — your own roofline: every other number becomes a %-of-mine.
2. **L2** — coalescing: the one kernel lesson that pays in every later lab.
3. **L6** — the decode GEMV ceiling: the single most-cited number in inference sizing.
4. **L10** — the fabric curve: you can read any TP/AllReduce result cold.
5. **L12** — the end-to-end benchmark: the habit that keeps all the rest honest.
Labs 3, 4, 5, 7, 8, 9, 11 deepen the same five skills into kernel, capacity, and
multi-GPU territory.

## Key Takeaways
1. **Measure your ridge first** — theoretical 295 (H100 BF16) is not your machine;
   Lab 1's number frames everything after it.
2. **The lab chain is a pipeline:** L1→L2→L3→L4 is the GEMM staircase; L6→L7 is the
   capacity story; L10→L11 is the fabric story; L12 fuses all three into one benchmark.
3. **Every "expect" is a hypothesis, not a result** — your logged, reproduced number is
   the [E]; the template's WHY gate is what separates a result from a noise sample.
4. **Coalescing, tiling, Tensor Cores, IO-awareness, launch overhead, fabric** — each lab
   isolates one mechanism and proves it on your hardware; skip none in order.
5. **Log like you'll defend it in review:** one CSV row per run, % vs your Lab-1 peaks,
   mechanism in the WHY column, scripts kept for 30-minute re-runs.

## Related
`Perf-Experiment-Template.md` · `Zero-to-Hero-Path.md` · `GEMM.md` · `Tensor-Cores.md` ·
`FlashAttention.md` · `Bandwidth-vs-Compute.md` · `Multi-GPU.md` · `Diagnostics.md` ·
`Kernel-Life.md` · `../Labs/README.md` (serving-side lab set) · `../KV-Cache/README.md` ·
`../Quantization/README.md` · `../Hardware/README.md`.

## References
- FlashAttention: 2205.14135 (IO-aware attention, O(S²) HBM traffic removed).
- NVIDIA H100 SXM datasheet constants (989 TFLOP BF16, 3.35 TB/s HBM3, ~900 GB/s NVLink)
  [F: vendor spec] — cross-checked in `_STYLE.md` and `../Hardware/README.md`.
- nccl-tests (NVIDIA/nccl-tests repo) for Lab 10; vLLM 2309.06180 / SGLang 2312.07104
  for Labs 11–12; Marlin/GPTQ 2210.17323 / AWQ 2306.00978 for Lab 8.
- Example-model arithmetic (6.5B, KV=128 KiB/token) per `_STYLE.md` convention.
