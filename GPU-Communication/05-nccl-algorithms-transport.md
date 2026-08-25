# NCCL Algorithms & Transport
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
For a given collective, NCCL chooses an **algorithm** (the message choreography:
ring, tree, NVLS, …) and a **protocol** (how each chunk is framed: Simple, LL,
LL128) and a **transport** per peer (NVLink, P2P, SHM, GDR, socket). The choice is
a function of message size and the discovered topology; the `T ≈ α + nβ` crossover
from [02](02-collective-communication-fundamentals.md) is exactly what the
auto-tuner is solving. This page is the "when does which win" map.

## 1. Algorithm selection logic
```text
input: (collective, N, message size, topology graph, transport capabilities)
output: (algorithm, protocol, channel count, NIC set)
```
- **Ring** — bandwidth-optimal (every link carries (N−1)/N × size per phase),
  O(N) latency. Wins: large messages, moderate N, uniform topology.
- **Tree** — O(log N) latency, slight bandwidth loss (imbalance on the
  non-leaf paths). Wins: small–medium messages, large N, deep hierarchies.
- **NVLS/NVLSTree** — single-shot offload to the NVSwitch (intra-domain); near
  line-rate with minimum latency inside an NVLink4 domain; requires NVLS support
  [F: NCCL env `NCCL_NVLS_ENABLE`, default 2].
- **PAT** (2.23+) — pipelined/adaptive tree-style algorithm for wide collectives
  [F: NCCL env docs].
- **CollnetChain/CollnetDirect** — SHARP-assisted paths where the NIC/switch does
  part of the reduction ([06](06-nccl-rdma-sharp.md)).
Per-function override since 2.24: `NCCL_ALGO="ring,collnetdirect;allreduce:tree,..."`
(`^` excludes); the same grammar applies to `NCCL_PROTO`
[../GPU-Systems/NCCL.md; F: NCCL env docs].

## 2. Why ring hits bandwidth
A ring AllReduce of total size S over N ranks: phase 1 (reduce-scatter) moves
S/N per step, N−1 steps; phase 2 (allgather) mirrors it. **Every link is busy in
every step** — no idle time, no straggler — so sustained bandwidth ≈ link
bandwidth × (N−1)/N × 2 (both directions) [E: factors 1.75 at N=8, 1.969 at
N=64, from 02's table]. The price: message latency grows linearly in N because
every step is serialized around the ring.

## 3. Why tree hits latency
A binary tree does log₂ N hops; for a 1 KiB AllReduce across 1024 ranks, ring
would queue 1023 serialized hops while tree queues ~10 [I: hop-count argument].
Small messages are latency-bound (02's α term), so fewer hops = much faster even
at lower per-hop efficiency. Cost: the tree's root and upper links carry more
traffic — bandwidth-bound large messages lose to ring.

## 4. Protocol choice by size (typical behavior, not a universal table)
```text
size          LL        LL128      Simple
< ~few KB     ✓ best    —          —
~few KB–MB    —         ✓ often    —
> ~MB         —         marginal   ✓ best
```
- **LL** doubles the wire bytes (8B data + 8B flag) → ~half bandwidth, but the
  flag lets the receiver act on each 8B element immediately — no tail
  synchronization. Best when α dominates.
- **LL128** (128B data + 128B flags, 128B-aligned) halves the overhead ratio;
  needs capable NIC/driver and aligned buffers; the default middle choice on
  modern hardware when the platform supports it
  [F: NCCL env `NCCL_PROTO` docs].
- **Simple** — plain large chunks; maximum bandwidth; wins above the crossover.
"Do not oversimplify": the actual winner depends on transport (SHM vs GDR vs
socket), channel count, and SM occupancy — measure with `nccl-tests`
([19 Practical Labs](19-practical-labs.md)) rather than memorizing a table.
The auto-tuner encodes the same physics: it picks the (algo, proto) pair whose
predicted `α + nβ` is lowest for *this* size on *this* topology.

## 5. Transport selection, per peer
NCCL's per-peer decision (conceptual order; topology discovery feeds it):
1. **NVLink** (direct, or via NVB/PXN intermediate GPU) — the default intra-node
   fast path.
2. **PCIe P2P** (BAR mapping, PIX/PXB in `topo -m`) — GDR-friendly.
3. **Shared memory** (host DRAM staging) — same-host fallback.
4. **Network**: GDR-capable → **GPUDirect RDMA** over the `ib` plugin; else host
   staging over IB; else **socket** (last resort — "Using network Socket" in
   INFO logs is your first red flag, see [17](17-troubleshooting.md)).
Multi-rail: with one-NIC-per-GPU topologies NCCL can stripe channels over all
NICs (`NCCL_MAX_NCHANNELS`, `nChannelsPerNetPeers` in ncclConfig_t) and keeps
rail-local routing when possible [F: NCCL config docs; 03 §3].
PXN: when GPU 3's traffic would have to cross the PCIe switch to reach NIC 0,
NCCL may instead route GPU 3 → GPU 2 (NVLink) → NIC 2 (GPU 2's local NIC) —
`NCCL_PXN_DISABLE` turns it off [F: NCCL env docs].

## 6. Channels, CTAs, and SM cost
Each channel is a parallel pipeline: a CTA (thread block) on the GPU + a matching
NIC QP when the transport is the network. `minCTAs`/`maxCTAs` (default
min 1 / max 32; NVLS CTA count auto) set the ceiling
[F: NCCL ncclConfig_t docs]. Consequences:
- More channels → more bandwidth saturation on large messages, more SMs busy →
  less SM for the compute kernels (the overlap trade-off of
  [16 Compute/Communication Overlap](16-performance-benchmarking.md)).
- Fewer channels → less SM pressure, better for small-message workloads that are
  latency-bound anyway.
NCCL 2.31's per-collective `ncclCollConfig_t` lets you tune this *per op* — e.g.
keep TP AllReduce on high channels, drop EP-style P2P to fewer
[F: NCCL 2.31 release notes].

## 7. Memory registration & the data path
- App buffers used repeatedly → `ncclCommRegister` once; NCCL reuses GDR mappings
  and skips per-call registration. For CUDA Graphs use
  `NCCL_GRAPH_REGISTER` [F: NCCL CUDA Graphs docs].
- GDR mapping details: IOMMU/BAR setup on the GPU root (ACS/IOMMU), NIC on the
  right switch — the failure mode is silent fallback to SHM/socket
  ([03 §2](03-gpu-network-architecture.md)).

## 8. Worked example (canonical numbers)
Two reference points, both machine-checked [E: this session's compute]:
- **32 MB AllReduce, 8 ranks, NVLink, ring, Simple:** every link carries
  2(N−1)/N × 32 MB = 56 MB; time ≈ 56e6 / 900e9 ≈ **62 µs** (≈ 20 µs per
  reduce-scatter + allgather phase pair) — i.e. TP AllReduce is *microseconds*,
  which is why TP lives inside the layer on NVLink.
- **4.0 GiB KV move over the 900 GB/s NVLink aggregate:** 4.295e9 B / 900e9 B/s
  = **4.77 ms ≈ 4.8 ms** [E] — the "4.8 ms/pass" reference in
  `../GPU-Systems/NCCL.md` and the NVLink row of the transfer table in
  `../GPU-Systems/Prefill-Decode-Disaggregation.md`.
- The *same* 4.0 GiB across 100 GbE (12.5 GB/s): **343.6 ms** [E] — a 72× split.
  That is the single clearest argument for NVLink-resident TP and for keeping KV
  hot (or quantizing it) in P/D.

## Key Takeaways
1. Algorithm = choreography (ring/tree/NVLS/PAT/Collnet); protocol = framing
   (Simple/LL/LL128); transport = physical rung (NVLink/P2P/SHM/GDR/socket).
   Three independent dials.
2. Ring wins on bandwidth, tree wins on latency, NVLS wins inside an NVLink4
   domain — the auto-tuner is a `T ≈ α + nβ` solver over the combinations.
3. Protocol crossovers are topology-dependent: measure per-size on your fabric,
   don't copy a table.
4. Channels/CTAs trade SMs for bandwidth — a 2.31 `ncclCollConfig_t` can tune
   that per operation.
5. The 4.0 GiB KV move ≈ 4.8 ms (NVLink aggregate) vs ≈ 344 ms (100 GbE
   cross-node) — a 72× split that is the clearest argument for NVLink-resident
   TP and hot/quantized KV.

## Related
[04 NCCL Deep Dive](04-nccl-deep-dive.md) · [06 NCCL + RDMA + SHARP](06-nccl-rdma-sharp.md) ·
[17 Troubleshooting](17-troubleshooting.md) · `../GPU-Systems/NCCL.md`

## References
- NCCL 2.31.2 env docs (`NCCL_ALGO`, `NCCL_PROTO`, `NCCL_NVLS_ENABLE`, PXN/NVB,
  CTA bounds, `NCCL_GRAPH_REGISTER`) [F: docs.nvidia.com, fetched 2026-08-25]
- NCCL ncclConfig_t docs (minCTAs/maxCTAs, nChannelsPerNetPeers) [F]
- `../GPU-Systems/NCCL.md` (4.8 ms reference; internal)
