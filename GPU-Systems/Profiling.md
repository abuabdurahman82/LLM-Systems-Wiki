# Profiling Tools for LLM Inference
`LAST_UPDATED: 2026-08-22 · Status: core page` · PART XXXI · [E] figures hand-derived; tool
claims cite vendor docs; snippets labeled REPRESENTATIVE are illustrative composites.

## 30-Second Explanation
You cannot fix what you cannot measure — but **each profiler answers a different
question**, and reaching for the wrong one wastes the whole session. Three organizing
questions cover nearly everything:

1. **"Where is time?"** → **Nsight Systems** — a wall-clock timeline of kernels, copies,
   NCCL and CPU threads. Gaps between kernels = launch/CPU-bound; one fat kernel =
   compute-bound; NCCL bars next to compute = comm-bound. The #1 tool for the
   [Diagnostics](./Diagnostics.md) decision tree.
2. **"Why is this kernel slow?"** → **Nsight Compute** — replays ONE kernel and reports
   achieved bandwidth, occupancy, warp-stall reasons, Tensor-Core and L2 utilization.
   Slows that kernel down (replays), so never profile a whole run with it.
3. **"What are the GPUs doing over time?"** → **nvidia-smi / DCGM / nvtop** — coarse
   utilization, memory, clocks, power, temps, per second, for triage and fleets.
4. **"Which OPS?"** → **PyTorch Profiler** — op-level hot spots and op→kernel mapping.
5. **"What's the engine serving?"** → **vLLM/SGLang/TensorRT-LLM metrics** — TTFT, ITL,
   KV utilization, queue depth; and **NCCL logs** for the collective layer.

Workflow: triage (nvidia-smi/DCGM) → locate the layer ([Diagnostics](./Diagnostics.md))
→ timeline (Nsight Systems) → kernel (Nsight Compute) → confirm (re-run + serving
metrics). Full method: `./Perf-Experiment-Template.md`.

---

## The tools

### 1. nvidia-smi — the first triage
**Question it answers:** "Are the GPUs even busy — or OOM / throttling / idle?"

REPRESENTATIVE output (`nvidia-smi`):
```
+-------------------------------------------------------------------------------+
| NVIDIA-SMI 570.xx    Driver: 570.xx    CUDA Version: 12.8                     |
| GPU  Name          Pers-Mem    Util   Temp   Pwr (L/Cap)   Clock  SM-Clock   |
| 0    H100 SXM      78GiB/95GiB  100%   63C    610W/700W    1980   1980 MHz    |
| 1    H100 SXM      94GiB/95GiB   30%   61C    480W/700W    1410*  1410 MHz    |
+-------------------------------------------------------------------------------+
```
*How to read:* **Util** is a single boolean-ish sample — % of the last sample interval
during which *some* kernel was active. 100% util does NOT mean the GPU is fast
(a single long kernel can hold 100% while doing 10% of peak work), and 0% util does not
mean no work (a launch-bound decode step can idle between kernels). `*` next to the clock
means the clock is **below max** — check the `Pwr` column: near the cap with a reduced
clock = **power/thermal throttling**. Memory near the total (94/95 GiB) on a serving GPU
means the KV pool is nearly full → expect queueing/preemptions.
*Practical example:* `nvidia-smi --query-gpu=utilization.gpu,memory.used,clocks.sm,power.draw,temperature.gpu --format=csv -l 1` gives a per-second CSV you can tail while a benchmark runs.
*Limit:* **coarse, per-second, no kernel detail** — it tells you *that* a GPU is busy,
never *why*. One number per GPU; a 20 µs kernel inside a 1 s window is invisible.

### 2. DCGM — the fleet / time-series monitor
**Question it answers:** "What is happening to the GPUs **over time, across a cluster**?"

REPRESENTATIVE (`dcgmi dmon`):
```
#Entity     GPU Util% Mem% Pwr W Temp C Fan  Xid ECC_DBE  Clock SM
1           0    98    92  702   65   -     -    0        1980
1           1     5    94  320   58   -     -    3        1395
```
*How to read:* DCGM fields map to the [GPU-Metrics](./GPU-Metrics.md) bank: SM util,
**DRAM/Copy-Engine bandwidth util**, HBM and L2 **ECC counters** (single/double-bit),
clocks, power, temperature, XID error codes, NVLink error counters. `dcgmi dmon -i 0 -d 1000`
streams every 1 s; `dcgmi hostengine` + `dcgmexporter` push fields into Prometheus for
long-term dashboards and alerts. A rising DBE (double-bit ECC) count or XID 48/63 over
hours is a **hardware-health** signal, not a perf one.
*Practical example:* alert on `DCGM_FI_PROF_DRAM_THROUGHPUT` sustained at 0 while
`DCGM_FI_PROF_SM_ACTIVE` is high — compute busy, memory silent → suspect a kernel that
should be streaming.
*Limit:* still **field-level, not kernel-level** — it says "DRAM was at 90% for 5 min",
never which kernel. Best as a background monitor + historical store, not a root-cause tool.

### 3. Nsight Systems (nsys) — the timeline ★ workhorse
**Question it answers:** "**WHERE is time spent?**" (kernel vs copy vs NCCL vs CPU gap.)

REPRESENTATIVE (what the `.nsys-rep` timeline shows):
```
GPU stream:  |==GEMM==|==FA==| |==GEMM==|===NCCL allreduce===|  (gaps = idle)
CPU thread:  [python tokenize/sample/launch .........][......]
             ^launch  ^launch   ^gap: 200µs  ^NCCL bar ~ compute
```
*How to read:* each bar is one kernel/copy/NCCL op with a start time and duration.
- **Gaps between kernel bars** → launch/CPU-bound (the GPU waited for work to be
  submitted); the fix space is CUDA Graphs / scheduling — see `./Kernel-Life.md`.
- **One or few very long bars** → compute-bound; that kernel is where to look next.
- **NCCL bars long relative to compute** → comm-bound (TP AllReduce, EP AllToAll) →
  `./Multi-Node.md`, `./Topology.md`.
- **Copy-engine bars** → data movement (H2D/D2H, P/D KV transfer) stealing time.
*Practical example (decode step):* a 32-layer model issues ~64–256 kernels/token
(2–8 kernels/layer × 32 [I]) — each a few µs. `nsys` shows hundreds of tiny bars with
gaps larger than the bars themselves: the step is **launch-bound**, not compute-bound.
*Command shape:* `nsys profile -o run --force-overwrite true python serve.py` then open
`run.nsys-rep` (GUI) or `nsys stats run.nsys-rep` for kernel-time / top-10 tables.
*Limit:* profiling adds overhead and the rep file is a *snapshot of that run*; it answers
"where" but not "why inside the kernel" (that is ncu). Heavy capture also perturbs the
very launch behavior you're measuring.

### 4. Nsight Compute (ncu) — the per-kernel deep dive ★ the "why"
**Question it answers:** "**WHY is this kernel slow?**" (BW, occupancy, stalls, TC util.)

REPRESENTATIVE (ncu kernel summary for a decode GEMV):
```
  Section: GPU Speed Of Light
  Duration:               0.87 ms
  Compute (SM) Throughput: 18.3 %
  Memory Throughput:       41.0 %   (DRAM)
  Duration / L2 hit / Occupancy:  71% / 88% / 2/6 warps/SM
  Warp state: 60% of cycles stalled on "Long Scoreboard" (memory latency)
```
*How to read:*
- **Memory Throughput (DRAM) %** vs **Compute (SM) Throughput %** tells you which roof
  ([Roofline](../Inference/Roofline.md)) the kernel is under. High DRAM%, low SM% =
  bandwidth-bound → quantize/batch (`./Bandwidth-vs-Compute.md`). High SM%, low DRAM% =
  compute-bound.
- **Achieved occupancy** (warps/SM vs max resident) — low occupancy with high latency
  stalls means not enough warps to hide HBM latency; see `./Kernel-Life.md`.
- **Warp-stall reasons** (Long Scoreboard = waiting on memory; MIO/Short Scoreboard =
  L2/shared; Math Pipe Throttle = Tensor/Core saturation) point at the fix.
- **L2 hit rate** — for KV/attention kernels, a low L2 hit = re-reading KV from HBM.
- **Tensor-Core util** (`sm__inst_executed_pipe_tensor`) — is it actually using MMA?
*Practical example [E, hand-derived]:* a decode GEMV streams 1.2 GB of weights; on H100
(3.35 TB/s HBM3, `../Hardware/README.md`) the floor is 1.2 GB ÷ 3.35 TB/s =
**0.358 ms**. If ncu shows **DRAM at 41%**, the measured time is 0.358 ms ÷ 0.41 =
**0.874 ms** — a **2.4× penalty** over the bandwidth floor. That ratio is the single
most useful ncu number: it tells you exactly how far below the roof you are.
*Command shape:* `ncu --set full --kernel-name-base demangled -k regex:gemv -c 1 python step.py`
(replays the matched kernel).
*Limit:* **ncu replays the kernel to collect counters, so it is slow and distorts
timing** — use it on ONE kernel, never a whole run. It also needs `--target-processes` /
root on some systems, and the exact counter set is GPU-generation dependent.

### 5. PyTorch Profiler — the framework-level trace
**Question it answers:** "Which **OPS** are the hot spots, and which kernels do they
map to?"

REPRESENTATIVE (torch.profiler table, abridged):
```
Name                          CPU time   CUDA time   #calls
aten::mm                      1.2 ms     120.4 ms    64
aten::linear                  0.9 ms     118.1 ms    32
CUDA Graph replay             —          95.0 ms     32   (decode, captured)
FlashAttention fwd            0.1 ms     40.2 ms     32
```
*How to read:* it records **op-level** (aten::) entries AND the **kernels** each op
launched, with CPU + CUDA time. The CPU↔CUDA gap per op shows launch overhead; a
`aten::linear` with high CUDA time maps to the GEMM kernels in `./GEMM.md`. The
"self CPU time" column isolates pure Python/aten overhead from the GPU work.
*Practical example:* run one decode iteration under `torch.profiler`, sort by
**self CUDA time** — the top ops are your optimization targets; if a whole step sits
under "CUDA Graph replay", the step is already captured and the remaining levers are
inside the graph (use nsys/ncu, not op counts).
*Limit:* op-level granularity hides *inside*-kernel behavior; it's the bridge from
"which op" to "which kernel", then you hand off to nsys/ncu for the why. Adds tracing
overhead.

### 6. nvtop — the quick interactive monitor
**Question it answers:** "What's on the GPUs *right now*, in one screen?"

REPRESENTATIVE (nvtop, like htop for GPUs):
```
 GPU 0 H100   98%  [██████████]  78/95G  610W  63C  1980MHz
 GPU 1 H100   30%  [███         ]  94/95G  480W  61C  1410MHz*
 Processes: python(1) 2.1G  |  vllm-worker 1.8G
```
*How to read:* live per-GPU util%, memory, power, temp, clock, plus the **process →
GPU memory** mapping — fast to spot "which process is eating 80 GB". Great for a
dev box; press `k` to kill a process.
*Practical example:* a mystery memory leak: nvtop shows the vLLM worker's footprint
climbing every hour → OOM risk before the engine's own metrics fire.
*Limit:* even coarser than nvidia-smi; no timeline, no kernel detail, no persistence.
Display-oriented; use it to *notice*, then switch to a real tool to *explain*.

### 7. CUPTI — the kernel API behind Nsight (concept)
**Question it answers:** "How do I build my **own** profiler/instrumentation?"

CUPTI (CUDA Profiling Tools Interface) is the **driver-level tracing API** that Nsight
Systems/Compute and torch.profiler call under the hood: it hooks kernel launch/finish,
memory copy, and performance-counter events, and delivers activity records + metrics to
your process. You use it directly when: you need **in-process, zero-GUI** instrumentation
(for a custom serving engine), you want **per-launch callbacks** (e.g. tag every kernel
with the request it belongs to), or you want to **record your own metrics** alongside your
engine's.
*Practical example:* an engine dev adds CUPTI activity records keyed by request-id so
each TTFT can be attributed to the exact kernels that ran for that prompt (the engine's
own tracing feeds this — see `./vLLM.md`).
*Limit:* it is a **low-level API** — you own buffer management, activity types, and
synchronization; misuse stalls the GPU or loses records. Prefer the built tools unless
you're embedding instrumentation.

### 8. NCCL debug logs — the collective layer
**Question it answers:** "Which **algorithm/ring/paths** did NCCL pick, and is the
topology healthy?"

REPRESENTATIVE (`NCCL_DEBUG=INFO`):
```
rank 0[0] NCCL INFO 8 coll comm, comm 0x... ; channel 00 0x...
rank 0[0] NCCL INFO Trees [1] comm ... ; Ring 0x... ; Use NCCL_P2P 1
rank 2[2] NCCL WARN ... proxy progress ... (on a degraded link)
```
*How to read:* at init NCCL prints the **number of ranks/comms**, the **algorithm**
(ring vs tree vs hierarchical) and **protocol** per collective, and the **transport**
chosen (P2P/NVLink, SHM, NET/IB). A `WARN` about a transport or proxy is a topology
problem — cross-check `./Topology.md` and `nvidia-smi topo -m`. Set `NCCL_DEBUG=WARN`
in production (INFO is very verbose and slows startup).
*Practical example:* TP=8 across 2 nodes runs slower than expected; NCCL INFO shows the
AllReduce using a **ring over NET** instead of NVLink+SHARP → the fabric path is wrong,
not the kernels.
*Limit:* it describes **what NCCL decided**, not measured kernel throughput; a quiet
log does not prove fast collectives. For numbers, pair with nsys (NCCL bars) or
nccl-tests.

### 9. vLLM metrics — the engine serving view
**Question it answers:** "What is the **engine serving** — latency, queue, KV pressure?"

REPRESENTATIVE (Prometheus, V1 set [F: vLLM docs — exact names, check current docs]):
```
vllm:gpu_cache_utilization        0.97   # KV blocks in use
vllm:num_requests_running         64     # vs --max-num-seqs
vllm:num_requests_waiting         28     # admission queue
vllm:time_to_first_token_seconds{p50="0.4", p99="2.1"}
vllm:time_per_output_token_seconds{p50="0.031", p99="0.09"}
```
*How to read:* these are the **request-facing** SLOs the user actually feels.
- `gpu_cache_utilization` → 1.0 = KV capacity wall: queueing/preemptions next
  (`./vLLM.md`, `../KV-Cache/README.md`).
- `num_requests_running` ≪ max → **KV-limited, not config-limited**.
- **TTFT** spikes = queueing + prefill; **ITL/TPOT** spikes = decode interference
  (chunked-prefill co-scheduling, preemption, CPU overhead, CUDA-Graph miss).
- Read together: high cache util + growing waiting + rising TTFT = KV-limited cluster;
  low util + high waiting = scheduler/admission problem, not memory.
*Practical example:* P99 ITL jumps but P50 is fine → tail-latency; check preemption
counters and chunked-prefill interference before blaming kernels.
*Limit:* engine-internal; it tells you *what* is slow request-side, not *which kernel* —
cross-reference with nsys/ncu and `./Diagnostics.md`.

### 10. SGLang / TensorRT-LLM metrics — equivalent serving views
**Question it answers:** the same as §9, for the other engines (no universal winner —
`./Engine-Comparison.md`).

REPRESENTATIVE (SGLang Prometheus [F: SGLang docs]):
```
sglang:num_running_reqs            58
sglang:num_queue_reqs              12
sglang:token_throughput            412.5   # tok/s
sglang:avg_prefix_cache_hit_rate   0.61    # RadixAttention hits
sglang:time_to_first_token_seconds{p50,p99}
```
TensorRT-LLM exposes an equivalent Prometheus + JSON observability surface
(`./TensorRT-LLM.md`): request counts, batch size, queue, TTFT/TPOT, KV-cache utilization.
*How to read:* SGLang adds a **prefix-cache hit rate** directly (RadixAttention) — a low
hit rate on a shared-prefix workload means the structural cache isn't paying off
(`./SGLang.md`). TRT-LLM's strength is that the same numbers map to its compiled
kernels, so a metric anomaly + nsys timeline is a tighter loop.
*Practical example:* SGLang token throughput dropped but util is still high → hit rate
fell (eviction churn under low overlap) → the cache, not the GPU, is the cause.
*Limit:* per-engine surfaces differ in name/granularity; treat these as **hypothesis
generators** and confirm at the kernel layer. No engine's metrics are independently
benchmarked — treat cross-engine numbers as comparable only under the same protocol
(`./Perf-Experiment-Template.md`).

---

## How to combine them (the workflow)

```
   problem ("slow")        tool                    layer it localizes
   ─────────────────────   ───────────────────────  ──────────────────
   triage / is it real?   nvidia-smi / DCGM / nvtop  busy? OOM? throttle? util%
   locate the layer        Diagnostics.md tree       CPU? launch? compute? mem? comm? KV?
   where is time          Nsight Systems            gaps / long kernels / NCCL / copies
   why this kernel        Nsight Compute            BW vs SM / occupancy / stalls / TC / L2
   which op               PyTorch Profiler          op → kernel mapping
   collective health      NCCL logs                 algorithm / ring / transport / topology
   is the SLO holding     vLLM/SGLang/TRT-LLM       TTFT/ITL/queue/KV
   confirm                re-run + serve metrics    delta under ONE variable
```

Steps:
1. **Triage** (nvidia-smi/DCGM/nvtop): is the GPU actually the bottleneck, or OOM/
   throttle/idle? If idle with high CPU → you never needed a GPU profiler.
2. **Locate the layer** with the [Diagnostics](./Diagnostics.md) tree: launch-bound?
   compute? memory? comm? KV? scheduler? Pick the matching question.
3. **Timeline** (Nsight Systems): see *where* — gaps, one fat kernel, NCCL vs compute,
   copy-engine bars. This is usually where the root cause becomes visible.
4. **Kernel** (Nsight Compute): open the one fat/low-efficiency kernel; read DRAM% vs
   SM%, occupancy, stalls, TC util, L2 hit.
5. **Confirm**: fix ONE variable, re-run, and watch the **serving metric** move
   (`./Perf-Experiment-Template.md`). If the metric didn't move, the fix wasn't the
   real bottleneck — go back to step 2.

### Question → tool → what to look for
| Question | Tool | What to look for |
|---|---|---|
| Is the GPU busy / OOM / throttling? | nvidia-smi, DCGM, nvtop | util%, mem/total, `*` clock vs Pwr cap, temp, ECC/XID |
| What are the GPUs doing over time / across the fleet? | DCGM (+exporter) | util/BW/clock/power/ECC trends, alerts, XID history |
| **Where is time spent?** | Nsight Systems | inter-kernel gaps, one long kernel, NCCL vs compute, copy bars |
| **Why is this kernel slow?** | Nsight Compute | DRAM% vs SM% (roof), occupancy, warp-stall reasons, TC util, L2 hit |
| Which OPS are hot? | PyTorch Profiler | self-CUDA-time by op, op→kernel map, CPU↔CUDA gap |
| Is a collective healthy? | NCCL logs | algorithm/ring/transport, WARN, P2P vs NET choice |
| Is the SLO (TTFT/ITL) holding? | vLLM / SGLang / TRT-LLM | TTFT/ITL P50-P99, num_waiting, cache util, hit rate |
| Build my own in-process instrumentation? | CUPTI | per-launch records, request-tagged kernels, own metrics |

---

## Nsight Systems — 9-field concept (the workhorse)
- **What:** a system-wide, wall-clock profiler producing a timeline (`.nsys-rep`) of
  GPU kernels, memory copies, NCCL ops, and CPU threads with exact start/duration.
- **Why:** "where is time" is the first question in every performance bug, and only a
  timeline shows gaps vs work vs communication at once.
- **How:** the driver records every kernel/copy/collective and CPU sampling; nsys
  assembles them into lanes (streams, CPU threads, GPU). Open in the GUI or run
  `nsys stats` for kernel-time and top-N tables.
- **When:** first stop after triage in the [Diagnostics](./Diagnostics.md) tree; whenever
  you need to separate launch-bound vs compute-bound vs comm-bound.
- **Hardware impact:** none on the model — pure measurement; overhead perturbs launch
  timing, so capture a representative window, not the whole serving session.
- **Inference impact:** directly exposes TTFT/ITL causes — gaps (ITL at low batch),
  long prefill kernels (TTFT), NCCL bars (multi-GPU TP/EP cost).
- **Example:** decode step ≈ 64–256 kernels [I]; nsys shows each a few µs with larger
  gaps → launch-bound → CUDA Graphs (`./Kernel-Life.md`).
- **Failure modes:** misreading a 100%-util kernel as "fine"; over-profiling (too-long
  capture changes behavior); forgetting NCCL bars when reasoning about TP.
- **How to measure it:** kernel-time sum, inter-kernel gap fraction, NCCL-time/total,
  copy-engine time — all from `nsys stats`.

## Nsight Compute — 9-field concept (the "why")
- **What:** a per-kernel counter collector that replays one kernel and reports a
  "Speed Of Light" + per-section breakdown (DRAM, SM, occupancy, warp state, caches).
- **Why:** the timeline says *where*; ncu says *why that kernel* is below its roof.
- **How:** it replays the kernel under PMU counters (`--set full`), then computes
  achieved DRAM/SM throughput, occupancy, stall reasons, L2 hit, Tensor-Core pipe util.
- **When:** after nsys names the fat/low-efficiency kernel. One kernel at a time.
- **Hardware impact:** none on correctness, but **replay is slow and timing is not
  representative** — never use it to measure end-to-end latency.
- **Inference impact:** tells you whether a decode GEMV is at the bandwidth floor
  ([Roofline](../Inference/Roofline.md), `./Bandwidth-vs-Compute.md`) and whether a
  prefill GEMM is on the compute roof (`./Tensor-Cores.md`).
- **Example [E]:** GEMV streaming 1.2 GB on H100 (3.35 TB/s) → floor 0.358 ms; ncu shows
  DRAM 41% → 0.874 ms → **2.4× below roof**. The ratio is the headline.
- **Failure modes:** profiling a whole run (slow + distorted); trusting one replay for
  timing; wrong counter set on a new GPU generation.
- **How to measure it:** Duration, Compute(SM)% vs Memory(DRAM)%, achieved occupancy,
  dominant warp-stall reason, L2 hit, `sm__inst_executed_pipe_tensor`.

---

## Key Takeaways
1. **One tool, one question:** nvidia-smi/DCGM/nvtop = "is it busy?"; nsys = "where";
   ncu = "why that kernel"; PyTorch = "which op"; NCCL logs = "which path"; engine
   metrics = "is the SLO holding". Reaching for the wrong one wastes the session.
2. **The two load-bearing tools are nsys (where) and ncu (why)** — use nsys to find the
   kernel, ncu to explain it; never ncu a whole run (it replays and distorts timing).
3. **The most useful single number is ncu's DRAM% → time-ratio**: measured time vs the
   bandwidth floor tells you exactly how far below the roof you are [E].
4. **Always end at the serving metric**: a fix that doesn't move TTFT/ITL/throughput
   wasn't the real bottleneck — return to the [Diagnostics](./Diagnostics.md) tree.
5. **Fleet and health** (ECC, XID, clocks, power) live in DCGM; keep it running in the
   background so a hardware signal is caught before it shows up as a perf mystery.

## Related
`./Diagnostics.md` (decision tree these tools feed) · `./GPU-Metrics.md` (the metric
bank) · `./Kernel-Life.md` (launch overhead, CUDA Graphs) · `./Bandwidth-vs-Compute.md`
(roofs) · `./vLLM.md`, `./SGLang.md`, `./TensorRT-LLM.md` (serving views) ·
`./Multi-Node.md`, `./Topology.md` (collectives/fabric) · `./Perf-Experiment-Template.md`
(confirm-the-fix discipline) · `../Inference/Roofline.md`.

## References
- NVIDIA Nsight Systems docs (timeline, gaps, kernel/copy/NCCL lanes) [F: NVIDIA docs].
- NVIDIA Nsight Compute docs (Speed Of Light, occupancy, warp-state, per-section
  counters) [F: NVIDIA docs].
- NVIDIA DCGM docs (field ids: util, BW, ECC, clocks, power, XID; `dcgmi dmon`)
  [F: NVIDIA docs].
- NVIDIA CUPTI / CUDA Profiling Tools Interface [F: NVIDIA docs].
- NCCL documentation, `NCCL_DEBUG=INFO/WARN` [F: NCCL docs].
- PyTorch Profiler docs (op-level + kernel mapping) [F: PyTorch docs].
- vLLM observability/Prometheus V1 metric set [F: vLLM docs]; SGLang Prometheus metrics
  [F: SGLang docs]; TensorRT-LLM observability [F: TensorRT-LLM docs].
- Hardware constants (H100 3.35 TB/s HBM3): `../Hardware/README.md` [F].
