# Tensor Parallelism — Column/Row-Parallel GEMMs and the 2 AllReduce per Layer
`LAST_UPDATED: 2026-08-21 · Status: core page` · TP deep-dive of `Multi-GPU.md`. Column/row
formulation follows Megatron-LM [F: arXiv:1909.08053]; all [E] arithmetic is hand-derived
inline and Python-verified this session.

## 30-Second Explanation
Tensor Parallelism splits **each layer's weight matrices across N GPUs**, so every GPU
computes a partial result and the partials are combined. Only two primitives are needed:
- **Column-parallel**: `Y = X·A` with `A = [A1 | A2]` (split column-wise). GPU *i* computes
  `X·Ai` independently — **zero communication** in the forward GEMM; the output is split
  column-wise.
- **Row-parallel**: `Y = B·X` with `B = [B1; B2]` (split row-wise). GPU *i* computes `Bi·X`
  — a *partial* sum of `Y` — then **one AllReduce** sums the partials.
A Transformer layer pairs them: QKV (column) → per-head attention (no comm) → output
projection (row, **AllReduce #1**); MLP up (column) → MLP down (row, **AllReduce #2**).
Net: **2 AllReduce per layer, every token** [F: Megatron-LM arXiv:1909.08053]. That is why
TP only works on a fast, low-latency fabric: NVLink ~900 GB/s [F: NVIDIA H100 SXM spec]
carries it; InfiniBand ~50 GB/s/link is a 18× slowdown [E: 900/50] and cross-node TP is
painful. TP is the **first** split for latency (per-token work ÷ TP) but it **cannot scale
past the node** (the fabric) — see `Multi-GPU.md` for the decision flow.

## Where this page sits
- The overview, the four problems, and the decision flow: `Multi-GPU.md` — this page is
  the deep dive of its TP section.
- Which collective TP uses and how it is implemented: `NCCL.md`. The fabrics themselves:
  `../Networking/README.md`, `Multi-Node.md`, `Scale-Up-vs-Scale-Out.md`.
- Why every op on this page is a GEMM/GEMM and what B=1 means for it: `GEMM.md`.
- Training-side parallelism (TP × PP × DP × ZeRO; TP in inference is the forward-only
  special case): `../Training-Engineering/Parallelism.md`.
- The six-dimension catalog (TP row): `../Distributed-Inference/README.md`.

## The core idea
Split each layer's weight matrices so that (a) each GPU holds 1/TP of the layer's weights
(capacity), (b) each GPU streams 1/TP of the weights per token (decode latency — the GEMM
degenerates to a GEMV at B=1, `GEMM.md`), and (c) each GPU's Tensor Cores do 1/TP of the
layer's FLOPs (throughput). The price is communication on the critical path: **2
AllReduce per layer per forward pass** [F: Megatron-LM arXiv:1909.08053].

Two matrix splits cover everything, because every linear layer in a Transformer is a
GEMM and the two GEMM dimensions behave differently:
- **Split the *output* dimension (N):** outputs are *disjoint* columns → no combination
  needed in forward. This is the **column-parallel** case (name follows the weight
  matrix being split column-wise).
- **Split the *reduction* dimension (K):** each GPU produces a *partial* sum of the full
  output → must be summed. This is the **row-parallel** case (the weight matrix is split
  row-wise; its rows ARE the reduction axis of the product `Y = B·X`).
Nothing is numerically changed: each output element is still computed once, just on a
different GPU. [I: the two splits are an algebraic identity; the whole design is making
the algebra match the hardware.]

## Column-parallel linear layer (primitive 1)
`Y = X·A`, `X ∈ R^{B×k}`, `A ∈ R^{k×n}`. Split `A` column-wise into `TP` shards
`[A1 | A2 | … | A_tp]` with `A_i ∈ R^{k×(n/tp)}`. GPU *i* computes `Y_i = X·A_i ∈
R^{B×(n/tp)}`.

### What
Each GPU holds `n/tp` columns of `A` and computes its disjoint slice of `Y`. `X` is
**replicated** on all GPUs (it's small: `[B,k]`). No data leaves the layer on the forward
path — the column-split output is carried *through* the next op (attention heads, or the
MLP activation) and only combined when a row-parallel layer follows.

### Why
Free in forward: the GEMM cost simply divides by TP and no collective sits on it. You
*always* pair it with a row-parallel layer downstream, whose AllReduce recovers the full
vector — so the split is "banked" until needed.

### How
1. Layout: `A` stored as `[k, n]`; shard by columns: GPU *i* owns columns
   `[i·n/tp, (i+1)·n/tp)`. Requires `n % tp == 0` (see Failure modes).
2. Forward: each GPU runs the GEMM `Y_i = X·A_i` locally (`GEMM.md` — M = B, N = n/tp,
   K = k; at B=1 this is a GEMV over the shard).
3. Backward (training only): `dA_i = Xᵀ·dY_i` is local; `dX = dY·Aᵀ` is partial →
   **AllReduce** in backward [I: consistent with `../Training-Engineering/Parallelism.md`].
4. Inference (this page): forward only — **0 collectives**.

### When
Use for the layer's **first** projection: QKV (attention) and MLP up (W1/W3 of SwiGLU).
These produce a wide intermediate (heads, or 4d) that is consumed *per-head* or
*per-shard* by the next op, so no combination is possible or needed yet.

### Hardware impact
Weight shard on GPU *i*: `k·(n/tp)` params. Activation `X` is replicated — at B=1 it is
trivial (a few KB), at prefill S it costs `S·k·2B` per GPU (unsplit; this is where
sequence-parallel attention saves memory, `../Training-Engineering/Parallelism.md`).

### Inference impact
Per-token GEMV bytes ÷ TP → ITL ÷ TP (ideal, before comm); prefill GEMM FLOPs ÷ TP →
TTFT ÷ TP. No direct comm cost on this primitive.

### Example [E]
LLaMA-2 7B-class QKV fused weight `W_qkv ∈ R^{4096×12288}` (3×d out), BF16:
- Full: `4096·12288·2 = 100.7 MB`. Decode B=1 GEMV at 3.35 TB/s H100 HBM3:
  `100.7e6 / 3.35e12 ≈ 30.0 µs` (Python-verified).
- TP=8 shard: `4096×1536` → `4096·1536·2 = 12.6 MB` → `12.6e6/3.35e12 ≈ 3.8 µs`.
  **÷8 in both memory and time, zero communication.** (Kernels at these N are
  bandwidth-bound — `GEMM.md` — so the time scales with the bytes.)

### Failure modes
- `n` not divisible by TP → shard sizes unequal / padding (see "Unbalanced shapes"
  below). For QKV, the binding constraint is **heads** (h or h_kv per GPU).
- `X` replication at large prefill S wastes HBM — mitigations live in
  sequence/context-parallel attention, not in col-parallel itself.

### How to measure it
It contributes nothing to the comm budget; verify the *weight shard* on each rank
(param count per rank = 1/TP of the layer's) and that Nsight Systems shows **no NCCL
kernel** between the col-parallel GEMM and the following per-head/per-shard op.

## Row-parallel linear layer (primitive 2)
`Y = B·X`, `X ∈ R^{B×k}`, `B ∈ R^{n×k}`. Split `B` row-wise into `[B1; B2; …]` with
`B_i ∈ R^{(n/tp)×k}`. GPU *i* computes `Y_i = B_i·X ∈ R^{B×(n/tp)}` — a **partial sum**
over the K-dimension of the true `Y = B·X`. The full `Y = Σ_i Y_i` is recovered by
**one AllReduce**.

### What
Each GPU holds `n/tp` *rows* of `B` (i.e., `n/tp` of the input dimensions of the product
are folded on this GPU), produces a partial output, and the group sums them. This is the
**only collective in TP**: 2 per layer (one after attention's output projection, one
after the MLP down projection) [F: Megatron-LM arXiv:1909.08053].

### Why
The reduction (K) dimension must be *shared* input on every GPU, so the only thing you
can split is *how much of the sum each GPU computes*. Splitting K gives partial sums;
summing partial sums is exactly an AllReduce. You could instead AllGather the input —
that moves more data (`(n-1)/n·M` in vs `(n-1)/n·M` out, two ops); AllReduce is the
minimal single-op form.

### How
1. Layout: `B ∈ R^{n×k}`; GPU *i* owns rows `[i·n/tp, (i+1)·n/tp)`; `X` is replicated
   (or is the column-split output of the preceding col-parallel layer, which each GPU
   already has locally).
2. Forward: local GEMM `Y_i = B_i·X`, then `AllReduce(Y_i)` → `Y` on all ranks
   (NCCL ring: reduce-scatter + allgather — `NCCL.md`).
3. Backward (training only): `dB_i = Yᵀ·Xᵀ…` — `dB_i` needs full `X` and full `Y`
   (both local) → local; `dX = Bᵀ·Yᵀ` is partial → **AllReduce** [I: consistent with
   the 4 AllReduce/layer fwd+bwd accounting in
   `../Training-Engineering/Parallelism.md`].
4. Inference: **1 AllReduce per such layer**, on the critical path of every token.

### When
Use for the layer's **last** projection: attention output projection `Wo` and MLP down
(W2 of SwiGLU). Anything that must hand a *full, summed* vector to the next sub-block
(residual add, norm) needs the AllReduce here — nowhere else it can be hidden.

### Hardware impact
Weight shard: `(n/tp)·k` params on each GPU (1/TP of the layer's matrix). The AllReduce
buffer is the *activation* `[B, n]` in BF16 — small at B=1, large at prefill S
(see the [E] section below).

### Inference impact
This is where TP **costs** latency: 2 AllReduce/token/layer × L layers sit in series with
every GEMM. If the fabric is slow, ITL grows *additively* per layer — the classic
"TP is latency-bound" symptom.

### Example [E]
LLaMA-2 7B-class MLP down projection `W2 ∈ R^{11008×4096}`, BF16, TP=8:
- Shard per GPU: `11008/8 = 1376` rows → `W2_i ∈ R^{1376×4096}` = `1376·4096·2 =
  11.3 MB` → B=1 GEMV `11.3e6/3.35e12 ≈ 3.4 µs` (Python-verified).
- Partial sum on each GPU: `[B, 4096]`; at B=1 that is `1·4096·2 = 8 KB`.
- AllReduce of 8 KB over NVLink ~900 GB/s (ring, net-data convention):
  `2·(7/8)·8192 B = 14,336 B` of ring traffic → `14336/900e9 ≈ 15.9 ns` of pure transfer
  (Python-verified). The *actual* latency is dominated by kernel launch + ring sync
  (microseconds, fabric-dependent) — see the comm-cost section.

### Failure modes
- Slow fabric: this AllReduce is the whole TP tax — 18× slower on IB than NVLink
  [E: 900/50] → cross-node TP collapse.
- Uneven `n` across shards → unequal GEMM work + an AllReduce with mismatched arrival
  times (the ring waits for the slowest rank).

### How to measure it
NCCL's `all_reduce_perf` for the fabric's AllReduce curve (`NCCL.md`); Nsight Systems:
the `nccl` kernel between the down-projection GEMM and the residual add **is** this
AllReduce — measure its time vs the GEMM time at your B/S (`Labs.md`).

## How a Transformer layer uses both
Megatron's recipe for one decoder layer [F: arXiv:1909.08053]:

| Sub-block | Split | Collective |
|---|---|---|
| QKV projection | **column-parallel** (n heads → h/tp heads per GPU) | none |
| Attention (QKᵀ, softmax, ·V) | per-head, local | none |
| Output projection `Wo` | **row-parallel** | **AllReduce #1** |
| + residual, RMSNorm | local | none |
| MLP up W1/W3 (SwiGLU) | **column-parallel** (4d → 4d/tp) | none |
| SiLU·mul, down W2 | W2 **row-parallel** | **AllReduce #2** |
| + residual, RMSNorm | local | none |

Why attention itself needs no communication: the column-parallel QKV gives each GPU
`h/tp` complete Q, K, V heads — QKᵀ and AV are fully contained within a head, so each GPU
runs its heads locally. (GQA caveat: KV heads are shared across Q heads, so each GPU gets
`h_kv/tp` KV heads; TP > h_kv forces padding/replication — Failure modes.)

## Where communication happens — per-layer diagram
```
                      GPU 0            GPU 1 … GPU tp-1          (each GPU, forward)
                     ┌──────────┐   ┌──────────┐
   X [B,d] ────────► │  QKV col │   │  QKV col │   W_qkv split column-wise, no comm
                     │  (GEMM)  │   │  (GEMM)  │
                     └────┬─────┘   └────┬─────┘
                          │ h/tp Q,K,V heads per GPU
                     ┌────▼─────┐   ┌────▼─────┐
                     │ attention│   │ attention│   per-head: no comm
                     └────┬─────┘   └────┬─────┘
                     ┌────▼─────┐   ┌────▼─────┐
                     │  Wo row  │   │  Wo row  │   partial sums
                     └────┬─────┘   └────┬─────┘
                          ▼             ▼
                ═══════  ALLREDUCE #1 (attention)  ═══════   ← comm point 1
                          │ X' [B,d] full, on all GPUs
                     ┌────▼─────┐   ┌──────────┐
                     │ up W1/W3 │   │ up W1/W3 │   column-parallel, no comm
                     │ (GEMM×2) │   │  (GEMM×2)│
                     └────┬─────┘   └────┬─────┘
                     ┌────▼─────┐   ┌────▼─────┐
                     │  down W2 │   │  down W2 │   row-parallel → partial sums
                     └────┬─────┘   └────┬─────┘
                          ▼             ▼
                ═══════  ALLREDUCE #2 (MLP)  ═══════       ← comm point 2
                          │ H [B,d] full
                          └──► next layer (or embedding → logits)
```
Exactly **two** ring collectives per layer, on the critical path of every token
[F: Megatron-LM arXiv:1909.08053]. (Training pays for backward too: ×2 → 4
AllReduce/layer; `../Training-Engineering/Parallelism.md`.)

## The collective ops — what TP actually uses
| Op | What it does | In TP? |
|---|---|---|
| **AllReduce** | every rank ends with the *sum* (or mean) of all ranks' tensors | **YES** — after each row-parallel projection, 2/layer |
| **AllGather** | every rank ends with the *concatenation* of all ranks' tensors | no, in standard TP |
| **ReduceScatter** | each rank ends with *its slice* of the sum | no, in standard TP |
| **AllToAll** | each rank sends a different slice to each rank | no (that's EP/CP — `MoE-Expert-Parallelism.md`) |
| **Send/Recv** | point-to-point | no (that's PP — `Pipeline-Parallelism.md`) |

TP uses **AllReduce after the row-parallel projections** — and only that. The subtlety:
NCCL *implements* ring AllReduce as a ReduceScatter followed by an AllGather (`NCCL.md`),
so on the wire you see two phases per AllReduce; the op TP *issues* is still a single
AllReduce per row-parallel layer. [F: NCCL ring algorithm; arXiv:1909.08053 for the
layer recipe.]

## Comm cost math [E] — how much does one AllReduce cost?
**Convention (stated explicitly):** ring AllReduce, *net-data* convention. A ring
AllReduce of a per-rank tensor of `M` bytes moves `M·(n−1)/n` distinct bytes through the
ring in each of its two phases (reduce-scatter, allgather), so ring traffic per rank is
`2·(n−1)/n·M`, and time ≈ that divided by effective fabric bandwidth `BW`:

```
t_AllReduce ≈  2·(n−1)/n · (B·d·2B_bytes) / BW     [BF16 → 2 bytes/elem]
```

This is a **bandwidth** estimate; for small messages add a latency term `~2α` per phase
(kernel launch, ring sync) — at B=1 that term, not the transfer, dominates [I].

**Example 1 — decode, B=1, d=4096, n=8, NVLink ~900 GB/s** [E, Python-verified]:
- `M = 1·4096·2 = 8,192 B` (8 KB).
- Traffic `= 2·(7/8)·8192 = 14,336 B ≈ 14.3 KB`.
- `t ≈ 14336 / 900e9 ≈ 15.9 ns` of pure transfer — per AllReduce.
- Per token, L=80 layers: 160 AllReduce × 16 ns ≈ **2.5 µs of raw transfer** — negligible;
  the real cost is the per-op latency (µs-class), so 160 × ~1–5 µs ≈ 0.16–0.8 ms of
  critical-path comm [I: order-of-magnitude; measure on your fabric].

**Example 2 — prefill, S=4096, d=4096, n=8** (here the bandwidth term rules) [E]:
- `M = 4096·4096·2 = 33,554,432 B = 33.6 MB`; traffic `= 2·(7/8)·M ≈ 58.7 MB`.
- NVLink 900 GB/s: `58.7e6/900e9 ≈ 65.2 µs` per AllReduce.
- PCIe 5.0 x16 ~64 GB/s: `58.7e6/64e9 ≈ 0.92 ms` — **14× slower** [E: 900/64 ≈ 14.1].
- InfiniBand NDR ~50 GB/s/link: `58.7e6/50e9 ≈ 1.17 ms` — **18× slower** [E: 900/50 = 18].
- L=80 layers, both AllReduce points: 160 × 65.2 µs ≈ **10.4 ms/step on NVLink** vs
  160 × 1.17 ms ≈ **188 ms/step over IB** [E] — the fabric decides whether TP is usable.

## Interconnects for TP
| Fabric | Per-GPU BW | Role for TP |
|---|---|---|
| PCIe 5.0 x16 | ~64 GB/s [F: PCIe 5.0 spec] | TP is painful: 0.92 ms AllReduce vs 0.065 ms on NVLink [E] |
| NVLink (H100) | ~900 GB/s aggregate [F: NVIDIA H100 SXM spec] | the standard TP fabric, 8-GPU node |
| NVSwitch | all-to-all intra-node, ~900 GB/s/GPU | makes the 8-GPU node one flat low-latency domain; NVL72 extends to 72 GPUs [I: NVIDIA NVL72 domain] |
| InfiniBand NDR 400G | ~50 GB/s/link [F: NDR spec] | 18× slower than NVLink [E] → cross-node TP |
| RoCE (RDMA over Ethernet) | per-NIC, comparable at a given line rate; lossy fabric, no SHARP-class in-network reduction | [I: treat as IB-class for TP; UNVERIFIED head-to-head] |

Why cross-node TP is painful: every token pays 2·L AllReduce; over IB instead of NVLink
each prefill AllReduce at S=4096, d=4096 goes from 65 µs to 1.17 ms [E], and decode adds
per-op RDMA latency on top. Hierarchical AllReduce / SHARP help, but they don't remove
the ~18× fabric gap [E] — so practice keeps TP inside the NVLink domain and moves the
slower axes (PP, EP, DP) across nodes [I: standard 2024+ practice;
`Multi-GPU.md`, `Scale-Up-vs-Scale-Out.md`, `Multi-Node.md`].

## Why TP demands high bandwidth *and* low latency
- **High bandwidth:** 2 AllReduce/layer carry the `[B, d]` (or `[S, d]`) activation every
  step — at prefill S that's tens of MB each (Example 2). Slow fabric → comm time adds
  to every step.
- **Low latency:** at decode B=1 the tensor is 8 KB — transfer is 16 ns [E], so the
  *fixed* cost (NCCL kernel launch, ring sync, NIC/switch latency) dominates. 160 of
  these per token are pure overhead if the fabric is slow or the topology is wrong.
- **On the critical path:** unlike DP's end-of-step gradient AllReduce (train) or PP's
  P2P (overlap with the next micro-batch), TP's AllReduce sits between two GEMMs of the
  *same token* — there is little or nothing to overlap against at B=1 [I].

## TP vs the other splits
- **Why TP first for latency:** it divides *per-token* work (weights ÷ TP, FLOPs ÷ TP)
  with a bounded, regular comm pattern — the only split that directly shrinks ITL.
- **Why it stops at the node:** the AllReduce is latency-critical and every-token; the
  ~18× IB/NVLink gap [E] breaks it across nodes. PP moves small P2P activations
  (bubble-tolerant, `Pipeline-Parallelism.md`), EP moves AllToAll only on MoE layers
  (`MoE-Expert-Parallelism.md`), DP replicates (no per-layer comm).
- **The practical stack:** TP inside the NVLink domain (≤8 GPUs, 72 on NVL72) +
  PP/EP/DP across nodes + router for DP — the decision flow in `Multi-GPU.md` and
  `../Distributed-Inference/README.md`.
- KV cache also shards with TP: each GPU holds `h_kv/tp` KV heads → KV memory ÷ TP,
  which is why TP additionally buys concurrency on top of latency [I: standard in
  vLLM/TRT-LLM layouts].

## Failure modes
1. **Cross-node TP:** 18× fabric slowdown [E] + per-op RDMA latency × 2L/token → ITL
   collapses. Fix: keep TP intra-node; use PP/EP across the fabric [I].
2. **TP on PCIe:** 0.92 ms prefill AllReduce vs 0.065 ms NVLink [E]; at B=1 the launch+
   sync latency over the host path makes ITL comm-dominated. Fix: use NVLink nodes, or
   TP=1 + DP/PP.
3. **Unbalanced shapes:** `d`, `d_ff`, or the head counts not divisible by TP →
   padding or uneven shards. Binding constraint in practice: **heads** — each GPU needs
   an integer number of Q heads (and, with GQA, of KV heads). TP = 16 with h_kv = 8
   forces KV-head replication/padding → wasted HBM + FLOPs (same class of waste as MMA
   tile padding, `GEMM.md`) [I]. Engines pick TP from the divisors; check
   `h % tp == 0` and `h_kv % tp == 0` before deploying.
4. **Activation recompute under TP:** at large prefill S, activations `[S, d]` (and the
   48h·B·S·d attention terms) can OOM *despite* weight sharding — the K-dim is split,
   not the S-dim. Selective/full recomputation (standard in training [F: Korthikanti et
   al. arXiv:2205.05198], ~⅓ extra forward FLOPs [I]) applies to inference prefill too;
   Megatron-SP shards the attention activations across the TP group to save the
   48h·B·S·d term [F: arXiv:2205.05198].
5. **Topology/NCCL path errors:** a GPU pair on the wrong PCIe switch, or P2P disabled,
   silently downgrades NCCL to the slow path → "TP works but ITL is 2×" [I;
   `Topology.md`, `Diagnostics.md`].

## How to measure it
- **Fabric baseline:** NCCL `all_reduce_perf` at your sizes (8 KB decode; 33 MB prefill)
  → build the AllReduce curve before touching the model (`NCCL.md`).
- **In-model comm:** Nsight Systems — the `nccl` kernels should appear exactly at the
  two diagram points; compare their time to the GEMM/GEMV time at your B/S.
- **Sweep:** ITL/TTFT vs TP degree on the same node (Labs.md) — the knee where comm
  catches up to compute is your max useful TP.
- **Sanity:** per-rank param count = layer params ÷ TP; per-rank KV = `h_kv/tp` heads.

## Key Takeaways
1. **Two primitives**: column-parallel (split output dim, 0 comm) + row-parallel (split
   reduction dim, 1 AllReduce); a layer is col → (local) → row, twice.
2. **2 AllReduce per layer, every token** [F: Megatron-LM arXiv:1909.08053] → TP's cost
   is on the critical path and scales with L.
3. **The math [E]**: `t ≈ 2(n−1)/n·B·d·2/BW` (ring, net-data) — 16 ns transfer at B=1
   (latency-bound), 65 µs at S=4096 on NVLink vs 1.17 ms on IB (18× [E]).
4. **TP lives inside the NVLink domain**; everything slower pushes that axis to
   PP/EP/DP across nodes.
5. **Check divisibility** (heads, d_ff, d) before choosing TP — unbalanced shapes waste
   HBM and FLOPs silently.

## Related
`Multi-GPU.md` (overview + decision flow) · `NCCL.md` (collectives) · `GEMM.md` (why
B=1 GEMV) · `Pipeline-Parallelism.md` · `MoE-Expert-Parallelism.md` · `Multi-Node.md` ·
`Scale-Up-vs-Scale-Out.md` · `Topology.md` · `Labs.md` (TP sweep) ·
`../Distributed-Inference/README.md` · `../Networking/README.md` ·
`../Training-Engineering/Parallelism.md` · `../Hardware/README.md`.
