# NCCL Deep Dive
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.
Verified against NCCL 2.31.2 documentation & repo (fetched 2026-08-25).

## 30-Second Explanation
**NCCL (NVIDIA Collective Communications Library)** is the topology-aware
communication engine under virtually all NVIDIA GPU workloads: it implements the
standard collectives (AllReduce, AllGather, ReduceScatter, Broadcast, …) *and*
P2P Send/Recv, and it is the de-facto standard — PyTorch's `torch.distributed`,
JAX/XLA, and every major serving engine call into it on NVIDIA hardware
[F: NCCL repo + PyTorch docs]. It supports both branches of the taxonomy:
**collective operations** and **point-to-point Send/Recv**. House deep-dive:
`../GPU-Systems/NCCL.md` (algorithms on NVLink, the 4.8 ms 32MB AllReduce).

## 1. Architecture
```text
PyTorch / JAX / TensorFlow / Application
                  │
                  ▼
                NCCL
                  │
       ┌──────────┼────────────┐
       │          │            │
     NVLink      PCIe       Network (NCCL NET)
       │                       │
   NVSwitch               IB / RoCE / TCP (sockets)
```
Key moving parts:
- **Communicator (`ncclComm`)** — the group handle; every operation runs in the
  context of one comm, which pins a set of ranks, transports, and channels.
- **Rank** — a participant's index in `[0, nranks)`; a *rank* is (process, device,
  communicator) — two ranks may share a physical GPU only with
  `NCCL_MULTI_RANK_GPU_ENABLE` (2.30+, experimental) [F: NCCL env docs].
- **CUDA streams** — collectives are stream-ordered; the app launches work on a
  stream and NCCL's kernels join that stream (or a proxy stream), enabling
  overlap. CUDA Graph capture of NCCL ops is supported since CUDA 11.3
  [F: NCCL CUDA Graphs docs].
- **Channels** — parallel communication paths NCCL opens inside a comm; more
  channels = more SMs and more NIC QPs working in parallel. `minCTAs`/`maxCTAs`
  (ncclConfig_t) bound them [F: NCCL types docs].
- **Topology discovery** — at init NCCL maps the local graph (NVLink, PCIe, NUMA,
  NICs) — the same data `nvidia-smi topo -m` exposes — and builds per-collective
  ring/tree graphs over it.
- **Transport selection** — per peer, per message-size, pick NVLink / P2P /
  shared memory / GDR / sockets; [05](05-nccl-algorithms-transport.md) details.
- **Network plugins (NET)** — `libnccl-net.so` ABI: NVIDIA ships `ib` (verbs) and
  `socket`; 2.31's logs show **three plugin slots** — NET, **GIN**, and **RMA**
  [F: NCCL 2.31.2 logging examples: "Assigned GIN plugin … / Assigned RMA plugin …"].
- **Proxy threads** — host-side threads that drive NIC work (WQE posting, CQ
  polling) for transports the GPU can't initiate; GIN/GDA removes the proxy from
  the path ([below]).
- **CUDA kernels** — the actual data movement is executed by NCCL's own SM-resident
  kernels (copy + signal), coordinated with the app's kernels via the stream.
- **Memory registration** — HBM regions are registered (pinned + GDR-mapped) so
  the NIC can DMA them; user buffer registration (`ncclCommRegister`) lets the
  app pre-register reusable buffers, cutting per-call setup
  [F: NCCL env `NCCL_GRAPH_REGISTER` + API docs].

## 2. Initialization sequence
```text
ncclGetUniqueId()          (rank 0 creates the id; app ships it to other ranks —
                            out-of-band, e.g. via env/bootstrap)
      ↓
Bootstrap                  (ranks exchange addresses; TCP/socket rendezvous)
      ↓
ncclCommInitRank()         (join the group; blocking or via ncclConfig_t)
      ↓
Topology Discovery         (local NVLink/PCIe/NUMA/NIC graph; remote via NET plugin)
      ↓
Transport Selection        (per peer: NVLink | P2P | SHM | GDR | socket)
      ↓
Channels Created           (parallel paths sized by CTA limits)
      ↓
Collective Ready           (comm returned; ops now stream-ordered)
```
What a **rank** is, precisely: the position of *this (process, GPU)* in this
communicator's ordering — `rank` identifies "who", `nranks` "how many", and
`comm` "which group". Split communicators (`ncclCommSplit`) let one process hold
multiple comms (TP comm × DP comm × EP comm — the standard 3D-parallel layout).

## 3. Algorithms (ring, tree, hierarchical)
**Ring** — every rank sends to its right neighbor and reduces along the circle;
reduce-scatter phase then allgather phase. Achieves near-line bandwidth because
every link is busy with (N−1)/N of the data in every phase [E: see 2(N−1)/N
factors in 02]. Cost: O(N) hops — latency grows with N.
```text
GPU0 → GPU1 → GPU2 → GPU3
 ↑                  ↓
 └──────────────────┘
```
**Tree** — hierarchical reduce up, broadcast down; O(log N) hops, so better
latency for small messages / wide collectives; sacrifices a little bandwidth
[../GPU-Systems/NCCL.md].
**Hierarchical** — ring within a node (NVLink), tree/ring across nodes (network):
```text
Node 1                    Node 2
GPU─GPU─GPU─GPU        GPU─GPU─GPU─GPU
      │                     │
      ▼                     ▼
   Network ◄──────────────►
```
NVLS (NVLink SHARP) generalizes this into a single hardware-offloaded operation
within the NVSwitch domain [F: NCCL env `NCCL_NVLS_ENABLE`].

## 4. Protocols (Simple, LL, LL128)
- **Simple** — large chunks, plain copies; best bandwidth at large sizes.
- **LL** — low-latency: 8-byte data + 8-byte flag per element; halves effective
  bandwidth but removes the final synchronization round; wins at small sizes.
- **LL128** — low-latency at 128-byte granularity (128B data + 128B flags);
  needs 128B-aligned data and a NIC/driver that supports it; the middle ground
  [F: NCCL env `NCCL_PROTO` docs].
NCCL picks (algo, proto) per size and topology; `NCCL_ALGO` / `NCCL_PROTO`
override — since 2.24 both accept per-function lists
(`allreduce:ring,tree;broadcast:ring` style, `^` for exclusion) [F: NCCL env docs].

## 5. Transport selection (conceptual)
```text
same GPU?        → (single device, no transport)
NVLink present?  → NVLink (via peer or via intermediate GPU: NVB/PXN)
PCIe P2P OK?     → P2P BAR mapping
same host?       → shared memory (host DRAM staging)
GDR-capable?     → GPUDirect RDMA (NIC↔HBM)
IB available?    → verbs (ib plugin)
else             → TCP sockets (last resort; "Using network Socket" in logs)
```
Relevant knobs: `NCCL_P2P_DISABLE`, `NCCL_SHM_DISABLE`, `NCCL_NET_GDR_LEVEL`
(GDR locality preference), `NCCL_PXN_DISABLE` (PXN = peer routing through an
intermediate GPU that owns the NIC) [F: NCCL env docs].

## 6. The network path, packet by packet
```text
GPU HBM
  │  (registered buffer; kernel writes chunks)
  ▼
NCCL kernel (SMs copy data into channel buffers, set signals)
  │
  ▼
GPU DMA / NIC engine reads via GDR mapping (PCIe P2P)
  │
  ▼
ConnectX NIC — post WQE, doorbell
  │
  ▼
RDMA verbs (ib plugin) — QP pairs to remote ranks, CQ completion
  │
  ▼
InfiniBand/RoCE fabric (lossless IB, or lossy + DCQCN RoCE, or EFA/SRD)
  │
  ▼
Remote NIC — completion on remote CQ
  │
  ▼
Remote NIC DMAs into remote GPU HBM (GDR) — proxy thread or GDA posts/acks
```
Mechanics: **memory registration** pins the HBM region and publishes an rkey;
**DMA** moves bytes without CPU; **queue pairs** (QP) are the RDMA connection
abstraction (one or more per peer, per channel); **completion handling** is CQ
polling by the proxy thread (or device-side with GDA); **synchronization** between
ranks is done by NCCL's own flags/signals in HBM, not by the network.
Multi-rail: with n NICs, NCCL opens channels on multiple NICs
(`nChannelsPerNetPeers`/`NCCL_MAX_NCHANNELS` style tuning) and stripes flows
[../GPU-Systems/Multi-Node.md; F: NCCL config docs].

## 7. Advanced features (mark: stable / experimental / hardware-gated)
- **Topology-aware communication** — stable since ~2.0 (graphs from the local
  topology; user topology XML override available).
- **Multiple NICs / multi-rail** — stable; per-rail channel assignment.
- **PXN** — stable (2.12+); routes a GPU's traffic through a peer GPU that owns
  the nearer NIC.
- **CollNet / SHARP** — hardware-gated (IB SHARP switch); `collnetEnable` in
  ncclConfig_t, default 0 [F: NCCL types docs].
- **NVLS / NVLink SHARP** — hardware-gated: NVLink4 (Hopper+, NVSwitch 3rd gen);
  `NCCL_NVLS_ENABLE` default 2 [F: NCCL env docs].
- **User buffer registration** — stable (2.11+ era; `ncclCommRegister`,
  `NCCL_GRAPH_REGISTER` for CUDA Graphs).
- **CUDA Graph support** — stable (CUDA ≥11.3; capture + replay).
- **Device API / GPU-initiated (GIN) + GDA** — **newer** (Device API shipped in
  2.28; GIN/GDA backends including IBGDA; EFA GDA contributed in 2.31):
  GPU threads directly issue Put/Get/Signal over the network — no proxy thread on
  the data path [F: NCCL deviceapi docs + 2.31 release notes].
- **CFT (Compute Fabric Transport)** — new in 2.31: host+device APIs to register
  windows and issue device-side Put/Get/Red/NVLS; **Blackwell + CUDA 13.3+ only**
  [F: NCCL 2.31.2 release notes].
- **NCCL EP** — new (nccl-ep v0.1.0 era): MoE dispatch/combine primitives built
  on LSA + GIN device operations; CUDA-Graph-compatible handles
  [F: NCCL EP release notes]. This is NVIDIA's answer to the EP branch of the
  taxonomy — see [10](10-uccl-collective-p2p-ep.md) and [14](14-moe-communication.md).
- **Per-collective configuration** — new in 2.31: `ncclCollConfig_t` APIs,
  per-collective algo/CTA overrides, `userTag` for profilers.
- **One-sided / RMA plugin slot** — emerging in 2.31 (see "RMA plugin" in logs)
  [F: NCCL 2.31.2 logging]; treat as experimental surface.

## 8. Version notes (do not confuse generations)
| Feature | Since |
|---|---|
| Ring/Tree + LL/LL128 | 2.5-era (stable) |
| CollnetChain/ Direct | 2.14+ |
| NVLS | 2.17+ |
| NVLSTree | 2.18+ |
| PAT | 2.23+ |
| Multi-rank-per-GPU | 2.30 (experimental) |
| Device API (GIN) | 2.28 |
| CFT, per-collective config, EFA GDA | 2.31 |

Deprecation warning: older docs' env-variable lists (e.g. `NCCL_BUFFSIZE`
tweaks, `NCCL_COLLNET_ENABLE`) have moved or changed defaults — check the live
2.31 env page before recommending; [17](17-troubleshooting.md) lists the current
debug set.

## Key Takeaways
1. NCCL = topology-aware engine for **both** collectives and P2P — the "collective
   library" label is shorthand, not the full picture.
2. comm → ranks → channels → transports: every knob in NCCL is a choice about one
   of those four objects.
3. Algorithms (ring/tree/hierarchical) × protocols (Simple/LL/LL128) form a
   per-size matrix; auto-selection is usually right, overrides are surgical.
4. 2.31 is the "device-initiated" inflection: GIN/GDA/CFT/EP move data-path work
   from host proxy threads onto the GPU.
5. Feature availability is hardware-gated (NVLS, SHARP, GDA, CFT) — read the env
   docs' "since X / hardware Y" lines before deploying.

## Related
[05 NCCL Algorithms & Transport](05-nccl-algorithms-transport.md) ·
[06 NCCL + RDMA + SHARP](06-nccl-rdma-sharp.md) ·
`../GPU-Systems/NCCL.md` ·
[19 Practical Labs](19-practical-labs.md)

## References
- NCCL GitHub (master, v2.31.2-1) — https://github.com/NVIDIA/nccl (fetched 2026-08-25) [F]
- NCCL 2.31.2 User Guide: env vars, types (ncclConfig_t), CUDA Graphs, device API —
  https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/ (fetched 2026-08-25) [F]
- NCCL 2.31.2 & nccl-ep v0.1.0 release notes (CFT, per-collective config, GIN GDA,
  EFA GDA, NCCL EP) [F]
- `../GPU-Systems/NCCL.md` (internal house deep-dive)
