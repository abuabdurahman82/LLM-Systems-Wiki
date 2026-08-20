# Scaling Training: 1 GPU → 10,000+ GPUs

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of
`Training-Engineering/`

> The engineering narrative of a real pretraining run: what changes as
> you go from a single 8-GPU node to a 10,000-GPU cluster — the topology,
> the MFU fight, the stability fight, and the cost model. `Parallelism.md`
> is the *decomposition*; this page is the *cluster* and the *operations*.

## 30-second explanation

At 1 node (8 GPUs) you fit a 7B model with ZeRO-3 and run a day of
training. At 100 nodes you add PP + cross-node DP and start fighting
the IB fabric. At 10,000 nodes you're fighting *failure rates,
stragglers, and checkpoint cadence* more than FLOPs: a 10k-GPU run
expects **hundreds of hardware failures** and the question is no longer
"can it run" but "how many GPU-hours do you lose to restarts and
spikes". [I: consistent across MegaScale 2402.15627 and every
2024–26 open training report.]

## The topology ladder

| Scale | Model class | Decomposition | Binding constraint |
|---|---|---|---|
| **1 node (8 GPU)** | 7B–13B dense | ZeRO-3/FSDP, no TP (or TP=2) | VRAM per GPU; HBM BW |
| **4–16 nodes** | 70B dense | TP=8 × PP=2–4 × DP, ZeRO-1/2 | intra-node NVLink + IB latency |
| **64–512 nodes** | 70B–405B dense | TP=8 × PP=8–32 × DP=… | IB AllReduce; data pipeline |
| **512–4k nodes** | 100B–700B / first MoE | + EP; comm-compute overlap | stragglers; IB BW |
| **4k–12k+ nodes** | 671B–1T MoE (DeepSeek-V3, K2) | full 5-axis + SP | **failure rate; stability** |
| **10k–100k nodes** | frontier MoE + long-ctx | + SP/Ring; NVL72 domains | *same*, plus NVL72 vs IB |

[F: 2402.15627 (MegaScale, 175B on 12,288 GPUs); 2412.19437
(DeepSeek-V3, 671B MoE on 2,048 H800s); 2507.20534 (Kimi K2, 1T MoE —
cluster size not in abstract).] **[I]** The row structure is a
reconstruction from these reports + standard practice; exact node
counts per model are in the full papers (UNVERIFIED against full text
this session).

### The atomic unit: the NVLink node
- **H100 node:** 8× H100/H800, 80 GB each, NVLink 3 (900 GB/s
  aggregate per GPU [F: vendor H100 page]) + 8× 400G IB (NDR) to the
  world. The NVLink domain is the *only* place TP is practical.
  [F: vendor spec]
- **B200/GB200 node (DGX B200):** 8× B200, 180 GB HBM3e each
  (1,440 GB total), 8 TB/s HBM3e BW per GPU, NVLink 5 (1.8 TB/s per
  GPU, 14.4 TB/s aggregate per node [F: vendor DGX B200 page]).
  **Node dense FLOPs: 72 PFLOP FP4 / 36 PFLOP FP8** (= 9 / 4.5
  PFLOP per B200); sparse peaks are 144 / 72 PFLOP FP4 / FP8
  [F: vendor DGX B200 page, fetched 2026-08-20; "Dense performance
  is ½ sparse spec"].
- **GB200 NVL72:** 72 B200 GPUs in *one* NVLink domain (4× B200 per
  NVL72 tray = 2 GB200 superchips × 2 GPUs each, × 18 trays = 72)
  — a 72-GPU NVLink island. This is the 2025–26 "TP can now span 72
  GPUs" change: TP/EP/SP all get a 9× bigger fast-fabric domain
  (72 vs 8 GPUs), which *relaxes* the cross-node DP/PP pressure.
  [F: vendor; I: the "TP on NVL72" practice is emerging, not yet
  the default.]

**[I] The ladder's logic:** every rung up is "the model no longer
fits in the fast-fabric domain, so you push more work across the slow
fabric (IB/Ethernet)". The whole systems game is *minimizing* that
cross-fabric work.

## The MFU fight (35% → 55%)

MFU = achieved FLOPs / (peak FLOPs × wall time). The *losses* between
the 6·N·D ideal and the wall clock are, in order of size [I:
MegaScale's full-stack analysis, 2402.15627]:

1. **Comm not overlapped** — AllReduce/AllToAll/AllGather that
   *waits* instead of overlapping with compute. **Fix:**
   comm/compute overlap (separate CUDA stream + NCCL), which is the
   single biggest MFU lever at scale. [F: MegaScale §4]
2. **Pipeline bubble** — (p−1)/m idle fraction. **Fix:** m ≥ 4p
   microbatches (see `Parallelism.md`).
3. **Activation recompute** — the ~1/3 extra forward FLOPs you pay
   for selective recompute. **Fix:** selective (attention-only)
   recompute when VRAM allows. [F: 2205.05198]
4. **Data pipeline starvation** — dataloader can't keep up at
   10^7 tokens/step. **Fix:** pre-tokenized sharded dataset, multiple
   readers, GPU-side prefetch. [I: standard]
5. **Stragglers** — one slow GPU (thermal/ECC/IB retry) stalls the
   whole sync step. **Fix:** detect + replace (see stability).
   [F: MegaScale §5–7]
6. **Kernel inefficiency** — GEMM/attention not hitting peak.
   **Fix:** FlashAttention-2/3 [F: 2307.08691, 2407.08608],
   tuned GEMM (cuBLAS/Triton).

**[E] The arithmetic of the fight:** 1000 H100s at *55% MFU* for
90 days delivers 1000 × 989e12 × 0.55 × 7.776e6 s = **4.23e24
FLOP** [E]; at *35% MFU* it's 2.68e24 [E] — a **1.58× difference
in usable compute for the same hardware** [E: 4.23/2.68 = 1.58;
equivalently 0.55/0.35 = 1.57]. That's the entire MegaScale result
(55.2% vs Megatron's ~41% baseline at 175B [F: 2402.15627]) —
*systems work, not bigger GPUs*, buys ~1.34× throughput [F:
MegaScale reports "improving the MFU by 1.34× compared to
Megatron-LM"].

## The stability fight (the real 10k-GPU problem)

**Failure rate [I: back-of-envelope, order-of-magnitude]:** a
10,000-GPU cluster = 1,250 nodes. If a node has a ~1-per-month MTBF
for a *fatal* failure (GPU fault, NVLink fault, IB port), the
cluster sees **1,250 fatal failures/month** [E: 1250 × 1] — i.e.
**one every ~34.6 min** [E: 43,200 min / 1250]. [UNVERIFIED MTBF
assumption; real data is proprietary — even at 1-per-3-months/node
that's one every ~104 min [E]. Treat as order-of-magnitude only.]

**The consequence:** the *dominant cost* of a 10k-GPU run is not
compute but **downtime + checkpoint overhead**:
- Every fatal failure → stop, diagnose, reschedule, restart from
  last checkpoint.
- **Checkpoint cadence vs cost:** the classic tradeoff —
  checkpoint every N steps. Recovery cost ∝ N × world_size ×
  (shard-read + re-broadcast) time. [I]
- **Loss spikes:** even without a hardware failure, a bad data
  shard or numerics edge case spikes the loss; you roll back to
  the last clean checkpoint and skip the shard. DeepSeek-V3: 0
  irrecoverable spikes over 14.8T tokens [F: 2412.19437]; Kimi K2:
  0 spikes over 15.5T [F: 2507.20534] — these "zero-spike"
  claims are the 2025–26 *stability* brag, and they're what
  separate a 2.788M-GPU-hour run from a 5M-GPU-hour one. [I]

**What the frontier actually does [I: synthesis of open reports]:**
1. **Continuous (async) sharded checkpoints** — not one big
   stop-the-world; shards written in the background, ~every
   100–1000 steps. [I: standard 2024–26]
2. **Elastic training** — a failed node is evicted and the
   remainder continues at reduced world-size rather than stopping
   the whole run (DeepSpeed-elastic / Torch Elastic). [I]
3. **Straggler detection** — per-rank step-time monitoring; a
   rank >50% slower than the median is flagged and swapped.
   [F: MegaScale §5–7]
4. **Pre-emptive failure prediction** — ML on SMART/thermal/IB-retry
   telemetry to predict a failure before it happens. [I: emerging]
5. **Spike policy** — on a loss spike: roll back, skip the data
   shard, optionally drop LR, resume. The *policy* is as
   important as the detection. [I]

**[E] Downtime math (order-of-magnitude, all in
`/tmp/te-research/audit.py`):** 6-month run, 1250 nodes, 1
failure/node/month → **7,500 failures** [E: 1250 × 6].
- **Stop-the-world** (5 min each): 625 h of downtime = **1.45%**
  of the 43,200-h run [E: 625/43200] — the run takes 1.45% longer,
  i.e. **~1.015× the GPU-hours** of the same work with no failures
  [E: 43200/42575 = 1.0147]. (The earlier "14.5× more GPU-hours"
  was a %-to-× slip: 1.45% overhead = 1.0145×, not 14.5×.)
- **Elastic + fast restart** (0.5 min each): 62.5 h = **0.14%**
  [E: 62.5/43200] — a ~10× smaller downtime overhead from the
  stability stack alone [E: 1.45%/0.14% ≈ 10.4].
**This is why the "zero-spike, elastic, fast-restart" stack is
table stakes at 10k GPUs** [I].

## The cost model (ties to `Interaction.md`)

A run's real cost = **useful compute + wasted compute**:
```
total_GPU_hours = (6·N_act·D / (peak·n_gpu·MFU)) × (1 + downtime_frac)
```
where `downtime_frac` is the stability overhead above. **[E]
DeepSeek-V3 sanity:** 6·37e9·1.48e13 = 3.29e24 FLOP [E]; at
2048 H800s @ 989 TFLOP, 100% MFU, that's
3.29e24/(989e12·2048) = **451 h** [E]. The run took
**2.788M H800-GPU-hours / 2048 = 1,361 h wall-clock** [E:
2.788e6/2048 = 1361 h = 57 days] → implied
**MFU ≈ 451/1361 ≈ 33%** [E] on the *activated*-FLOPs basis
(H800 peak = 989 TFLOP, vendor-true for compute [F]).
A ~33% activated-MFU on a 671B-total / 37B-activated MoE over
57 days is at the low end of the dense 40–60% band [I] —
consistent with MoE AllToAll overhead + stability overhead.
(The paper does not state MFU; this is a back-calc, flagged as
such.)

## What actually limits each rung (honest summary)

| Rung | *Not* the limit | The limit |
|---|---|---|
| 1 node | FLOPs | VRAM (fits?); HBM BW |
| 16 nodes | VRAM | IB latency (PP/DP) |
| 512 nodes | IB BW | comm overlap; data pipeline |
| 4k nodes | overlap | stragglers; failures |
| 10k+ nodes | FLOPs | **failure rate + spike policy + checkpoint cadence** |

**[I]** The single most important strategic fact: *above ~1k
GPUs, the binding constraint is reliability, not FLOPs.* The labs
that run 10k-GPU jobs at 55%+ MFU (ByteDance/MegaScale, DeepSeek,
Kimi/Moonshot) invested in **stability engineering** (elastic
scheduling, fast restart, straggler detection) *as much as* in
comm overlap. [F: 2402.15627; 2412.19437]

## Key takeaways

1. The topology ladder: each rung up pushes more work across the
   slow fabric; the whole systems game is minimizing that.
2. The NVLink node (8-GPU, H100/B200) is the atomic unit; NVL72
   makes a 72-GPU fast-fabric island (2025–26).
3. **MFU 35→55%** is mostly *comm/compute overlap*, not bigger
   GPUs — a 1.58× usable-compute win for the same hardware [E].
4. At 10k GPUs, **failure rate + spike policy + checkpoint
   cadence** dominate the cost, not FLOPs — "zero-spike" runs
   (DeepSeek-V3, K2) are the 2025–26 stability bar.
5. The cost model: `total = ideal_compute/MFU × (1 + downtime)`;
   downtime is the term everyone underestimates.

## References

- MegaScale (12,288 GPUs, 55.2% MFU, stability) — `2402.15627`
  [F, verified]
- DeepSeek-V3 (2,048 H800, 2.788M GPU-h, 0 spikes) —
  `2412.19437` [F, verified]
- Kimi K2 (0 spikes, MuonClip) — `2507.20534` [F, verified]
- FlashAttention-2/3 — `2307.08691`, `2407.08608` [F, verified]
- Activation recompute (selective) — `2205.05198` [F, verified]
- H100/B200 specs — vendor pages fetched 2026-08-20 (retained in
  `/tmp/te-research/`)
- MTBF/failure-rate figures — [UNVERIFIED] order-of-magnitude,
  proprietary real data; treat as illustrative only.
