# NCCL + RDMA + SHARP
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
NCCL's network transport is **RDMA under the hood** — they are layers, not
competitors. RDMA moves bytes without CPU; NCCL decides *what* to move (the
collective choreography). On top of that, **in-network computing** (SHARP on
InfiniBand, NVLink SHARP/NVLS on NVSwitch) moves part of the *reduction itself*
into the fabric, so switches stop being dumb pipes for AllReduce traffic.

## 1. Normal AllReduce vs in-network AllReduce
```text
Normal:
GPU → NIC → Switch → NIC → GPU
               (switch mainly forwards packets)

SHARP:
GPU → NIC ──┐
             │  Smart fabric performs reduction
GPU ← NIC ──┘   (partial sums computed in the switch)
```
In-network computing: the switch holds reduction state per flow; instead of N
GPUs pushing N copies through the fabric, each GPU pushes one copy to its switch,
the switch produces partial/complete results, and each GPU receives what it still
needs. Fabric traffic for an AllReduce drops from ~2(N−1)/N × size per link to
roughly 2/N × size per uplink [I: SHARP traffic-model analysis; exact factor
depends on tree shape and N].
When it's beneficial:
- **High N, large allreduce-heavy workloads** (DDP/ZeRO-1 gradient sync across a
  whole pod/cluster) — the fabric is the bottleneck and the switch has room.
- **Not** intra-node: NVLink/NVLS already offloads inside the NVSwitch domain;
  SHARP is an inter-node IB feature [F: NCCL docs distinguish NVLS (NVSwitch) vs
  SHARP (IB switch)].
- **Not** small messages: switch reduction state has setup cost; the crossover
  mirrors [05](05-nccl-algorithms-transport.md)'s α/nβ argument.

## 2. SHARP (InfiniBand in-network)
- Requires IB switches with SHARP (e.g. Quantum family) and NICs that expose the
  offload [F: NVIDIA networking docs]; NCCL exposes it via CollNet
  (`collnetEnable` in ncclConfig_t, default 0; `NCCL_COLLNET_ENABLE` legacy)
  [F: NCCL types docs].
- NCCL's **CollnetDirect** (2.14+) path: reduction happens in the switch, data
  path is direct NIC↔HBM (GDR), no host staging — this is the form to enable in
  new deployments [../GPU-Systems/NCCL.md].
- Operational notes: SHARP engine sizing, QP counts per rank, and per-switch
  license — a fabric-level configuration, coordinated across the whole job.
  Treat as a *fabric capability you opt into*, not an NCCL env var you flip
  [I: standard IB SHARP deployment practice].

## 3. NVLS / NVLink SHARP (intra-node)
- Hardware: NVSwitch 3rd gen (NVLink4), Hopper and later [F: NCCL env docs —
  "available in third-generation NVSwitch systems (NVLink4) with Hopper and
  later"].
- `NCCL_NVLS_ENABLE`: 0 off, 1 on (hard-fail if resources unavailable),
  **2 = default** (soft behavior: don't fail at init if unsupported, fail at
  resource allocation) [F: NCCL env docs].
- What it buys: AllReduce as one hardware-offloaded operation across the whole
  NVLink domain — no ring choreography, no per-step SM copies; latency and SM
  usage drop, bandwidth saturates [F: NCCL docs + `../GPU-Systems/NCCL.md`].
- Caveats: resource allocation per comm; multi-rank-per-GPU comms disable NVLS
  (2.30-era note) [F: NCCL env docs].

## 4. Where RDMA sits in the NCCL stack
```text
NCCL (collective choreography, algorithm/protocol, channels)
   │
   ▼
NCCL NET plugin ABI (libnccl-net.so): ib | socket | <third-party>
   │                                    (+ 2.31: GIN & RMA plugin slots)
   ▼
RDMA verbs (ib) over InfiniBand/RoCE   |  TCP sockets
   │
   ▼
GPUDirect RDMA mapping (NIC↔HBM, when P2P+IOMMU permit)
   │
   ▼
NIC QP/CQ  →  fabric
```
- GDA/IBGDA (2.28+ Device API): the *GPU* posts work and polls completions —
  no proxy thread on the data path; DeepEP V2 builds on exactly this (NCCL Gin
  backend) [F: NCCL 2.31 release notes; DeepEP README].
- 2.31 added EFA GDA support (AWS contribution, PR #2273) — GPU-initiated
  networking over EFA [F: NCCL 2.31 release notes].

## 5. Failure modes & what they look like
- "NCCL INFO Using network Socket" → GDR/IB path broken (IOMMU, ACS, BAR size,
  wrong HCA) → [17](17-troubleshooting.md) decision tree, branch 1.
- "NCCL WARN … QP/CQ error" → fabric or NIC issue; check `ibstat`, PFC counters
  on RoCE, adaptive routing on IB [I: standard RDMA debugging].
- Bandwidth far below line rate with socket/SHM in the path → CPU bounce;
  GDR disabled somewhere in the chain ([03 §2](03-gpu-network-architecture.md)).
- NVLS "silently disabled" under multi-rank-per-GPU → check `NCCL_NVLS_ENABLE`
  semantics (0/1/2) [F: NCCL env docs].

## 6. Decision summary
| Situation | Use |
|---|---|
| Intra-node Hopper+, NVSwitch | NVLS (default-on; verify in INFO logs "NVLS") |
| Cross-node IB with SHARP switches, DDP-heavy | SHARP CollnetDirect (opt-in, fabric-configured) |
| Cross-node RoCE, no switch offload | plain GDR ring/tree (the default; tune channels) |
| EFA cloud | GDR via EFA + GDA when available (2.31); else proxy path |
| GPU-initiated (EP/one-sided) | GIN/GDA backends (IBGDA, EFA GDA) — [10/14](10-uccl-collective-p2p-ep.md) |

## Key Takeaways
1. RDMA is a transport NCCL *uses*; "NCCL vs RDMA" is a category error — compare
   NCCL to UCX/UCCL, compare RDMA to TCP.
2. SHARP/NVLS move the *reduction* into the switch: traffic ↓, SMs ↓, but only
   for large, high-N, reduction-heavy workloads on capable hardware.
3. NVLS is default-on (`=2`) on NVLink4 domains — absence of "NVLS" in INFO logs
   means something disabled it.
4. GDA/GIN (2.28+/2.31) removes the host proxy from the data path — the same
   architecture DeepEP V2 and NCCL EP exploit.
5. Fabric offloads (SHARP, NVLS) are *capabilities you provision*, not flags you
   toggle per-job.

## Related
[04 NCCL Deep Dive](04-nccl-deep-dive.md) · [11 UCX/RCCL/UCC/NVSHMEM/DeepEP](11-ucx-rccl-ucc-nvshmem-deepep.md) ·
`../GPU-Systems/NCCL.md`

## References
- NCCL 2.31.2 docs: `NCCL_NVLS_ENABLE`, CollNet/`collnetEnable`, GIN device API,
  2.31 release notes (CFT, GIN GDA, EFA GDA PR #2273) [F: docs.nvidia.com +
  github.com/NVIDIA/nccl, fetched 2026-08-25]
- NVIDIA SHARP / in-network computing — https://www.nvidia.com/en-us/networking/infiniband/sharp/ [F]
- DeepEP README (V2 → NCCL Gin backend, zero-SM modes) — https://github.com/deepseek-ai/DeepEP [F]
