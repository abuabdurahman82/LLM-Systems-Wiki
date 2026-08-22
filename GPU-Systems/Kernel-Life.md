# The Life of a CUDA Kernel — From Python Call to GPU Result
`LAST_UPDATED: 2026-08-22 · Status: core page` · PART III of the GPU-systems zero-to-hero
path. Launch-overhead magnitude is framed as "tens of microseconds" [I; UNVERIFIED —
device/driver-dependent, not a sourced spec]; all [E] arithmetic is hand-derived.

## 30-Second Explanation
One line of Python (`y = torch.rms_norm(h, weight)`) is one **CPU call** that must cross the
CPU → driver → GPU boundary, schedule threads onto SMs, execute them, and hand the result
back. The GPU-side execution of a B=1 RMSNorm moves ~24 KB of data — ~7 ns of pure memory
time [E] — yet the launch itself costs **tens of microseconds** of CPU/driver handoff even
when the kernel does almost nothing [I]. At prefill that is noise (kernels run for ms).
At decode, a single token runs ~5–10 small kernels per layer × 32 layers, so the **sum of
many launch overheads** becomes a real fraction of a 10–30 ms/token step [E]. That sum —
not any one kernel — is what kernel fusion (./Fused-Kernels.md) and CUDA Graphs
(F: NVIDIA docs) attack: fuse N launches into one, or capture the whole per-token DAG and
replay it with far lower launch cost.

## The End-to-End Pipeline — One RMSNorm, Followed Stage by Stage
Concrete example: `y = RMSNorm(x)` at decode batch B=1, d=4096, BF16 — one row of 8 KB
input, one row of 8 KB output, 8 KB gain vector (from ./CUDA-From-Zero.md §8).

1. **Python / PyTorch.** `torch.rms_norm(h, weight)` runs on the CPU. The dispatcher routes
   the call to the ATen operator; for CUDA tensors the op resolves to a CUDA kernel (ATen's
   native kernel, or an engine-provided fused/custom one). Nothing has touched the GPU yet.
2. **Framework operator → launch config.** The operator picks the kernel and computes the
   split: `grid = B` (one block per row), `block = 128` threads, d passed as an argument.
   Device pointers `x_d, g_d, y_d` were allocated once at load time — no copies per call
   (weights/activations live in HBM; CUDA-From-Zero.md §Memory).
3. **CUDA runtime: the `<<<>>>` call.** `rmsnorm<<<B, 128, 0, stream>>>(x_d, g_d, y_d, d)`
   hands the runtime a **launch descriptor**: grid dims, block dims, dynamic shared memory,
   kernel arguments, target stream [F: NVIDIA CUDA C Programming Guide,
   docs.nvidia.com/cuda/cuda-c-programming-guide]. The runtime enqueues it on the stream's
   FIFO and **returns immediately** — launches are asynchronous; the host does not wait.
4. **CPU → driver → GPU handoff.** The driver layer pushes the launch packet into the GPU's
   work channels (PCIe doorbell + command buffer). This round-trip — descriptor setup,
   validation, doorbell, hardware pickup — is where the "tens of microseconds" of launch
   overhead lives [I; UNVERIFIED, device/driver-dependent]. The CPU is free the moment the
   enqueue succeeds.
5. **Block scheduling.** The GPU's global block scheduler hands the block to an idle SM as
   capacity frees; a block lives on **one SM its entire life** and blocks may run in any
   order (Architecture.md, Execution Hierarchy). At B=1 the grid is one block — one SM does
   the whole kernel while ~131 SMs sit idle [I].
6. **Warp execution.** Inside the SM, 32 consecutive threads form a warp; the warp
   schedulers issue one instruction per warp per clock, switching in a cycle to any ready
   warp when one stalls (Architecture.md, Concept 2/4). 128 threads = 4 warps.
7. **Memory accesses.** Warp-wide coalesced loads pull the 8 KB row `x` and the 8 KB gain
   `g` from HBM → L2 → L1/shared → registers; reduction partials accumulate in
   registers/shared with no further HBM.
8. **Compute: CUDA cores, not Tensor Cores.** `Σx²`, `rsqrt`, and `x·rstd·g` are scalar
   FP32/BF16 FMAs on **CUDA cores**; Tensor Cores are idle for a norm. A GEMM at this stage
   instead issues MMA instructions into the Tensor Cores (GEMM.md §How) — the SM is the
   same, the pipe is different.
9. **Synchronization → back to the framework.** Block exits → grid complete → `y` is in HBM
   → the stream's progress advances. The *next* op enqueued on the same stream runs after
   it (same-stream ordering); the host only blocks if it explicitly syncs — a D2H copy of
   logits, an event wait, or `cudaStreamSynchronize` (CUDA-From-Zero.md §Memory).

```
HOST (CPU)                                        GPU (H100-class, 132 SMs)
════════════════════════════════════════          ═══════════════════════════════
Python:  y = torch.rms_norm(x, weight)
  │  dispatcher → ATen op (CPU)
  ▼
ATen:  pick kernel + config  (grid=B, block=128)
  │
  ▼
rmsnorm<<<B,128,0,stream>>>(x_d, g_d, y_d, d)     │
  │  runtime fills launch descriptor            │
  │  (dims, smem, args, stream); enqueues;      │
  │  host RETURNS (async)                        │
  ▼                                              │
stream FIFO (ordered per stream)                 │
  │  driver pushes launch packet                 │
  ▼  ─── PCIe doorbell / cmd buffer ───────────► │
                                       global block scheduler
                                         │  hands blocks to idle SMs
                                         ▼
                                       SM #k: block resident
                                         │  128 threads → 4 warps
                                         ▼
                                       warp schedulers (4/SM)
                                         │  1 instr/warp/clock;
                                         │  load → FMA → shuffle → store
                                         ▼
                                       memory:  HBM ─► L2 ─► L1/shared ─► regs
                                        (row x 8KB + gain g 8KB, coalesced)
                                         │
                              CUDA cores: Σx², rsqrt, x·rstd·g
                              (Tensor Cores idle for norm;
                               GEMM.md uses MMA at this stage)
                                         │
                                         ▼  writes y (8KB) to HBM;
                                           grid done → stream advances
 ◄────────────────────────────────────────┘
host: next same-stream op ordered after it; host blocks only on
explicit sync (D2H copy of logits, event wait, cudaStreamSynchronize)
```

## Kernel Launch Overhead

### What
The cost of getting one kernel from a CPU call to running on the GPU: descriptor
construction, enqueue, driver handoff, doorbell, hardware pickup. The kernel's own
execution time (often sub-µs for small decode kernels) is a **separate** number; the two
add in series.

### Why
Every launch is a cross-boundary transaction: the CPU fills a work descriptor, the driver
makes it visible to the GPU's block scheduler over PCIe, and the hardware latches it.
None of that scales with kernel size — it is paid **per launch** regardless of how little
the kernel does [I]. Exact magnitude is device/driver-dependent: "tens of microseconds"
is the safe frame; commonly quoted figures of a few µs up to tens of µs are UNVERIFIED
here (no sourced spec).

### How
It appears as a fixed per-kernel tax: elapsed = launch_overhead + kernel_time. When
kernel_time ≈ 1 µs and launch ≈ 5 µs, launch is ~83% of elapsed [E: 5/6]. It also serializes:
launches from one host thread on one stream are issued back-to-back, each paying the tax.

### When
It dominates whenever **many small kernels** run per step: small-batch decode, B=1 serving,
unfused eager PyTorch. It is invisible at prefill (a 4 ms GEMM dwarfs a 5 µs launch) [I].

### Hardware impact
SMs do nothing special — they just wait for blocks. The GPU may be fully idle between
kernels: utilization looks "pulsed", and `nsys` shows gaps between kernel bubbles
[How to measure].

### Inference impact
Decode ITL at low batch is often launch-bound: the CPU (Python + dispatcher + driver) is
the metronome, the GPU idles between kernels. This is the #1 reason engines move launch
orchestration off the Python hot path: CUDA Graphs replay, fused kernels, C++/CUDA
schedulers (./Inference-Engines.md, ./vLLM.md).

### Example [E, hand-derived]
B=1 RMSNorm, d=4096, BF16: 24 KB moved (x + g in, y out) → 24·1024 B ÷ 3.35 TB/s ≈
**7 ns** of memory time [E] on H100 — while one launch costs ~5 µs [I; UNVERIFIED] =
**~700× the kernel's own memory time**. The kernel is a rounding error; the launch is
the cost.

### Failure modes
- **Assuming kernel time = op time** when profiling decode: you optimize a 7 ns kernel and
  fix none of the 5 µs launch tax.
- **One kernel per framework op, eager mode:** ~5–10 launches per layer per token with no
  fusion or graph capture (the pathological baseline below).
- **Debugging on the default stream with implicit syncs:** pageable-memory copies add
  hidden host-blocks that masquerade as launch overhead (CUDA-From-Zero.md §Failure modes).

### How to measure it
`nsys` (Nsight Systems): the gaps between kernel bubbles on the timeline *are* the launch
+ handoff cost; `torch.profiler` op durations vs kernel durations; count kernels/step
(kernel rate, kernels/s). If GPU utilization is <50% with tiny kernels and gaps, you are
launch-bound (README decision tree, GPU-Systems).

## CUDA Graphs

### What
A **CUDA Graph** is a DAG of kernel launches, memory copies, and dependencies, recorded
once into a graph object and **replayed as a single unit** — the GPU executes the whole
DAG with far lower per-launch overhead than N individual `<<<>>>` calls from the CPU
[F: NVIDIA docs, CUDA C Programming Guide / CUDA Runtime API "CUDA Graphs"].

### Why
Launch overhead is paid per CPU-issued launch. If the same set of launches (same shapes,
same pointers) repeats every decode step — true at fixed batch size — the per-launch tax
is pure waste. Capture the DAG once; replay many times: the CPU issues **one** graph
execution instead of hundreds of launches [I]. This is the engine-level fix for the
many-tiny-kernels problem; fusion (./Fused-Kernels.md) cuts the number of nodes in the
DAG, graphs cut the per-node cost — the two are complementary.

### How
Engine flow: (1) at a stable batch, run the whole per-token forward pass in **capture
mode** — no execution, just recording launches into a graph; (2) `instantiate` the graph;
(3) each decode step: `graphLaunch` (one CPU call) + update any variable inputs (input
tensor, sampling params) in place. vLLM captures a graph **per batch size** it may run
(./vLLM.md); SGLang does the same with static batching (Kernel-Stack.md, L5).

### When
Decode loops with **fixed shapes per batch size** — exactly the small-batch,
latency-sensitive regime where launch overhead dominates. Prefill (variable sequence
lengths per step) usually stays eager/captured-per-shape or falls back (graph-break
behavior, Kernel-Stack.md §Failure modes).

### Hardware impact
The GPU runs the same kernels; the block scheduler simply receives work pre-packaged as
one DAG instead of a stream of independent packets → smaller inter-kernel gaps, denser
SM occupancy [I].

### Inference impact
ITL at B=1..B=32 drops because per-token launch overhead collapses (from O(kernels) CPU
work to O(1) graph launch) [I]. Engines report meaningful decode-latency reductions from
graph capture; treat specific magnitude claims as engine/vendor-dependent (UNVERIFIED
here). It also removes CPU-side variance from the token loop → better P99.

### Example [E, hand-derived]
Per-token baseline: ~160–320 launches [E: 32 layers × 5–10 ops, below] × ~5 µs [I;
UNVERIFIED] ≈ **0.8–1.6 ms** of pure launch tax per token [E]. With graph replay the CPU
does ~1 launch per token → launch tax drops to one graph-launch cost [I] — the entire
0.8–1.6 ms is the prize; against a ~10 ms/token step that is 8–16% [E: 0.8/10, 1.6/10].

### Failure modes
- **Graph break / dynamic shapes:** variable batch size or sequence length forces recapture
  or eager fallback — engines bucket batch sizes (e.g. 1,2,4,8,...) and pad [I].
- **Pointer churn:** capture bakes in addresses; rotating KV blocks / new activations
  require stable pre-allocated buffers + in-place updates (engines preallocate pools).
- **Capturing with side effects:** capture runs the ops' *record* path; anything that must
  actually execute (allocation, sync) must be handled explicitly [F: NVIDIA docs].

### How to measure it
`nsys` before/after: kernel count unchanged, **inter-kernel gaps shrink**, CPU thread time
on launch work collapses. ITL/TPOT at low batch: the end-to-end proof (Perf-Experiment-Template.md).

## Why Many Tiny Kernels Hurt — and How Decode Hits It
A pre-norm decoder layer runs, per token: RMSNorm → QKV GEMM → RoPE → attention (+ KV
update) → O-proj → residual add → RMSNorm → MLP (up/gate/down GEMMs + activation) →
residual add. That is **~5–10 kernel launches per layer** even with a decent framework
(some ops fuse; some, like RoPE and residual add, often don't). At B=1 every one of them
is *small*: work ≈ 1 µs or less, launch ≈ 5 µs [I; UNVERIFIED] → **you are launch-bound,
not compute-bound**: [E] 5 µs launch + 1 µs work → launch = 83% of elapsed. The GPU sits
between kernels doing nothing; the CPU is the bottleneck (./Cross-Layer-Optimization.md:
fix the kernels and the scheduler/launch overhead *becomes* the next limiting resource).
Batching helps by shrinking relative work-per-launch, but at B=1..8 the per-token sum of
launches still matters — hence graphs + fusion (below).

## Mitigations: Streams, Events, Graphs, Fusion

| Mechanism | What it does | When an engine uses it |
|---|---|---|
| **CUDA streams** | Independent FIFO queues of work; work on different streams may **overlap** (kernel on SMs + copy on a copy engine at once); same-stream work stays ordered [F: NVIDIA docs] | Overlapping KV-cache movement / D2H with the next layer's compute; TP allreduce pipelined with GEMMs |
| **CUDA events** | Timestamp/sync points; `record` on one stream, `wait` on another → cross-stream dependency + timing [F] | Ordering cross-stream overlap safely; measuring inter-stream latency; P/D KV-transfer handoff |
| **Asynchronous execution** | Kernels + HtoD/DtoH `cudaMemcpyAsync` on a stream don't block the host; the CPU keeps issuing work (pinned host memory for true async copies) [F: CUDA-From-Zero.md] | The whole decode loop: host enqueues step N+1 while step N's kernels finish; D2H of logits overlaps last layer |
| **CUDA Graphs** | Capture a DAG of launches once, replay as one unit → far lower per-launch overhead [F: NVIDIA docs] | Fixed-shape decode steps per batch size: the engine-level fix for many-tiny-kernels (above) |
| **Kernel fusion / batching** | Combine N launches into 1 kernel (residual+RMSNorm, QKV concat, gate+up+act+down) → fewer launches *and* fewer HBM round-trips | Everywhere: 2L norms, MLP, RoPE (./Fused-Kernels.md) |
| **Stream sync + dependencies** | Explicit ordering (`streamSynchronize`, events, implicit same-stream order) so overlapping work can't race | Before D2H of logits; between prefill and decode on different streams; KV block handoffs |

**Asynchronous execution is the precondition, streams are the mechanism, events are the
glue, and CUDA Graphs are the shortcut** [I]: async lets the host outrun the GPU; streams
let different kinds of work (compute vs copy vs collective) overlap; events make that
overlap *safe* (you declare exactly which stream waits on which event); graphs replace the
per-launch handshake with one DAG replay. Engines combine all four: an engine's decode
step is a graph replay on a primary stream, with KV/movement side streams ordered by events
(./Inference-Engines.md, ./vLLM.md).

## Decode-Token Cost Breakdown [E, hand-derived]
One decode token, 32-layer decoder, unfused baseline, B=1:
- Per layer: RMSNorm, QKV GEMM, RoPE, attention, O-proj, residual add, RMSNorm,
  up/gate, down, activation ≈ **5–10 launches** [I: op list above].
- Per token: 5–10 × 32 = **160–320 kernel launches** [E].
- At ~5 µs pure launch overhead each [I; UNVERIFIED]: 160 × 5 µs = **800 µs**,
  320 × 5 µs = **1.6 ms** of launch tax per token, *before a single FLOP of the kernels
  finishes* [E: 160·5e-6, 320·5e-6].
- Against a ~10–30 ms/token decode step at low batch (a typical B=1..8 ITL range; an
  assumption, [A]), that
  is **8–16% of a 10 ms step** and **2.7–5.3% of a 30 ms step** [E: 0.8/10, 1.6/10,
  0.8/30, 1.6/30]. And the launch tax is *CPU-bounded*: it shows up as GPU idle, not
  kernel time.
- Contrast the compute itself: a 7B-class model streams ~14 GB of BF16 weights/token [E:
  7e9·2 B] → ~4.2 ms of HBM time at 3.35 TB/s [E] — so the launch tax is a **real fraction
  of, not a rounding error against, the memory time** at B=1 [E: 0.8–1.6 ms vs 4.2 ms].
This arithmetic is the root motivation: fusion cuts the 160–320 nodes to a fraction
(./Fused-Kernels.md); CUDA Graphs cut the per-node cost to one graph launch
(F: NVIDIA docs) — and batching (continuous batching, ../Inference) shrinks work-per-op so
the tax amortizes across tokens.

## Failure modes (pipeline level)
- **Eager, unfused decode at B=1:** the 0.8–1.6 ms/token launch tax above; GPU utilization
  pulses. Fix: graph capture + fusion + C++ scheduler.
- **Graphs with dynamic shapes:** recapture thrash or eager fallback on every shape change.
  Fix: batch-size buckets + padded capture (./vLLM.md).
- **Overlapping streams without events:** data races / use-before-write on KV or
  activations. Fix: explicit event record/wait (above).
- **Pageable host copies in the hot path:** hidden syncs per copy. Fix: pinned memory +
  async copies (CUDA-From-Zero.md §Failure modes).

## How to measure the whole pipeline
- **`nsys` timeline:** kernel bubbles + gaps + copy engines + stream lanes in one view;
  gaps = launch/handoff cost; copy lanes = streams working [F: Nsight Systems docs].
- **Kernel count/step:** `torch.profiler` — count launches/token; compare fused vs unfused.
- **Launch-vs-work ratio:** per-kernel (kernel time vs inter-kernel gap) in `nsys`;
  ratio > 0.5 → launch-bound (Kernel-Stack.md §How to measure).
- **ITL/TPOT before/after** graph capture or fusion, at the same batch: the serving-level
  proof (Perf-Experiment-Template.md).

## Key Takeaways
1. One PyTorch op = one CPU call → launch descriptor → driver handoff → block scheduler →
   warps → memory → cores → sync back; the GPU side can be **nanoseconds** while the
   handoff is **tens of microseconds** [I; UNVERIFIED].
2. Launch overhead is a **per-launch fixed tax**: 5 µs launch + 1 µs work = 83% overhead
   [E] — launch-bound, not compute-bound, at small-batch decode.
3. A decode token runs ~160–320 launches (32 layers × 5–10 ops) [E] → 0.8–1.6 ms of pure
   launch tax [E] ≈ 3–16% of a 10–30 ms/token step [E] — the sum of many small launches
   dominates ITL, not any one kernel.
4. The toolkit: async execution (host doesn't block) + streams (overlap work) + events
   (safe ordering) + CUDA Graphs (one DAG replay instead of N handshakes) + fusion (fewer
   DAG nodes) [F: NVIDIA docs].
5. Fixing kernels exposes launch/scheduler overhead next — always re-measure the next
   limiting resource (./Cross-Layer-Optimization.md).

## Related
`./CUDA-From-Zero.md` (launch syntax + the RMSNorm kernel this page follows) ·
`./Architecture.md` (SM/warp/scheduler model) · `./GEMM.md` (the Tensor-Core stage) ·
`./Fused-Kernels.md` (cutting launch count) · `./Kernel-Stack.md` (which layer owns what) ·
`./Inference-Engines.md` / `./vLLM.md` (engines that capture per-token graphs) ·
`./Cross-Layer-Optimization.md` (the next-limiting-resource principle) ·
`../Inference/The-Life-of-a-Token.md` · `../Inference/Continuous-Batching.md` ·
`./Profiling.md` / `./Diagnostics.md`.

## References
NVIDIA CUDA C++ Programming Guide (kernels, streams, events, `<<<>>>` launch semantics,
asynchronous execution; docs.nvidia.com/cuda/cuda-c-programming-guide) [F: NVIDIA docs] ·
NVIDIA CUDA Runtime API — CUDA Graphs (capture, instantiate, graphLaunch; DAG of
kernels/copies/syncs) [F: NVIDIA docs] · NVIDIA H100 specs (3.35 TB/s HBM3, 132 SMs)
[F: vendor spec; ../Hardware/README.md] · RMSNorm [F: arXiv:1910.07467] ·
NVIDIA Nsight Systems/Compute docs (timeline gaps, launch rate, per-kernel timing)
[F: NVIDIA docs] · launch-overhead magnitudes throughout: [I; UNVERIFIED] — framed as
"tens of microseconds", device/driver-dependent, not a sourced spec.
