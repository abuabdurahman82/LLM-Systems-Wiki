# Architecture Decision Guide
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
The whole section compressed into two decision surfaces: (1) the **tree** —
"what problem am I solving?" → which branch/library; (2) the **scenario
matrix** — "here's my fleet/workload" → recommended starting point + *why*.
Every recommendation names its decision factors so you can re-derive it when
the fleet or the library landscape changes (fast: see
[21 References](21-references-and-research.md) for the 2026-08 state).

## 1. The decision tree
```text
What problem are you solving?
        │
        ├── GPU collective communication?
        │           │
        │           ├── NVIDIA GPUs, standard fabric ──► NCCL
        │           ├── AMD GPUs ──────────────────────► RCCL (or UCCL-Tran)
        │           ├── Heterogeneous / lossy-Ethernet / multi-vendor
        │           │        ─────────────────────────► UCCL-Tran
        │           └── HPC portability / existing MPI stack
        │                    ─────────────────────────► MPI (CUDA-aware) / UCC
        │
        ├── Distributed inference KV transfer?
        │           │
        │           └── NIXL
        │                 │
        │                 ├── IB/RoCE, NVIDIA fleet ─────► UCX backend (+ GDR)
        │                 ├── EFA / multi-vendor / lossy ► UCCL backend (or libfabric)
        │                 ├── NVMe tier ─────────────────► GDS backend
        │                 └── object/file storage ───────► obj / posix / azure_blob / hf3fs …
        │
        ├── MoE Expert Parallel?
        │           │
        │           ├── NVIDIA-first, IB, max performance ─► DeepEP (V2, NCCL Gin)
        │           ├── Heterogeneous fleet / EFA / AMD ───► UCCL-EP
        │           └── All-in on NCCL ecosystem (2.31+) ──► NCCL EP (new; watch maturity)
        │
        ├── One-sided GPU programming?
        │           │
        │           └── NVSHMEM (PGAS; custom kernel-level comm)
        │
        └── Need a transport, no semantics?
                │
                ├── widest hardware coverage ─────► UCX
                ├── fabric abstraction (EFA/IB/…) ► libfabric
                └── programmable GPU collectives ─► MSCCL++
```
Reading note: the tree is *branch-first* (the taxonomy of
[01 §3](01-why-communication-matters.md)), not library-first. Answer the
"what problem" question first; the library follows.

## 2. The scenario matrix (with the *why*)
| Scenario | Recommended starting point | Why |
|---|---|---|
| PyTorch DDP training | **NCCL** | the default torch.distributed backend on NVIDIA; ring/tree auto-tuned; NVLS/SHARP offloads when hardware present [04; 12] |
| Tensor Parallel inference | **NCCL** | TP AllReduce ×2/layer on NVLink is microseconds ([05 §8] 56 MB ring ≈ 62 µs [E]) — nothing else needs to be there intra-node [13 §2] |
| Multi-node TP | **NCCL** (+ GDR over IB/RoCE; rail-optimized topology) | the cross-node cost is the argument *for* NVLink-resident TP; when you must cross, NCCL's GDR path + channels are the mature answer [05 §8; 03] |
| Prefill/decode KV transfer | **NIXL** | heterogeneous endpoints + dynamic peers + one-sided async + engine-native connectors (vLLM NixlConnector, Dynamo KVBM) [07; 08; 13] |
| Dynamo distributed inference | **NIXL + appropriate backend** (UCX default; UCCL on EFA/multi-vendor; GDS for NVMe tiers) | KVBM uses NIXL underneath; backend choice is fabric-dependent [08 §3; 13 §5.4; F: Dynamo README] |
| MoE Expert Parallel | **DeepEP / UCCL-EP** | branch-local choice: DeepEP = NVIDIA/IB ceiling (NCCL Gin, EP2048, 0-SM modes); UCCL-EP = portable (AMD/EFA/Broadcom, DeepEP-compatible API) [14 §5; 10 §3.4] |
| AMD GPU training | **RCCL** (or UCCL-Tran for new heterogeneous work) | RCCL is the ROCm-native default; TheRock also ships UCCL — the line is softening [11 §2; I: posture] |
| Heterogeneous GPU/NIC environment | **Investigate UCCL / NIXL / UCX** | UCCL-Tran/EP for collectives+EP across vendors; NIXL for the inference data-movement side with UCX/UCCL/GDS backends; UCX as the widest-coverage transport [09; 07; 11] |
| GPU→storage transfer | **NIXL + storage backend** (GDS for NVMe; obj/posix/azure for files & objects) | NIXL's mem-type model (FILE/BLK/OBJ) is the only one of the three built for this [07 §5; 15 matrix] |
| Custom one-sided GPU communication | **NVSHMEM** | PGAS programming model; kernel-level put/get/atomics; DeepEP V1's substrate [11 §4] |

The *why* column is the payload: a recommendation without its decision factors
is a guess. Re-derive per fleet.

## 3. Cross-cutting decision factors (checklist)
1. **Branch** — collective / P2P / EP / one-sided? (the tree's root question)
2. **GPU vendor mix** — NVIDIA-only, AMD-only, mixed? (gates NCCL/RCCL/UCCL/DeepEP)
3. **Fabric** — IB / RoCE / EFA / lossy Ethernet? (gates GDA/IBGDA, PFC, spraying, GDR)
4. **Topology** — NVLink domain size; rail-optimized? NIC affinity? (gates NVLS, TP placement, multi-rail)
5. **Cadence & size** — every-token KiB (TP) vs per-request GiB (KV) vs per-microbatch dynamic (EP)? (gates overlap strategy; [02 §3; 14])
6. **Elasticity** — static world (training) vs dynamic pool (serving, scale-to-zero)? (gates NIXL's dynamic metadata; [07 §4])
7. **Maturity bar** — production-default (NCCL) vs rapidly-evolving (UCCL, NCCL EP, NIXL storage backends)? (gates rollout: pilot + benchmark first; [19])
8. **Team** — who operates it? (PFC/DCQCN tuning skill; RDMA debugging skill; [17])

## 4. Anti-patterns (what not to do)
- **One library to rule them all** — flattening the taxonomy; you'll hand-roll
  the missing branch badly (e.g. NCCL for KV transfer, or NIXL for in-layer
  collectives) [15 §5.1/5.4].
- **Buying the NIC, ignoring the rung** — a 400 G NIC behind a SYS-affinity
  placement delivers SYS-limited bandwidth ([03 §4] haircut); fix topology
  before hardware [16 §8].
- **Trusting vendor tables without the workload** — "2.5×/3.7×" AllReduce and
  "exceeds bandwidth limits" EP are *project-reported on project targets*;
  reproduce on your fabric before believing ([10 §1; 14 §5]; [19 §methodology]).
- **Treating RoCE like a black box** — PFC/ECN/DCQCN are the workload's
  performance ceiling; the libraries adapt to the fabric, they don't fix it
  [16 §6.2].
- **Benchmarking AllReduce only** — the comm that hurts your p99 TTFT is the KV
  transfer, not the AllReduce [16 §2, 30-workload split].

## 5. The "Central Question" architecture, answered
The prompt's reference stack:
```text
vLLM
 │
Tensor Parallel ────── NCCL
 │
Prefill/Decode ─────── NIXL
 │                       │
 │                       ├── UCX
 │                       └── UCCL
 │
MoE ────────────────── UCCL-EP / DeepEP
 │
 ▼
GPUDirect RDMA
 │
 ▼
InfiniBand / RoCE / EFA
```
- **What every layer does**: vLLM = orchestration of the three streams;
  TP→NCCL = per-layer collective choreography; P/D→NIXL = per-request KV
  movement with backend choice (UCX or UCCL per fabric); MoE→EP library =
  per-microbatch dynamic all-to-all; GDR = the zero-copy mapping; the fabric =
  the bytes.
- **Why it exists**: each layer exists because the problem beneath it has a
  different shape (cadence, size, symmetry, endpoint heterogeneity) — see
  [13 §1](13-distributed-inference-communication.md) for the three-stream
  argument.
- **Which layer performs the actual data movement**: always the bottom — GDR +
  NIC + fabric. The layers above decide *what/where/how-choreographed*
  ([15 §4](15-nccl-vs-nixl-vs-uccl.md)).
- **Which components complement each other**: NCCL + NIXL + EP run *simultaneously*
  in one cluster; UCX/UCCL are *interchangeable backends under NIXL*; GDR is
  *shared infrastructure* under all three [01 §3; 15 §7].
- **Where collectives / KV / EP traffic occur**: in-layer / per-request /
  per-microbatch respectively ([13 §6](13-distributed-inference-communication.md)).
- **What hardware acceleration is involved**: NVLink/NVSwitch (NVLS), GDR, IBGDA/
  GDA (device-initiated), SHARP/NVLS in-network, EFA GDA/SRD
  [04 §7; 06; 11].
- **What network characteristics matter**: bandwidth *and* latency, loss
  behavior, routing adaptivity, PFC/ECN health, rail topology, MTU
  [16 §5–6; 03].
- **How to benchmark it**: micro (nccl-tests/NIXLBench) → app (TTFT/ITL/step
  time) with the workload battery; [16 §1–3, 19].
- **How to troubleshoot it**: the decision tree + the two canonical diagnoses;
  [17].
- **How to choose the correct stack**: this page's tree + matrix + checklist;
  re-derive per fleet (factors §3).

## Key Takeaways
1. Decide branch-first: collective / P2P(KV) / EP / one-sided / transport.
2. The scenario matrix answers "my fleet is X" with a starting point *and* its
   decision factors — re-derive, don't copy.
3. The eight checklist factors (vendor mix, fabric, topology, cadence,
   elasticity, maturity, team) are what make the recommendation *yours*.
4. Anti-patterns: one-library-flattening, buying NICs before fixing rungs,
   trusting un-reproduced vendor numbers, RoCE black boxes, AllReduce-only
   benchmarking.
5. The Central Question architecture is answered layer-by-layer in §5 — keep it
   as the section's capstone.

## Related
[15 NCCL vs NIXL vs UCCL](15-nccl-vs-nixl-vs-uccl.md) ·
[19 Practical Labs](19-practical-labs.md) · [01 Why Communication Matters](01-why-communication-matters.md)

## References
- All [F] claims inherit the fetch dates of [21 References](21-references-and-research.md)
  (NCCL 2.31.2; NIXL v1.4.0 + tree; UCCL main + OSDI'26; DeepEP main; llm-d v0.5;
  Dynamo README; vLLM NixlConnector docs — all fetched 2026-08-25)
- [16](16-performance-benchmarking.md) (the benchmark battery), [17](17-troubleshooting.md)
  (the tree), [13](13-distributed-inference-communication.md) (engine maps) — internal
