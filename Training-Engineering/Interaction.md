# Interaction — how architecture, hardware, memory, and network
# constrain each other

`LAST_UPDATED: 2026-08-20` · Status: core page · Part of
`Training-Engineering/`

> The synthesis page. Everything so far is one variable at a time;
> this page shows the *coupling*: why the architecture picks the
> parallelism, why the fabric picks the architecture, why memory
> picks the precision, and how it all collapses to a single
> $/token number. This is the page to read when you need to make a
> real decision, not just recall a fact.

## 30-second explanation

You have four resources that must agree: **FLOPs** (compute the
model needs), **HBM** (memory it must fit), **fabric** (bytes it must
move per step), and **wall-clock** (the budget). The design space is
the *intersection* of four inequalities:

```
compute :  6·N_act·D / (peak·n_gpu·MFU)  ≤  T_wall
memory  :  12·N/n_shard + A(S,B,L,h)/n   ≤  HBM·(1−reserve)
fabric  :  Σ_axis comm(axis, n_axis)     ≤  fabric_BW·T_step
stability: failures(T_wall) · downtime   ≤  budget
```

Every "why" in training engineering resolves to *which* of these
four is binding, and the design choice is *which one to relax by
changing another*.

## The three-number hardware model (reprise, tied to training)

From `Hardware/README.md` — for training, rewrite the three numbers
as **compute** (peak FLOPs), **memory** (HBM capacity + BW),
**fabric** (NVLink intra / IB inter):

| | H100/H800 SXM [F: vendor] | B200 SXM [F: vendor, fetched 2026-08-20] |
|---|---|---|
| Peak FLOPs (BF16 dense) | 989 TFLOP | 2,250 TFLOP (2.25 PFLOP) |
| Peak FLOPs (FP8 dense) | 1.98 PFLOP | **4.5 PFLOP** (2× H100 FP8) |
| Peak FLOPs (FP4 dense) | n/a | 9.0 PFLOP |
| HBM | 80 GB (H100) / 141 GB (H200) HBM3 | 180 GB HBM3e |
| HBM BW | 3.35 TB/s (H100) | 8 TB/s |
| Intra fabric | NVLink 3, 900 GB/s/GPU | NVLink 5, 1.8 TB/s/GPU (14.4 TB/s/node) |
| Inter fabric | 8×400G NDR IB (50 GB/s/link) | 8×400G NDR IB/eth (50 GB/s/link) |

**[I] The 2026 implication:** B200 delivers ~2.2× BF16 / ~2.3× FP8
compute and 2× HBM BW *per GPU*, and NVL72 makes a 72-GPU
fast-fabric island (72 × 180 GB = 12.96 TB HBM — ≈ 20 H100
nodes' worth of memory; 9 H100 nodes' worth of *GPU count*).
That's the whole reason the 2025–26 frontier shifted to
"fewer, bigger NVLink domains + aggressive EP inside them"
[I: DeepSeek-V3.2 DSA + NVL72-class deployments].

## Coupling 1 — architecture ↔ memory (HBM decides the precision)

The per-GPU memory equation (`Parallelism.md`):
`12N/n_shard + 2(34L+48h)·B·S·d/n_...`. Two architecture knobs hit
this directly:
- **MoE** → N_total ↑ but N_act flat → *stored* memory ↑, *compute*
  flat. Memory becomes the binding constraint, not FLOPs. This is
  why **MoE models are trained in FP8 (FP4 training is
  2026-emerging, not yet the 2024–25 standard), not BF16**
  [I: DeepSeek-V3 trained on H800 in FP8, 2412.19437] — a 671B
  model in BF16 is
  ~1.34 TB of *params alone*, which won't fit even sharded across
  thousands of 80GB GPUs without extreme sharding; FP8 halves it to
  ~0.67 TB. [E: 671e9 × 2B = 1.34e12 B; × 1B = 0.67e12 B]
- **GQA/MLA** → KV-cache shrink → *inference* memory drops, but at
  *training* time it barely matters (training recomputes K/V,
  doesn't cache the full sequence). [I: head-design is an
  *inference* knob first, a *training* knob second — a common
  confusion.]

**Decision rule [I]:** if 12N/n_shard > HBM·0.8 even at your max
shard, the architecture (not the cluster) is the problem → either
smaller N, more sharding (more GPUs), or lower precision (FP8).

## Coupling 2 — architecture ↔ fabric (the comm pattern is chosen
by the split, and the split is chosen by the fabric)

Each parallelism axis has a *mandatory* comm pattern
(`Parallelism.md` table). The fabric forces the assignment:

```
NVLink domain (≤8, or ≤72 on NVL72)  ← TP, and usually EP, SP
   (fast, low-latency, AllReduce/AllToAll)
IB/Ethernet inter-node (50 GB/s/link) ← DP (AllReduce), PP (P2P)
   (bandwidth-bound, latency-tolerant)
```

**[E] The hard proof (from `Parallelism.md`):** a 70B flat-DP
AllReduce across IB is ~140 GB/GPU/step → 5.6 s at 50 GB/s, vs
~0.6 s compute time. **The fabric alone forbids large flat DP.**
So:
- TP must live in NVLink (2 AllReduce/layer — latency-killer
  otherwise).
- EP (AllToAll) must live in NVLink/NVL72 (many small messages).
- DP AllReduce is the *only* big comm that's tolerable on IB, and
  only with hierarchical reduction + SHARP.

**This is the single most important architectural↔fabric coupling:
the model's layer count and head design are chosen so that the TP
split (≤8) leaves an integer number of layers for PP, and the expert
count is a multiple of the EP group. (Concrete example: Llama-3 405B
is 126 layers — divisible by 9, 14, 18, 21, 42, 63 — a practical
PP/TP/EP split set; DeepSeek-V3's 256 experts divide evenly by 8,
16, 32, 64, 128, 256.) [I: standard "make the numbers divide
evenly" practice]

## Coupling 3 — precision ↔ compute (the FLOPs/BW tradeoff)

The roofline (`Inference/Roofline.md`, but applies to training
prefill): compute-bound regimes want **FLOPs**, memory-bound want
**BW**. In training:
- **Forward/backward GEMMs** are compute-bound → *more peak FLOPs*
  helps (B200's FP8 = 2× H100 FP8 FLOPs → ~2× prefill throughput).
- **Optimizer state** is memory-BW-bound (12N of reads/writes per
  step) → *HBM BW* helps; this is why ZeRO-Offload exists (move
  optimizer state to CPU DRAM when HBM BW is the bottleneck, at the
  cost of PCIe bandwidth). [I]
- **FP8 training** [F: DeepSeek-V3 2412.19437; Hopper+]: 2× GEMM
  throughput + half the param memory, *if* you keep FP32 master
  weights + FP32 Adam state (else divergence). [I: the "FP8 fwd/bwd,
  FP32 optimizer" split is the 2024–26 standard].

**Decision rule [I]:** B200/GB200 → FP8 training by default; H100 →
BF16 with selective FP8; A100 → BF16 only. The precision is a
*hardware* decision, not a model one.

## Coupling 4 — wall-clock ↔ stability (the 10k-GPU term)

The cost model (`Scaling-1-to-10k.md`):
```
total = 6·N_act·D / (peak·n_gpu·MFU) × (1 + downtime_frac)
```
The `(1 + downtime_frac)` term is *the stability tax*. It grows with
cluster size (more nodes → more failures) and shrinks with the
stability stack (elastic + fast restart + spike policy). **[E]
DeepSeek-V3 worked example:** 6·37e9·1.48e13 /
(989e12·2048) = 451 h at 100% MFU [E]. The run took
**2.788M H800-GPU-hours / 2048 GPUs = 1,361 h wall-clock = 57
days** [E: 2.788e6/2048 = 1361 h]. So effective
**MFU ≈ 451/1361 ≈ 33%** [E] on the *activated*-FLOPs basis
(H800 peak = 989 TFLOP, the H100-class compute figure
[F: vendor]). This is a **non-circular back-calc**: 451 h is the
*ideal* wall-clock at 100% MFU computed from first principles
(6·N_act·D / peak·n_gpu), and 1361 h is the *reported* wall-clock
(2.788M GPU-h / 2048 GPUs), so the ratio is a genuine MFU estimate
independent of either input. The DeepSeek-V3 paper does **not**
report an MFU figure (verified 2026-08-20: 0 occurrences of "MFU"
/ "Model FLOPs Utilization" in the full paper text) — this 33% is
our reconstruction. A ~33% activated-MFU on a 671B-total /
37B-activated MoE is at the low end of the dense 40–60% band
[I] — consistent with MoE AllToAll overhead + 57 days of
stability overhead. (Assumes H800 peak FLOPs = H100's 989 TFLOP,
which is vendor-true for the compute part [F].)

## The $/token model (the endgame)

Everything collapses to **$/training-token**:
```
GPU-h / token = 6·N_act / (peak · MFU · 3600)      [E: FLOP/(FLOP/s) = GPU-s; /3600 → GPU-h]
$/token       = GPU-h/token · $/GPU-h + wasted_gpu_h/D
```
**[E] Worked example (DeepSeek-V3, empirical GPU-h basis — no
peak-FLOP assumption needed):** 2.788M H800-GPU-hours /
1.48e13 tokens = **1.88e-7 GPU-h/token** [E: 2.788e6/1.48e13].
At $3.5/GPU-h ([I: 2024–26 on-demand H100-class; committed/spot
~$1.5–2.5]) → **$6.6e-7/token ≈ $659 per billion training
tokens** [E]. The total pretraining compute bill is ~**$9.8M**
[E: 2.788e6 × $3.5] — before cluster overhead (power/cooling/
networking, ~1.5–2× [I]), the stability tax, and post-training/RL.
Cross-check via the formula: 6·37e9/(989e12·0.33·3600) =
1.90e-7 GPU-h/token [E] → consistent with the empirical 1.88e-7
[E]. [UNVERIFIED: exact 2026 $/GPU-h varies by contract; use as
order-of-magnitude.]

**[I] The strategic read:** every one of the five levers (bigger
N_act, more D, higher MFU, lower $/GPU-h, lower downtime) is a
*$/token* lever. "Is 10k GPUs worth it?" is answered by whether
the MFU + stability gains beat the $/GPU-h premium — and for
frontier labs the answer is yes: a 55% MFU × 1.4% downtime
configuration (elastic + fast restart [E: 62.5 h / 4,320-h window])
beats a 40% MFU × 5% downtime configuration at the
same $/GPU-h by ~**1.43×** [E: (0.55×0.986)/(0.40×0.95) =
0.5423/0.3800 = 1.427].
That's the entire MegaScale result restated as a $/token delta
[F: 2402.15627 reports 55.2% vs ~41% baseline, "1.34× MFU
improvement"].

## The decision checklist (real run, start to finish)

1. **Pick (N, D)** from `Scaling-Laws.md` for your $/token budget.
2. **Pick precision** from hardware (B200→FP8, H100→BF16/FP8).
3. **Fit check:** 12N/n_shard + A ≤ HBM·0.8 → pick n_shard
   (ZeRO level) and recompute policy.
4. **Pick TP** = NVLink domain size (8, or 72 on NVL72).
5. **Pick EP** = expert-count / n_ep (must divide evenly).
6. **Pick PP** = remaining layer-span across nodes; m ≥ 4p.
7. **Pick DP** = remainder; check the AllReduce fits the fabric
   (hierarchical + SHARP).
8. **Pick SP** if S > 32k (Ring/Megatron-SP on the TP group).
9. **Set the stability stack:** async checkpoints, elastic
   scheduling, straggler detection, spike policy.
10. **Set MFU target** (45–55% at scale) and a *comm-overlap*
    budget; profile before you scale.
11. **Re-plan at the first OOM / spike / straggler** — the plan is
    a hypothesis, not a spec. [I]

## Key takeaways

1. Training design is the *intersection* of four inequalities
   (compute, memory, fabric, wall-clock) — the binding one picks
   the next lever.
2. **Architecture↔fabric:** the split (TP/EP/PP/DP) is chosen by
   the fabric, and the model's layer/expert counts are chosen to
   divide evenly by the split — "make the numbers divide" is a
   real constraint.
3. **MoE flips the binding constraint** from FLOPs to HBM → hence
   FP8/FP4 training for MoE.
4. **Stability is a $/token term**, not an ops footnote: at 10k
   GPUs, downtime_frac is the difference between a $10M and a
   $15M run.
5. Everything collapses to **$/training-token = 6·N_act/(peak·MFU)
   · $/GPU-h + wasted/D** — the one number to optimize.

## References

- MegaScale (55.2% MFU, full-stack) — `2402.15627` [F, verified]
- DeepSeek-V3 (FP8, 2.788M H800-h, MoE) — `2412.19437` [F,
  verified]
- Kimi K2 (1T MoE, MuonClip) — `2507.20534` [F, verified]
- H100/B200 specs — vendor pages fetched 2026-08-20
  (`/tmp/te-research/b200.html` + H100 page)
- Roofline (compute vs BW) — `Inference/Roofline.md` (wiki)
- $/GPU-h figures — [UNVERIFIED] 2026 market rates vary; use as
  order-of-magnitude only.
