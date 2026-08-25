# NCCL for LLM Engineers (PART XXIII)
`LAST_UPDATED: 2026-08-21 · Status: core page` · Source note: NCCL behavior
cross-checked against the official repo/docs (github.com/NVIDIA/nccl); all
hardware constants taken from `../Hardware/README.md` and the style guide bank.

## 30-Second Explanation
**NCCL (NVIDIA Collective Communications Library)** is the de-facto engine that
implements multi-GPU collective operations — AllReduce, AllGather, ReduceScatter,
Broadcast, AllToAll, Send/Recv — over whatever fabric is available:
NVLink/NVSwitch, PCIe, InfiniBand, RoCE [F: nccl repo, github.com/NVIDIA/nccl].
Every parallelism strategy in `./Multi-GPU.md` *pays* in NCCL collectives:
```
TP   → 2× AllReduce / layer   → wants NVLink (lowest latency, highest BW)
EP   → 2× AllToAll / MoE layer → wants NVSwitch intra-node or fast RDMA
PP   → Send/Recv / stage      → any fabric, RDMA cross-node
FSDP → AllGather + ReduceScatter → bandwidth-hungry
```
A **rank** is one GPU (or one process); a **communicator** is a group of ranks
that share a collective. NCCL's job is to pick, per communicator and per message
size, the fastest path (NVLink > P2P/PCIe > shared memory > RDMA > TCP) and a
fast algorithm (ring for large messages, tree for small). **The fabric you
actually have decides which parallelism you can run** — that mapping is the whole
point of this page.

## What NCCL Is
- A C/C++ library + CUDA kernels; the framework (PyTorch `torch.distributed`,
  Megatron-Core, TRT-LLM, vLLM/SGLang multi-GPU backends) calls into it for every
  collective [F: nccl repo].
- It is **not** the fabric itself: it builds on NVLink/P2P, shared memory,
  GDRCopy, IB verbs (RC/UC), and TCP sockets, and it **enumerates the topology at
  init time** to route around it.
- It ships `nccl-tests` (`all_reduce_perf`, `alltoallv_perf`, …) that report
  **busbw** — "bus bandwidth" — defined for ring AllReduce as
  `busbw = 2(n−1)/n · S / time`, i.e. the ring-traffic convention below [F: nccl docs].
- Open source, BSD-3 licensed [F], CUDA-only; on AMD the equivalent is RCCL (a fork) [I].

## Ranks and Communicators
- **Rank:** identity number `0..n−1` of one participant. In single-node
  PyTorch, rank = GPU index; multi-node, rank = (node, local GPU) pair [I].
- **Communicator (comm):** the group of ranks that execute a collective
  together; `ncclCommInitRank` creates one. All ranks in a comm must agree on the
  same sequence of calls (collectives are **synchronous barriers** — every rank
  must enter).
- **World communicator:** the comm over *all* n ranks. **Sub-communicators:**
  the usual split in practice — e.g. one comm per TP group of 8 (NVLink),
  one comm per PP/EP group, one comm for the data-parallel replicas. A layer's
  AllReduce runs in the TP comm, not the world comm [I: standard layout].
- Consequence: a collective's cost depends on **its comm's size and fabric**,
  not on the cluster size. TP=8 on a 1024-GPU cluster still pays an 8-GPU
  AllReduce — provided the TP group is contained in one NVLink domain.

## The Six Collectives
| Collective | Math | LLM use | Cost (ring, size S) | Best fabric |
|---|---|---|---|---|
| **AllReduce** | every rank gets `Σ_i x_i` | TP: 2×/layer (after attn, after MLP) | 2(n−1) steps; wire 2(n−1)/n·S | NVLink/NVSwitch |
| **AllGather** | every rank gets `[X_1…X_n]` (rank i holds chunk X_i) | ZeRO-3/FSDP param gather; MoE gather | (n−1) steps; wire (n−1)/n·S | NVLink / IB |
| **ReduceScatter** | rank j gets chunk j of `Σ_i x_i` | ZeRO-1 grad partition | (n−1) steps; wire (n−1)/n·S | NVLink / IB |
| **Broadcast** | every rank gets `X_root` | init/broadcast of weights; small sync | 1 hop (NVSwitch) or ~log n (tree) | any |
| **AllToAll** | rank i sends chunk i→j to rank j for all j (full shuffle) | EP dispatch+combine; CP/Ulysses | per-rank send (n−1)S/n | NVSwitch intra; fast RDMA inter |
| **Send/Recv** | point-to-point: rank j gets X_i | PP stage-to-stage activations | S + 1 latency | any; RDMA cross-node |

### AllGather (compact)
- **Intuition:** "each rank contributes a chunk; everyone ends up with the full
  tensor." Rank i owns `X_i` of size S/n; after the op every rank holds all n
  chunks, i.e. the full S.
- **Use in LLMs:** ZeRO-3/FSDP gathers sharded weights right before use
  [F: ZeRO arXiv:1910.02054]; MoE "combine" of expert outputs.
- **Cost:** (n−1) ring steps; wire traffic (n−1)/n·S (half of AllReduce's, no
  reduction half).

### ReduceScatter (compact)
- **Intuition:** "reduce and keep only your piece." Sum everything, then each
  rank keeps only 1/n of the result — the inverse shape of AllGather.
- **Use in LLMs:** ZeRO-1 gradient partitioning: all-reduce grads, but each rank
  only stores its shard [F: ZeRO arXiv:1910.02054]. Note
  `AllReduce = ReduceScatter + AllGather` exactly (and the ring runs both
  back-to-back — that's *why* 2(n−1) steps).

### Broadcast (compact)
- **Intuition:** one rank's tensor to everyone. Trivial over NVSwitch (1 hop);
  over a tree, ~log n steps.
- **Use in LLMs:** weight init, small control data; rarely on the hot path.

### Send/Recv (compact)
- **Intuition:** point-to-point; no group semantics, no barrier.
- **Use in LLMs:** PP stage-to-stage activations [I]; P/D KV transfer uses
  RDMA copies rather than a pure NCCL op (see `Prefill-Decode-Disaggregation.md`).
- **Cost:** S bytes + one link latency — the cheapest collective per byte.

## AllReduce (the TP workhorse) — full treatment
### What
Every rank in the comm holds a tensor `x_i` (same shape); after the op, every
rank holds `x_i + x_j + … + x_n` (or the mean — division is done by the caller).
It is the single most latency-exposed op in LLM inference.
### Why
TP splits a layer's GEMMs (col/row-parallel); the partial results are
**sharded along the feature dim** and must be summed back before the next
layer — 2× per layer, once after attention, once after the MLP
[F: Megatron-LM arXiv:1909.08053]. Two per layer × ~32 layers × every token:
if one AllReduce takes 76 µs (worked example below), that is ≈ 4.6 ms of
pure comm per forward pass at TP=8 on NVLink [E].
### How
NCCL's ring: the tensor is split into n chunks; phase 1 (ReduceScatter) spends
n−1 steps circulating and summing chunks; phase 2 (AllGather) spends n−1 steps
circulating the reduced chunks. Every step moves S/n bytes per rank on every
link, so the ring is **bandwidth-saturating**: ~2 links' worth of traffic
(2(n−1)/n·S) with all links busy simultaneously.
### When
TP inside an NVLink/NVSwitch domain (n ≤ 8, up to 72 on NVL72). Never TP across
nodes: 2(n−1) hops over RDMA latency multiplies into ms [I].
### Hardware impact
NVLink lanes are shared with P2P; NCCL kernels also occupy SMs, so a giant
AllReduce steals SMs from the GEMM it's supposed to feed [I]. NVSwitch makes
the "one ring" a physical all-to-all fabric — latency stays ~1 hop even for
AllToAll [F: NVIDIA NVSwitch docs].
### Inference impact
ITL directly: TP's promise is compute ÷ n, but ITL ≈ compute/n + 2·t_AllReduce
per layer. At TP=8 on H100 NVLink the comm adds ~76 µs × 2 × 32 layers ≈
4.8 ms/pass for a 32MB AllReduce (decode with large batch); at batch=1 the
AllReduce payload shrinks with S (S = B·d·2 bytes), so the comm term falls
[ E, I].
### Example
32 MB AllReduce, n=8, NVLink ~900 GB/s: wire = 2·(7/8)·32 MB = 56 MB;
56 MB / 900 GB/s ≈ 62.2 µs + 2·7·1 µs ≈ 14 µs latency ≈ **76 µs** [E] — full
arithmetic in the cost model below.
### Failure modes
- TP group not contained in one NVLink domain → ring falls to PCIe (~64 GB/s):
  875 µs per AllReduce instead of 62 µs [E: 56/64].
- Straggler rank: the collective is a barrier — one slow rank's GPU (power
  cap, ECC storm, thermal) serializes all 8.
- See "Failure modes" section below for GDR/topology variants.
### How to measure it
`all_reduce_perf` from nccl-tests: read the `busbw` column and compare to
fabric peak (NVLink ~900 GB/s aggregate [F: style bank]); NCCL_DEBUG=INFO shows
the chosen transport (NVLink vs P2P/IPC vs NET/IB); Nsight Systems shows the
NCCL kernels on the GPU timeline competing with GEMMs.

## All-to-All (the MoE workhorse) — full treatment
### What
Each rank holds an n×S/n block-matrix of chunks; rank i sends its chunk i→j to
rank j for every j. After the op, rank j holds the whole row of chunks it was
sent — a **full shuffle** with no reduction.
### Why
MoE EP: the router sends each token to its chosen expert's GPU
(**AllToAll dispatch**), experts compute, results come back (**AllToAll
combine**) [F: DeepSeekMoE arXiv:2401.06066; Mixtral arXiv:2401.04088]. CP/Ulysses
splits attention heads and shuffles K/V the same way [F: arXiv:2309.14509].
Two AllToAlls per MoE layer, every token, so the MoE layer's comm time ≈
2·t_AllToAll [I].
### How
n−1 independent point-to-point transfers per rank (S/n bytes each). Over
NVSwitch all 7 (of 8) transfers overlap on the switch fabric; over RDMA, NCCL
pipelines them over the available HCAs. Wall-clock ≈ total per-rank send
(n−1)S/n divided by the rank's *aggregate* fabric bandwidth, assuming all
transfers overlap — the model used in the example below.
### When
Intra-node: NVSwitch (NVL72 made wide-EP practical [F: NVIDIA NVL72]).
Cross-node: only on fast RDMA with enough HCA links, and then EP degree
suffers — which is why "TP intra-node + EP across nodes" keeps EP small
[I: ./Multi-GPU.md default stack].
### Hardware impact
AllToAll is the one collective that needs **many** high-BW links simultaneously:
it is the workload NVSwitch and fat-tree IB topologies are designed for
[I: ./Topology.md]. A PCIe-only box doing EP is a recipe for comm-dominant MoE.
### Inference impact
MoE ITL ≈ expert compute/EP + 2·t_AllToAll. If tokens are imbalanced, the
largest (n−1)S/n transfer — not the average — sets the time, because the ring/
P2P waits for the last peer [I]. Hot expert → its inbound chunk > S/n → tail
latency; capacity factors and expert placement are the fixes
(`./MoE-Expert-Parallelism.md`).
### Example
n=8, total buffer S=32 MB: per-rank send = (7/8)·32 MB = 28 MB. Over NVLink
~900 GB/s: 28 MB / 900 GB/s ≈ **31 µs** [E]. Over one 50 GB/s IB NDR link:
28/50 ≈ **560 µs** [E] — an 18× gap, and ×2 for dispatch+combine per layer.
### Failure modes
- EP across a slow fabric (PCIe): AllToAll dominates the layer.
- Expert imbalance: one rank's send/receive > S/n → collective stalls on the
  slowest peer.
- IB/RoCE misconfig under 8-way shuffle: loss, PFC pauses, retransmits.
### How to measure it
`alltoallv_perf` (busbw column); DCGM per-link NVLink utilization (all 7
neighbors should be ~saturated and ~equal during EP); NCCL trace shows which
transport per peer (NVLink vs NET/IB).

## Ring vs Tree vs Hierarchical
```
The ring (n=4 shown; AllReduce = 2(n−1) = 6 steps total):

                G0 ───────────────► G1
                │ c0               │ c1
                │                  │
                ▼                  ▼
               G3 ◄─────────────── G2   chunk c_i lives on rank i

Phase 1 · ReduceScatter (n−1 = 3 steps). Each step, every rank simultaneously
sends one S/n chunk to its right neighbor AND adds the chunk it just received
to the one it holds for forwarding:
  step 1: G0→G1(c0), G1→G2(c1), G2→G3(c2), G3→G0(c3)
  step 2: G1→G2(c0+c1), G2→G3(c1+c2), G3→G0(c2+c3), G0→G1(c3+c0)
  step 3: G2→G3(c0+c1+c2), G3→G0(c1+c2+c3), G0→G1(c2+c3+c0), G1→G2(c3+c0+c1)
  → rank i now holds the FULL sum of its own chunk c_i.

Phase 2 · AllGather (n−1 = 3 steps): the reduced chunks rotate the same way;
after 3 more steps every rank holds all 4 reduced chunks = the AllReduce result.
```
| Algorithm | Steps | Latency | Bandwidth | Wins when |
|---|---|---|---|---|
| **Ring** | 2(n−1) | ∝ n (bad as n grows) | near-optimal (~BW/2 aggregate) | large messages; n ≤ ~32; uniform fabric |
| **Tree** | ~2·log2(n) | ∝ log n (good) | ~BW/n at large S (poor) | small messages; latency-critical; large n |
| **Hierarchical** | (n_node−1) + 2·log2(n_nodes) | inter-node part only log-scaled | near-ring inside nodes | multi-node: ring intra-node + tree inter-node [F: NCCL supports node-grouped algos] |

Intuition: ring = "everyone moves data every step, saturate the links"; tree =
"few hops, but the trunk link is shared by n ranks, so big messages serialize
at the top". NCCL picks per message size — typically tree (or a small ring
variant) for small messages, ring for large ones; the choice is logged at
`NCCL_DEBUG=INFO` [I: observed behavior].

## Communication Cost Model
**Communication convention (state before doing arithmetic):** two counts are
confused in the literature. (1) **Net-data**: unique new bytes a rank gains =
(n−1)/n·S for AllReduce. (2) **Ring-traffic / wire traffic**: total bytes a rank
*sends* over all 2(n−1) ring steps = 2(n−1)/n·S. This wiki uses the
**ring-traffic** convention (it equals what nccl-tests `busbw` measures and
what the links actually carry) [F: nccl docs; I: convention choice].
Time model: `t ≈ wire/BW + 2(n−1)·τ`, where BW = the rank's aggregate
fabric bandwidth and τ = hop latency.

### Worked example: AllReduce, n=8, S = 32 MB, NVLink ~900 GB/s [E]
```
S = 32 MB = 3.2×10⁷ bytes (GB=10⁹; this is 29.8 MiB)
wire  = 2·(n−1)/n·S = 2·(7/8)·32 MB = 56 MB
t_bw  = 56×10⁶ B / 900×10⁹ B/s = 62.2 µs
t_lat = 2·(n−1)·τ = 14 hops × 1 µs/hop = 14 µs   (τ ≈ 1 µs NVLink hop [A])
t_all ≈ 62.2 + 14 = 76.2 µs
```
Same AllReduce, other fabrics [E]:
- PCIe 5.0 x16 (~64 GB/s): 56/64 = 875 µs + 14 ≈ **889 µs** — 11.7× slower.
- IB NDR (~50 GB/s/link): 56/50 = 1120 µs + 14 ≈ **1.13 ms**.
That 15×–17× spread between NVLink and PCIe/IB is *why* TP lives inside the
NVLink domain and PP/EP get the inter-node fabric (`./Scale-Up-vs-Scale-Out.md`).

### Worked example: AllToAll, n=8, S = 32 MB [E]
```
per-rank send = (n−1)·S/n = 7·32/8 = 28 MB
NVLink (aggregate 900 GB/s, transfers overlap): 28/900 ≈ 31.1 µs
IB NDR (~50 GB/s): 28/50 ≈ 560 µs
```
(Assumption: the rank's send bandwidth is the *aggregate* of its links, all
transfers in flight; serialized peers would multiply this. [A])

### Sanity read [I]
TP=8, 32 layers, 32 MB AllReduce: 2 × 32 × 76 µs ≈ 4.9 ms comm per forward
pass. If your forward pass is ~10 ms, you are ~half comm-bound — shrink S
(batch/dim), keep TP inside NVLink, or reduce AllReduce count (overlap, or
TP=4 + PP instead). Effective NCCL bandwidth is typically below line-rate;
treat the model as an upper bound [A].

## NCCL ↔ the Fabric
NCCL probes the topology at communicator init (NVLink links, PCIe roots,
shared-memory paths, RDMA HCAs) and assigns each channel a transport
[I: mechanism]:
| Fabric | Where | Properties | NCCL collectives it serves |
|---|---|---|---|
| NVLink | intra-node, 8 GPUs | ~900 GB/s aggregate (H100) [F: style bank], ~1 µs hops [A] | TP AllReduce, FSDP |
| NVSwitch | intra-node all-to-all | any-to-any 1 hop; no P2P bottleneck | AllToAll, wide EP, NVL72 domains |
| PCIe 5.0 x16 | intra-node fallback | ~64 GB/s, higher latency | P2P/IPC when P2P off |
| InfiniBand NDR | inter-node | ~50 GB/s/link, lossless, adaptive routing | PP, EP, CP, P-D |
| RoCE | inter-node, Ethernet | same RDMA semantics, needs PFC/ECN tuning | PP, EP, P-D |
| TCP sockets | bootstrap only | slow; used for init/control, not data | (none on hot path) |

How the choice plays out [I]:
- **Intra-node:** NCCL prefers NVLink P2P for TP comm; with NVSwitch it can run
  AllToAll without a "ring" bottleneck.
- **Inter-node:** NCCL uses IB verbs (GDR = GPU-memory-direct, no host bounce
  when enabled); the number of HCAs per node × their bandwidth sets the
  inter-node floor.
- **Multi-node comm:** the hierarchical algorithm (ring inside node, tree
  across nodes) keeps the 2(n−1)-step penalty mostly on the fast fabric.
Topology is the silent variable — wrong GPU↔NIC or PCIe-root placement halves
measured throughput; read `nvidia-smi topo -m` first (`./Topology.md`). The
fabric itself (IB vs RoCE, GDR, SHARP in-network reduction) is covered in
`../Networking/README.md`; node anatomy and NUMA/NIC affinity in `./Multi-Node.md`.

## Debugging and Tuning
```bash
export NCCL_DEBUG=INFO            # WARN=errors only, INFO=transports+algos, TRACE=per-op
export NCCL_DEBUG_FILE=/tmp/nccl_%h_%p.log   # %h=host %p=pid; keep per-rank logs
export NCCL_DEBUG_SUBSYS=INIT,GRAPH,NET,COLL # narrow the noise
nccl-tests: ./all_reduce_perf -b 8M -e 256M -f 2 -g 8   # busbw column
```
Key knobs [F: nccl docs — verify current names upstream]:
- `NCCL_P2P_LEVEL` — where P2P (NVLink/PCIe direct) is allowed; if P2P is
  unavailable NCCL falls back to shared memory or a host copy.
- `NCCL_IB_HCA` — which IB HCAs to use (e.g. `mlx5_0,mlx5_1`); `NCCL_IB_DISABLE=1`
  forces non-IB (debugging, not production).
- `NCCL_SOCKET_IFNAME` — which interface bootstrap/control uses; a wrong value
  makes init slow or hang (symptom: all ranks stuck in `ncclCommInit`).
- `NCCL_ALGO=Ring|Tree`, `NCCL_PROTO=Simple|LL|LL128` — force algo/proto to
  isolate regressions (measure the default first; [I] forced choices are rarely
  better than auto).
- GDR knobs (`NCCL_NET_GDR_LEVEL` etc.) — keep GPU-direct on for IB paths.
**Reading an NCCL INFO trace:** (1) init block — the topology NCCL saw (NVLink
link count, HCAs, P2P/IPC enablement); a "P2P disabled" line on an NVLink box is
a red flag. (2) per-channel transport lines — `NVLink`, `P2P/IPC`, `NET/IB`,
`SHM` tell you *which* link each channel uses; mixed transports in one comm =
topology problem. (3) COLL lines show the selected ALGO/PROTO and channel count
per collective. Correlate with busbw: if busbw ≈ 1/2 of fabric peak, suspect a
channel using the slow path.

## Failure Modes
1. **Wrong topology:** TP group straddles PCIe roots / GPU pair lacks the
   NVLink path → ring runs on PCIe; measured AllReduce ~10× slower than the
   NVLink case above (875 vs 62 µs [E]). Check `nvidia-smi topo -m`
   (`./Topology.md`).
2. **P2P disabled** (IOMMU, `NCCL_P2P_LEVEL`, driver): NVLink P2P off → NCCL
   bounces through shared memory or host PCIe copies; same 5–15× collapse
   [I]. Trace line: `P2P disabled`.
3. **IB vs RoCE misconfig:** RoCE without proper PFC/ECN → head-of-line
   blocking, retransmits, latency spikes under AllToAll shuffle; IB with
   wrong HCAs pinned (`NCCL_IB_HCA`) → one slow link. `../Networking/README.md`.
4. **Straggler:** every collective is a barrier — one rank's thermal/power/ECC
   hiccup serializes all ranks; ITL tail = slowest rank. Watch per-GPU clocks +
   DCGM ECC counters (`GPU-Metrics.md`).
5. **GDR off on IB path:** data bounces GPU→host RAM→NIC→host RAM→GPU; doubles
   copies and adds host-BW contention; enable GPUDirect RDMA for P2P and
   cross-node collectives [F: NVIDIA GPUDirect RDMA].
6. **Bootstrap/interface wrong:** `NCCL_SOCKET_IFNAME` mismatch → slow/hanging
   init, not a throughput bug — read the log before tuning.
7. **Cross-node TP:** the 2(n−1)-step ring pays inter-node latency per step;
   ms-scale AllReduce × 2 × layers. Keep TP intra-node [I].

## How to Measure It (page-level)
- `all_reduce_perf` / `alltoallv_perf` busbw vs fabric peak (NVLink ~900 GB/s,
  PCIe ~64 GB/s, IB ~50 GB/s/link [F: style bank]) — characterizes the fabric,
  not your model.
- Nsight Systems: NCCL kernel time as a fraction of step time; if > 30%,
  comm-bound (`Profiling.md`).
- DCGM: per-NVLink and per-NIC utilization — balanced across the comm? A quiet
  link inside an NVSwitch group means the wrong path is being used.
- Sweep `TP`, `EP`, `batch` and plot ITL; the slope reveals where comm eats
  compute (`Labs.md` Lab 18/19; `Perf-Experiment-Template.md`).

## Key Takeaways
1. **NCCL is the collective engine, not the fabric** — it routes over
   NVLink/NVSwitch/PCIe/IB/RoCE and picks ring vs tree per message size.
2. **AllReduce pays 2(n−1)/n·S ring traffic**; at n=8, S=32 MB, NVLink that is
   ~76 µs [E] — and TP calls it 2× per layer, every token.
3. **AllToAll is MoE's tax:** per-rank (n−1)S/n send, 31 µs on NVLink vs 560 µs
   on one IB link [E] — why EP wants NVSwitch inside the node.
4. **Match collective → fabric:** TP AllReduce → NVLink; PP Send/Recv → any;
   EP/CP AllToAll → NVSwitch or fast RDMA; FSDP → bandwidth.
5. **When it's slow, read the trace before tuning:** P2P disabled, wrong
   topology, straggler rank, GDR off, or RoCE PFC — in that order of frequency
   [I].

## Related
`./Multi-GPU.md` · `./Tensor-Parallelism.md` · `./Pipeline-Parallelism.md` ·
`./MoE-Expert-Parallelism.md` · `./Multi-Node.md` · `./Scale-Up-vs-Scale-Out.md` ·
`./Topology.md` · `../Networking/README.md` · `../Hardware/README.md` ·
`Prefill-Decode-Disaggregation.md` · `Distributed-Architectures.md` ·
`../GPU-Communication/README.md` · `../GPU-Communication/04-nccl-deep-dive.md`.
