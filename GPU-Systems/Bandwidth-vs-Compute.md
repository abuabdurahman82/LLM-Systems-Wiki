# Why LLM Inference Is Often Memory-Bound
`LAST_UPDATED: 2026-08-21` · Status: core page · PART V — the conceptual heart of the
GPU-systems section. All [E] numbers Python-verified this session; crux arithmetic
shown inline. Hardware constants per `../Hardware/README.md` and NVIDIA specs.

## 30-Second Explanation
A modern GPU has two big numbers: **peak FLOPS** (H100 SXM: 989 TFLOP BF16 dense
[F: vendor spec]) and **HBM bandwidth** (3.35 TB/s [F: vendor spec]). Which one
limits a kernel is decided by one ratio — **arithmetic intensity, AI = FLOPs
performed / bytes pulled from HBM**:
- **Prefill** processes S prompt tokens in one parallel pass; its dense GEMMs
  `[S,d]×[d,d]` reuse every weight element S times → AI ≈ 1365–2048 at d=4096,
  BF16 [E] ≫ the ridge (≈ 295 FLOP/byte, H100 BF16 [E]) → **compute-bound**.
- **Decode** emits one token at a time; every token streams the entire weight
  matrix (a 27B BF16 model ≈ 50 GiB [E]) plus its KV cache → AI ≈ 1 [E] →
  **memory-bandwidth-bound**; ceiling ≈ 62 tok/s on an H100 [E] while the
  989-TFLOP Tensor Cores sit mostly idle waiting for data.
Everything reduces to four regimes — **compute-bound, memory-bandwidth-bound,
latency-bound, communication-bound** — and every optimization (quantization,
batching, CUDA Graphs, TP, P/D split) attacks one of them. The Roofline model
(Williams, Waterman & Patterson 2009 [F: ACM CACM]) makes this precise:
`achieved FLOP/s = min(Peak FLOPS, HBM-BW × AI)`. One-page version:
[Roofline](../Inference/Roofline.md); token walkthrough:
[The-Life-of-a-Token](../Inference/The-Life-of-a-Token.md).

## The master ratio: arithmetic intensity
**Definition.** `AI = FLOPs / bytes transferred from HBM` (FLOP/byte). A GPU
executes FLOPs at rate P (FLOP/s) and feeds bytes at rate BW (B/s); a kernel
needing 1/AI bytes per FLOP cannot exceed `BW × AI` FLOP/s, nor P, so
`FLOP/s ≤ min(P, BW·AI)` [I: one-line derivation of the roofline].
- **AI is a property of kernel shape, not hardware:** the same `d×d` weight
  matrix has AI ≈ 2S/b_w with S tokens in flight (prefill) but ≈ 2/b_w at B=1
  (decode) — the regime switch is the GEMM's M dimension
  ([GEMM](./GEMM.md), "why GEMM performance depends on shape").
- **Raise AI without new hardware:** batch more tokens (amortize the weight
  stream — [Continuous-Batching](../Inference/Continuous-Batching.md)), keep
  data in SRAM/L2 via tiling ([Memory-Hierarchy](./Memory-Hierarchy.md)), fuse
  so intermediates never round-trip HBM (`Fused-Kernels.md`).
- **Lower bytes without touching FLOPs:** quantize weights/KV
  (`../Quantization/README.md`).
- **The ridge** of a machine: `R = P/BW`; H100 SXM BF16: `989e12 ÷ 3.35e12 =
  295.2 ≈ 295 FLOP/byte` [E]. AI ≥ R → compute roof; AI < R → memory roof.

## The Roofline Model
*9-field concept. Goes deeper than the one-page [Roofline](../Inference/Roofline.md)
on prefill/decode asymmetry, the four regimes, and the knee batch B*; that
page's numbers (H100 ridge ≈ 295, decode AI ≈ 1–4) are reused, not re-derived.*

### What
`achieved FLOP/s = min(P, BW × AI)`: P is the flat **compute roof**,
`BW × AI` the sloping **memory roof**; the **ridge point** `AI* = P/BW`
separates them. Origin: Williams, Waterman & Patterson, "Roofline" (ACM CACM
2009 [F]); LLM-serving application follows Pope et al. (arXiv:2111.02534 [F]).

### Why
Compute and memory are sized by different economics, and the ratio drifts
across generations: H100 BF16 ridge ≈ 295 FLOP/byte [E], B200 FP8
`4.5e15 ÷ 8e12 = 562.5 FLOP/byte` [E]. Without a model tying workloads to
roofs you'd "optimize FLOPs" for a kernel that is actually byte-starved [I].

### How
Count FLOPs (F = 2·M·N·K for a GEMM; `GEMM.md`) and HBM bytes (weights +
activation in/out + KV), compute AI = F/B, locate it: `AI ≥ P/BW` → compute
roof (levers: Tensor Cores, better dtype, larger GEMMs); `AI < P/BW` → memory
roof (levers: fewer bytes via quant/KV shrink, or more reuse via batching/SRAM).
Real kernels sit **below** both roofs — the roof is a ceiling, not a promise;
the gap is kernel quality / MFU [I].

H100 SXM roofline (BF16):
```
 FLOP/s
 989e12 ┤                          ┌─────────────  compute roof: P
        │                         ╱
        │                       ╱   ● prefill GEMM (AI ≈ 1365–2048)
        │                      ╱      (compute roof)
        │                    ╱
        │         ● B ≈ 345 knee (AI = ridge)
        │╱
 3.35e12┤● decode B=1 (AI ≈ 1; FLOP/s = BW × 1 = 3.35e12)
        └────────────────────────────────── AI (FLOP/byte)
          1             B* ≈ 295–345        295 (ridge = P/BW)
```
(Memory-roof slope = HBM bandwidth; at AI = 1 the achievable rate is
BW × 1 = 3.35e12 FLOP/s = 0.34% of peak [E: 3.35/989 = 0.0034].)

### When
Predict which roof a new model/workload sits under before running it; pick
kernels (large-M prefill vs skinny-M decode, `GEMM.md`); size batching
(throughput rises with B until AI(B) hits the ridge — B*, derived in
[E3](#e3-knee-batch-b--where-decode-crosses-from-memory-to-compute)); reason
about quantization (weight quant cuts bytes → lifts the memory roof).

### Hardware impact
H100 SXM BF16 ridge ≈ 295 FLOP/byte [E: 989e12 ÷ 3.35e12 = 295.2]; B200 FP8
ridge 562.5 [E above] — doubled, but decode (AI ≈ 1–4) stays far below it, so
bandwidth still binds token generation [I]. PCIe 5.0 x16 (≈ 64 GB/s) and
NVLink (≈ 900 GB/s) are **separate roofs** in multi-GPU systems: the fabric
becomes the "HBM" of the parallel machine (communication-bound regime below).

### Inference impact
**TTFT** (prefill, compute roof): FP8/FP4, FlashAttention
(../Attention/README.md), more GPUs (TP). **ITL** (decode, memory roof):
`ITL ≈ (weight_bytes + KV_bytes)/effective_BW` → quantize, batch to B*,
GQA/MLA, KV quant (`../KV-Cache/README.md`). Full metric mapping:
[Inference-Optimization](../Inference/Inference-Optimization.md).

### Example
[Worked below](#e1-prefill-gemm--sd-dsd--s--4096-d--4096-bf16). Short version
[E]: `[4096,4096]×[4096,4096]` BF16 → F = 2·4096³ = 137,438,953,472 FLOP;
B = 3·4096·4096·2 = 100,663,296 B; AI = 1365.3 ≫ 295 → compute roof. Decode
GEMV on the same weights: F = 2·4096² = 33,554,432; B = 33,554,432; AI = 1.0
≪ 295 → memory roof.

### Failure modes
Treating the roof as gospel — real kernels sit below it (good GEMM MFU 40–70%
[A]); counting FLOPs without the two S·d activation moves per GEMM [I];
one-precision peaks (FP8 peak is 2× BF16, so the ridge shifts — a quantized
model is not automatically "on the memory roof" if P doubled too); ignoring
the latency roof (small kernels miss *both* roofs via launch gaps).

### How to measure it
Nsight Compute: `dram__throughput` vs `sm__inst_executed_pipe_tensor`;
achieved FLOP/s vs `BW × AI` locates you on the roofline
[F: Nsight Compute docs] → `Profiling.md`, `Diagnostics.md`. Engine-level
sanity check: prefill vs decode tok/s should track the two roofs in ratio.

## Prefill vs Decode — the regime split
*9-field concept. The "master switch" of LLM inference: one model, two
bottlenecks. Op-by-op: [The-Life-of-a-Token](../Inference/The-Life-of-a-Token.md);
kernel-shape view: [GEMM](./GEMM.md).*

### What
- **Prefill:** S prompt tokens in one parallel pass; each layer runs dense
  GEMMs `[S,d]×[d,d]` + the O(S²) attention core. Weights are read once and
  reused across all S rows → AI ≈ 1365–2048 at S=d=4096, BF16 [E] →
  **compute-bound**; bottleneck = TFLOPS; metric = **TTFT**.
- **Decode:** one token per step; every step re-reads *all* weights and *all*
  prior KV. GEMMs degenerate to GEMVs `[B,d]×[d,d]` with B small →
  AI ≈ 2B·d/(2B·b + b_w·d) ≈ 1 at B=1, BF16 [E] → **memory-bandwidth-bound**;
  bottleneck = TB/s; metric = **ITL/TPOT**.

The conceptual contrast:
```
               PREFILL                                DECODE
            (S tokens in)                          (1 token in, 1 token out)
                  │                                      │
      X [S,d] ────┤                            x [1,d] ───┤
                  ▼                                      ▼
        dense GEMMs [S,d]×[d,d]                   GEMVs [1,d]×[d,d]
  each weight element is reused S times per      each weight is read exactly
  output element (K-loop reuse)                   once per token (no reuse)
                  │                                      │
                  ▼                                      ▼
        Tensor Cores near peak                   HBM streams ≈ 50.3 GiB of
        AI ≈ d/b_w (≈ 1365–2048, BF16 [E])        weights + ≈ 1.0 GiB of KV [E]
                  │                                      │
                  ▼                                      ▼
       COMPUTE-INTENSIVE                          BANDWIDTH-INTENSIVE
  bottleneck: 989 TFLOP roof               bottleneck: 3.35 TB/s roof
  metric: TTFT                               metric: ITL
```

### Why
Autoregression is the root cause: position t needs positions < t, so
generation cannot parallelize *within* a sequence, only *across* sequences
(batching) — and serving keeps B small for latency [I]. Prefill parallelizes
*within* the prompt (S tokens), so its GEMMs stay dense. Same weights, same
GPU, opposite roofs: the asymmetry is a property of GEMM shape, not the model
(`GEMM.md`).

### How
**Prefill:** one shot — embeddings → L × (attention + FFN) dense GEMMs + O(S²)
attention → logits at the last position. **Decode:** a loop — sample →
embedding → L × GEMV stack (streams all weights + KV) → logits → sample;
`ITL ≈ (weight_bytes + KV_bytes)/effective_BW + overheads`. The **KV cache**
bridges them: written once at prefill (big burst), read every decode step;
size `2·L·B·h_kv·d_h·S·b` caps concurrency ([KV-Cache](../KV-Cache/README.md)).

### When
**TTFT matters** (long prompts, RAG, agents): pay on the compute roof →
prefill levers (FP8/FP4, FlashAttention, prefix cache, TP). **ITL matters**
(interactive chat): pay on the memory roof → decode levers (quantization,
batching, GQA, KV quant, CUDA Graphs, spec decoding). **Serving both at
once:** continuous batching interleaves prefill chunks with decode steps —
the two regimes fight for the same SMs (../Inference/Continuous-Batching.md;
`Prefill-Decode-Disaggregation.md`).

### Hardware impact
Prefill loads the **Tensor Cores** (H100: 989 TFLOP BF16 dense); HBM traffic
= weights once + S·d activations in/out (+ S² scores pre-FA). Decode loads
**HBM**: a 27B BF16 model moves ≈ 50.3 GiB per token
[E: 27e9 × 2 B = 5.4e10 B = 50.29 GiB]; at 3.35 TB/s that is
`5.4e10 ÷ 3.35e12 = 16.1 ms`/token → ≈ 62 tok/s ceiling [E] — 989 TFLOPS is
essentially irrelevant at B=1 (achieved rate at AI=1 is only 3.35e12 FLOP/s
= 0.34% of peak [E: 3.35/989 = 0.0034]). KV adds ≈ 1.0 GiB/step at 8192 ctx,
GQA h_kv=8, BF16 [E, `The-Life-of-a-Token.md`: 2·32·8·128·8192·2 B = 1.07e9 B]
→ total 5.507e10 B → `3.35e12 ÷ 5.507e10 = 60.8 tok/s` [E].

### Inference impact
**Throughput** = B × per-token rate, rising with B until the knee batch B*
(E3) — the entire economic case for batching
(../Inference/Continuous-Batching.md). **P99 vs P50:** prefill interference
inflates the decode ITL tail unless you chunk prefill or split P/D
(../Inference/Inference-Optimization.md). **Speculative decoding** turns GEMVs
into small GEMMs (draft+verify), raising AI and lifting ITL above the B=1 roof
(../Speculative-Decoding/README.md) [I].

### Example
27B model, one H100 SXM [E, Python-verified]:
- Weights: 27e9 × 2 B = 5.4e10 B = **50.3 GiB**; KV @ 8192 (GQA, h_kv=8):
  **1.0 GiB**; total per decode step: 5.507e10 B.
- Decode ceiling: `3.35e12 ÷ 5.507e10 = 60.8 tok/s` (weights only:
  `3.35e12 ÷ 5.4e10 = 62.0 tok/s` — `GEMM.md` quotes ≈ 65 tok/s, a looser
  rounding of the same ratio).
- Prefill @ S=8192: 2·N·S = 2 × 27e9 × 8192 = 4.42e14 FLOP
  [E, `The-Life-of-a-Token.md`]; at 60% MFU of 989 TFLOP [A] →
  `4.42e14 ÷ 5.93e14 ≈ 0.75 s` of prefill work [I].
- NVFP4 weights: 27e9 × 4.5/8 = 1.519e10 B = 14.1 GiB [E; 4.5 bits/param
  counts block-scale overhead, matching `Roofline.md`] → ceiling
  `3.35e12 ÷ 1.626e10 = 206 tok/s` [E] — ≈ 3.4× because bytes fell 3.4×
  [E: 5.507e10 ÷ 1.626e10 = 3.39].

### Failure modes
Treating decode like prefill (or vice versa): large-M GEMM kernels at B=1, or
compute-roof optimizations aimed at B=1. "Faster GPU = faster tokens": H100 →
B200 lifts P from 989 TFLOP to ≈ 4.5 PFLOP FP8, but at B=1 the ceiling is
BW ÷ bytes, so the token-rate gain is ≈ the bandwidth ratio
(8/3.35 = 2.39× [E: 8e12 ÷ 5.507e10 = 145 tok/s vs 60.8]), not the FLOPS
ratio (4.5× [E: 4.5e15 ÷ 989e12 = 4.55]) [I]. Ignoring KV growth: ITL
degrades with context as the KV read grows. Prefill/decode contention on one
GPU inflates P99 ITL — the classic continuous-batching failure mode.

### How to measure it
Trace one request (`Profiling.md`): prefill chunk time vs each decode step
should track the two roofs. `nvidia-smi`/DCGM: prefill → Tensor Cores busy;
decode → DRAM throughput near peak, SM utilization single-digit %
(`GPU-Metrics.md`) [I: expected pattern].

## The four regimes
Two of these are the two roofline roofs; the other two appear when the work
is too small to reach a roof (latency) or is split across GPUs (communication).

**1. Compute-bound** — Tensor Cores saturated, HBM below peak; AI ≥ ridge.
*Example:* prefill GEMM `[4096,4096]×[4096,4096]` (AI ≈ 1365–2048 [E]); any
M ≫ B*; training. *Lever:* FP8/FP4 weights, FlashAttention, TP, big-K
pipelining; prefill *should* live here.

**2. Memory-bandwidth-bound** — HBM ≈ peak, SMs mostly idle; AI < ridge.
*Example:* decode GEMV at B ≤ B* (AI ≈ 1–4 [E]); long-context KV reads.
*Lever:* weight quant, batch to B*, GQA/MLA, KV quant
(../KV-Cache/README.md), speculative decoding.

**3. Latency-bound** — kernel-stream gaps: each kernel is too small to hide
launch/completion latency, so neither roof is reached. *Example:*
small-batch decode on an unfused stack: ≈ 300 kernels per token
(≈ 9–10 per layer × 32 layers, from the op list in
[The-Life-of-a-Token](../Inference/The-Life-of-a-Token.md)) [I]. Magnitude
[I]: with ≈ 4 µs launch overhead per kernel [A], 300 × 4 µs = 1.2 ms;
against a B=1 27B ITL of ≈ 16.1 ms [E] that is ≈ 7% of the token's time
[E: 1.2/16.1 = 0.074]. *Lever:* CUDA Graphs, kernel fusion, continuous
batching, off-CPU sampling (`Kernel-Life.md`, `Fused-Kernels.md`).

**4. Communication-bound** — collective/fabric time ≫ time to use the data;
HBM idle waiting on the network. The fabric roof: NVLink ≈ 900 GB/s vs HBM
3.35 TB/s; PCIe 5.0 x16 ≈ 64 GB/s; IB NDR ≈ 50 GB/s/link [F: vendor specs].
*Examples [E: arithmetic]:*
- **TP AllReduce** at decode B=1, BF16: each AllReduce moves ≈ 2·d·b_w =
  2·4096·2 = 16,384 B per rank (ring, N ≥ 2); 2 AllReduces/layer × 32 layers
  = 1,048,576 B/token → NVLink `÷ 900e9 = 1.2 µs`, PCIe `÷ 64e9 = 16.4 µs`,
  IB `÷ 50e9 = 21.0 µs`. Tax on a 16.1 ms ITL ≈ 0.01% [E:
  1.2e-6 ÷ 1.61e-2 = 0.00007] — but it happens 64×/token and serializes the
  step (`Tensor-Parallelism.md`) [I].
- **MoE AllToAll:** DeepSeek-V3-class (d=7168, top_k=8 [F: arXiv:2412.19437]),
  B=1: dispatch moves 8·7168·2 = 114,688 B one way; ×2 (dispatch + combine)
  ≈ 229,376 B/token [E] → over IB NDR `229,376 ÷ 50e9 = 4.6 µs`/token. EP
  routes *all* expert traffic through the fabric; hot experts contend
  (`MoE-Expert-Parallelism.md`) [I].
- **P/D KV transfer:** 1.0 GiB KV (8192 ctx, [E]): IB NDR
  `1.074e9 ÷ 50e9 = 21.5 ms` vs NVLink `1.074e9 ÷ 900e9 = 1.2 ms` [E] —
  exactly the cost DistServe (arXiv:2401.09670 [F]) and Mooncake
  (arXiv:2407.00079 [F]) engineer around; P/D split is a *communication*
  decision, not just scheduling (`Prefill-Decode-Disaggregation.md`).
*Lever:* NVLink over PCIe (TP), hierarchical ring/tree collectives, colocate
P/D on a fast fabric, RDMA/GPUDirect for KV (`Multi-Node.md`, `NCCL.md`).

### Regime cheat sheet
| Regime | Signature metric | Typical LLM phase | Lever that helps |
|---|---|---|---|
| Compute-bound | AI ≥ ridge (≈ 295 @ H100 BF16 [E]); Tensor Cores ≈ peak, HBM < peak | Prefill GEMM (S ≫ B*); training | FP8/FP4, FlashAttention, TP, big-K pipelining |
| Memory-bandwidth-bound | HBM ≈ peak; SM util single-digit %; AI ≈ 1–4 [E] | Decode GEMV (B ≤ B*) | Weight quant, batch to B*, GQA/MLA, KV quant |
| Latency-bound | Kernel gaps in trace; GPU util low **and** DRAM < peak; µs-scale kernels | Small-batch decode, unfused stacks, sampling/scheduler overhead | CUDA Graphs, fusion, continuous batching, off-CPU sampling |
| Communication-bound | Collective time ≫ data-use time; fabric ≈ peak, HBM idle | TP AllReduce (2/layer), MoE AllToAll, P/D KV transfer | NVLink over PCIe, hierarchical NCCL, colocated P/D, RDMA |

## Why bandwidth can matter more than theoretical TFLOPS
The 27B/H100 argument [E, Python-verified]:
1. 27B BF16 = 27e9 × 2 B = **5.4e10 B = 50.3 GiB**. A dense model uses *all*
   weights on *every* token — no sparsity escape (unlike MoE).
2. H100 SXM HBM3 = 3.35e12 B/s.
3. Per decode step the GPU must stream those bytes at least once (+ ≈ 1.0 GiB
   KV at 8192 ctx) → min time/token = `5.4e10 ÷ 3.35e12 = 16.1 ms` →
   **62.0 tok/s ceiling** (60.8 with KV [E: 3.35e12 ÷ 5.507e10]) —
   **regardless of the 989 TFLOPS**: at AI ≈ 1 the machine can only
   usefully execute 3.35e12 FLOP/s = 0.34% of peak [E: 3.35/989 = 0.0034].
4. TFLOPS only pay off when batching or quantization pushes AI toward the
   ridge (E3); quantize → bytes ÷ 2 (FP8) or ÷ 3.4 (NVFP4: 50.3 → 14.1 GiB
   [E]; ceiling 62 → 206 tok/s with KV [E]).
For **token generation** the HBM stack is the engine and the Tensor Cores the
transmission: more TFLOPS buys prefill speed and headroom, but the decode
ceiling is `bandwidth ÷ bytes per token`, full stop. Same arithmetic on a
GDDR7 card (≈ 1.79 TB/s [Roofline.md]): `1.79e12 ÷ 5.507e10 ≈ 32.5 tok/s`
(≈ 33 tok/s as quoted in `Roofline.md` [E]) — bandwidth decided it [I].

## Hand-calculable examples
*(All [E], Python-verified this session; every step shown.)*

### E1. Prefill GEMM — `[S,d]×[d,d]`, S = 4096, d = 4096, BF16
- FLOPs: F = 2·S·d·d = 2·4096·4096·4096 = 2·2³⁶ = 2³⁷ = **137,438,953,472**
  (≈ 137.4 GFLOP).
- HBM bytes: act-in S·d·2 = 33,554,432; weights d·d·2 = 33,554,432; act-out
  S·d·2 = 33,554,432 → B = 3 · 33,554,432 = **100,663,296 B** (≈ 0.096 GiB).
- AI = 137,438,953,472 ÷ 100,663,296 = **1365.3 FLOP/byte**. (The weight-only
  approximation used by `Roofline.md`, bytes ≈ d·d·b_w, gives
  AI ≈ 2S/b_w = 4096/2 = **2048 = d/b_w**.)
- H100 BF16 ridge = 989e12 ÷ 3.35e12 = **295.2** [E].
- 1365.3 ≥ 295.2 (4.6× the ridge; 2048 is 6.9×) → **compute roof**: the 32 MiB
  of weights is read once and does 2³⁷ FLOPs of work — that reuse is what
  makes prefill compute-bound.

### E2. Decode GEMV — B = 1, d = 4096, b_w = 2
- FLOPs: F = 2·1·d·d = 2·4096·4096 = **33,554,432** (≈ 33.55 MFLOP).
- HBM bytes: weights d·d·2 = 33,554,432; activations 2·d·2 = 16,384 (0.05%,
  negligible) → B ≈ **33,554,432 B** (32 MiB).
- AI = 33,554,432 ÷ 33,554,432 = **1.0 FLOP/byte** (0.9995 counting act bytes).
- 1.0 ≪ 295 → **memory roof**: achievable FLOP/s = 3.35e12 × 1.0 = 3.35e12
  (0.34% of 989e12 [E: 3.35/989 = 0.0034]); one such matrix takes
  33,554,432 ÷ 3.35e12 = **10.0 µs** [E].
- Whole-token rate: bytes/token ÷ BW. 27B: 5.507e10 B ÷ 3.35e12 B/s =
  16.1 ms → **60.8 tok/s** [E] (`GEMM.md` quotes ≈ 65 tok/s, looser rounding).

### E3. Knee batch B* — where decode crosses from memory to compute
Per `Roofline.md`, batched-decode AI is `AI(B) = 2B·d / (2B·b_act + b_w·d)`.
Set AI(B*) = R (ridge) and solve:
```
2·B*·d = R·(2·B*·b_act + b_w·d)
B*·(2d − 2R·b_act) = R·b_w·d
B* = R·b_w·d / (2·(d − R·b_act))
```
- Large-d limit (d ≫ R·b_act): **B* ≈ R·b_w/2** [E: limit of the expression]
  = 295·2/2 = **295** (H100, BF16).
- Exact at d = 4096: B* = 295·2·4096 / (2·(4096 − 295·2)) = 295·4096 / 3506
  = **344.6 ≈ 345** [E: 1,208,320 ÷ 3,506] — matches "BF16 on H100 ≈ 345"
  in `Roofline.md`.
- **Read:** at B < 345, decode is bandwidth-bound and each extra request
  multiplies throughput (weight stream amortized); at B > 345, requests queue
  against the compute roof [I]. This is the entire economic argument for
  continuous batching (../Inference/Continuous-Batching.md).
- **Dtype invariance [E]:** B* ≈ R·b_w/2 = P·b_w/(2·BW). FP8 doubles P
  (989 → 1979 TFLOP [F: vendor spec]) and halves b_w (2 → 1), so the limit
  knee is **unchanged** (295 in both dtypes; exact at d=4096:
  590.7·4096/(2·(4096 − 590.7)) = 345.1 [E: 590.7 = 1979/3.35]).
  Quantization does not move the knee — it lifts the *rate* on each side:
  bytes fall on the memory roof, FLOPS rise on the compute roof.

## Related
[Roofline](../Inference/Roofline.md) (one-page roofline; ridge examples; the
B* numbers re-derived here) ·
[The-Life-of-a-Token](../Inference/The-Life-of-a-Token.md) (op-by-op
walkthrough; KV formula) · [GEMM](./GEMM.md) (M is the regime switch) ·
[Memory-Hierarchy](./Memory-Hierarchy.md) (where bytes move; tiling/
coalescing) · [Continuous-Batching](../Inference/Continuous-Batching.md)
(operating at B*) · [Inference-Optimization](../Inference/Inference-Optimization.md)
(TTFT/ITL → levers) · [KV-Cache](../KV-Cache/README.md) (the
`2·L·B·h_kv·d_h·S·b` budget) · Siblings: `Kernel-Life.md` · `Fused-Kernels.md`
· `Tensor-Parallelism.md` · `MoE-Expert-Parallelism.md` · `NCCL.md` ·
`Prefill-Decode-Disaggregation.md` · `Diagnostics.md` · `Profiling.md`.

## Key Takeaways
1. **AI = FLOPs/bytes** picks the roof; the ridge (H100 BF16 ≈ 295 FLOP/byte
   [E]) is where the two roofs meet.
2. **Prefill = compute roof, decode = memory roof** — same model, opposite
   bottlenecks; the switch is the GEMM's M dimension (`GEMM.md`).
3. **The decode ceiling is BW ÷ bytes-per-token**: 27B BF16 on H100 =
   3.35e12 ÷ 5.507e10 ≈ 61 tok/s [E] — 989 TFLOPS is irrelevant at B=1
   (0.34% utilized [E]).
4. **The knee batch B* ≈ R·b_w/2 (≈ 345 exact at d = 4096 [E])** is the
   continuous-batching target — and is dtype-invariant.
5. **Four regimes, four levers:** compute → FLOPS/dtype; bandwidth →
   bytes/batch; latency → graphs/fusion; communication → fabric/topology.
