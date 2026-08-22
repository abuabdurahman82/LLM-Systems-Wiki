# GPU Metrics — The Dashboard for LLM Inference
`LAST_UPDATED: 2026-08-22 · Status: core page` · PART XXXII — the metric layer of the
GPU-systems handbook. Every metric below is mapped to (a) the roofline regime it
falsifies or confirms ([Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)) and (b) the
serving SLO it moves ([Inference-Metrics](../Inference/Inference-Metrics.md)). Tool
coverage: `nvidia-smi`, DCGM, Nsight Systems/Compute; tool-to-question routing is in
`Profiling.md`, decision trees in `Diagnostics.md`.

## 30-Second Explanation
A slow LLM service is one of four problems: **compute-bound** (Tensor Cores near
peak — usually prefill), **bandwidth-bound** (HBM near peak — usually decode),
**latency-bound** (SMs and HBM both idle, many µs-scale kernels — small-batch
decode), or **communication-bound** (fabric near peak, GPUs waiting on each other
— TP/EP/P-D). GPU metrics are how you tell them apart: SM utilization says the GPU
is *busy*, Tensor-Core utilization says the *compute roof* is loaded, memory-bandwidth
utilization says the *memory roof* is loaded, warp stalls say *why* threads wait,
kernel gaps say the CPU can't feed the GPU, and fabric counters say the network is
the bottleneck. Each of these falsifies or confirms one regime, and each regime has a
known SLO signature: bandwidth-bound → **ITL high**; compute-bound → **TTFT high**;
latency-bound → **ITL high at low batch**; comm-bound → **both high**. The traps:
`GPU-Util` ≠ which resource is loaded; P50 can be fine while P99 breaks; and a
"mystery" slow kernel is often just a capped clock (`nvidia-smi -q -d CLOCK`).

## Part A — GPU-side metrics: meaning, bottleneck tell, tool
Each entry: **meaning** (one line) → **what it tells you** → **tool**.

### 1. SM utilization (GPU-Util)
- **Meaning:** fraction of the *sampling window* in which at least one kernel is
  resident on the device. [F: nvidia-smi/DCGM docs]
- **Tells you:** the GPU is engaged vs idle. A *low* value with a *high* request
  rate → CPU/scheduler-bound (host can't enqueue). A *high* value tells you nothing
  about **which** resource is saturated — it can be 80% while HBM is idle and
  Tensor Cores idle (launch-bound small kernels). It is a gate, not a diagnosis.
- **Tool:** `nvidia-smi` (GPU-Util), DCGM `PROF_SM_ACTIVE` / `DCGM_FI_PROF_SM_ACTIVE`.

### 2. Tensor Core utilization
- **Meaning:** fraction of peak MMA (mixed-precision matrix-multiply-accumulate)
  throughput achieved by the active kernels. [F: Nsight Compute docs]
- **Tells you:** the **compute-bound** tell. High Tensor-Core util + low DRAM
  util → you are on the compute roof: prefill GEMMs, big-batch decode past B*,
  or training. If decode kernels show meaningful Tensor-Core util, your GEMM shape
  is too small to stream weights efficiently — wrong kernel choice (`GEMM.md`).
- **Tool:** Nsight Compute `sm__inst_executed_pipe_tensor` /
  `sm__pipe_tensor_op_hmma.active` (per-kernel); no direct nvidia-smi equivalent.

### 3. Memory-bandwidth utilization
- **Meaning:** achieved HBM (DRAM) throughput ÷ sustained peak HBM bandwidth.
- **Tells you:** the **decode/BW-bound** tell. ≈90%+ on decode kernels → the memory
  roof is loaded; the only levers left are *fewer bytes* (quantize weights/KV) or
  *more work per byte* (batch past B*, [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)
  E3). Low on decode kernels with ITL high → something else (launch, comm, clocks).
- **Tool:** Nsight Compute `dram__throughput.avg.pct_of_peak_sustained_elapsed`
  (the canonical metric); DCGM `PROF_DRAM_ACTIVE` for live monitoring. 9-field deep
  dive below.

### 4. Achieved occupancy
- **Meaning:** resident warps per SM ÷ maximum warps the SM can hold, averaged over
  the kernel. [F: CUDA C Programming Guide]
- **Tells you:** low occupancy → **register pressure** (regs/warp capped the
  blocks/SM), too few threads launched (B=1 grids: one block per row), or
  small shared-memory allocations. Occupancy is *necessary but not sufficient* for
  bandwidth hiding: a memory-bound GEMV can hit near-peak BW at low occupancy if
  each warp issues enough in-flight requests.
- **Tool:** Nsight Compute (achieved occupancy in the launch/section summary).

### 5. Warp stall reasons
- **Meaning:** a histogram of *why* warps sat at each instruction issue:
  `long_scoreboard` (waiting on global/L2 memory), `short_scoreboard` (shared),
  `barrier`, `branch_resolving`, `wait` (fixed-latency dependency), `not_selected`,
  `membar`, `no_instruction`, etc. [F: Nsight Compute docs]
- **Tells you:** the "why is it slow" signal — the single most useful Nsight
  section. `long_scoreboard` dominant → memory latency not hidden: raise occupancy,
  widen access, or (for decode) accept that you *are* the memory roof. `barrier` →
  sync/fusion boundary. `branch_resolving` → divergent control flow (MoE gating,
  sampling). `not_selected` → healthy: enough work, scheduler just rotating.
- **Tool:** Nsight Compute only (per-kernel `stall_*` metrics); no live equivalent.

### 6. L2 hit rate
- **Meaning:** fraction of L2 requests served from the L2 partition vs sent to DRAM.
- **Tells you:** cache efficiency / locality. Low hit rate on a *prefill* kernel
  with big K is expected (streaming); low hit rate on decode *KV* reads with a
  PagedAttention layout that fragments blocks → the effective bytes/token is higher
  than your model says. KV-cache placement, block size, and GQA all show up here.
- **Tool:** Nsight Compute `l2__request_hitrate` / per-slice hit rate.

### 7. DRAM throughput
- **Meaning:** absolute HBM bytes/s actually moved (reads + writes), vs the
  utilization percentage above (absolute vs relative — keep both in a report).
- **Tells you:** the raw byte stream feeding the memory roof. Decode: compare
  achieved DRAM B/s against the bytes-per-token model
  (`(weight_bytes + KV_bytes)/ITL`); a big gap → the GEMV kernel isn't streaming
  efficiently (strided access, bad tiling, kernel picks).
- **Tool:** Nsight Compute `dram__bytes.sum`; DCGM live DRAM activity
  (`PROF_DRAM_ACTIVE`); `nvidia-smi` memory-utilization (coarse, sampling-based).

### 8. Kernel duration + kernel launch rate
- **Meaning:** per-kernel wall time, plus the count/rate of kernel launches and the
  **gaps** between them on the GPU timeline.
- **Tells you:** the **launch-bound** tell. Many µs-scale kernels with idle gaps →
  the latency roof of [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md) regime 3;
  small-batch decode on an unfused stack (≈ 9–10 kernels/layer × 32 layers,
  [The-Life-of-a-Token](../Inference/The-Life-of-a-Token.md)) [I]. Long kernels with
  no gaps → look at stall reasons instead. CUDA Graphs and fusion attack exactly
  this metric (`Kernel-Life.md`, `Fused-Kernels.md`).
- **Tool:** Nsight Systems (GPU timeline: `nvprof`-class gap detection),
  PyTorch Profiler (op-level), DCGM kernel-activity sampling (coarse).

### 9. PCIe / NVLink throughput
- **Meaning:** bytes/s actually crossing the on-node fabric (per link, per direction).
- **Tells you:** the **intra-node interconnect tell**. TP AllReduce traffic
  (2 AllReduces/layer, `Tensor-Parallelism.md`), EP AllToAll
  (`MoE-Expert-Parallelism.md`), and P/D KV transfer
  (`Prefill-Decode-Disaggregation.md`). If NVLink is near its sustained ceiling and
  HBM is idle → the fabric *is* the roof and TP degree or topology is the lever
  (`Multi-GPU.md`, `Topology.md`). Also catches topology mistakes (PCIe path instead
  of NVLink path silently degrading NCCL, `NCCL.md`).
- **Tool:** DCGM NVLink counters (`DCGM_FI_PROF_NVLINK_*`), `nvidia-smi nvlink`,
  Nsight Systems (P2P transfers), `nccl-tests` (bus bandwidth).

### 10. Network throughput (fabric, cross-node)
- **Meaning:** bytes/s over IB/RoCE/Ethernet between nodes (per rail, per NIC), plus
  collective latency.
- **Tells you:** the **cross-node comm-bound** tell. EP and PP live here; a
  multi-node TP degree shows up as "NCCL time ≈ compute time" in the trace. Low
  achieved vs link rate → topology/rail affinity or GPUDirect issues
  (`Multi-Node.md`, `Scale-Up-vs-Scale-Out.md`).
- **Tool:** `nccl-tests` (all_reduce/alltoall bus bandwidth), IB counters
  (per-rail port counters), Nsight Systems + NCCL debug logs (`NCCL_DEBUG=INFO`),
  DCGM where NIC telemetry is exposed [I: platform-dependent].

### 11. GPU power + clocks
- **Meaning:** actual draw vs the power cap, and actual SM/memory clocks vs the
  nominal boost clocks — plus the **throttle reason bits** (SW power cap, HW
  thermal, SW thermal, sync boost). [F: nvidia-smi/DCGM docs]
- **Tells you:** the **throttling tell**. A kernel that "mysteriously" runs 2×
  slower is often running at ~45% of nominal clock under a power or thermal cap
  [I: common failure pattern] — every other metric then lies by the same factor
  (utilization looks fine, throughput halves). Check clocks *before* profiling
  microarchitecture; DCGM `CLOCK_EVENT_COUNTERS` /
  `nvidia-smi -q -d CLOCK` makes capping visible in production.
- **Tool:** `nvidia-smi` (power.draw, clocks, throttle reasons), DCGM
  `POWER_USAGE` / `SM_CLOCK` / `CLOCK_EVENT_COUNTERS` (fleet-scale capping).

## Part B — Serving-side metrics: the SLO layer
Glossary and per-workload choice: [Inference-Metrics](../Inference/Inference-Metrics.md). This page adds the **GPU side** of each metric.

- **TTFT (time-to-first-token)** — request-in → first token out = queue time +
  prefill. The **prefill-side SLO**. GPU signature: Tensor-Core utilization high
  during the window (compute roof); if SM util is *low* while TTFT is high, the
  time is queue/scheduler, not compute. Prefill interference (chunked-prefill vs
  decode steps on the same SMs) inflates TTFT under load
  (`Prefill-Decode-Disaggregation.md`).
- **ITL / TPOT (inter-token latency / time-per-output-token)** — gap between
  consecutive tokens; TPOT ≈ mean ITL over a request. The **decode-side SLO**.
  GPU signature: DRAM throughput near peak + Tensor Cores idle = bandwidth roof;
  kernel gaps = launch roof; fabric near peak = comm roof.
- **tokens/sec** — per-request (= 1/ITL for one stream) and aggregate
  (system output rate). Aggregate tok/s is what batching buys; per-request tok/s
  is what the user feels. Report both, at a pinned concurrency
  (`Perf-Experiment-Template.md`).
- **requests/sec** — completed requests / time. Pure throughput; says nothing
  about SLO conformance — see goodput.
- **P50 / P95 / P99** — percentiles of TTFT/ITL. SLOs are built on the tail; the
  P50 is a marketing number. Tail causes: long-context requests (KV reads grow),
  hot experts (MoE capacity spikes, `MoE-Expert-Parallelism.md`), preemption/GC of
  KV blocks, prefill interference, throttling.
- **goodput** — *SLO-conforming* requests/sec under a fixed arrival/concurrency
  regime [F: DistServe (arXiv:2401.09670), Orca, llm-d usage]. The capacity metric
  once latency limits exist: throughput keeps rising as goodput falls, past the
  SLO-conformance knee. 9-field deep dive below.

### GPU-metric → SLO mapping (the pairs that matter)
1. **DRAM-BW-util↑ + Tensor-Core-util↓ + ITL high** → decode bandwidth-bound.
   Levers: quantize (bytes↓), batch to B* (AI↑), KV shrink (GQA/MLA, KV quant).
   *The most common serving signature at low-to-mid batch.*
2. **Tensor-Core-util↑ + DRAM-util↓ + TTFT high** → prefill compute-bound.
   Levers: FP8/FP4, FlashAttention, longer prefix-cache hits, more TP.
   Usually *correct* behavior — don't "fix" prefill with quant if the SLO is ITL.
3. **NCCL/fabric fraction of step time↑ → TTFT *and* ITL both high** →
   communication-bound. Check link counters first (9/10 above): NVLink vs PCIe
   path, topology, EP imbalance. Lever: topology, hierarchy collectives, colocated
   P/D (`Multi-GPU.md`, `NCCL.md`).
4. **Low occupancy + many short kernels + gaps + ITL high at low batch** →
   launch-bound. Levers: CUDA Graphs, fusion, raise batch, off-CPU sampling
   (`Kernel-Life.md`).
5. **SM-util low + DRAM-util low + TTFT/ITL high** → the GPU is not the problem:
   CPU/scheduler/tokenization/KV-allocator bound (`Diagnostics.md` branch 1).
6. **Throughput drifts down over time + throttle bits set + clocks < nominal** →
   capping; every metric in this page is off by the same factor. Fix cooling/
   power budget before anything else (11 above).

## Master table — metric → tells you → SLO → tool
| Metric | What it tells you | SLO it moves | Tool |
|---|---|---|---|
| SM utilization | engaged vs idle; gate only | TTFT + ITL (both, indirectly) | nvidia-smi, DCGM `SM_ACTIVE` |
| Tensor Core utilization | compute roof loaded (prefill / big batch) | TTFT | Nsight Compute |
| Memory-BW utilization | memory roof loaded (decode) | ITL | Nsight Compute, DCGM `DRAM_ACTIVE` |
| Achieved occupancy | regs-pressure / launch-shape limits | ITL (low batch) | Nsight Compute |
| Warp stall reasons | *why* warps wait (memory/barrier/branch) | ITL | Nsight Compute |
| L2 hit rate | locality; KV/weight access efficiency | ITL | Nsight Compute |
| DRAM throughput (B/s) | raw bytes moved vs bytes-per-token model | ITL | Nsight, DCGM |
| Kernel duration + launch rate | launch-bound vs kernel-bound | ITL at low batch | Nsight Systems |
| PCIe / NVLink throughput | intra-node fabric roof (TP/EP/P-D) | TTFT + ITL | DCGM NVLink, `nccl-tests` |
| Network throughput (fabric) | cross-node comm roof (EP/PP) | TTFT + ITL | `nccl-tests`, IB counters |
| Power + clocks | throttling; scale factor on everything | TTFT + ITL (drift) | nvidia-smi, DCGM |
| TTFT | prefill + queue SLO | — (user-facing) | engine Prometheus |
| ITL / TPOT | decode SLO | — (user-facing) | engine Prometheus |
| P50/P95/P99 | where SLOs break (tail) | — (user-facing) | engine Prometheus |
| goodput | capacity under SLO limits | — (user-facing) | engine Prometheus + offline |

## 9-field template: memory-bandwidth utilization (the #1 decode metric)

### What
`DRAM-BW-util = achieved HBM throughput ÷ sustained peak HBM bandwidth` for the
kernel (or window) under inspection. Nsight's
`dram__throughput.avg.pct_of_peak_sustained_elapsed` is the canonical form
[F: Nsight Compute docs]. Distinguish it from `nvidia-smi`'s "memory utilization"
(sampling-window, coarse) and from absolute `dram__bytes` (B/s).

### Why
Decode streams weights + KV every token (AI ≈ 1–4, [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)
E2); the token ceiling is `BW ÷ bytes-per-token`. This metric answers the one
question every decode optimization reduces to: *how much of the memory roof are we
actually hitting?* High → the remaining levers are bytes and reuse, not compute.
Low → the roof is not the problem; look at stalls, gaps, fabric, or clocks.

### How
`ncu --set full -k <decode-gemv>` → read `dram__throughput` and
`pct_of_peak_sustained_elapsed`; cross-check with absolute `dram__bytes.sum` ÷
kernel time; compare against the bytes-per-token model
(`weight_bytes + KV_bytes` per [GEMM](./GEMM.md) §Example).

### When
Decode diagnosis; quantization verification (bytes↓ → ceiling↑, same roof);
kernel-algo selection (cuBLASLt vs custom skinny GEMM, `Custom-GEMM.md`);
fleet capping audit (low DRAM-active + low SM-active = workload idle, not slow).

### Hardware impact
Utilization is relative to the *sustained* spec of the SKU's HBM stack
(H100 SXM ≈ 3.35 TB/s [F: vendor spec]); burst ≠ sustained, and the L2 partition
serves some traffic *before* it counts as DRAM — hit-rate changes shift the
numerator. Newer stacks raise the roof; the *ratio* is the comparable quantity.

### Inference impact
Direct ITL lever. Signature: DRAM-util ≈ 90%+ with Tensor-Core-util low →
ITL ≈ bytes/BW + overheads; moving this ratio (quant, batch) moves ITL
linearly [I: from the roofline]. Low DRAM-util with high ITL → not the roof;
use stall reasons + kernel gaps instead.

### Example [E, arithmetic]
Kernel achieves 3.0 TB/s on a 3.35 TB/s sustained stack:
3.0e12 ÷ 3.35e12 = **89.6%** → memory roof loaded; further GEMM "compute"
optimizations will not help this kernel. Same kernel at 1.8 TB/s:
1.8e12 ÷ 3.35e12 = **53.7%** → roof not reached; profile stalls/gaps next.

### Failure modes
- Comparing *burst* peak to *sustained* peak (or vice versa) — misreads by 10s of %.
- Counting L2-resident traffic as DRAM (hit-rate shifts the numerator).
- Averaging prefill + decode windows — they sit under opposite roofs
  (`Bandwidth-vs-Compute.md`); measure per regime.
- nvidia-smi sampling window hiding the true kernel-time utilization.

### How to measure it
Nsight Compute per-kernel (authoritative); DCGM `PROF_DRAM_ACTIVE` for live
fleet monitoring; plot against the roofline (AI on x-axis, achieved FLOP/s or
B/s on y-axis) to locate the kernel, `Profiling.md`.

## 9-field template: goodput (the capacity metric under SLO limits)

### What
Goodput = **requests/sec that meet the SLO** (e.g., P99 ITL ≤ 60 ms and
P99 TTFT ≤ 2 s) at a pinned concurrency/arrival regime. It is *not* raw
requests/sec [F: DistServe (arXiv:2401.09670), Orca (USENIX ATC'22), llm-d
usage]. If the SLO is "mean ITL ≤ 50 ms" you can still have a terrible tail;
define the SLO on percentiles.

### Why
Admitting more load always raises raw throughput until the queue explodes —
past the knee, throughput rises *while* SLO conformance collapses. Goodput is the
curve that has a **maximum**: capacity planning, P/D sizing, and pricing must be
done on it, or you oversell the SLO [I: the shape of throughput-vs-concurrency
with a concave SLO region is standard queueing behavior].

### How
1. Pin model + quant + hardware + workload + SLO definition + concurrency
   (`Perf-Experiment-Template.md`). 2. Sweep concurrency up. 3. At each point,
   count the fraction of *requests* (not tokens) meeting the SLO. 4. goodput =
   completed-req/s × conformance-rate. 5. Report the peak and the concurrency
   at which it occurs.

### When
Capacity planning; scaling decisions (add GPUs vs add capacity headroom);
P/D disaggregation sizing (each stage has its own SLO); pricing/cost-per-good-
request; regression gating after kernel/quant changes.

### Hardware impact
Which GPU metric governs goodput depends on the regime: bandwidth roof → HBM
(TTFT-independent, ITL-bound tail); comm roof → fabric (both SLOs degrade
together); capping → both drift slowly. Goodput at *low* concurrency is usually
limited by tail events (hot experts, long contexts), not by any sustained roof.

### Inference impact
[ I, illustrative ] At concurrency 64 you complete 40 req/s, but 80% of
requests meet P99 ITL ≤ 60 ms → goodput = 40 × 0.8 = **32 req/s**. Raising
concurrency to 128 might complete 55 req/s at 60% conformance → 33 req/s
goodput: raw throughput up 37.5%, goodput up 3%. Report both.

### Failure modes
- Defining the SLO on a *mean* (tail vanishes from the metric).
- Not pinning concurrency/arrival (open vs closed loop) — goodput is undefined.
- Counting *tokens* meeting an ITL bound instead of requests meeting a
  percentile bound.
- Measuring during warm-up (cold prefix cache inflates TTFT, `Perf-Experiment-Template.md`).

### How to measure it
Engine Prometheus (TTFT/ITL histograms per request) + offline aggregation;
sweep protocol from `Perf-Experiment-Template.md`; per-GPU sidecar
(DCGM) to attach the regime signature to each point.

## Reading a metric correctly — the traps
1. **Util% ≠ which resource.** "GPU-Util 85%" is a boolean (something was
   resident), not a resource saturation. The same 85% can hide a Tensor-Core
   roof, a DRAM roof, or a launch-bound SM. Always pair the util with
   *the two roofs' indicators*: Tensor-Core activity vs DRAM activity
   (metrics 2 and 3). This is the #1 misread in inference triage.
2. **P50 good, P99 bad → the tail is the problem.** Mean/P50 metrics hide
   exactly the requests users notice. Tail = long-context KV reads, hot
   experts, KV preemption/GC, prefill interference, or throttling. Go to
   per-request percentile histograms, slice by context length and by
   expert-id if MoE (`MoE-Expert-Parallelism.md`,
   [Inference-Metrics](../Inference/Inference-Metrics.md) § misreadings).
3. **Power capping hides as a "slow kernel."** A kernel that suddenly runs
   2× slower with *unchanged code* is often at ~45% of nominal clock under a
   power/thermal cap [I: common failure pattern] — utilization looks normal,
   throughput halves, and every ratio in this page shifts by the clock factor.
   `nvidia-smi -q -d CLOCK` / DCGM `CLOCK_EVENT_COUNTERS` first; profiling
   second. In a fleet, DCGM makes this checkable at scale.
4. **One number, one window.** Every metric above is window-averaged. Prefill
   and decode sit under opposite roofs; a mixed-window average can be *both
   high and low at the same time* and diagnose nothing. Split windows by
   regime before interpreting.

## Related
`Profiling.md` (tool → question routing) · `Diagnostics.md` (the decision tree
this page feeds) · [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md) (the roofs
these metrics map to) · [Inference-Metrics](../Inference/Inference-Metrics.md)
(the SLO glossary) · `Kernel-Life.md` · `Multi-GPU.md`, `NCCL.md`,
`Topology.md` (fabric) · `Perf-Experiment-Template.md` · `Memory-Hierarchy.md`.

## Key Takeaways
1. **Four regimes, four signatures:** Tensor Cores (compute), DRAM (bandwidth),
   kernel gaps (latency), fabric (comm) — SM util alone cannot tell them apart.
2. **Memory-BW utilization is the #1 decode metric**; Tensor-Core utilization is
   the #1 prefill metric. Everything else is supporting evidence.
3. **Every GPU metric maps to an SLO:** BW-util↑ → ITL; TC-util↑ → TTFT;
   NCCL-fraction↑ → both; kernel gaps → ITL at low batch; capping → slow drift
   in everything.
4. **Goodput, not throughput, is capacity under SLOs** — and it has a maximum.
5. **Check clocks and the tail before you profile microarchitecture**: two
   "slow kernel" cases are usually capping and P99, not a bad kernel.
