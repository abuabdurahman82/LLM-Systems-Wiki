# Diagnostics — How to Diagnose an LLM Performance Problem
`LAST_UPDATED: 2026-08-22 · Status: core page` · The **DECISION TREE** page.
`Cross-Layer-Optimization.md` says "find the next limiting resource"; this page is the
concrete flow for finding it: step by step, with the tool that reveals each branch, the
typical cause, the fix, and how to confirm the bottleneck actually moved.

## 30-Second Explanation
A performance problem — bad ITL, bad TTFT, low throughput — lives at **exactly ONE
layer of the stack at a time**: the bottleneck. Fix that layer and the bottleneck
**moves** to the next limiting resource; it does not disappear. Your job is therefore to
**FIND the layer**, not to optimize everything:
- Optimizing a non-bottleneck layer buys ~nothing (and can regress P99). [I: core argument]
- The regime (compute / memory / launch / KV / scheduler / comm / storage) is a **name
  you derive from metrics**, not a guess from the symptom. [I]
- Every step below has the same six-field shape: *what to look for → the symptom →
  the tool that reveals it → the typical cause → the fix → how to confirm it moved*.
- The tree runs from the **outside in**: "is it even a GPU problem?" (Step 0) down to
  "which physical resource is the GPU actually saturated with?" (Steps 2–8).
Read this page with `./Cross-Layer-Optimization.md` (the method) and `./Profiling.md`
(which tool answers which question).

## The Decision Tree
```
Symptom: "ITL/TTFT/throughput is bad"
├─ Step 0: Is it even a GPU problem? (CPU-side: Python GIL, tokenizer, scheduler, API server, router, NCCL host overhead)
├─ Step 1: GPU utilization (nvidia-smi/DCGM) — is the GPU busy or idle?
│   ├─ GPU idle a lot → CPU/scheduler/kernel-launch bound (→ Kernel-Life.md, Cross-Layer)
│   └─ GPU busy → where?
│       ├─ Step 2: Compute-bound? (Tensor Core util high, BW util low) → kernel quality / quantization
│       ├─ Step 3: Memory-bandwidth-bound? (BW util high, compute util low) → decode regime; quantize / better GEMV
│       ├─ Step 4: Kernel-launch-bound? (many small kernels, GPU gaps) → fusion / CUDA Graphs
│       ├─ Step 5: KV-cache-limited? (OOM, low occupancy, eviction) → bigger KV, quantized KV, P/D
│       ├─ Step 6: Scheduler-limited? (batch not full, poor packing) → continuous batching, chunked prefill
│       ├─ Step 7: Network-limited? (NCCL kernels dominate, cross-node) → topology, TP intra-node
│       └─ Step 8: Storage-limited? (model load, checkpoint, offload) → HBM/CPU/NVMe hierarchy
```
Note: Steps 2–8 are **a checklist, not a strict ladder** — a single step can show two
resources (e.g. compute *and* comm), so rank them by **fraction of step time** [I:
synthesis], fix the biggest one, re-run the tree.

## Step 0 — Is it even a GPU problem? (CPU side)
- **What to look for:** load is present but the GPU looks nearly idle.
- **Symptom:** requests are queued or slow while `nvidia-smi` util is low/intermittent;
  host CPU is hot; the delay lives *between* forward passes, not inside one.
- **The tool that reveals it:** `nvidia-smi -l` (util over time) next to a host profiler
  (`py-spy`, `perf`), plus API-server / router queue depth. [F: standard practice]
- **Typical cause:** Python GIL contention in the serving loop; slow tokenize/detokenize
  on the hot path; a single-threaded scheduler; the API server or router serializing
  requests; NCCL host-side overhead. [I: typical]
- **The fix:** async / offloaded scheduling, move tokenization off the critical path,
  fix the router (balance remaining work, not just requests — `Load-Balancing.md`),
  move sampling off the CPU.
- **Confirm it moved:** GPU util rises under the same load, kernel gaps shrink on the
  Nsight timeline, host CPU cools. Then restart the tree at Step 1.

## Step 1 — GPU utilization: busy or idle? (first triage)
- **What to look for:** the routing question for everything downstream.
- **Symptom:** sustained high GPU util% → the GPU is doing real work → go to Steps 2–8
  to find *which* resource is saturated. Mostly idle under load → something upstream is
  starving it → Step 0 (CPU), Step 4 (launch gaps), or Step 6 (scheduler not filling).
- **The tool that reveals it:** `nvidia-smi` / DCGM util% over time. [F: NVIDIA DCGM]
- **Typical cause of "idle":** launch gaps, an under-filled batch, CPU-side stalls —
  not an inefficient kernel.
- **The fix:** none directly; util% only routes you.
- **Confirm it moved:** n/a — the output is the branch choice. **Trap:** util% does not
  say *which* resource is busy (SMs? memory? fabric?) — that is Steps 2–3, and the
  subject of the 9-field trap below. [I: the whole page hinges on this distinction]

## Step 2 — Compute-bound?
- **What to look for:** the GPU is busy **and** the bottleneck is FLOPs.
- **Symptom:** Nsight Systems shows long GEMM kernels dominating the step; Tensor-Core
  util high, HBM BW util low. Usually prefill (large M) or large-batch decode.
  [A: typical prefill signature]
- **The tool that reveals it:** Nsight Compute: `sm__inst_executed_pipe_tensor`,
  achieved FLOP/s vs peak; the Nsight Systems kernel timeline. [F: Nsight Compute docs]
- **Typical cause:** BF16 weights on FP8-capable hardware; GEMM shapes not hitting
  tuned kernels; no FlashAttention on long prefill; TP too small to finish prefill in
  time (TTFT).
- **The fix:** quantize weights (FP8/FP4), better kernels (cuBLASLt algo / custom,
  `Custom-GEMM.md`), FlashAttention, chunked-prefill sizing, TP for TTFT. [I]
- **Confirm it moved:** Tensor-Core util drops (or FLOPs per kernel drop) and HBM BW
  util or NCCL time rises to the new ceiling; the SLO delta matches the mechanism you
  predicted (the WHY gate in `./Perf-Experiment-Template.md`).

## Step 3 — Memory-bandwidth-bound?
- **What to look for:** the classic **decode regime**.
- **Symptom:** HBM BW util near peak, SM / Tensor-Core util low — the GPU mostly
  waits on HBM. The step is a stream of GEMVs that read the full weights per token.
  [A: typical decode signature]
- **The tool that reveals it:** DCGM / Nsight: `dram__throughput` vs peak BW, achieved
  bytes/s per kernel; roofline position (AI below the ridge, `./Bandwidth-vs-Compute.md`).
- **Typical cause:** unquantized weights (2 B/weight), big KV reads at long context, or
  a GEMV kernel that doesn't coalesce (strided access, a large-M cuBLAS kernel picked
  for M=1).
- **The fix:** quantize weights (INT8/FP8/FP4 → bytes/token falls proportionally), a
  better skinny GEMV, batch up toward the knee B* (amortizes weights, but watch ITL),
  GQA/MLA to cut KV bytes.
- **Confirm it moved:** BW util drops below the roof and compute/launch becomes the new
  ceiling; ITL delta ≈ the bytes/token ratio. If the delta is *less* than predicted, the
  GEMV kernel was part of the problem, not just the dtype. [I]

## Step 4 — Kernel-launch-bound?
- **What to look for:** **many small kernels** with idle gaps between them.
- **Symptom:** Nsight Systems shows a sawtooth — kernel, gap, kernel, gap — with SMs
  idle for a large fraction of the step; per-token time is dominated by launch +
  host-side scheduling, not by any single kernel. [A: typical low-batch signature]
- **The tool that reveals it:** Nsight Systems timeline (gap fraction), kernels-per-step
  count, launch rate; `./Kernel-Life.md` explains where the launch cost lives.
- **Typical cause:** low-batch decode (B=1–4) with dozens of unfused kernels per
  layer-step, Python/framework overhead between launches, no CUDA Graphs.
- **The fix:** CUDA Graphs (capture the step → one replay), kernel fusion (RMSNorm +
  residual, QKV, bias + act — `Fused-Kernels.md`), raise the batch, off-CPU sampling.
  [I: standard fix]
- **Confirm it moved:** gap fraction in the timeline drops, SM idle% drops, launches per
  step drop. Then BW or compute usually becomes the ceiling.

## Step 5 — KV-cache-limited?
- **What to look for:** the GPU has room to compute, but **no room for the KV**.
- **Symptom:** OOM on KV allocation, or the scheduler cannot admit requests (the
  "waiting" queue grows, `gpu_cache_utilization` pinned high), forced eviction, P99 ITL
  spikes at high concurrency.
- **The tool that reveals it:** engine metrics — num running/waiting requests, KV block
  utilization, OOM events — plus `nvidia-smi` memory. [F: vLLM/SGLang metrics]
- **Typical cause:** HBM capacity left after weights is small relative to
  concurrency × context; no KV quantization; long-context requests draining the pool.
- **The fix:** FP8/INT8 KV quant (halves KV bytes), bigger HBM, GQA/MLA, eviction
  (H2O/SnapKV), smaller max-seq-len, or P/D disaggregation
  (`./Prefill-Decode-Disaggregation.md` — a decode pool with its own KV budget).
- **Confirm it moved:** the waiting queue drains, KV utilization stays under the cap,
  and the next ceiling shows up (usually Step 3 or Step 7).

## Step 6 — Scheduler-limited?
- **What to look for:** the GPU is under-used **even though requests exist**.
- **Symptom:** running batch ≪ the engine's max, poor packing (mixed lengths stranding
  slots), prefill blocking decode (no chunked prefill), admission policy starving the
  tail workloads.
- **The tool that reveals it:** engine metrics (num running seqs vs max, queue depth,
  prefill/decode step mix) and the Nsight timeline (idle windows between scheduled steps).
- **Typical cause:** static batching, no continuous batching, chunked-prefill disabled
  or mis-sized, a first-come-first-served admission that ignores remaining work.
- **The fix:** continuous batching (iteration-level admission), chunked prefill (co-
  schedule prefill with decode), KV-aware / remaining-work-aware admission
  (`Load-Balancing.md`).
- **Confirm it moved:** batch utilization and GPU util rise; the next ceiling is usually
  KV capacity (Step 5) or bandwidth (Step 3) — the two scheduler-shifts in
  `./Cross-Layer-Optimization.md`.

## Step 7 — Network-limited?
- **What to look for:** multi-GPU / multi-node, and **collectives are a big fraction
  of the step**.
- **Symptom:** NCCL kernels (AllReduce / AllGather / AllToAll) dominate the Nsight
  timeline; visible comm time inside decode ITL; cross-node TP; AllReduce that was
  hidden under the GEMM and is now visible after the GEMM shrank (the worked example 1
  in `./Cross-Layer-Optimization.md`).
- **The tool that reveals it:** Nsight Systems (NCCL kernel fraction), NCCL debug logs,
  DCGM NVLink/PCIe counters, `nvidia-smi topo -m`. [F: NCCL docs]
- **Typical cause:** TP across nodes over a slow fabric, a wrong topology path, no
  comm/compute overlap, TP degree too high for the fabric.
- **The fix:** move TP intra-node (NVLink), overlap comm with compute, lower TP or mix
  in PP/EP (`./Multi-GPU.md`), fix the topology (`Topology.md`), upgrade the fabric.
- **Confirm it moved:** NCCL's fraction of step time drops; compute or BW becomes the
  ceiling; ITL delta ≈ the removed comm time. [I: expected mechanism]

## Step 8 — Storage-limited?
- **What to look for:** the problem is at **load time / checkpoint time / offload**, not
  in steady-state token generation.
- **Symptom:** slow model load or checkpoint save; weight/KV offload to CPU RAM or NVMe
  causing HBM ↔ system-memory thrashing; step time balloons whenever data ping-pongs
  between hierarchy levels.
- **The tool that reveals it:** DCGM / `nvtop` PCIe throughput, I/O counters,
  time-to-first-token after a restart, copy kernels on the Nsight timeline. [I]
- **Typical cause:** offload-by-design with PCIe-bound copies, huge checkpoint writes,
  unpinned host buffers, no NVMe-direct path.
- **The fix:** keep weights in HBM (shrink the offload), pinned memory for H2D, fast
  NVMe + GPUDirect Storage, smarter offload policy (hot layers on-GPU), bigger HBM.
  [I: standard]
- **Confirm it moved:** load/offload time drops, copy kernels leave the steady-state
  timeline, and the steady-state ceiling (Steps 2–7) resurfaces.

## The flagship trap, 9 fields: "GPU util 90% = the GPU is the problem"
The single most common misdiagnosis in inference work [I: this is where most
investigations waste a day]:
1. **What you see:** `nvidia-smi` reports ~90% GPU util.
2. **What it suggests:** "the GPU is the bottleneck; my kernels must be slow."
3. **What it actually is:** util% says *a* resource is busy — not *which* one. 90% can
   be HBM bandwidth (bandwidth-bound decode) with the Tensor Cores mostly idle.
4. **The tool that reveals it:** Nsight Compute / DCGM, splitting "util" into SM
   active%, `dram__throughput`%, and Tensor-pipe%. [F: Nsight Compute docs]
5. **Typical cause of the wrong read:** util% is a single scalar that conflates
   compute, memory, launch, and comm time into one number.
6. **The fix you'd take if you were right:** "optimize the GEMM" — which does nothing
   for a bandwidth-bound GEMV already streaming HBM at the roof.
7. **The regime you should name first:** compute / memory / launch / comm — the
   `./Bandwidth-vs-Compute.md` roofs, read from separate metrics, not from util%.
8. **How to confirm the fix moved it:** after the fix, the *other* metric rises to the
   ceiling (BW→SM active, or comm fraction) — the bottleneck relocated, it didn't vanish.
9. **The next layer to check:** after a BW fix, it is usually launch/scheduler
   (Steps 4–6) or KV capacity (Step 5) — exactly the "next limiting resource" step of
   `./Cross-Layer-Optimization.md`.

## Common misdiagnoses (the other traps)
- **"GPU util 90% = the GPU is the problem"** — wrong, see the 9-field trap above:
  util ≠ which resource.
- **"Throughput low → add more GPUs"** — maybe it is the router or scheduler
  (Steps 0/6), not compute. Scale-out a non-bottleneck layer and you just buy more
  idle GPUs.
- **"TTFT high → bigger prefill"** — maybe it is queueing / admission (Step 6), not
  prefill compute. TTFT = queue time + prefill time; only the split tells you which.
- **"ITL high → slow GPU"** — maybe it is kernel-launch bound at low batch (Step 4)
  or network (Step 7); check the timeline gaps and NCCL fraction first. [I]
- **"Bandwidth-bound → quantize"** — sometimes it is a *bad GEMV* (coalescing, kernel
  selection for M=1) rather than the dtype; quantize only after the bytes/s per kernel
  is near the roof.

## Symptom → first tool → likely layer (quick table)
| Symptom | First tool | Likely layer (step) |
|---|---|---|
| Requests queued, GPU util low under load | `nvidia-smi -l` + host profiler (`py-spy`) | CPU / API server / router (0) |
| GPU util oscillates; gaps between kernels | Nsight Systems timeline | launch / scheduler (4, 6) |
| Long GEMM kernels; Tensor-Core util high | Nsight Compute (`pipe_tensor`) | compute roof (2) |
| HBM BW near peak; SMs mostly idle | DCGM / Nsight (`dram__throughput`) | memory roof, decode (3) |
| KV OOM / forced eviction | engine metrics (KV block util, running/waiting) | KV capacity (5) |
| Batch size ≪ max; poor packing | engine metrics (num running seqs) | scheduler (6) |
| NCCL kernels a big fraction of the step | Nsight Systems + NCCL logs | network (7) |
| Slow load / checkpoint / offload thrash | DCGM PCIe counters, I/O counters | storage (8) |
| High TTFT, normal ITL | prefill vs queue time split | prefill path / admission (0, 2, 6) |
| High ITL at B=1, fine at B>8 | Nsight Systems gaps | launch overhead (4) |
| P99 ≫ P50, P50 fine | serving metrics + scheduler trace | tail: scheduling / interference (5, 6) |

## How to CONFIRM the bottleneck moved
A fix only "works" if the bottleneck demonstrably relocated — not just if the SLO ticked
up:
1. **Re-run the tree from Step 0** on the new config, with the same pinned workload
   (`./Perf-Experiment-Template.md`: one variable changed, everything else identical).
2. **Check the regime shift:** the metric that was at the ceiling should now be off it,
   and a *different* metric should be at the new ceiling. That different metric *is* the
   next limiting resource (`./Cross-Layer-Optimization.md` "regime shift" table).
3. **Pass the WHY gate:** the SLO delta must match the mechanism you predicted
   (bytes/token fell, gaps shrank, NCCL fraction dropped). If the mechanism is not
   visible in GPU metrics, the delta is suspect.
4. **Watch the tail, not just the mean:** a P50 win with a P99 regression is not a
   confirmed move — it may be a load shift onto KV or a scheduler tail.
5. **Log it:** "fixed layer X → next limiter is layer Y" is the cross-layer story; keep
   a per-step log (the "next limiter log" in `./Cross-Layer-Optimization.md`), which
   becomes the case study (`Case-Studies.md`).
Stop when the SLO is met or no levers remain at any layer.

## Related
`./Cross-Layer-Optimization.md` (the method this tree operationalizes) ·
`./Perf-Experiment-Template.md` (pin the config, one variable, WHY gate) ·
`./Profiling.md` (tool catalog) · `./GPU-Metrics.md` (metric → SLO mapping) ·
`./Kernel-Life.md` (launch overhead, CUDA Graphs) · `./Bandwidth-vs-Compute.md`
(compute vs memory roofs) · `./Multi-GPU.md` + `NCCL.md` + `Topology.md` (Step 7) ·
`./Prefill-Decode-Disaggregation.md` (Step 5's structural fix) · `Kernel-Stack.md`
(the layer map) · `Case-Studies.md` (worked paths through this tree).

## Key Takeaways
1. **One bottleneck at a time;** your job is to find its layer, not to optimize all of
   them.
2. **Run outside-in:** CPU side → GPU busy/idle → *which resource* (compute / BW /
   launch / KV / scheduler / comm / storage).
3. **Util% routes you; it never answers the question.** Split "busy" into SM%, DRAM%,
   Tensor%, NCCL fraction before choosing a fix.
4. **Confirm by relocation:** the old ceiling drops, a new ceiling rises, and the SLO
   delta matches the mechanism — else it's noise or a load shift.
