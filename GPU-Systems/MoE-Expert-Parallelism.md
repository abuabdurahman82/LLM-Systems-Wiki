# MoE and Expert Parallelism
`LAST_UPDATED: 2026-08-21 · Status: core page` · PART XXII. [E] numbers are
hand-derived/Python-verified this session; model specs re-checked against the arXiv
abstracts and full text of 2412.19437, 2401.04088, 2401.06066 on 2026-08-21.

## 30-Second Explanation
A MoE layer replaces the dense FFN with **N experts** (small FFNs) + a **router** that
sends each token to only its **top-k** experts. Total parameters grow with N; activated
parameters stay ~constant (k experts' worth) → "big but cheap per token". Expert
Parallelism (EP) shards the **experts** across GPUs: router picks top-k → **AllToAll
dispatch** each token to the GPU holding its experts → grouped expert GEMM → **AllToAll
combine** back. Because any token can go to any expert, the AllToAll is a full shuffle:
at EP=8, 87.5% of dispatched bytes cross the fabric [E]. Load is not uniform → **hot
experts** make one GPU the bottleneck; **capacity factors** bound its buffers. MoE
inference is a **networking problem wearing a GEMM costume** [I].

## The MoE Layer — router → expert → combine
### What
One Transformer layer's FFN becomes N small FFNs (experts) plus a router:
```
router:  g = TopK( gate( h · W_gate ) , k )      W_gate ∈ R^(d × N)
output:  y = Σ_i g_i · E_i(h)                    E_i = expert i's FFN
```
Modern models add **shared experts** (always-on, dense residual path) alongside the
routed ones: DeepSeek-V3 has 1 shared + 256 routed experts per MoE layer [F:
arXiv:2412.19437]; the shared+routed design goes back to Switch Transformer
[F: arXiv:2101.03961]. Only N routed experts must be *sharded*; the shared expert is
just a dense FFN.
### Why
MoE decouples **stored capacity** from **per-token compute** [F: arXiv:2401.04088]:
- Mixtral 8x7B: 47B total, **13B active** per token (8 experts, top-2) [F: arXiv:2401.04088].
- DeepSeek-V3: 671B total, **37B active** per token (256 routed, top-8) [F: arXiv:2412.19437].
Total/active ratio: 47/13 ≈ 3.6× and 671/37 ≈ 18.1× [E: from the cited figures].
You pay in **memory** (all expert weights resident) and **communication** (routing),
not in FLOPs — which is why a 671B model can serve at 37B-class compute.
### How
Per token, per MoE layer: (1) a tiny gate GEMM `h·W_gate` over N experts, (2) top-k
selection, (3) k expert FFNs on the selected experts, (4) gated weighted sum. In
inference the gate GEMM is trivial (d×N×b: 7168×256×2 B ≈ 3.7 MB read [E: for
d=7168, N=256, BF16]); the experts dominate. Gate form is a design choice:
normalized-softmax top-k (Switch-style [F: arXiv:2101.03961]) vs sigmoid (unnormalized)
gates [A: varies by model].
### When
Every token, in every MoE layer, in both prefill and decode. DeepSeek-V3 uses MoE in
all FFN layers **except the first three** (dense) [F: arXiv:2412.19437] — those dense
layers are exactly what EP can't shard and TP must cover.
### Hardware impact
All N expert weights must be resident (HBM) or offloaded. At decode, the k selected
experts' weights are streamed per token → more HBM bytes/token than a dense FFN with
equal active params [I: roofline-derived; cf.
`../Model-Architectures/Mixture-of-Experts.md`]. EP exists to divide those bytes.
### Inference impact
- **TTFT:** prefill MoE = k expert GEMMs with M=S (compute-bound, parallel across
  experts) — fast when experts are split across GPUs.
- **ITL:** decode MoE ≈ k expert GEMVs; the lever is EP (bytes ÷ EP) until AllToAll wins.
- **KV cache:** unaffected — MoE is FFN-side, KV formula unchanged.
### Example
DeepSeek-V3 expert: d=7168, expert intermediate dim 2048 [F: arXiv:2412.19437].
With a 3-matrix SwiGLU-style FFN [A: 3 matrices assumed], expert weights =
88,080,384 B ≈ 88.1 MB (84 MiB) [E: hand-derived]. 256 experts →
≈ 22.5 GB (21.0 GiB) of routed-expert weights **per layer** [E: 256 × 84 MiB]; × 58 MoE layers
(all but the first 3 [F: arXiv:2412.19437]) is the 671B bulk — why you shard.
### Failure modes
Training: **expert collapse** (a few experts hog all tokens) — fought with auxiliary
load-balancing loss (Switch) or auxiliary-loss-free balancing (DeepSeek-V3)
[F: arXiv:2412.19437]. Inference: capacity overflow, hot-expert tail latency (below).
### How to measure it
Per-layer gate histograms (tokens/expert distribution), routed vs shared expert bytes
in HBM, and expert-visit counts from the engine's routing table.

## The EP data path — 4 steps, 2 AllToAlls
```
 EP=4, N=128 experts (32/rank) · B tokens in flight · each token picks top-2 experts

 GPU0 (E0–31)         GPU1 (E32–63)        GPU2 (E64–95)        GPU3 (E96–127)
┌──────────────┐    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Step 1 ROUTER│    │              │     │              │     │              │
│ local gate:  │    │              │     │              │     │              │
│ tok x → E5,  │    │              │     │              │     │              │
│        E70   │    │              │     │              │     │              │
└──────┬───────┘    └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │  Step 2: ALLTOALL DISPATCH — each rank ships token rows to
       │  the ranks holding the chosen experts (x → GPU0 for E5, x → GPU2 for E70)
       ▼              ▼                     ▼                     ▼
┌──────────────┐    ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Step 3 EXPERT│    │              │     │              │     │              │
│ GROUPED GEMM │    │              │     │              │     │              │
│ (per-expert  │    │              │     │              │     │              │
│  small GEMMs)│    │              │     │              │     │              │
└──────┬───────┘    └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │  Step 4: ALLTOALL COMBINE — expert outputs ship back to the
       │  token's HOME rank, which sums g_i·E_i(h) (gate-weighted combine)
       ▼              ▼                     ▼                     ▼
      token x output on its home rank → next layer
```
- **Step 1 (router):** local — a gate GEMM + top-k, no communication.
- **Step 2 (dispatch):** AllToAll **out** — token rows fly to expert-holding GPUs.
- **Step 3 (expert GEMM):** each rank runs many small GEMMs (one per local expert,
  different M each) — **grouped GEMM**; see `./GEMM.md` and `Custom-GEMM.md`.
- **Step 4 (combine):** AllToAll **back** to home ranks; gate-weighted sum.
Two collectives **per MoE layer** [F: DeepSeekMoE arXiv:2401.06066; Mixtral
arXiv:2401.04088 both dispatch/combine every token].

## All-to-All dispatch/combine — the MoE collective
### What
**AllToAll:** every rank sends a *different* slice to *every other* rank in one
collective (the transpose of the send matrix). EP's dispatch is an AllToAll where
slice (i→j) = "the tokens on rank i whose top-k includes an expert on rank j".
Combine is the reverse-direction AllToAll for results.
### Why
Tokens have **no fixed shard** — unlike TP (column i always lives on rank i) or PP,
a token's destination is decided *by the router, per token*. Only a full-mesh
collective can move an arbitrary permutation in one shot.
### How
NCCL AllToAll (`ncclAlltoall`), typically over NVLink intra-node or RDMA cross-node
(`./NCCL.md` for the collective machinery, `./Multi-Node.md` for the fabric). Each
rank also ships gate metadata (which experts, gate values) so the receiving expert
can weight its output. Dispatch volume one way = **B·k·d·b** bytes (b = bytes/param),
both ways = 2·B·k·d·b [E: derived — k routed slots/token, d hidden dim].
### When
Every MoE layer, every step, in prefill and decode. With 58 MoE layers, a step carries
58×2 AllToAlls' worth of movement.
### Hardware impact
Both **bandwidth and latency** matter:
- **Large B (prefill/throughput decode):** bandwidth-bound — volume B·k·d·b grows linearly.
- **Small B (interactive decode):** latency-bound — 112 KiB moves in ~0.13 µs at
  ~900 GB/s NVLink but ~2.3 µs at ~50 GB/s IB NDR *before adding round-trip latency*
  [E: 114688 B ÷ 900e9 vs 50e9 B/s; latency adds tens–hundreds of µs].
- The **remote fraction** of dispatched bytes is (E−1)/E for a uniform router:
  75% at EP=4, 87.5% at EP=8, 98.4% at EP=64 [E: (E−1)/E]. Wider EP = more of the
  model on the *slow* fabric.
### Inference impact
EP expert time ÷ EP, **until** the AllToAll dominates. At B=1 the expert GEMV is
trivial (84 MiB of weights ≈ 26 µs at 3.35 TB/s H100 [E: 88.1e6 B ÷ 3.35e12 B/s])
AllToAll + its latency can be the *entire* MoE layer cost; batching amortizes it.
### Example
DeepSeek-V3, B=1, top-k=8 (routed), d=7168, BF16:
- dispatch one way = 8·7168·2 = **114,688 B = 112 KiB** [E: hand-derived].
- dispatch + combine both ways = **229,376 B = 224 KiB** [E].
Mixtral (d=4096 [F: Mixtral-8x7B config.json], k=2), B=1: 2·4096·2 = 16 KiB one way, 32 KiB
both ways [E]. Small messages → the fabric's **latency**, not its bandwidth, sets
per-token cost at B=1 [I].
### Failure modes
Hot expert oversubscribes one rank's receive queue; fabric contention when many
ranks' AllToAlls overlap; EP across a slow fabric (PCIe ~64 GB/s: 112 KiB ≈ 1.8 µs
pure BW [E] + latency, ×58 layers × per-token → seconds of idle).
### How to measure it
`nccl-tests` `alltoall_perf` per message size on your fabric; Nsight Systems timeline
(AllToAll kernels between expert kernels); DCGM fabric-utilization per rank;
per-rank send/recv byte counters from the engine.

## Token routing — top-k gating
- **Top-k selection:** gate scores all N experts; only the k highest get the token
  (Mixtral: 2 of 8 [F: arXiv:2401.04088]; DeepSeek-V3: 8 of 256 routed
  [F: arXiv:2412.19437]). k=1 (Switch-style) is max-specialized but brittle; k=2–8
  balances capacity vs communication.
- **The gate:** `softmax` (scores sum to 1, "how the probability mass splits") vs
  `sigmoid` (independent per-expert weights) [A: model-dependent]. The gate is what
  the router *learns* to spread: during training the router is pushed (aux loss or
  router-FM balancing) toward even expert visit counts.
- **Load-spreading in practice:** real traffic is *not* uniform — a handful of experts
  are popular for common content (code, math, certain languages). The gap between the
  median and the hottest expert is the whole imbalance story (next section).
- **DeepSeek-V3 adds a routing constraint:** each token is sent to **at most 4 nodes**
  [F: arXiv:2412.19437] — an explicit placement objective, not just load balance.

## Expert imbalance — the hot-expert problem
Tokens are not uniformly distributed: some experts are "hot". The hot expert's GPU
does more work than its peers → **its latency is the layer's latency** — EP's
speedup collapses to the slowest rank, not the average.
```
B=32 tokens · N=8 experts · top-2 → 64 expert-slots. Uniform: 8/expert.
E5 is 3× hot (24 tokens); the other 7 split 40 → ~5.7 each [E: (64−24)/7].

 EP=4, 2 experts/rank:
 GPU0: E0,E1 → ~11 tokens ┐
 GPU1: E2,E3 → ~11 tokens │ balanced ranks: ~11 tokens each
 GPU2: E4,E5 → 5.7+24 ≈ 30 tokens ┐
 GPU3: E6,E7 → ~11 tokens ┘        ┘ HOT RANK: ~3× the work of the rest
                                   ─────────────────────────────────
 step time = time on GPU2, not the average (2.7× here [E: 30/11])
```
At DeepSeek-V3 scale the uniform expectation is tiny: 8 slots over 256 experts =
3.125% of the batch per expert [E: 8/256]; a 3× hot expert takes ~9.4% — still a
round of extra work on its rank while the other 31 experts on that rank sit idle
within the step [I].

## Capacity factors & routing efficiency
- **Capacity factor:** each expert's input buffer holds `capacity = expected_load ×
  factor` (typically 1.0–1.5× in training). **Training:** tokens above capacity are
  dropped from that expert (the drop is exactly what the load-balancing loss fights).
  **Inference:** you can't drop a user's token — you either grow the buffer (more
  HBM) or serialize/overflow; capacity overflow shows up as tail-latency spikes on
  hot experts [A: engineering convention; factor values vary by deployment].
- **Routing efficiency** = useful expert slots ÷ dispatched slots. Two losses:
  **dropped** tokens (over-capacity in fixed-buffer training-style serving) and
  **redundant** work when the same token hits two experts on the *same* rank (no
  comm saved, but no harm) or when hot experts force the whole step to wait.
  A perfect-uniform router has 100% efficiency; a 3× hot expert with 1.0 capacity
  factors drops ~33% of the overflow on its rank [E: (3−1)/3 of the hot expert's
  traffic exceeds its 1× slot] unless the buffer absorbs it [A].

## Expert placement
Which expert sits on which rank is a first-class decision:
- **Uniform round-robin** (expert i on rank i mod E) is the default and fine when load
  is ~uniform.
- **Co-locate frequently co-selected experts:** if E5 and E70 are chosen together
  often, putting them on the same rank turns a 2-rank hop into a local GEMM — the
  router histogram is the data source [A: standard practice].
- **KV-aware / node-aware placement:** DeepSeek-V3 constrains each token to ≤ 4 nodes
  [F: arXiv:2412.19437]; its reference decode deployment uses **EP320 with one expert
  per GPU**, reserving 64 GPUs for redundant + shared experts [F: arXiv:2412.19437] —
  redundancy is a *placement* choice that buys hot-expert headroom.
- **Hot-expert migration:** re-sharding the hottest experts to under-loaded ranks at
  runtime is an open serving-systems direction [I].

## Communication bottlenecks — why MoE becomes a networking problem
- AllToAll is a **full shuffle**: every rank both sends and receives, so *all* links
  are busy at once — there is no idle-pair to hide in, and fabric contention is
  systemic, not pairwise.
- **Small B → latency regime:** 58 MoE layers × 2 AllToAlls × per-step latency means
  the *collective's startup/round-trip time* — not its bandwidth — sets ITL at B=1
  on RDMA fabrics [I]. NVLink (intra-node, ~900 GB/s [F: NVIDIA H100 spec]) makes
  EP "free-ish"; IB NDR (~50 GB/s/link [F: vendor spec]) makes every EP degree cost
  real latency — see `./Scale-Up-vs-Scale-Out.md` and `./Multi-Node.md`.
- **Large B → bandwidth regime:** volume B·k·d·b grows linearly with batch; wide-EP
  deployments (EP=320-class) are only viable where the AllToAll fits the fabric's
  bisection bandwidth [I].
- The practical consequences: keep EP **intra-NVLink-domain when possible**; push EP
  cross-node only where RDMA is fast; overlap AllToAll with expert compute where the
  engine permits; and remember that fabric upgrades (NVLink5/IB NDR320) buy MoE
  throughput directly [A].

## Modern MoE models
| Model | Experts | top-k | Hidden d | Total / active | Notable |
|---|---|---|---|---|---|
| Mixtral 8x7B [F: arXiv:2401.04088] | 8 | 2 | 4096 [F: config.json] | 47B / 13B | first open frontier MoE; 3.6× ratio [E] |
| DeepSeekMoE [F: arXiv:2401.06066] | mN fine-grained + Ks shared | mK | — | — | fine-grained expert segmentation (mN experts, mK active) for specialization |
| DeepSeek-V3 [F: arXiv:2412.19437] | 256 routed + 1 shared | 8 routed | 7168 | 671B / 37B | aux-loss-free balancing; ≤4-node routing; 18.1× ratio [E] |
DeepSeekMoE's core move: split each coarse expert into **m fine-grained experts** and
activate **mK** of them — more, smaller, more specialized, with **shared experts**
holding common knowledge [F: arXiv:2401.06066]. Fine-grained experts are *smaller
GEMMs per expert* — grouped-GEMM efficiency and AllToAll granularity both shift
(see `./GEMM.md`). DeepSeek-V3 inherits it at scale: 61 layers, d=7168, expert
intermediate 2048, MoE everywhere except the first 3 dense layers [F: arXiv:2412.19437].

## Hybrid EP+TP — the standard MoE serving stack
MoE layers mix **dense parts** (attention, shared experts, the first dense layers)
with **routed experts**, and those parts want different fabrics:
- **TP within node (NVLink):** attention + shared/dense layers. AllReduce is
  latency-critical → needs the fast fabric (`./Tensor-Parallelism.md`).
- **EP across nodes (RDMA):** routed experts. AllToAll is bandwidth-tolerant per
  token but volume-heavy → it's the cross-node parallelism dimension
  (`./Multi-GPU.md` § EP, `../Distributed-Inference/README.md`).
- Reference: DeepSeek-V3's minimum decode deployment = **40 nodes / 320 GPUs**,
  attention at TP4+SP with DP80, **MoE at EP320** (one expert per GPU, 64 GPUs
  holding redundant + shared experts) [F: arXiv:2412.19437].
So the 2024+ MoE stack = **TP intra-node for the dense/shared path + EP across the
NVLink/RDMA boundary for the experts + DP replicas for throughput**, exactly the
composition in `./Multi-GPU.md` §6 and `./Scale-Up-vs-Scale-Out.md`.

## Key Takeaways
1. **MoE = capacity without compute:** 671B stored, 37B active [F: arXiv:2412.19437];
   you pay in HBM residency + AllToAll, not FLOPs.
2. **The data path is 4 steps:** router (local) → AllToAll dispatch → grouped expert
   GEMM → AllToAll combine — two collectives per MoE layer.
3. **AllToAll is the bottleneck:** a full shuffle where (E−1)/E of bytes cross the
   fabric [E]; latency-bound at small B, bandwidth-bound at large B.
4. **Hot experts beat EP speedup:** the layer waits on its busiest rank; capacity
   factors, placement (co-location, redundancy, ≤4-node routing) and load-balancing
   are the fixes.
5. **The serving stack is hybrid:** TP within node (dense/attention), EP across nodes
   (experts), DP for scale-out — fabric decides each split.

## Related
`./Multi-GPU.md` · `./Tensor-Parallelism.md` · `./Pipeline-Parallelism.md` ·
`./NCCL.md` · `./Multi-Node.md` · `./Scale-Up-vs-Scale-Out.md` · `./GEMM.md` ·
`./Custom-GEMM.md` · `./Topology.md` · `../Model-Architectures/Mixture-of-Experts.md` ·
`../Distributed-Inference/README.md` · `../Hardware/README.md`.

## References
- [F] DeepSeek-V3 Technical Report — arXiv:2412.19437 (671B/37B; 256+1 experts, top-8,
  d=7168, expert intermediate 2048, MoE in all but first 3 layers; EP320 reference
  deployment; ≤4-node routing; aux-loss-free balancing).
- [F] Mixtral of Experts — arXiv:2401.04088 (8 experts, top-2, 47B total / 13B active).
- [F] DeepSeekMoE: Towards Ultimate Expert Specialization in MoE LMs —
  arXiv:2401.06066 (fine-grained mN/mK experts + shared experts).
- [F] Mixtral 8x7B hidden dim 4096 — model config.json (HF: mistralai/Mixtral-8x7B-v0.1),
  consistent with the Mistral-7B base architecture [F: arXiv:2310.06825].
- [F] Switch Transformers — arXiv:2101.03961 (top-1 routing, auxiliary load-balancing loss).
