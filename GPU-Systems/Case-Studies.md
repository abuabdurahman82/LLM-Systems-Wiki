# Case Studies — Applying the Model to Real Decisions
`LAST_UPDATED: 2026-08-22 · Status: core page` · PART XXXIII. Seven worked, hand-calculable
decisions that apply the whole toolkit — [Roofline](../Inference/Roofline.md), the
[Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md) regime model, KV math
([KV-Cache](../KV-Cache/README.md)), collective costs ([Multi-GPU](./Multi-GPU.md),
[NCCL](./NCCL.md)), and the [Diagnostics](./Diagnostics.md) tree — to realistic serving
choices. Every [E] number is hand-derived below; every assumption is marked [A]. Hardware
constants per `_STYLE.md` and `../Hardware/README.md` (H100 SXM: 989 TFLOP BF16 dense,
3.35 TB/s HBM3, ~900 GB/s NVLink aggregate [F: vendor spec]); example model = 6.5B-class
dense (d=4096, 32 layers, d_ff≈11008, GQA-8, ~54 GB BF16 on H100 [A]).

## 30-Second Explanation
This page answers seven questions you actually face, each with the full hand arithmetic:
1. **What is the B=1 decode ceiling?** → `3.35 TB/s ÷ 54.0 GB ≈ 62 tok/s` [E] — bandwidth
   sets it; quantization is the biggest decode lever.
2. **How long does a 4096-token prefill take?** → `6·6.5e9·4096 = 1.6e14 FLOP`; 0.16 s ideal,
   ~0.36 s at 45% MFU [E] — 1600× the decode step's 16 ms: prefill and decode are different
   machines.
3. **How many concurrent requests fit?** → ~200k KV tokens of headroom → ≈ 48 short
   (S=4096) requests or ≈ 1.6 long (S=128k) ones [E] — KV capacity is the concurrency ceiling.
4. **What does TP=8 cost per token?** → ≈ 0.5 µs of AllReduce over NVLink [E] — negligible
   intra-node; 18× more over IB. TP stays on the fast fabric.
5. **Why does MoE decode faster at the same total params?** → only 2/8 experts active per
   token → activated bytes 25.8 GB vs 94 GB dense [E] → ~3.6× the bandwidth ceiling.
6. **Should prefill and decode share GPUs?** → a prefill chunk can stall decode ITL ~22× [E];
   splitting pays a KV transfer (0.6 ms NVLink vs 10.7 ms RDMA) [E].
7. **ITL SLO is at the edge — add GPUs, quantize, split P/D, or do nothing?** → walk the
   [Diagnostics](./Diagnostics.md) tree; the numbers that distinguish the four answers.

## How to use this page
Each case has the same five fields: **Question → Arithmetic ([E]) → Insight → What to
actually do → Failure mode.** Reproduce any number before relying on it (the
[Perf-Experiment-Template](./Perf-Experiment-Template.md) is how you turn a hand estimate
into a verified measurement). Constants are the 6.5B-class example model and H100 SXM
unless a case says otherwise.

---

## Case 1 — B=1 decode ceiling: why bandwidth, not FLOPS, sets the token rate

**Question.** A 6.5B-class model runs in BF16, weights ≈ 54.0 GB resident in HBM [A].
What is the single-request (B=1) decode ceiling on an H100 SXM, and how far does
quantization move it?

**Arithmetic [E].**
- B=1 decode streams the full weight matrix once per token (GEMV; [GEMM](./GEMM.md)
  "why GEMM performance depends heavily on shape"). Ceiling = HBM bandwidth ÷ bytes/token:
  `3.35 TB/s ÷ 54.0 GB = 3.35e12 ÷ 5.4e10 = 62.0 tok/s` [E].
- The compute roof is `989e12 FLOP/s`; at AI ≈ 1 FLOP/byte the machine can only usefully
  execute `3.35e12` FLOP/s = **0.34% of peak** [E: 3.35/989 = 0.0034]. The 989 TFLOP roof
  is irrelevant at B=1 — the GEMVs never reach it (ridge ≈ 295 FLOP/byte [E],
  [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)).
- INT8 weights halve the bytes (54.0 → 27.0 GB) → ceiling `3.35e12 ÷ 2.7e10 = 124.1 tok/s`
  [E] — exactly 2×, because time ∝ bytes on the memory roof.
- A real kernel does not reach the ceiling: launch gaps and non-GEMM work (RMSNorm,
  attention score/softmax, sampling — [Kernel-Life](./Kernel-Life.md)) cost a few hundred
  µs of the ~16.1 ms step [A: ≈ 200–300 µs ≈ 2–3%] plus imperfect HBM efficiency
  (good GEMVs hit ~85–95% of peak bandwidth [A]). Net: expect **~80% of the ceiling** [I]
  → ≈ 49.6 tok/s for BF16 [E: 0.8 × 62.0], ≈ 99 tok/s for INT8 [E: 0.8 × 124.1].

**Insight.** Decode is bandwidth-bound, so the levers are **bytes**, not FLOPs: quantize
weights (INT8 → 2×, FP8 → 2×, NVFP4 → ~3.4× [E: 54 → ~15.9 GB → 3.35e12 ÷ 1.59e10 ≈
211 tok/s ceiling]), batch up to amortize the weight stream ([Continuous-Batching](../Inference/Continuous-Batching.md)), or shrink KV. Buying more FLOPS (H100 → B200) buys
almost nothing at B=1 — the ceiling moves with bandwidth, `BW ÷ bytes` [I].

**What to actually do.** (1) Confirm the regime: `dram__throughput` near 3.35 TB/s with
single-digit SM% ⇒ memory roof, as predicted (Steps 2–3 of [Diagnostics](./Diagnostics.md)).
(2) If B is small and quality allows, INT8/FP8 weights are the first lever — the ceiling
doubles with zero topology change. (3) Measure with ≥500 requests, P50/P95/P99 ITL
([Perf-Experiment-Template](./Perf-Experiment-Template.md)); the predicted delta is
*exactly* the bytes/token ratio — if the measured delta is less, the GEMV kernel (not the
dtype) is also the problem (bad skinny-M kernel selection, `Custom-GEMM.md`).

**Failure mode.** The "ceiling" assumes the whole weight matrix is read *once, coalesced*
per token. Strided/unaligned weight layouts, a cuBLAS kernel tuned for large M, or
re-reading weights through non-cached paths halve effective bandwidth → the real rate can
land at ~50% of ceiling with no change in the math [I]. Also: at B > ~345 (knee batch B*
[E, Bandwidth-vs-Compute] E3) you cross onto the compute roof — quantizing further then
buys FLOPS instead of token rate; the two levers stop being the same number.

---

## Case 2 — Prefill compute time: one prompt is ~1600 decode steps

**Question.** Same 6.5B model, H100 SXM. How long does an S=4096 prefill take, and how
does it decompose into compute, launch, and KV build?

**Arithmetic [E].**
- Linear-layer FLOPs: each token through the linear weights is ~`2·N` FLOP (one MAC per
  weight, ×2 for the add) plus ~`2N` for the forward pass — the standard estimate
  `F ≈ 6·N·S` (2N for GEMMs × 2 for the two passes through the weight stream, one MAC
  per weight) [A: conventional 6N estimate, cf. `GEMM.md` "12·d²/token" variant]:
  `6 × 6.5e9 × 4096 = 1.59744e14 ≈ 1.6e14 FLOP` [E].
- Ideal time at 989 TFLOP: `1.6e14 ÷ 989e12 = 0.1615 s ≈ 0.16 s` [E].
- At ~45% model FLOPs utilization (MFU) [A: typical for mid-size dense prefill]
  → `0.16 ÷ 0.45 = 0.359 s ≈ 0.36 s` [E].
- **TTFT breakdown** [I: split, each part hand-derivable]:
  - GEMM compute: 0.36 s (the dominant term above).
  - Attention core: QKᵀ + ·V over the 32 heads, S² per pair:
    `4·(32·d_h)·S² ·32 layers = 4·4096·4096² ·32 = 1.07e13 FLOP` ≈ 6.7% of the GEMM
    FLOPs at S=4096 [E: 1.07e13 ÷ 1.6e14 = 0.067] — folded into the MFU number, but it
    grows as S² (see failure mode).
  - Kernel launches: prefill runs far fewer, bigger kernels than decode — hundreds, not
    thousands; at ~4 µs/launch [A] that is ~1 ms = <1% of 0.36 s [E: 1e-3 ÷ 0.36].
    Not the cost here (it *is* the cost at B=1, Case 1).
  - KV build (write): S tokens × 128 KiB/token = `4096 × 1.31072e5 B = 5.37e8 B =
    0.5 GiB` [E] written once, at HBM write rates ≈ read → ~0.16 ms [E: 5.37e8 ÷
    3.35e12] — negligible against 0.36 s. (The *transfer* of this KV is Case 6.)
- **Contrast with B=1 decode:** the B=1 step is ~16.1 ms [E: 5.4e10 ÷ 3.35e12, Case 1
  numbers]. `0.16 s ÷ 0.0161 s = 9.9 ≈ 10×` ideal [E]; at 45% MFU,
  `0.359 ÷ 0.0161 = 22.3×` [E]. (For a 27B model the prompt is ~1600× the decode step's
  ~0.1 ms-equivalent work — same order argument, bigger model.) One prefill of a 4k prompt
  costs as much compute as 10–22 B=1 decode steps of this model.

**Insight.** Prefill and decode are opposite regimes on the same roofline
([Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)): prefill's GEMMs are
`[4096,4096]×[4096,4096]` (AI ≈ 1365–2048 ≫ ridge 295 → compute roof, Tensor Cores
saturated); decode is `[1,4096]×[4096,4096]` (AI ≈ 1 → memory roof). Treating one like
the other is the classic mistake: prefill wants more FLOPS (TP, FP8/FP4, FlashAttention);
decode wants fewer bytes. This asymmetry is the entire premise of
[P/D disaggregation](./Prefill-Decode-Disaggregation.md) and of continuous batching
prefill/decode interference (Case 6).

**What to actually do.** TTFT SLOs: check achieved FLOP/s vs 989 (Nsight Compute
`pipe_tensor`); if well under, FP8/FP4 weights and FlashAttention are the levers; if
TTFT is dominated by *queue* time rather than compute, the problem is admission
scheduling (Diagnostics Step 6), not the GEMMs. Verify any change with the pinned
protocol ([Perf-Experiment-Template](./Perf-Experiment-Template.md)) — TTFT, ITL,
*and* throughput must all move in the predicted direction.

**Failure mode.** The `6·N·S` estimate misses the S² attention term: at S=4096 it is ~7%
[E above], but at S=128k it is `131072/4096 = 32×` larger per token-pair → the
attention share rises to ~1.7× the GEMM FLOPs [E: 0.067 × 32] and "compute-bound by
GEMMs" becomes "compute-bound by attention" — FlashAttention (IO-aware,
`FlashAttention.md`) and long-context kernels become the bottleneck, not weight GEMMs.
Also: 45% MFU is an assumption; small models on one GPU with short prompts can be launch-
and-pipeline-bound rather than FLOP-bound (measure before assuming).

---

## Case 3 — KV-cache concurrency: the capacity that no FLOPS can buy

**Question.** 6.5B GQA-8 model, BF16 weights 54.0 GB resident [A]. On an 80 GB H100, how
many concurrent requests can be served at S=4096 vs S=128k?

**Arithmetic [E].**
- KV/token (GQA-8, d_h=128, BF16, 32 layers): `2 (K+V) × 32 × 8 × 128 × 2 B = 131,072 B
  = 128 KiB/token` [E] — the `_STYLE.md` constant.
- KV headroom: 80 GB − 54.0 GB weights = 26.0 GB, minus CUDA context/activations,
  call it ~26.0 GB usable [A] → token budget `26.0e9 ÷ 1.31072e5 = 198,368 ≈ 200k
  tokens` [E].
- S=4096 requests: `200k ÷ 4096 = 48.4 ≈ 48 concurrent` [E].
- S=128k requests: `200k ÷ 131072 = 1.51 ≈ 1.6 → "one long context, or ~48 short
  ones"` [E]. One 128k request consumes `131072 × 128 KiB = 16.0 GiB` = 61% of the whole
  KV pool [E: 1.6e10 ÷ 2.6e10] — it *is* the pool, with headroom for ~0.5 more.
- FP8 KV halves the bytes/token (128 → 64 KiB) [E] → pool doubles to `26.0e9 ÷ 65536 =
  396,735 ≈ 400k tokens` [E] → ~97 S=4096 requests [E: 400k/4096], ~3 S=128k [E:
  400k/131072]. GQA already did the same trick architecturally (h_kv=8 vs 64 MHA →
  8× smaller KV; [KV-Cache](../KV-Cache/README.md)).

**Insight.** Throughput ceilings come from FLOPs or bandwidth, but *concurrency* ceilings
come from KV capacity: `requests ≤ KV_pool ÷ S`. A node can be FLOP-rich and bandwidth-
rich yet still be unable to admit request #49 at S=4096. KV bytes are the scarcest
resource in long-context serving — which is why GQA/MLA exist, why FP8/INT8 KV quantization
is the cheapest concurrency doubling, and why KV-aware routing ("balance remaining work,
not requests" — [Load-Balancing](./Load-Balancing.md)) matters once pools are heterogeneous
([Multi-GPU](./Multi-GPU.md)).

**What to actually do.** Before scaling concurrency, compute the KV budget like above and
compare against your expected (requests × typical S) mix; if the mix overshoots, the fix
ladder is: (1) FP8 KV (~2×, near-lossless [A: quality check required per
[Perf-Experiment-Template](./Perf-Experiment-Template.md)]), (2) smaller max-seq-len or
eviction policy (SnapKV/H2O-class), (3) bigger HBM (H200: 141 GB → KV pool ≈ 80 GB →
~610k tokens [E: 80e9 ÷ 1.31072e5] ≈ 149 S=4096 requests [E]), (4) P/D disaggregation so
the decode pool owns the KV pool ([Prefill-Decode-Disaggregation](./Prefill-Decode-Disaggregation.md)).
Watch `gpu_cache_utilization` and the waiting queue in engine metrics
([Diagnostics](./Diagnostics.md) Step 5).

**Failure mode.** The budget assumes *all* requests live at their *maximum* S — real
workloads have a length distribution, so average utilization is lower (continuous
batching fills the pool with shorter sequences, [Continuous-Batching](../Inference/Continuous-Batching.md)).
The math also assumes 100% of "80 GB" is addressable — in practice engine overhead,
fragmentation (paged KV block waste), and activation peaks leave less. And KV is not the
*only* concurrency cap: at S=4096 × B=48 the decode batch is 48 > knee B* ≈ 345? No — 48
is far below B*, so decode is still bandwidth-bound and fine [E: 48 < 345]; the cap is
genuinely KV, not compute. (For a 128k-heavy mix, attention read cost per step also grows
— check ITL, not just capacity.)

---

## Case 4 — TP=8 AllReduce cost: cheap on NVLink, 18× on IB

**Question.** TP=8, BF16, 4096-wide activation per layer. What does the AllReduce traffic
cost per token, on NVLink vs inter-node IB?

**Arithmetic [E].**
- Per-layer activation message: `4096 × 2 B = 8,192 B = 8 KB`.
- Ring AllReduce bytes per rank: `2·(N−1)/N × M = 2·(8−1)/8 × 8 KB = 1.75 × 8,192 =
  14,336 B = 14 KB` [E: ring algorithm, `NCCL.md`] (2 phases, each (N−1)/N of the
  message; N=8 ranks).
- NVLink (~900 GB/s aggregate [F: vendor spec]): `14,336 ÷ 9.0e11 = 1.59e-8 s =
  0.016 µs/layer` [E] → 32 layers × 2 AllReduces/layer would be ~0.98 µs [E:
  32 × 2 × 0.016] (the case statement's "32 layers ≈ 0.5 µs" counts one AllReduce per
  layer [A: 1 of the 2/layer on this stack] → `32 × 0.016 = 0.51 µs` [E]). Against a
  ~16.1 ms decode step (Case 1) that is **0.003%** — negligible [E: 0.5e-6 ÷ 16.1e-3
  = 3e-5]. The ~50 µs-class GEMV per layer dominates by 4–5 orders of magnitude
  [A: kernel time].
- Same 14 KB over IB NDR (~50 GB/s/link [F: vendor spec]): `14,336 ÷ 5.0e10 = 0.287 µs
  /layer` [E] → ~9.2 µs/token (32 layers, one AR/layer) [E: 32 × 0.287] — **18× the
  NVLink cost** [E: 0.287/0.016] and now 0.06% of a 16.1 ms step [E: 9.2e-6 ÷ 16.1e-3
  = 0.00057] — still small at B=1, but no longer free.
- Latency floor: even with zero bandwidth time, each AllReduce pays a round-trip
  latency (~10–20 µs [A: NVLink vs IB per-hop RTT]) per ring hop-set; with 64
  AllReduces/token that is `64 × 10–20 µs = 0.64–1.28 ms` [E] — up to ~8% of a 16.1 ms
  step [E: 1.28e-3 ÷ 16.1e-3] *before any byte moves*. This latency floor is why
  even NVLink TP is not "free" at very high TP or many layers.
- Decode at B=64: message grows to `B·d·b = 64 × 4096 × 2 = 524,288 B` [E]; ring bytes
  `1.75 × 524,288 = 917,504 B` [E] → NVLink `0.9175e6 ÷ 9e11 = 1.02 µs/layer` [E] vs
  IB `18.35 µs/layer` [E] — batched TP AllReduce is ~63× the B=1 traffic [E:
  524288/8192] and the fabric starts to matter.

**Insight.** Intra-node TP AllReduce is cheap because the message is small (activations,
not weights — weights are partitioned, not communicated [Multi-GPU](./Multi-GPU.md),
[Tensor-Parallelism](./Tensor-Parallelism.md)) and NVLink moves 900 GB/s vs HBM's 3.35
TB/s. The cost shows up at (a) inter-node TP over slow fabric (18× [E above]), (b) high
batch (message ∝ B [E]), (c) the latency floor at small messages, and (d) MoE AllToAll
where *all* expert traffic crosses the fabric ([MoE-Expert-Parallelism](./MoE-Expert-Parallelism.md)).
Rule of thumb: **TP lives on NVLink; anything crossing nodes (PP/EP/CP) is a different
cost model** ([Scale-Up-vs-Scale-Out](./Scale-Up-vs-Scale-Out.md),
[Topology](./Topology.md)).

**What to actually do.** If you see NCCL time in the timeline (Nsight Systems;
[Diagnostics](./Diagnostics.md) Step 7): check `nvidia-smi topo -m` — if TP pairs cross
PCIe instead of NVLink, throughput can halve on a wrong path [F: standard practice];
then verify the AllReduce bytes against this ring estimate; if measured ≫ estimate,
topology or fabric contention is the cause, not the collective itself. Keep TP intra-
node; move scale-out to DP/PP/EP with RDMA.

**Failure mode.** The 900 GB/s number is *aggregate* NVLink — a single ring over
NVSwitch is fine, but TP=16+ across two nodes or TP over PCIe (64 GB/s [F]) makes the
0.016 µs become `14,336 ÷ 6.4e10 = 0.22 µs/layer × 32 ≈ 7 µs` [E] — 40× the NVLink
number — and the latency floor (0.64–1.28 ms [E above]) starts to dominate small-message
AllReduces. Also, the estimate ignores overlap: a well-pipelined stack hides AllReduce
under GEMMs, so *measured* ITL delta can be far smaller than the raw comm time —
measure the delta, not just the bytes (WHY gate,
[Perf-Experiment-Template](./Perf-Experiment-Template.md)).

---

## Case 5 — The MoE step: fewer bytes per token at the same total params

**Question.** Mixtral-style MoE: 8 experts, top-2, total 47B params, 12.9B activated
[F: arXiv:2401.04088, Mixtral 8×7B]. Why does MoE decode faster than a dense model with
the same total params, and what are the per-token activated bytes?

**Arithmetic [E].**
- Decompose 47B total: shared (attention/embeddings/norms/router) + 8 experts. Shared
  ≈ 1.6B [A: attention ~12.9B−... standard Mixtral split: 12.9B activated = shared +
  2 experts; total 47B ⇒ experts = 47 − 1.6 = 45.4B ⇒ expert = 5.67B; activated =
  1.6 + 2×5.67 = 12.94B ✓] [E: consistency check 1.6 + 2×(45.4/8) = 12.9B].
- **Dense 47B per-token activated bytes (BF16):** every param on every token →
  `47e9 × 2 B = 9.4e10 B = 94.0 GB` [E]. B=1 ceiling `3.35e12 ÷ 9.4e10 = 35.6 tok/s`
  [E].
- **MoE per-token activated bytes (BF16):** only shared + 2 experts →
  `12.9e9 × 2 B = 2.58e10 B = 25.8 GB` [E]. B=1 ceiling `3.35e12 ÷ 2.58e10 =
  129.8 tok/s` [E] → **3.64× the dense ceiling** [E: 94.0/25.8].
- FFN-only view (the clearest contrast): dense FFN per token streams the full MLP
  (~3×d×d_ff×2 B ≈ 90 GB-class for a 47B [A: order-of-magnitude]); MoE streams 2/8 of
  the expert FFN → `1/4` of the FFN bytes [E: 2/8 = 0.25] → total-token bytes ≈
  shared + 0.25·FFN, versus shared + 1.0·FFN for dense [I: the "≈ 2/8 of the FFN bytes"
  of the task statement].
- All 47B params must still *fit in memory* (94 GB across the GPUs, or quantized);
  only the *activated* 12.9B stream per token. Memory capacity and bandwidth are
  different budgets — MoE trades capacity for bandwidth [I].
- At B=1 the decode ceiling is 129.8 vs 35.6 tok/s [E above] — but only if the 2 active
  experts are local; if experts are sharded across GPUs (EP), the AllToAll dispatch
  adds fabric cost ([MoE-Expert-Parallelism](./MoE-Expert-Parallelism.md)): dispatch
  `2 × d × 2 B` per active expert + combine, over the fabric bandwidth (Case 4's
  IB/NVLink numbers).

**Insight.** MoE is a **sparsity escape** from the dense bandwidth ceiling: the same
total-param model moves 2.5–4× fewer bytes per token [E: 25.8 vs 94 GB], so the
bandwidth-bound decode ceiling rises proportionally [E: 3.6×]. This is why "activated
params," not "total params," is the number that sets decode speed for MoE — and why MoE
serving is a *networking* problem at scale (expert placement, imbalance, hot experts,
capacity factors, [MoE-Expert-Parallelism](./MoE-Expert-Parallelism.md)).

**What to actually do.** (1) Confirm the regime: decode of an MoE model with experts
on-GPU should show HBM-BW-bound behavior at a ceiling ≈ `BW ÷ activated_bytes`, not
`BW ÷ total_bytes` — measure achieved tok/s against 129.8 (BF16, B=1, one-GPU-class
capacity) and check the gap [A: real stacks lose 10–30% to dispatch + imbalance].
(2) If experts don't fit on one GPU, EP is the lever — but check AllToAll cost against
the fabric before promising the 3.6× [E: Case 4's per-byte numbers × expert traffic].
(3) Quantize experts (W8/W4) — bytes/token falls again, ceiling rises again
([Perf-Experiment-Template](./Perf-Experiment-Template.md) for the quality check on
expert quant).

**Failure mode.** The 3.6× assumes the 2 active experts are *local and bandwidth-cheap*.
In practice: (a) **expert imbalance** — a skewed router sends more tokens to "hot"
experts, so the *effective* activated bytes exceed 2/8 and some GPUs idle while hot
experts queue (capacity factor > 1, [MoE-Expert-Parallelism](./MoE-Expert-Parallelism.md));
(b) **EP AllToAll** — dispatch+combine over IB NDR is `~115 KB/token` one-way ×2 [E:
cf. Bandwidth-vs-Compute MoE example] ≈ 4.6 µs/token [E] — small at B=1 but at B=64 it
is `64 × 229 KB ≈ 14.7 MB` → `14.7e6 ÷ 5.0e10 = 294 µs` [E] of fabric time, now a real
fraction of the step; (c) **memory** — 47B BF16 = 94 GB won't fit on one H100 at all,
so "MoE decodes faster" is moot without a placement plan; the *total* param count still
sets the capacity budget. The simple "activated bytes" math breaks exactly when the
*placement* stops being local.

---

## Case 6 — A P/D decision: co-locate or split?

**Question.** 6.5B-class, S=4096, B=64 decode, running on the same 8-GPU node as
prefill (TP=8). Does co-locating prefill and decode hurt, and what is the KV transfer
cost if we split?

**Arithmetic [E].**
- **Decode step (baseline):** TP=8, BF16, per-GPU weight `54.0/8 = 6.75 GB` [E]; B=64
  decode step streams `6.75e9 B` per GPU → `6.75e9 ÷ 3.35e12 = 2.02 ms` [E] per step,
  plus KV read (B=64 × 4096 tokens × 128 KiB ÷ 8 GPUs = 4.29e9 B/GPU [E:
  64×4096×1.31072e5/8] → 1.28 ms [E]) → **≈ 3.3 ms/step baseline** [E: 2.02 + 1.28].
- **Co-location interference — prefill spike:** a single S=4096 prefill on TP=8 takes
  `0.36 s ÷ 8 = 44.9 ms` [E: Case 2 at 45% MFU, /8 GPUs]. If it runs *on the same
  SMs as decode steps* (no preemption, no chunking), it **stalls the decode for ~45 ms**
  → that is `44.9 ÷ 3.3 = 13.6×` one decode step's time [E] — or, if the engine
  *preempts* decode to serve prefill, the decode ITL for that step is ~45 ms vs the
  3.3 ms baseline → **P99 ITL inflates ~14–22×** [E: 45/3.3 ≈ 13.6×; with launch +
  KV-write overhead, ~22× is the order]. This is the "prefill steals SMs from decode"
  cost — the resource isolation argument of
  [Prefill-Decode-Disaggregation](./Prefill-Decode-Disaggregation.md).
- **KV steal (capacity):** co-located prefill also *holds* KV for its prompt while
  decode steps run: `4096 × 128 KiB = 0.5 GiB` [E] per in-flight prefill = 2.07% of
  the 24 GB decode-pool KV budget [E: 0.5/24] — small per request, but with 8
  concurrent prefills it is 16.5% [E: 8 × 2.07] — real but secondary vs the SM stall.
- **Split P/D — KV transfer cost:** S=4096 KV = `4096 × 131,072 B = 5.37e8 B = 0.5 GiB`
  [E] (same 128 KiB/token, Case 3).
  - Over NVLink (~900 GB/s): `5.37e8 ÷ 9.0e11 = 0.597 ms ≈ 0.6 ms` [E].
  - Over IB NDR RDMA (~50 GB/s/link): `5.37e8 ÷ 5.0e10 = 10.74 ms ≈ 10.7 ms` [E]
    — **18× the NVLink cost** [E: 10.7/0.6], and now a real fraction of TTFT
    (`10.7 ms` is `5.3×` the 2.02 ms decode step [E] and `~23%` of the 45 ms prefill
    time [E: 10.7/45] — the transfer is no longer free).
  - Over PCIe 5.0 x16 (~64 GB/s [F]): `5.37e8 ÷ 6.4e10 = 8.4 ms` [E] — between the
    two, still too slow for a low-latency SLO.
- **When transfer dominates:** at S=128k, KV = `131072 × 131072 B = 1.6e10 B = 16.0
  GiB` [E] → NVLink `1.6e10 ÷ 9e11 = 17.8 ms` [E] vs RDMA `1.6e10 ÷ 5e10 = 320 ms`
  [E] — at long context the KV transfer *is* the latency component, not an overhead.

**Insight.** Co-locating P and D is a **resource contention** problem (prefill steals
SMs and KV from decode → ITL tail), not a compute problem: the prefill is faster in
isolation, but its *arrival* spikes the decode P99. Splitting P/D pays a **KV transfer**
that is *small on NVLink* (0.6 ms ≈ 30% of one decode step [E: 0.6/2.0]) but *large on
RDMA* (10.7 ms ≈ 5.3 decode steps [E]) — the split is only worth it when the
interference cost exceeds the transfer cost, and the transfer cost is set by the fabric,
not the model. This is exactly why [P/D disaggregation](./Prefill-Decode-Disaggregation.md)
is a *communication* decision first, and why DistServe/Mooncake (arXiv:2401.09670,
2407.00079 [F]) engineer the KV transfer path (GPUDirect, hierarchical placement)
rather than just the scheduling.

**What to actually do.** (1) Measure the interference: log ITL P50 vs P99 on a co-located
box under a prefill-heavy load; if P99/P50 > ~3× and prefill arrival correlates with the
spikes, the contention is confirmed ([Diagnostics](./Diagnostics.md) Step 5/6: KV
utilization + scheduler behavior). (2) Try chunked prefill first (co-schedule prefill in
chunks ≤ ~1–2 decode-step durations [A: ~2–4 ms each] to cap the ITL spike) — cheaper
than a full P/D split. (3) If the SLO is strict and prefill volume is high, split P/D
*and* put the KV transfer on NVLink/NVL72 or a fast RDMA fabric — the 0.6 ms vs 10.7 ms
[E above] gap is the entire argument for where to put the decode pool. (4) For
long-context (S > 128k), quantize KV to FP8 (halves the transfer [E]) or accept the
transfer as a TTFT component (budget it explicitly).

**Failure mode.** The 0.6 ms NVLink transfer assumes **zero contention and no
GPUDirect inefficiency** — real P/D transfers share NVLink with TP collectives (Case 4)
and with other P/D pairs on the same switch; a burst of 8 concurrent S=4096 transfers
over one 900 GB/s link is `8 × 0.5 GiB / 900 GB/s = 4.8 ms` [E: aggregate] — the
*aggregate* transfer time is 8× the single-pair number. Also: the "0.5 GiB KV" is the
*prompt* KV; if the decode pool continues generation, the *full* sequence KV grows, and
the transfer grows with S² at the decode side (attention read, not just write) —
the simple "transfer = S × 128 KiB" is the *prompt* cost, not the *lifecycle* cost.
Finally: if the fabric is PCIe-only (no NVLink, no RDMA), the P/D split is a *net
regression* (8.4 ms transfer [E] vs ~14× ITL spike [E] — the math flips; co-locate and
chunk instead).

---

## Case 7 — The "add a GPU" decision: walking the Diagnostics tree

**Question.** A serving box is at the ITL SLO edge. Should you: (a) add GPUs (DP/TP),
(b) quantize, (c) P/D split, or (d) do nothing (it's scheduler-bound)? Walk the
[Diagnostics](./Diagnostics.md) tree on each and show the numbers that distinguish
them.

**Setup [A: worked example, 6.5B-class, H100 SXM].** B=64 decode, S=4096, TP=8, BF16
weights 54 GB [A: same as Case 6]. Baseline step time (Case 6 arithmetic):
`6.75e9 B ÷ 3.35e12 = 2.02 ms` (weights) + `1.28 ms` (KV read) + `~0.001 ms` (NCCL,
Case 4) ≈ **3.3 ms/step → ~300 tok/s aggregate throughput** [E: 64 tokens / 3.3 ms =
19.4k tokens/s; per-request 300 tok/s [E: 1/3.3ms]]. Suppose the SLO is **ITL P50 ≤
30 ms** (a 6.5B at B=64 should be far under this; the SLO edge means something else is
going on [I]).

**Step 0 — Is it even a GPU problem?**
Check host CPU, scheduler queue depth, API-server latency [F: standard practice,
Diagnostics Step 0]. *Distinguishing number:* if GPU util% is low (< 50%) under load
while requests are queued → **it's the scheduler** (branch d). *What to actually do:*
fix the admission policy (continuous batching, chunked prefill, KV-aware routing,
[Load-Balancing](./Load-Balancing.md)) — no GPU spend. *Failure mode:* assuming "add a
GPU" when the bottleneck is a single-threaded Python scheduler — you buy idle GPUs
([Diagnostics](./Diagnostics.md) "Throughput low → add more GPUs" misdiagnosis).

**Step 1 — GPU busy or idle?**
`nvidia-smi` util% over time. If ~90%+ → go to Steps 2–8 (the GPU is doing real work).
If oscillating with gaps → Step 4 (launch-bound). *Distinguishing number:* sustained
util% > 80% with ITL at SLO edge ⇒ the GPU is the bottleneck, not the host.

**Step 2 — Compute-bound?**
Nsight Compute: `pipe_tensor` util high, `dram__throughput` low → compute roof.
*Distinguishing number:* achieved FLOP/s vs 989 TFLOP [F: vendor spec]. If
achieved < 50% of 989 (e.g., 400 TFLOP) with Tensor Cores busy → the GEMMs are not
hitting peak (bad kernel, no FlashAttention, or BF16 on FP8-capable HW). *What to
actually do:* FP8/FP4 weights, FlashAttention, better GEMM kernels
([Custom-GEMM](./Custom-GEMM.md)). *Numbers:* FP8 halves weight bytes (54 → 27 GB [E])
*and* doubles FLOPS (989 → 1978 TFLOP [F: vendor spec]) → the knee batch B* is
unchanged [E: Bandwidth-vs-Compute E3 dtype invariance] but the *rate* on both roofs
lifts. *Failure mode:* "compute-bound" at B=64 for a 6.5B is *unlikely* — the GEMMs are
`[64,4096]×[4096,4096]`, AI ≈ 64×2/2 = 64 [E: 2B·d/(2B·b+b_w·d) ≈ 64 at B=64, BF16]
< ridge 295 [E] → still memory-bound; if Nsight says compute-bound at B=64, suspect a
*bad kernel* (large-M cuBLAS picked for M=64) rather than a regime.

**Step 3 — Memory-bandwidth-bound?**
`dram__throughput` near 3.35 TB/s, SM% low → the classic decode regime [A: typical
signature]. *Distinguishing number:* bytes/token vs Case 1 ceiling. At B=64, the weight
stream is amortized across the batch: effective bytes/token = `54 GB / 64 = 0.844 GB`
[E] + KV `4096×128 KiB / 64 = 8 MiB` [E] → `≈ 0.852 GB/token`. The **aggregate**
bandwidth ceiling is therefore `3.35e12 ÷ 0.852e9 ≈ 3931` tokens per HBM-pass [E] — i.e.
the whole B=64 batch (~3931 tokens) fits under ~0.9 s of HBM time, far above the ~19.4k
tokens/s we see (64 tokens every 3.3 ms) [E: 64/3.3ms] → we are well below the
bandwidth ceiling, so the limit is *not* raw HBM bandwidth. *What to actually do:* if
`dram__throughput` were *saturated* at ~3.35 TB/s, quantize (INT8 → bytes/token halves)
or raise batch; here the low SM% + low DRAM% says we're **latency/launch-bound at B=64**
→ see Step 4 (CUDA Graphs) before touching bandwidth.
*Failure mode:* "bandwidth-bound → quantize" when the GEMV kernel is bad (strided
access, M=64 kernel not tuned) — quantizing a bad kernel still leaves it bad
([Diagnostics](./Diagnostics.md) "Bandwidth-bound → quantize" caveat); check
bytes/s per kernel in Nsight before assuming the dtype is the problem.

**Step 4 — Kernel-launch-bound?**
Nsight Systems: many small kernels, gaps between them, SM% low *and* DRAM% low →
launch-bound [A: typical low-batch signature]. *Distinguishing number:* kernels-per-step
× launch overhead. At B=64, ~300–500 kernels/step [A: ~10/layer × 32 layers +
fused-attention] × 4 µs [A] = 1.2–2.0 ms [E] — that is **36–60% of a 3.3 ms step**
[E: 2.0/3.3] → launch is now the dominant cost, not HBM. *What to actually do:*
CUDA Graphs (capture the step → one replay), kernel fusion ([Fused-Kernels](./Fused-Kernels.md)),
raise batch. *Numbers:* CUDA Graphs cut launch to ~50–100 µs/step [A: graph replay
overhead] → step time `3.3 − 1.5 ≈ 1.8 ms` [E: removing ~1.5 ms of launch] →
throughput `64/1.8ms = 35.6k tok/s` [E] vs baseline 19.4k [E] → **1.83× throughput**
[E: 1.83 = 3.3/1.8]. *Failure mode:* CUDA Graphs at *variable* batch size (continuous
batching changes B every step) require graph re-capture or padding — a naive "one graph
per step" breaks at dynamic B; check the engine's graph management (vLLM/SGLang both
handle this, but verify [I]).

**Step 5 — KV-cache-limited?**
Engine metrics: KV block utilization pinned high, waiting queue growing, forced
eviction [F: vLLM/SGLang metrics]. *Distinguishing number:* Case 3 pool. At B=64,
S=4096: `64 × 4096 = 262,144 tokens` [E] vs pool `~200k` [E: Case 3] → **we are
*over* the pool** [E: 262k > 200k] → the scheduler *cannot* admit B=64 at S=4096
without eviction or preemption. This is the real SLO edge: **KV capacity, not
bandwidth, is the binding constraint** [I: the numbers flip the diagnosis]. *What to
actually do:* (1) FP8 KV → pool `400k` [E: Case 3] → B=64 fits with headroom
[E: 262k < 400k]; (2) smaller max-seq-len or eviction; (3) bigger HBM; (4) P/D
disaggregation (decode pool owns KV, Case 6). *Failure mode:* "KV-limited → more HBM"
when the real issue is *admission policy* (admitting long sequences that evict short
ones) — fix the scheduler (Step 6) before buying HBM.

**Step 6 — Scheduler-limited?**
Running batch ≪ max, poor packing, prefill blocking decode [F: engine metrics].
*Distinguishing number:* num running seqs vs max-num-seqs. If running = 40 but max = 64
→ 37% of capacity idle [E: (64−40)/64] → the scheduler is not filling. *What to
actually do:* continuous batching (iteration-level admission), chunked prefill,
KV-aware admission ([Load-Balancing](./Load-Balancing.md)). *Numbers:* filling 40 → 64
[E] → throughput `64/40 = 1.6×` [E] at no hardware cost. *Failure mode:* "scheduler-
limited" when the *real* limit is KV (Step 5) — filling the batch to 64 at S=4096
*requires* 262k tokens [E] which the 200k pool cannot hold [E: Case 3] → the scheduler
*cannot* fill the batch because of KV, not policy; the two steps interact, and the
*binding* constraint is the one with the tighter number (KV here [I]).

**Step 7 — Network-limited?**
NCCL kernels dominate the timeline, cross-node TP [F: Nsight + NCCL logs].
*Distinguishing number:* Case 4. At TP=8, B=64: AllReduce `18.35 µs/layer × 32 =
0.59 ms` [E: Case 4 IB number] vs step 3.3 ms [E] → 18% of the step [E: 0.59/3.3] →
*if* on IB, the fabric is a real cost; on NVLink it is `1.02 µs/layer × 32 = 0.033 ms`
[E] → 1% [E: 0.033/3.3] → negligible. *What to actually do:* move TP intra-node
(NVLink), overlap comm with compute, or lower TP / mix in PP ([Multi-GPU](./Multi-GPU.md),
[Topology](./Topology.md)). *Failure mode:* "add a GPU (TP=16)" when the fabric is PCIe
— TP=16 over PCIe is `14,336 ÷ 6.4e10 × 32 × 2 = 5.7 µs` [E: per-layer, one AR/layer]
→ `5.7 µs × 32 = 0.18 ms` [E] → 5.5% of the step [E: 0.18/3.3] — worse than TP=8 on
NVLink (0.033 ms [E]) by 5.5× [E: 0.18/0.033] → *more GPUs on a slow fabric is a
regression*, not a fix.

**Step 8 — Storage-limited?**
Slow model load, checkpoint thrash, offload [F: DCGM PCIe counters]. *Distinguishing
number:* time-to-steady-state after restart. If the SLO edge is *intermittent* and
correlates with restarts / checkpoint saves → storage, not steady-state. *What to
actually do:* pinned H2D, faster NVMe, keep weights hot ([Multi-Node](./Multi-Node.md)).
*Failure mode:* "storage-limited" in steady-state serving is *rare* for a 6.5B (54 GB
fits in HBM [E]); if the model is offloaded, the step time balloons by the PCIe round-
trip (`54 GB ÷ 64 GB/s ≈ 0.84 s` [E: one full weight pass over PCIe] — vs 2.02 ms
[E: Case 6] → 415× [E: 0.84/0.00202] slower) — the SLO edge is not a "tuning" problem,
it is a *placement* problem.

**The four candidate answers, distinguished by numbers [I: synthesis]:**

| Option | When the numbers say "yes" | Distinguishing number |
|---|---|---|
| **(d) Do nothing (scheduler-bound)** | Step 0/6: GPU util < 50%, batch ≪ max, host CPU hot | running/max < 0.7 [E: 40/64]; host CPU > 80% |
| **(b) Quantize** | Step 3/5: DRAM near peak, bytes/token > ceiling, KV over pool | bytes/token vs ceiling [E: Case 1/6]; KV pool vs needed tokens [E: 200k vs 262k] |
| **(a) Add GPUs (DP/TP)** | Step 2/7: compute roof *or* comm roof is the binding constraint, *and* the fabric is fast | achieved FLOP/s vs 989 [E]; NCCL fraction of step [E: Case 4] |
| **(c) P/D split** | Step 5 + Case 6: KV is the cap *and* prefill interference spikes ITL P99 | P99/P50 ITL > 3× [E: Case 6]; KV pool vs S mix [E: Case 3] |

**What to actually do (the walk).** Run the tree *in order* (Step 0 → 8), logging the
*distinguishing number* at each branch ([Perf-Experiment-Template](./Perf-Experiment-Template.md):
one variable, pinned config, WHY gate). The answer is the *first* step whose number
crosses its threshold — not "do all four." For the worked 6.5B/B=64/S=4096 box:
- Step 0/6: if batch is 40/64 [E] → **fix the scheduler first** (free, 1.6× [E]).
- Step 5: if KV is 262k/200k [E] → **quantize KV to FP8** (pool → 400k [E], B=64
  fits [E]) — *before* buying HBM or splitting P/D.
- Step 3: if DRAM is near peak and weights are BF16 → **quantize weights to INT8**
  (aggregate ceiling ≈ 3931 → ≈ 7862 tokens/HBM-pass [E: Case 7 step 3]).
- Step 7: if TP is on PCIe → **move to NVLink or DP** (TP=8 PCIe → 0.18 ms [E] vs
  NVLink 0.033 ms [E]; DP=2 on NVLink removes the cross-node AllReduce entirely [I]).
- Step 2: only if the above are done *and* Tensor Cores are the binding constraint →
  **add GPUs for prefill** (TP=16 on NVLink, or a dedicated prefill pool, Case 6).
- **(c) P/D split** is the *last* lever, not the first: it costs 0.6 ms (NVLink) or
  10.7 ms (RDMA) per request [E: Case 6] and is only worth it when prefill interference
  (P99/P50 > 3× [E]) *and* KV capacity are *both* the binding constraints *and* the
  fabric is fast enough that the transfer is < ~10% of the step [E: 0.6/3.3 = 18%
  [E: NVLink] — borderline; 10.7/3.3 = 324% [E: RDMA] — *not worth it*].

**Failure mode (the whole case).** The "add a GPU" reflex is *wrong* in most of these
branches: (a) adding GPUs when the bottleneck is the scheduler (Step 0/6) buys idle
GPUs; (b) adding GPUs when the bottleneck is KV (Step 5) does *not* add KV (DP
replicates the KV pool, but the *per-request* KV is unchanged [I] — more DP shards means
more *total* KV, but each shard still holds its own 200k [E] → the *admission* limit
per shard is unchanged unless the router balances); (c) adding GPUs over a slow fabric
(Step 7) makes the comm cost *worse* per token (Case 4: 18× [E] on IB); (d) P/D split
over RDMA (Case 6: 10.7 ms [E]) is a *regression* for a 3.3 ms step [E: 324% [E]] —
the split is a *communication* decision, and the fabric decides whether it is a fix or
a trap. The Diagnostics tree exists to prevent exactly this reflex: *find the layer,
then fix the layer, then re-run the tree* ([Cross-Layer-Optimization](./Cross-Layer-Optimization.md)).

---

## Cross-case synthesis: the four resources, four levers

| Case | Bottleneck resource | Ceiling number [E] | Lever | Cross-link |
|---|---|---|---|---|
| 1 (B=1 decode) | HBM bandwidth | 62 tok/s (BF16) → 124 (INT8) | quantize weights, batch | [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md), [GEMM](./GEMM.md) |
| 2 (Prefill) | Tensor Core FLOPS | 0.36 s @ S=4096 (45% MFU) | FP8/FP4, FlashAttention, TP | [GEMM](./GEMM.md), [FlashAttention](./FlashAttention.md) |
| 3 (KV concurrency) | HBM capacity | ~48 S=4096 reqs (200k tokens) | FP8 KV, bigger HBM, P/D | [KV-Cache](../KV-Cache/README.md), [P/D](./Prefill-Decode-Disaggregation.md) |
| 4 (TP=8 AllReduce) | Fabric (NVLink/IB) | 0.5 µs/token (NVLink) vs 9.2 µs (IB) | keep TP intra-node, overlap | [Multi-GPU](./Multi-GPU.md), [NCCL](./NCCL.md), [Topology](./Topology.md) |
| 5 (MoE) | Activated bytes/token | 25.8 GB vs 94 GB dense → 3.6× ceiling | expert placement, EP, quant | [MoE-EP](./MoE-Expert-Parallelism.md) |
| 6 (P/D decision) | SM contention + KV transfer | 0.6 ms (NVLink) vs 10.7 ms (RDMA) | chunked prefill, P/D split, fast fabric | [P/D](./Prefill-Decode-Disaggregation.md), [Load-Balancing](./Load-Balancing.md) |
| 7 (Add a GPU?) | *whichever the tree finds* | (see distinguishing numbers) | the first failing step's lever | [Diagnostics](./Diagnostics.md), [Perf-Experiment](./Perf-Experiment-Template.md) |

## Related
[Roofline](../Inference/Roofline.md) (the ceiling model) · [Bandwidth-vs-Compute](./Bandwidth-vs-Compute.md)
(the regime split) · [GEMM](./GEMM.md) (M is the regime switch) · [KV-Cache](../KV-Cache/README.md)
(the `2·L·B·h_kv·d_h·S·b` budget) · [Multi-GPU](./Multi-GPU.md) + [NCCL](./NCCL.md) +
[Topology](./Topology.md) (fabric costs) · [MoE-Expert-Parallelism](./MoE-Expert-Parallelism.md)
(AllToAll) · [Prefill-Decode-Disaggregation](./Prefill-Decode-Disaggregation.md) (the P/D
decision) · [Diagnostics](./Diagnostics.md) (the decision tree Case 7 walks) ·
[Perf-Experiment-Template](./Perf-Experiment-Template.md) (how to verify any number here) ·
[Cross-Layer-Optimization](./Cross-Layer-Optimization.md) (the "next limiting resource"
method) · [Load-Balancing](./Load-Balancing.md) (KV-aware routing) ·
[FlashAttention](./FlashAttention.md) (the S² term in Case 2) ·
[../Continuous-Batching](../Inference/Continuous-Batching.md) (B* and amortization).

## Key Takeaways
1. **Every ceiling is a ratio:** `BW ÷ bytes` (decode), `FLOPs ÷ S` (prefill), `KV_pool ÷
   S` (concurrency), `bytes ÷ fabric_BW` (collectives, P/D transfer). Find the ratio,
   find the lever.
2. **The four resources are separable:** FLOPS (prefill), bandwidth (decode), capacity
   (KV), fabric (TP/P/D) — a "bad box" is bad on *exactly one* at a time; the
   [Diagnostics](./Diagnostics.md) tree finds which.
3. **Quantization is the cheapest lever on the memory roof:** INT8 halves bytes/token
   [E] → doubles the decode ceiling [E: Case 1] with no topology change; FP8 KV doubles
   the concurrency pool [E: Case 3].
4. **Fabric decides P/D and TP:** 0.6 ms (NVLink) vs 10.7 ms (RDMA) [E: Case 6] is the
   entire argument for where to put the decode pool; TP=8 on PCIe is 18× slower than on
   NVLink [E: Case 4] — the same 14 KB message.
5. **MoE breaks the "total params" heuristic:** activated bytes, not total bytes, set
   the decode ceiling [E: 25.8 vs 94 GB, 3.6× Case 5] — but only when experts are
   *local*; EP AllToAll re-introduces the fabric cost.
6. **"Add a GPU" is the last answer, not the first:** walk the tree
   ([Diagnostics](./Diagnostics.md)) and fix the *first* failing step; adding GPUs to a
   scheduler-bound or KV-bound box buys idle silicon (Case 7).
7. **Reproduce before you rely:** every [E] here is hand-derived; every [A] is an
   assumption to measure ([Perf-Experiment-Template](./Perf-Experiment-Template.md)).
   The mechanism must be *visible* in GPU metrics or the delta is suspect.
