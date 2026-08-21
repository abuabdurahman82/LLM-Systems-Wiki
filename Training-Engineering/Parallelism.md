# Parallelism — splitting one model across many GPUs

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of `Training-Engineering/`

> The question: a step of a 70B model doesn't fit on one GPU, and even if
> it did, one GPU is too slow. How do you split (model, activations, batch,
> optimizer state) across 8 → 8,000 GPUs so the *step* is fast and the
> *cluster* stays busy? Answer: a product of independent split axes,
> each with its own communication pattern. This page is the catalog +
> the math; `Networking/` is the fabric side.

## 30-second explanation

Every parallelism axis answers one question: **what does a single GPU
hold, and what does it send to its neighbors each step?**

| Axis | Splits | Holds per GPU | Comm per step | Fabric needed |
|---|---|---|---|---|
| **DP** (data) | batch | full model copy | AllReduce(grads) | any (slow ok) |
| **TP** (tensor) | a layer's matrices | model slice | 2× AllReduce/layer | **fast** (NVLink) |
| **PP** (pipeline) | layers | layer range | P2P activations | medium |
| **EP** (expert) | MoE experts | expert subset | AllToAll ×2 | fast (RDMA/NVLink) |
| **SP/CP** (seq) | sequence | token range | AllToAll / ring | fast |
| **ZeRO/FSDP** | optimizer state (over DP) | shard | AllGather/ReduceScatter | any, BW-bound |

Real runs compose: **DP × TP(intra-node) × PP(cross-node) × EP(MoE)
× SP(long-context)** with ZeRO-1/2/3 layered on DP [I: standard;
the Megatron/DeepSpeed
lineage (ids: Megatron-LM `1909.08053` [F]; the 3D-parallelism
paper and DeepSpeed OSDI'20 ids are UNVERIFIED this session — see
the references block) are the two reference frameworks].

## The memory equation (why you need any of this)

Per-GPU memory for one step, batch B, sequence S, hidden d, layers L,
heads h, BF16, AdamW:

```
P      params (BF16)          2·N
G      gradients              2·N
O      Adam state (FP32 m+v + master)  8·N        (12·N total for P+G+O)
A      activations (no recompute)  2·(34L + 48h)·B·S·d / n_shard
```

**[E] Verified in Python** (audit in `/tmp/te-research/audit.py`):
LLaMA-7B (N=6.7e9, L=32, h=32, d=4096), B=1, S=2048, no sharding:
- P+G+O = 12 × 6.7e9 B = **80.4 GB**
- A = 2·(34·32 + 48·32)·1·2048·4096 = **44.0 GB**
- **total ≈ 124 GB** → does *not* fit in one 80 GB H100. [E]
⇒ **even 7B needs ZeRO/checkpointing at S=2048.** Every axis below
is a way to shrink one of these terms.

### Activation checkpointing (the cheap first lever)
Recompute attention/FFN activations in backward instead of storing
them → A drops from O(L) to O(√L) at the cost of ~1/3 extra forward
FLOPs [F: Korthikanti et al. 2205.05198, "Reducing Activation
Recomputation in Large Transformer Models"]. [E] For 7B B=1 S=2048:
A goes 44.0 GB → ~4–8 GB (selective recompute) → total model+activations
≈ 33.5 GB (ZeRO-1) + 4–8 GB = **~38–42 GB**, which *fits comfortably*
in one 80GB H100. This is why "full recompute" is the default at scale
(for bigger S or B where 44 GB of activations alone blows the budget).

## The axes, one by one

### DP — data parallelism
- Split: the *batch*. Each GPU holds the full model, sees B/n_dp
  examples, computes local grads.
- Comm: **AllReduce of gradients** each step — 2×(n−1)/n of the
  gradient bytes move per ring step, ×2 (forward of ring allreduce:
  reduce-scatter + allgather) [I: standard NCCL accounting].
- Bytes/step ≈ **2·G_bytes · 2(n−1)/n** ≈ **4·N bytes** (BF16 grads,
  n≫1). [E] 7B: 4 × 6.7e9 ≈ 27 GB/step of gradient traffic — trivial
  on NVLink (900 GB/s), painful across 400G IB (50 GB/s → ~0.54 s/step
  just for the AllReduce at n=8 nodes [E: 27e9/50e9 = 0.54 s]).
- **DP scales nearly linearly in FLOPs** (more batch = more useful
  work) but *linearly in comm* too. Past ~1–2k GPUs, grad AllReduce
  dominates → introduce ZeRO.

### ZeRO / FSDP — shard the optimizer state
ZeRO (Rajbhandari et al. [F: 1910.02054, verified 2026-08-20;
also ZeRO-Infinity 2104.07857 [F, verified]]), FSDP (PyTorch
[I: torch.distributed.fsdp; the OSDI'23 paper id is UNVERIFIED
this session]):
- **ZeRO-1**: shard Adam state only → per-GPU memory
  `4N + 8N/n` bytes (2N BF16 params + 2N BF16 grads +
  sharded FP32 Adam state), vs `12N` full. For 7B
  (N = 6.7e9 params): full = 12 × 6.7e9 B = **80.4 GB**
  [E]; ZeRO-1 at n=8: `4N + N = 5N` = 5 × 6.7e9 B
  ≈ **33.5 GB** [E: 2·6.7e9 + 2·6.7e9 + 8·6.7e9/8] —
  i.e. ZeRO-1 alone makes 7B fit on a single 8×80GB node.
  [I: 4 B/param for params+grads (BF16), 8 B/param for the
  unsharded Adam terms (FP32 m + v + master weight).]
- **ZeRO-2**: + shard gradients → per-GPU `2N (params) + 2N/n
  (grads) + 8N/n (Adam)` = `2N + 10N/n` bytes [E: at n=8 =
  2N + 1.25N = 3.25N ≈ 21.8 GB → 7B + activations fits with
  room to spare].
- **ZeRO-3 / FSDP**: + shard parameters → per-GPU `12N/n`
  [E: at n=8 = 1.5N ≈ 10 GB] — every param is AllGathered
  just-in-time for its layer's forward/backward, then
  discarded.
- Comm: ZeRO-3 ≈ **1.5× plain-DP grad AllReduce** in net received
  data [E: plain DP receives ≈2·(n−1)/n·M ≈ 280 GB at 70B; ZeRO-3
  additionally AllGathers params in *both* fwd and bwd, 2 × 140 GB
  = 280 GB more, so ≈420 GB total received/GPU vs 280 GB for plain
  DP = 1.5×]. Each param AllGather is small and *layer-overlap-able*.
  The ZeRO paper's headline "1.5× the DP communication volume"
  [F: 1910.02054] matches this net-data accounting. (In raw ring
  wire-traffic terms the figure is ~2× larger, ≈560 GB, because each
  byte traverses the ring ~(n−1) hops.)
- **[I] Practice rule:** ZeRO-1 fits ~16B, ZeRO-2 ~24B, ZeRO-3
  ~53B on 8×80GB (ignoring activations) [E: 12N/n vs 4N+8N/n etc.];
  in practice with activations, ZeRO-3/FSDP is the workhorse for
  70B–700B, and ZeRO-3 + offload (ZeRO-Infinity, 2104.07857 [F])
  when even sharding doesn't fit.

### TP — tensor parallelism
Megatron-LM (Sho et al. [F: 1909.08053, verified]; the
3D-parallelism/"1F1B" paper, arXiv id UNVERIFIED this session —
see references):
- Split: the *width* of a layer. Column-parallel: split QKV/FFN-up
  along output (each GPU holds 1/n of W_q, 1/n of experts' W1/W3).
  Row-parallel: split out-proj/FFN-down along input; combine with
  AllReduce.
- **Attention** (Megatron split): QKV column-parallel (n heads/GPU),
  softmax + AV inside each head, out-proj row-parallel → **1 AllReduce
  after attention** per layer.
- **FFN (SwiGLU)**: W1, W3 column-parallel; W2 row-parallel → **1
  AllReduce after FFN** per layer.
- **Total: 2 AllReduce/layer/step** (fwd + bwd each → ×2 →
  4 AllReduce/layer counting bwd) [I: Megatron-1/2 accounting].
- Bytes/layer ≈ 4·(B·S·d)·(fwd) + bwd ≈ 8·B·S·d bytes per
  AllReduce pair [E: per-GPU view]. For 7B B=1 S=2048 d=4096:
  8·2048·4096 ≈ 67 MB/layer — trivial on NVLink, which is why
  **TP lives inside the NVLink domain** (≤ 8 GPUs for H100;
  ≤ 72 for NVL72) [I: standard].
- **TP does not scale across nodes**: 4 AllReduce/layer (fwd + bwd,
  attention + FFN) × L layers. Each AllReduce moves ~134 MB
  (S=4096, d=8192, 2·(n−1)/n·S·d·2B [E]) → transfer ≈ 134e6/50e9
  = 2.7 ms per AllReduce on IB, vs 134e6/900e9 = 0.15 ms on NVLink
  [E]. For a 70B model (80 layers): 320 AllReduces/step →
  **inter-node ≈ 320 × 2.7 ms ≈ 0.86 s/step** [E] vs ~0.4 s
  compute — i.e. *comm exceeds compute*. Intra-node (NVLink):
  320 × 0.15 ms ≈ 0.05 s/step ≈ 12% of compute. [I: bandwidth-
  bound, not latency-bound, at these message sizes; the ~18×
  (900/50) fabric slowdown is the killer]

### PP — pipeline parallelism
- Split: *layers* into stages; stage i sends activations to stage i+1
  (P2P send/recv), gradients back.
- **The bubble**: with m microbatches and p stages,
  **bubble fraction = (p−1)/m** [E: GPipe 1811.06965 [F, verified]; PipeDream `1806.03377`
  [F, verified this session]]. For p=8 stages, m=32:
  (8−1)/32 = 21.9% of the pipeline idle [E]. **Fix: more
  microbatches.** A naive "m ≥ 4·p" target only gets you to
  (p−1)/(4p) ≈ 25% — *still large*. The practical floor is
  **m ≈ 16·p** (e.g. m=128 for p=8): (p−1)/(16p) ≈ 6% [E:
  7/128 = 0.0547]. (Earlier draft said "m ≥ 4p → bubble ≤ 6%" —
  that arithmetic was wrong: 4p only gets you to 25%.)
- 1F1B schedule: one-forward-one-backward keeps peak activation
  memory to ~2 microbatches instead of m. The 1F1B/3D-parallelism
  paper (Narayanan et al., *Efficient Large-Scale Language Model
  Training on GPU Clusters*, 2021, arXiv id UNVERIFIED this
  session) is the canonical reference; the schedule is also
  documented in Megatron-LM `1909.08053` [F].
- PP trade: zero extra AllReduce-like traffic (only P2P
  activations), so it's the *cross-node* axis — but the bubble
  caps MFU and stage imbalance (unequal layer costs) wastes the
  slowest stage. [I]

### EP — expert parallelism (MoE only)
- Split: the *expert set*. Each GPU holds E/n_ep experts.
- **Dispatch**: tokens route to expert owners → **AllToAll** (every
  GPU sends its tokens' routed experts to their owners); compute
  local experts; **AllToAll** back (combine). 2× AllToAll/layer
  that has MoE. [F: GShard 2006.16668; DeepSpeed-MoE;
  Megatron-MoE]
- AllToAll is bandwidth-hungry *and* latency-sensitive (many small
  messages) → needs fast fabric: intra-node NVLink or NVL72;
  cross-node RDMA at scale [I: consistent across DeepSeek-V2/V3
  and Kimi K2 reports].
- Load imbalance: if the router sends 3× more tokens to some
  experts, those GPUs wait → **aux-loss-free load balancing**
  (DeepSeek-V3 [F: 2412.19437]) or capacity-factor overflow
  [I: standard].

### SP / CP — sequence (context) parallelism
- Split: the *sequence dimension* of one example.
- **Megatron-SP** (Korthikanti et al. [F: 2205.05198]): split
  attention's K/V along the sequence across GPUs within a TP group;
  combines with TP to save activation memory (the 48h·B·S·d term
  above).
- **Ring Attention** [F: 2310.01889 — verified this session,
  *not* 2211.12876]: pass K/V blocks around a ring of GPUs so one
  example can span S = 10⁶+ tokens; comm ∝ S but overlaps with
  compute. The 2025–26 long-context training default for
  128k–1M contexts [I: DeepSeek-V3.2 DSA and Llama-4 mid-training
  both use sequence-parallel attention].
- Used for: long-context pretraining (32k→1M), and *inference*
  prefill of huge prompts.

## Composition — the real decomposition

The classic 3D split (3D-parallelism paper, id UNVERIFIED this
session; see references): **DP × TP × PP**.
2024–26 frontier adds EP (MoE) and SP (long context):

```
world = DP × TP × PP × EP × SP        (all independent axes)
  DP   = outermost (one full optimizer step per DP replica)
  TP   = innermost, inside one node (NVLink)
  PP   = across nodes, sequential
  EP   = on the MoE layers only (can equal TP group or span nodes)
  SP   = on the attention K/V of long sequences
ZeRO-1/2/3 layers over DP (shard optimizer/grads/params)
```

**Worked example [E + I: reconstruction from open reports; verify
exact numbers against each paper's §Training]:**
- **Llama-3 405B** (L=126, d=16384, 128 heads, GQA 8 groups,
  ~8k context): trained on ~16k H100s [I: reported order]. Plausible
  decomposition: TP=8 (one node), PP=4–8 across nodes, DP=~250–500
  replicas, ZeRO-3, full activation recompute. [I: the Llama-3
  report describes the training at a high level; exact
  DP/TP/PP split not in the abstract — re-verify against full
  text before citing specific numbers.]
- **DeepSeek-V3** (61 layers, 256 routed experts + 1 shared,
  top-8, MLA): trained on 2048×H800 [F: 2412.19437]. The report
  details a hybrid of TP/EP/PP with 3D + EP [F: paper §3]; exact
  factorization in the paper (not reproduced here — UNVERIFIED
  against full text this session).
- **Kimi K2** (1T/32B): "trained on a large GPU cluster with
  MuonClip" [F: 2507.20534] — exact topology not in the abstract
  [I: treat detailed claims about its parallelism as UNVERIFIED
  until the full text is read].

**[I] The invariant:** TP ≤ (NVLink domain size), EP ≤ (fast-fabric
domain size), PP spans the rest, DP is whatever's left. If the
world has 8,192 GPUs = 1024 nodes × 8: typical choice TP=8,
EP=8 (within node), PP=8 (across 8 nodes), DP=16, ZeRO-3 →
world = 8×8×8×16 = 8,192 ✓ [E: 8*8*8*16=8192].

## Communication budget — the step's cost

For a 70B dense model, DP=512, TP=8 (intra-node), PP=8, ZeRO-3,
micro S=4096, d=8192 [I: 70B-class hidden]:

Per step, per GPU [E: audit in `/tmp/te-research/audit.py`]:
- **TP AllReduce** (NVLink): each AllReduce moves ring-traffic
  2·S·d·(2 B) = 2·4096·8192·2 ≈ **134 MB** [E]; ×4
  AllReduce/layer (fwd+bwd × attention+FFN) × 80 layers = **42.9
  GB/step** [E: 320 × 134 MB] → at 900 GB/s ≈ **48 ms** [E]. ✓
  comfortable on NVLink.
- **DP + ZeRO-3** (inter-node) — *the fundamental AllReduce floor*
  [E, derived]: every rank must *finish* the step with the full
  averaged gradient for the parameters it owns, and start with only
  its local copy, so a rank must move ≈ M·(n−1)/n bytes in each of
  the two ring phases, i.e. ≈ **2·(n−1)/n·M** total ring traffic,
  where M = gradient bytes. In *plain DP* M = 2N (BF16 grads):
  at 70B M = 140 GB, so effective ring traffic ≈ 2·(511/512)·140 GB
  ≈ **279 GB/GPU/step** [E]. At 50 GB/s per-GPU IB that's
  279e9/50e9 = **≈5.6 s/step un-overlapped** [E] — *far* worse than
  the compute time (≈0.08 s/step, below), i.e. **infeasible**. This
  is the fundamental argument for:
  (a) keeping the DP AllReduce on the *fastest* fabric,
  (b) hierarchical AllReduce (intra-node NVLink ring → inter-node
  ring of node-aggregates), and (c) SHARP in-network reduction.
  [I: standard 2024–26 cluster practice]
- **ZeRO-3's comm** [E, derived + F: ZeRO paper 1910.02054]: a
  rank stores N/n_dp params, so to run a layer it AllGathers that
  layer's full parameters. In net *received data* per pass, a rank
  moves ≈ (n−1)/n × N_bytes. At 70B (N_bytes = 70e9 × 2 B = 140 GB),
  one pass ≈ (511/512)×140 ≈ **140 GB**; fwd + bwd = 2 passes ≈ 280
  GB, plus the end-of-step ReduceScatter of its grad shard ≈ 140 GB
  → **≈420 GB received/GPU/step net** [E: 3 × (511/512)×140 GB].
  That is **1.5× plain DP's 279 GB** — matching the ZeRO paper's
  reported ≈1.5× comm-volume figure [F: 1910.02054 §3; net-data
  accounting]. (If instead you count *ring wire-traffic* —
  2·(n−1)/n per AllGather — the numbers are ~2× larger, ≈560 GB,
  because each byte traverses the ring ~(n−1) hops; the net-data
  figure above is what "how much distinct data does this GPU receive"
  asks, and it's the one consistent with the paper's 1.5×.) The key
  difference vs plain DP is *timing*: ZeRO-3's param AllGather is
  **layer-by-layer and overlap-able with compute** (gather layer i+1
  while computing layer i), whereas plain DP's grad AllReduce is a
  bulk end-of-step operation. So ZeRO-3's *effective* cost is far
  below the raw number. [I: this is the standard explanation for why
  ZeRO-3 + comm/compute overlap reaches 40–50% MFU where un-overlapped
  DP can't; and why ZeRO-3 is paired with TP (which shrinks N per rank
  before sharding) at 100B+.]
- **PP P2P**: S·d·2 B ≈ 67 MB per stage boundary (activation,
  not a full AllReduce) × p boundaries — small and latency-bound
  (first/last stage).
- **EP AllToAll (MoE only)**: ~ (routed tokens · d · 2 B) × 2
  dispatch/combine per MoE layer — order 1–10 GB/step
  depending on expert layout [I: DeepSeek-V3-class].

**[E] Bottom line:** at 70B, DP=512, the *NVLink* side (TP) is
~43 GB/step ≈ 48 ms [E]; the *IB* side (DP AllReduce ≈279 GB
effective, ZeRO-3 ≈420 GB net, both overlap-able) is **≈5.6 s /
≈8.4 s at 50 GB/s/GPU if un-overlapped** [E: 279e9/50e9,
420e9/50e9]. Compute/step across all 32,768 GPUs (512×8×8) at
35% MFU is **≈0.078 s** [E: 6·70e9·(4096·512) tokens /
(32768·989e12·0.35)]. So the *naive, un-overlapped* decomposition
is **~72× (DP) to ~107× (ZeRO-3) slower** than compute
[E: 5.6/0.078 ≈ 72; 8.4/0.078 ≈ 107]. Hence real runs use
**hierarchical AllReduce + comm/compute overlap + SHARP**, which
is exactly what pushes MFU from ~35% to ~50–55% [I: MegaScale
reports 55.2% with full-stack overlap, F: 2402.15627]. The
lesson: *the DP group size is a fabric decision, not a model
decision* [I].

## Choosing the decomposition (the checklist)

1. **Fit check**: 12N/n + activations ≤ HBM. Pick n_dp·n_tp·n_pp·n_ep
   so that ZeRO-shard + TP-shard + activation budget ≤ VRAM −
   ~20% (NCCL buffers, kernels). [I]
2. **TP first, inside NVLink**: TP ≤ 8 (H100 node) or ≤ 72
   (NVL72). [I]
3. **PP second, across nodes**: p ≈ 4–16, microbatches m ≥ 4p to
   kill the bubble. [I]
4. **EP if MoE**: n_ep = TP-group size (intra-node) or node
   count; balance experts (capacity factor 1.25–2× [I]).
5. **SP if S > 32k**: ring attention or Megatron-SP; n_sp usually
   = TP size (reuses the NVLink group). [I]
6. **DP = remainder**: it's the throughput axis; scale it last.
7. **ZeRO level**: *pick the minimum ZeRO level that fits*.
   12N/GPU ≤ VRAM → plain DP (no ZeRO). 4N + 8N/n ≤ VRAM →
   ZeRO-1. 2N + 10N/n ≤ VRAM → ZeRO-2. 12N/n + activations ≤
   VRAM → ZeRO-3. (Earlier draft phrased this backwards — "ZeRO-1
   if 12N fits" is wrong: if 12N fits per GPU, you don't need
   ZeRO at all.) [E]. Offload (ZeRO-Offload) only as a last
   resort — it steals PCIe bandwidth and caps MFU. [I]
8. **Recompute policy**: selective (attention only) if it fits;
   full otherwise. [I]

**[E] Sanity:** the *product* must equal the world size. 8×8×8×16
= 8192 ✓. If the product doesn't equal n_gpus, you have a bug —
the most common operator error in real runs. [I]

## Failure modes by axis

| Axis | Symptom | Cause |
|---|---|---|
| DP | step time spikes with n | AllReduce on slow fabric / IB retry storm |
| ZeRO-3 | AllGather dominates | n too large for the fabric; move params to TP |
| TP | latency-bound step | TP across nodes (never do this) |
| PP | bubble > 25% | too few microbatches (m < 4p) |
| EP | some GPUs idle | router imbalance; check aux-loss/capacity |
| SP | K/V ring stall | one node's NIC slow; ring is only as fast as its slowest |

## Key takeaways

1. Every axis splits one thing and buys one comm pattern —
   DP=AllReduce, TP=AllReduce×2/layer, PP=P2P+bubble, EP=AllToAll,
   SP=ring. Match the pattern to the fabric.
2. **TP lives on NVLink** (≤ 8 GPUs per node; 72 on NVL72).
   **PP spans nodes.** **DP is the throughput axis.** **EP is the
   MoE tax.** **SP is the long-context tax.**
3. ZeRO-3/FSDP is how dense models 70B+ fit: shard 12N across DP
   replicas; pay ~1.5× DP comm.
4. The bubble formula (p−1)/m is the single most-misunderstood
   PP number — m ≥ 4p is the practical floor.
5. At scale, the *communication/compute overlap* (not raw
   bandwidth) is what separates 35% MFU from 55% MFU.

## References

- Megatron-LM (Sho et al.) — `1909.08053` [F, verified]
- Megatron-3 / 3D parallelism + 1F1B (Narayanan et al., "Efficient
  Large-Scale Language Model Training on GPU Clusters", 2021) —
  arXiv id UNVERIFIED this session (candidate `2006.15843`
  resolved to an *unrelated SBM paper*)
- ZeRO (Rajbhandari et al.) — `1910.02054` [F, verified
  2026-08-20]; ZeRO-Infinity — `2104.07857` [F, verified]
- DeepSpeed (Rajbhandari et al., OSDI'20; arXiv id UNVERIFIED this
  session — candidate `2004.11302` resolved to an unrelated
  self-adaptive-systems paper)
- GPipe (So et al.) — `1811.06965` [F, verified];
  PipeDream (Hogwage? no — **PipeDream: Fast and Efficient
  Pipeline Parallel DNN Training, Huang et al.** — `1806.03377`
  [F, verified this session; *not* `1806.07384`])
- FlashAttention (K/V IO) — `2205.14135`; FA2 — `2307.08691`;
  FA3 — `2407.08608` [all F, verified]
- Korthikanti et al. (activation recompute + Megatron-SP) —
  `2205.05198` [F, verified]
- Ring Attention (Liu et al.) — `2310.01889` [F, verified
  2026-08-20]
- GShard — `2006.16668`; Switch — `2101.03961`; Sparsely-Gated —
  `1701.06538` [all F, verified]
- DeepSeek-V3 (EP/MLA training) — `2412.19437` [F, verified]
- MegaScale (comm-compute overlap at 10k GPUs) — `2402.15627`
  [F, verified]
- FSDP OSDI'23 paper — UNVERIFIED this session (cite via
  PyTorch docs)
