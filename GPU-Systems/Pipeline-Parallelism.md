# Pipeline Parallelism
`LAST_UPDATED: 2026-08-21 · Status: core page` · [E] arithmetic Python-verified this session
(see the worked-example sections); GPipe [F: arXiv:1811.06965] and PipeDream [F: arXiv:1806.03377]
are the cited scheduling papers. `Multi-GPU.md` is the overview; this page is the deep dive.

## 30-Second Explanation
Split the model **by layers**, not by batch (DP) and not by a layer's matrices (TP). GPU0 owns
layers 0–19, GPU1 owns 20–39, … each GPU is a **stage**; the activation tensor flows
stage-to-stage with **P2P send/recv** (not a collective). Two consequences define everything:
(1) the **bubble** — with p stages and m micro-batches, idle time is `(p−1)/(m+p−1)` of total
time [E], so more micro-batches shrink it; (2) **tiny comm** — each hand-off moves only
`B·S·d·b` bytes of activation, not a whole layer, which is why PP is the one parallelism
dimension that is **cross-node friendly** (RDMA) while TP is not. The trade: PP is
**throughput-friendly but latency-penal** — a single request crosses all p stages serially, so
per-request latency grows by a stage each. In training, 1F1B/GPipe micro-batch schedules hide the
bubble; in inference there is no gradient to pipeline, so PP is used mainly for **capacity**
(models too big for one node), not latency [I].

## The core idea: split layers, flow activations P2P
- **WHAT:** cut the L layers into p contiguous ranges; stage i holds layers `[i·L/p, (i+1)·L/p)`
  and forwards its output activation to stage i+1.
- **WHY:** weight-per-GPU drops ÷ p with **no AllReduce** — only neighbor-to-neighbor P2P.
  That is the cheapest split comm cost of all six dimensions (see `Multi-GPU.md`).
- **HOW:** stage i computes its slice, then `P2P-send(activation)` to stage i+1; stage i+1
  `recv`s, computes, sends on. The P2P primitive (NCCL `Send`/`Recv`, or a raw RDMA write) is
  what moves data — covered in `NCCL.md`.
- **WHEN:** the model exceeds one node's HBM, or you need a capacity split that a fabric
  (PCIe/RDMA) can carry. TP is tried first (latency-friendlier); PP is the cross-node axis.

### Stage diagram — 4 GPUs, 80 layers
```
 input ──▶ ┌──────────────┐  act  ┌──────────────┐  act  ┌──────────────┐  act  ┌──────────────┐
           │  GPU0  stage0│──────▶│  GPU1  stage1│──────▶│  GPU2  stage2│──────▶│  GPU3  stage3│──▶ output
           │ layers  0-19│◀──────│ layers 20-39│◀──────│ layers 40-59│◀──────│ layers 60-79│
           └──────────────┘ grad └──────────────┘ grad └──────────────┘ grad └──────────────┘
                    ▲ P2P send/recv on the activation (forward) / gradient (backward) edges ▲
```
Each stage holds 80/4 = 20 layers [E]. Forward: activation B·S·d·b travels left→right.
Backward (training only): gradient travels right→left. **No AllReduce, no AllToAll — only
neighbor P2P.**

## The pipeline bubble
A stage can only start a micro-batch when its input arrives. With p stages in series, the
first micro-batch must be "warmed up" through all p stages before the pipeline is full, and
the last must drain. That warm-up + drain time is the **bubble**.

### Deriving the fraction (show the arithmetic) [E]
Assume each stage takes the same time T for one micro-batch (balanced pipeline). Total time to
finish m micro-batches through p stages:

```
T_total = m·T + (p−1)·T          # m useful slots + (p−1) warm/drain slots
bubble  = (p−1)·T / (m+p−1)·T = (p−1)/(m+p−1)
```

Cross-check by counting stage-time slots: there are `p·(m+p−1)` stage-slots total, of which
`p·(p−1)` are idle (each stage idles p−1 slots: p warm-up + drain gaps minus the 1 shared)
[E: p·(p−1)/(p·(m+p−1)) = (p−1)/(m+p−1), same result]. So:

| p | m | total (m+p−1) | bubble (p−1)/(m+p−1) | useful m/(m+p−1) |
|---|---|---|---|---|
| 4 | 1  | 4  | **3/4 = 75%** (only 25% useful) | 25% |
| 4 | 4  | 7  | 3/7 ≈ 42.9% | 42.9% |
| 4 | 16 | 19 | 3/19 ≈ **15.8%** | 84.2% |
| 4 | 47 | 50 | 3/50 = **6.0%** | 94% |
| 4 | 64 | 67 | 3/67 ≈ 4.5% | 95.5% |

All values Python-verified [E]. **Why more micro-batches shrink the bubble:** the numerator
(p−1) is fixed by topology, but the denominator (m+p−1) grows with m — the warm-up/drain cost is
amortized over more useful work. As m→∞, (p−1)/(m+p−1) → 0, so bubble → 0. The practical rule:
pick m ≫ p so `(p−1)/(m+p−1)` is small. (GPipe's large-m limit is ≈ (p−1)/m [F: arXiv:1811.06965],
which at m=16,p=4 is 3/16 = 18.75% — a looser bound than the exact (p−1)/(m+p−1) above.)

### Bubble-fraction timeline (p stages, m micro-batches)
General shape for p=4, m=4 — `X` = computing micro-batch, `.` = idle bubble:

```
time→  μ1  μ2  μ3  μ4  |  warm-up + drain
S1:    X   X   X   X   .    .
S2:    .   X   X   X   X    .
S3:    .   .   X   X   X    X
S4:    .   .   .   X   X    X
       └── bubble ──┘        └ bubble ─┘
```
Idle cells = p(p−1) = 12 of p(m+p−1) = 28 total [E: 12/28 = 3/7 ≈ 42.9%]. The staircase of
X's *is* the pipeline: each stage starts one slot later and finishes one slot later. Fill the
gaps with more micro-batches (taller staircase) and the idle fraction collapses.

## Microbatches: keeping stages busy
The bubble is an artifact of sending **one big batch** down the pipeline. The fix is to split
the batch into **m small micro-batches** and stream them so every stage is always working on
*some* micro-batch while its neighbors handle the rest.
- **GPipe (arXiv:1811.06965 [F]):** split batch into m; all m forwards, then all m backwards
  ("All-Forward-All-Backward"). Simple, big bubble unless m is large; stores all m
  activations (memory ∝ m).
- **PipeDream (arXiv:1806.03377 [F]):** **Weight-Staleness (1F1B)** and
  **Gradient-Staleness (1B1F)** — pipeline forward/backward *interleaved* so a stage starts
  backprops before all forwards are done → hides more bubble at the cost of stale weights or
  stale gradients.
- **1F1B (Megatron, arXiv:1909.08053 [F]):** "one-forward-one-backward" [I: standard schedule] — a warm-up of F forwards
  to reach steady state, then alternating 1F/1B so **peak activation memory ≈ 2 micro-batches**
  instead of m. This is the training default at scale and the reason 1F1B is named as *the*
  bubble-hiding schedule. [I: standard 2021+ practice]

**Training vs inference here:** training has a batch + a **backward pass**, so 1F1B/GPipe/PipeDream
all apply and the bubble is amortized across the whole step. Inference has **no backward pass** —
each request is an independent forward stream, so those schedules do not transfer directly. See
the 9-field section below.

## Latency vs throughput
- **Throughput-friendly:** P2P comm is tiny (∝ B·S·d·b, not the layer) and overlaps easily with
  compute on the *next* micro-batch; total cluster FLOPs ≈ p × one-GPU FLOPs.
- **Latency-penal:** a single request must cross **all p stages serially** — it cannot start on
  GPU1 until GPU0 finishes its slice. Per-request latency ≈ Σ stage-latency + per-stage P2P
  round-trip. So PP buys capacity/throughput but **adds a fixed stage-latency tax to every
  request's TTFT/ITL**. This is why the rule of thumb is "TP first (latency), PP second
  (capacity)" (`Multi-GPU.md`).

## 9-Field Template — the pipeline bubble
- **What:** the fraction of wall-clock a stage spends idle waiting for its input to arrive, when
  the pipeline is not full of micro-batches. Equals (p−1)/(m+p−1) of total time for a balanced
  p-stage, m-micro-batch pipeline [E].
- **Why:** it exists because stages are serially dependent — stage i+1 needs stage i's output —
  so the first input must traverse p hops before the pipeline is "full" and the last output
  must drain. The warm-up (p−1) slots and drain slots are irreducible per *batch boundary*.
- **How:** it is eliminated by (a) **more micro-batches** (m ≫ p amortizes the warm-up), and
  (b) **schedules that overlap forward/backward** (1F1B) so a stage is never waiting on the
  whole batch. Both act on the denominator (m+p−1) growing while numerator (p−1) stays fixed.
- **When:** always present at a batch boundary; negligible when m ≫ p, dominant when m ≈ p or m < p.
- **Hardware impact:** none directly — it is a scheduling artifact, not a fabric one. A fast
  fabric does **not** shrink the bubble (smaller P2P latency ≠ more useful slots).
- **Inference impact:** this is where it bites hardest — see below. In training, the bubble is a
  fraction of the *step*; in inference it maps onto **per-request TTFT** (pre- and post-stall).
- **Example:** [E] p=4, m=1 → bubble 3/4 = 75%, only 25% of time useful. p=4, m=47 → 3/50 =
  6.0%. The same 4-GPU pipeline, 1× vs ~19× more micro-batches: 75% → 6% idle. (Python-verified
  arithmetic: 3/(1+4−1)=0.75; 3/(47+4−1)=0.06.)
- **Failure modes:** under-provisioned m (m < p) → bubble > 50% → most GPUs idle; a single slow
  stage (imbalance) widens the effective bubble because downstream stages stall on it; cold
  first-batch latency (no warm micro-batch to overlap the P2P) makes the *first* request's TTFT
  worst.
- **How to measure it:** stage idle-time / total-time from Nsight Systems or engine per-stage
  timing (`GPU-Metrics.md`); or model it: estimate (p−1)/(m+p−1) and compare to measured
  stage-utilization. If measured idle ≫ modeled bubble → you have imbalance or slow-P2P, not
  just the fundamental bubble.

## 9-Field Template — inference PP vs training PP
- **What:** the same layer-split + P2P, but inference has **no backward pass, no gradient, no
  optimizer step** — each request is an independent forward stream. So the micro-batch
  schedules that hide the training bubble (1F1B/GPipe/PipeDream) do not apply verbatim.
- **Why:** training pipelines a *batch* with a forward **and** backward wave, so there is a
  steady-state to overlap and a denominator (m+p−1) to grow. Inference pipelines *requests*;
  there is no second wave, and the "micro-batch" is really the *request* (or a chunk of it).
  The bubble therefore becomes the **per-request prefill/decode latency** spent waiting for the
  previous stage to finish its slice, not an amortizable warm-up.
- **How:** inference PP serves requests one at a time per stage (or with a small in-flight
  batch), so each request's TTFT ≈ Σ stage-forward-time + per-stage P2P latency. Throughput
  rises with concurrency (many requests overlap across stages), but **per-request latency grows
  by a stage** — there is no free overlap because there is no backward wave to hide it behind.
- **When:** inference PP is chosen for **capacity** — the model's weights won't fit on one node's
  HBM (e.g. a 70B+ dense model spanning nodes) — not for latency. Use it when you *must* place
  the model across nodes and NVLink is unavailable.
- **Hardware impact:** P2P over RDMA (IB/RoCE) is the norm cross-node; a few KiB–MiB per
  hand-off is trivial for RDMA, but the **P2P latency** (tens of µs per hop) serializes into
  TTFT. Unlike TP (AllReduce every layer), PP sends one activation per stage-boundary, so the
  fabric is far more forgiving.
- **Inference impact:** **throughput ↑** (more GPUs in the pipeline), **TTFT ↑** (extra stage
  hops + P2P round-trips), **ITL roughly unchanged per-token** (a decode token still crosses all
  p stages, but each stage is fast). Net: PP is the tool when the model is too big for one node
  and you accept the TTFT cost for the capacity. It is *not* the tool for cutting latency.
- **Example:** [E] same 4-GPU, 80-layer model. Training at m=47: bubble ≈ 6% of the step, hidden
  by 1F1B. Inference at B=1: no m to amortize — a request's TTFT adds ~3 P2P hops + the
  sequential stage forwards; the "bubble" is the request's own prefill latency waiting on
  stage i−1, which a 1F1B-style schedule cannot remove (no backward wave to overlap). This is
  why inference PP is a capacity decision, not a latency one.
- **Failure modes:** latency SLO miss (per-request P2P + serial stages); cold-start TTFT spike on
  the first request (no in-flight overlap); a slow stage serializing every request downstream;
  P2P latency over a congested RDMA link turning a "small" hand-off into a visible TTFT adder.
- **How to measure it:** compare TTFT/ITL with PP=1 vs PP=p on the **same** model + fabric
  (`Labs.md` Lab 19); isolate P2P contribution by timing stage-boundaries in Nsight Systems;
  confirm it is capacity-driven by checking that a single node *cannot* hold the weights.

## Latency vs throughput (recap)
| | Throughput | Latency (per request) |
|---|---|---|
| Training PP (1F1B, large m) | high (bubble ≈ 0) | n/a (step-based) |
| Inference PP (B=1, no m) | rises with concurrency | **grows by ~a stage per extra GPU** |
| Comm | tiny P2P | tiny P2P, but P2P **latency** serializes |

## Imbalance: uneven layer splits → last stage idles
The (p−1)/(m+p−1) bubble assumes **equal stage cost**. Real layers are not equal:
- **MLP-heavy layers are more expensive** (the SwiGLU MLP is ~⅔ of a layer's FLOPs, vs ~⅓ for
  attention projections — `GEMM.md` maps this). A stage holding more MLP-heavy layers is slower.
- **Early layers can be cheaper** (e.g. the embedding + first block has less work than a mid
  block with full attention span).
- **The final stage often holds the LM head** (vocab projection) — a `[d, vocab]` matrix that can
  be ~0.7 GiB at d=4096, vocab=100k, b=2 [A] — making stage p the slowest and
  the **last stage the bottleneck that idles everyone else** on it.

**Fix: balance by FLOPs, not by layer count.** Assign stage boundaries so each stage's *work*
(≈ FLOPs + weight-bytes) is equal, even if that means uneven layer counts. `Multi-GPU.md`
states this as "PP imbalance (uneven layer splits → last stage idles. Fix: balance
FLOPs/stage)." Practical approach: profile per-layer FLOPs (or weight-bytes) and cut the 80
layers into p near-equal-cost ranges rather than at L/p.

## Communication: P2P activations are small → cross-node friendly
- **What moves:** the **activation tensor** `B·S·d·b` between stage i and i+1 — **not** the
  layer's weights, **not** a full AllReduce. For B=1, S=1, d=4096, b=2: **8192 B = 8 KiB** [E].
  Even a full prefill step (S=4096) is 1·4096·4096·2 = 32 MiB [E] — still tiny vs a TP
  AllReduce of the same layer.
- **Why it's cross-node friendly:** at 50 GB/s IB NDR, 8 KiB takes ≈ 0.16 µs of transfer [E:
  8192/50e9 s] — negligible; the *latency* (setup + RDMA) matters more than the bandwidth, and
  RDMA handles that well. TP, by contrast, AllReduces `2×S×d×b` **every layer** — that volume
  over RDMA dominates (`Tensor-Parallelism.md`).
- **Result:** PP is the dimension you reach for **across nodes** when NVLink is absent; the P2P
  volume is a fraction of TP's, so the fabric (RDMA) is not the limiter — the **bubble and
  stage-latency** are. See `Multi-Node.md` + `Networking/README.md` for the RDMA side.

## Hybrid: TP within node + PP across nodes
The standard large-model stack composes dimensions to match the fabric:
```
Node 0 (NVLink, 8× H100)        Node 1 (NVLink, 8× H100)
 ┌──────────────────────────┐    ┌──────────────────────────┐
 │  TP=4: split each layer's │    │  TP=4: split each layer's │
 │  matrices over 4 GPUs     │    │  matrices over 4 GPUs     │
 │  ┌──┐ ┌──┐ ┌──┐ ┌──┐      │    │  ┌──┐ ┌──┐ ┌──┐ ┌──┐      │
 │  │G0│ │G1│ │G2│ │G3│ ◀──RDMA──▶ │G4│ │G5│ │G6│ │G7│      │
 │  └──┘ └──┘ └──┘ └──┘      │    │  └──┘ └──┘ └──┘ └──┘      │
 │  stage 0 (layers 0–39)     │    │  stage 1 (layers 40–79)   │
 └──────────────────────────┘    └──────────────────────────┘
        TP AllReduce (fast NVLink)      PP P2P (RDMA, small activation)
```
- **TP lives inside the NVLink domain** (fast, every layer, latency-critical) — `Tensor-Parallelism.md`.
- **PP spans the nodes** (slow RDMA, but only a small P2P per stage-boundary) — this page.
- For the 27B example from `Multi-GPU.md`: TP=4 × PP=2 → 50.3 GiB / 8 = **6.29 GiB weights/GPU**
  [E], vs 12.575 GiB/GPU for PP=4 alone [E: 50.3/4]. The hybrid keeps the latency-critical
  AllReduce on NVLink and puts only the cheap P2P on the slow link. This "TP within node +
  PP/EP across nodes" is the 2024+ default (`Multi-GPU.md`, `Distributed-Architectures.md`).

## Failure modes
- **Pipeline bubble (idle):** m too small relative to p → (p−1)/(m+p−1) large → most GPU-time
  idle. Fix: raise m, or use 1F1B overlap (training) / accept the latency tax (inference).
- **Stage imbalance:** uneven layer cost (MLP-heavy, LM-head) → one stage is slower → the whole
  pipeline's effective throughput is capped by the **slowest stage**; downstream stages idle on
  it. Fix: balance by FLOPs, not layer count.
- **Activation recompute (training):** 1F1B stores ~2 micro-batches of activations; at large
  p×m you may checkpoint and recompute activations to fit HBM, trading ~⅓ extra FLOPs
  (the `../Training-Engineering/Parallelism.md` checkpointing trade).
- **A slow stage serializes the whole pipeline:** a single under-provisioned or hot stage (e.g.
  last stage with the LM head, or a stage on a slow PCIe link) makes *every* request wait on
  it — the pipeline is only as fast as its slowest stage.
- **Cross-node P2P latency:** each stage-boundary adds a P2P round-trip; over a congested or
  high-latency RDMA link, the "tiny" activation hand-off becomes a visible adder to per-request
  TTFT. Fix: keep PP hops few, ensure GPUDirect RDMA, avoid PCIe detours (`Topology.md`).

## How to measure it
- **Bubble fraction:** stage idle-time / total-time (Nsight Systems per-GPU timeline, or engine
  per-stage timing). Compare to the modeled (p−1)/(m+p−1); measured ≫ modeled → imbalance or
  slow P2P, not the fundamental bubble.
- **TTFT/ITL vs PP degree:** the sweep — PP=1 vs PP=2 vs PP=4 on the same model + fabric
  (`Labs.md` Lab 19); expect TTFT to rise per extra stage.
- **P2P time vs compute time:** Nsight Systems shows the NCCL Send/Recv kernels on the timeline;
  if P2P time is a large fraction of a stage → P2P-bound (check fabric/latency).
- **Per-GPU HBM BW util + fabric util (DCGM):** is the slow stage actually busy, or idle waiting?
- **NCCL P2P benchmark:** characterize the P2P send/recv latency + bandwidth of the fabric itself.

## Related
`Multi-GPU.md` (overview + all six dimensions) · `Tensor-Parallelism.md` (the intra-node
latency split; 2 AllReduce/layer) · `MoE-Expert-Parallelism.md` (the MoE AllToAll axis) ·
`NCCL.md` (the Send/Recv + collective primitives) · `Multi-Node.md` + `Topology.md` (the RDMA
fabric + topology mistakes) · `Distributed-Architectures.md` (11 reference stacks incl. TP+PP) ·
`../Distributed-Inference/README.md` (PP as the cross-node capacity dimension) ·
`../Networking/README.md` (RDMA / IB / RoCE).

## Key Takeaways
1. **PP splits layers; the activation (not the layer) flows P2P** — that is why its comm is
   tiny and it is the cross-node-friendly dimension.
2. **The bubble is (p−1)/(m+p−1)** of total time [E]; more micro-batches (m ≫ p) amortize the
   fixed (p−1) warm-up/drain. p=4: m=1 → 75% idle; m=47 → 6%.
3. **Training hides the bubble with 1F1B/GPipe/PipeDream** (forward+backward overlap);
   **inference has no backward wave**, so PP is a **capacity** tool, not a latency one.
4. **Balance by FLOPs, not layer count** — the LM head / MLP-heavy / early layers make "equal
   layers" uneven work; the slowest stage caps the whole pipeline.
5. **Hybrid = TP within node (NVLink) + PP across nodes (RDMA)** — match each dimension to its
   fabric; that is the 2024+ large-model default.

## References
- GPipe (Hao et al., *GPipe: Efficient Training of Giant Neural Networks using
  Pipeline Model Parallelism*) — arXiv:1811.06965 [F, in citation bank].
- PipeDream (Huang et al., *PipeDream: Fast and Efficient Pipeline Parallel DNN Training*) —
  arXiv:1806.03377 [F; cross-checked vs `../Training-Engineering/Parallelism.md`].
- Megatron-LM (Sho et al.) — arXiv:1909.08053 [F; 1F1B schedule documented there].
- Sibling cross-refs: `Multi-GPU.md`, `Tensor-Parallelism.md`,
  `MoE-Expert-Parallelism.md`, `NCCL.md`, `../Distributed-Inference/README.md`,
  `Distributed-Architectures.md`, `../Networking/README.md`.
