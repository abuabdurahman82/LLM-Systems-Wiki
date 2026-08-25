# NCCL vs NIXL vs UCCL
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
The three primary libraries of this section solve **different problems at
different layers** — and the most common error in the field is flattening them
into "three collective libraries that compete". They do not. NCCL answers
*"what collective operation should these GPUs perform?"*; NIXL answers *"how
can an inference system move data between heterogeneous memory/storage
resources?"*; UCCL answers *"can we run collectives / P2P / EP across a
heterogeneous, possibly lossy, multi-vendor fabric?"*. A production stack runs
**all three at once** — that is the point of the taxonomy
([01 §3](01-why-communication-matters.md)).

## 1. The comparison matrix
Values: **Native** · **Supported via backend** · **Limited** · **Experimental** ·
**Not primary purpose**. (Capability claims verified against upstream docs,
fetched 2026-08-25; "Limited/Experimental" reflect the 2026-08 snapshot.)

| Feature | NCCL | NIXL | UCCL |
|---|---|---|---|
| Primary purpose | GPU collectives + P2P (NVIDIA) | Inference data movement (heterogeneous mem/storage) | Flexible GPU communication across vendors/fabrics |
| Training | **Native** | Not primary purpose | Supported (UCCL-Tran; AMD Primus EP) |
| Distributed inference | Native (TP/PP/CP) | **Native** (P/D KV, offloading) | Supported (KV via P2P; EP; Dynamo-adjacent) |
| Collective communication | **Native** (AllReduce/AllGather/…) | Not primary purpose | **Native** (UCCL-Tran, NCCL-API drop-in) |
| P2P communication | **Native** (Send/Recv) | **Native** (READ/WRITE one-sided) | **Native** (UCCL-P2P, NIXL-style) |
| KV-cache transfer | Limited (possible but not the fit) | **Native** (the design target) | Native via P2P (NIXL backend; llm-d) |
| Expert Parallel | Experimental (NCCL EP, new in 2.31-era) | Not primary purpose | **Native** (UCCL-EP, DeepEP-compatible) |
| GPU→GPU | **Native** | **Native** | **Native** |
| GPU→CPU | Native (SHM/P2P paths) | **Native** (DRAM mem type) | Native (P2P GPU IPC + DRAM) |
| GPU→Storage | Limited (no storage semantics) | **Native** (FILE/OBJ/BLK mem types, GDS) | Limited (P2P to registered regions; storage via NIXL/GDS) |
| RDMA | **Native** (ib plugin + GDR) | **Native** (UCX/GDS/libfabric backends) | **Native** (Tran RDMA; P2P; EP; NVIDIA/Broadcom) |
| RoCE | **Native** | **Native** (via UCX etc.) | **Native** (RoCE NICs incl. Broadcom) |
| InfiniBand | **Native** (+SHARP/NVLS offloads) | **Native** (via backends) | **Native** |
| EFA | Supported (GDA in GIN, 2.31; aws-ofi-nccl) | Supported via backend (libfabric) | **Native** (collective/efa; P2P; EP) |
| TCP | **Native** (socket transport, last resort) | **Native** (via backends) | **Native** (TCP; TCP-X via GCP; ENA/VirtIO AFXDP) |
| Heterogeneous GPUs | Limited (NVIDIA-only) | Supported (CPU/GPU/storage abstractions) | **Native** (NVIDIA + AMD; portability goal) |
| Storage abstraction | Not primary purpose | **Native** (file/block/object, incl. Azure blob, 3FS, DDN, Mooncake) | Not primary purpose |
| GPU-initiated communication | **Native** (GIN/GDA device API, 2.28+/2.31) | Not primary purpose | **Native** (EP IBGDA-level; GPU-driven P2P) |
| Framework integration | **Native** (torch.distributed default; all engines) | **Native** (vLLM NixlConnector, Dynamo KVBM, SGLang, TRT-LLM, LMCache, llm-d) | Native (NIXL backend; NeMo EP; Primus; llm-d v0.5; TheRock) |
| Typical deployment | Every NVIDIA training + serving cluster | Disaggregated / elastic inference, tiered KV | Multi-vendor or lossy-fabric fleets; EP at scale |

Reading the matrix: **columns don't compete — they tile the problem space**.
NCCL's column is "NVIDIA-native collective engine"; NIXL's is "inference
data-movement agent"; UCCL's is "portable collective+P2P+EP". Overlap is
*feature* overlap (all three can move bytes over RDMA), not *purpose* overlap.

## 2. Three questions, three answers
```text
NCCL
"What collective operation should these GPUs perform?"

UCX
"How can data efficiently move between these endpoints?"

NIXL
"How can an inference system move data between heterogeneous memory/storage resources?"
```
Real examples:
- **NCCL**: "AllReduce these 56 KiB attention outputs across 8 ranks, every
  layer, on NVLink" — [05 §8](05-nccl-algorithms-transport.md).
- **UCX**: "Move 4 MiB from this GPU's HBM to that host's DRAM over the fastest
  transport I have (SHM? verbs? TCP?)" — [11 §1](11-ucx-rccl-ucc-nvshmem-deepep.md).
- **NIXL**: "This request's KV blocks (32k context, 4.0 GiB) now live on
  prefill worker P-3; decode worker D-7 will need them; move them
  asynchronously and tell D-7 when they're ready" — [08 §2](08-nixl-kv-cache-transfer.md).

## 3. The layer diagram (from the user's PART 15)
```text
┌──────────────────────────────────────────────┐
│        LLM / Distributed AI Application      │
│ PyTorch | JAX | vLLM | SGLang | TRT-LLM    │
├──────────────────────────────────────────────┤
│              Communication Layer             │
│ NCCL | RCCL | UCCL | NVSHMEM | DeepEP      │
├──────────────────────────────────────────────┤
│        Data Movement / Abstraction Layer     │
│            NIXL | UCX | UCC                 │
├──────────────────────────────────────────────┤
│                 Transport                    │
│ RDMA | verbs | libfabric | TCP | EFA        │
├──────────────────────────────────────────────┤
│              Hardware Offloads               │
│ GPUDirect RDMA | IBGDA | SHARP | NVLS       │
├──────────────────────────────────────────────┤
│              Physical Fabric                 │
│ NVLink | PCIe | InfiniBand | RoCE | EFA     │
└──────────────────────────────────────────────┘
```
**The boundaries are not perfectly rigid — some libraries span multiple
layers.** Examples:
- **NCCL** spans Communication + Transport (its NET plugin layer) and, since
  2.28/2.31, reaches into Offloads (GDA/GIN, CFT) [04 §7].
- **NIXL** spans Data-Movement + Transport (its backends *are* transport
  implementations: UCX, GDS, libfabric) [07 §2].
- **UCCL** spans Communication + its own software Transport (Tran is both the
  collective engine *and* the transport) [09 §3].
- **NVSHMEM/DeepEP** sit in Communication but implement Offloads (IBGDA)
  directly [11 §4].
So the diagram is a *mental model*, not a strict dependency graph.

## 4. Which layer does the actual data movement?
The honest answer: **the hardware offload + physical fabric layers, always**.
- Intra-node: NVLink (SM-driven copies) or PCIe GDR.
- Inter-node: NIC DMA over IB/RoCE/EFA (GDR mappings), with the *decision* made
  by the layer above.
The upper layers are **choreography**: NCCL decides ring order & chunking;
NIXL decides which backend & which buffer list; UCCL decides spray pattern & CC.
"Which library is faster" only has an answer *per problem* — the three
libraries rarely answer the *same* problem head-to-head (the exception:
NCCL vs UCCL-Tran on collectives, and NCCL-P2P vs NIXL on KV — both have
measured answers, [10 §1](10-uccl-collective-p2p-ep.md), [08 §5](08-nixl-kv-cache-transfer.md)).

## 5. The six common misconceptions
### 5.1 "NIXL replaces NCCL."
Usually incorrect. Different branches: NCCL = in-layer collectives; NIXL = KV /
weight / storage movement. A serving stack keeps NCCL *and* adds NIXL
([13 §6](13-distributed-inference-communication.md)). NCCL's P2P Send/Recv is
*not* a substitute for NIXL's heterogeneous, dynamic, notification-driven
model [08 §5].

### 5.2 "RDMA and NCCL are competing technologies."
They are layers:
```text
NCCL
 ↓
may use
 ↓
RDMA
```
NCCL's network plugin *is* RDMA (verbs) when IB/RoCE is present [04 §6].
Compare NCCL↔UCX (both communication frameworks), or RDMA↔TCP (both
transports) — not NCCL↔RDMA.

### 5.3 "RoCE is the same thing as NCCL."
RoCE is a *fabric protocol* (RDMA over Ethernet, L2/L3); NCCL is a *library*.
NCCL runs on RoCE (via its ib plugin + GDR) exactly as it runs on InfiniBand or
EFA [03 §5; 16 network chapter]. Confusing the two is like calling "TCP" and
"PostgreSQL" the same thing.

### 5.4 "NCCL handles KV-cache movement automatically."
It doesn't. NCCL moves *what the application asks it to move*, in collectives or
Send/Recv — it has no concept of KV blocks, request affinity, producer/consumer
roles, or tiered placement. That bookkeeping *is* NIXL (or the engine's
connector) [07; 08]. NCCL is a *possible* transport underneath a hand-rolled KV
path, but no engine ships that as its KV path today [13 §5].

### 5.5 "Maximum NIC bandwidth means maximum NCCL bandwidth."
No. Measured NCCL busbw is gated by: transport actually selected (socket vs
GDR), topology (GPU→NIC distance), channel/CTA counts, protocol, algorithm,
fabric congestion, and collective overhead (the 2(N−1)/N factor and ring
serialization) [05; 17]. A 400 Gb NIC delivering 20 GB/s of AllReduce
busbw is a *topology/protocol* problem, not a NIC problem — the
[17 Troubleshooting](17-troubleshooting.md) tree exists for this.

### 5.6 "All-to-All is basically the same as AllReduce."
No. AllReduce: symmetric, fixed-size, every participant contributes equally,
deterministic schedule. All-to-All: N(N−1) flows, per-destination sizes set by
*data* (the router), hotspots, non-uniform load [14 §1]. Treating MoE
dispatch as "AllReduce with a twist" is the design error behind most bad
EP deployments — it's why dedicated EP libraries exist.

## 6. When they *do* compete (the honest overlap)
| Overlap | Contestants | Decider |
|---|---|---|
| GPU collectives, NVIDIA fleet | NCCL vs UCCL-Tran | fabric (lossy/multi-vendor → UCCL; standard NVIDIA → NCCL) [10 §1; 18] |
| GPU collectives, AMD fleet | RCCL vs UCCL-Tran | ecosystem posture (TheRock ships both) [11 §2] |
| KV transfer, NVIDIA fabric | NIXL+UCX vs hand-rolled NCCL P2P | the engine's connector (all major engines chose NIXL) [13] |
| KV transfer, EFA | NIXL+libfabric vs NIXL+UCCL | backend maturity on the fleet [07 §7; llm-d v0.5] |
| MoE EP, NVIDIA IB | DeepEP vs NCCL EP vs UCCL-EP | performance ceiling vs native-integration vs portability [14 §5] |
Every row is *feature* competition at one branch — never the three libraries
competing on one problem simultaneously.

## 7. The complementarity diagram (user's example, annotated)
```text
Application / Framework
        │
        ▼
vLLM / SGLang / TensorRT-LLM / Dynamo
        │
        ├──────── Collective operations ───────► NCCL
        │        (TP AllReduce ×2/layer — every token)
        │
        ├──────── KV-cache transfer ───────────► NIXL
        │        (per request; async, one-sided, tiered)
        │                                        │
        │                                        ▼
        │                                 UCX / UCCL / GDS
        │        (the transport NIXL picked for this fabric/tier)
        │
        └──────── MoE Expert Parallel ─────────► UCCL-EP / DeepEP
                 (per micro-batch; GPU-driven all-to-all)
                                                  │
                                                  ▼
                                          RDMA / IB / RoCE
```
Every arrow is a *different branch of the taxonomy*; the same request, in the
same token, exercises several of them. "Complement, not compete" is a
*structural* statement: the branches are disjoint by cadence and payload.

## Key Takeaways
1. One matrix, three purposes: NCCL (collectives), NIXL (inference data
   movement), UCCL (portable collective+P2P+EP) — the columns tile, not
   overlap.
2. The layers diagram is a mental model; NCCL/NIXL/UCCL each span 1–2 layers
   (rigid-layer thinking misleads).
3. The bottom layer always moves the bytes; the top layers are choreography.
4. The six misconceptions are layer-confusions (NCCL↔RDMA, NCCL↔RoCE,
   NIXL↔NCCL, NCCL↔KV, NIC-bw↔NCCL-bw, AllToAll↔AllReduce).
5. Real competition is branch-local (NCCL vs UCCL-Tran; DeepEP vs UCCL-EP vs
   NCCL EP) and decided by fleet + fabric.

## Related
[18 Architecture Decision Guide](18-architecture-decision-guide.md) ·
[20 One-Page Cheat Sheet](20-one-page-cheat-sheet.md) ·
[19 Practical Labs](19-practical-labs.md)

## References
- NCCL 2.31.2 docs + release notes (GIN/GDA/CFT/EP, EFA GDA) [F: fetched 2026-08-25]
- NIXL README + BackendGuide (agent, backends, one-sided model) [F]
- UCCL README (three components, adoptions) [F]
- `../Networking/README.md` (layer summary; internal)
