# Multi-Node LLM Inference (PART XXIV)
`LAST_UPDATED: 2026-08-21 · Status: core page` · The fabric page for `Multi-GPU.md`: the
two-node anatomy, the bandwidth ladder, RDMA/GPUDirect, and how every parallelism
dimension lands on a hop of that ladder. Constants from `../Hardware/README.md`
(NVLink ~900 GB/s H100, IB NDR ~50 GB/s/link, PCIe 5.0 x16 ~64 GB/s, HBM3 3.35 TB/s).

## 30-Second Explanation
A **node** is 8 GPUs on an NVLink/NVSwitch fabric, each GPU wired to its own NIC, and
the NICs plug into an InfiniBand/RoCE fabric that stitches nodes into a cluster:
```
inside the node:  ~900 GB/s (NVLink/NVSwitch)     crossing the node: ~50 GB/s (1 IB link)
ratio: 900/50 ≈ 18×  [E]  — every byte that crosses the node boundary loses ~an order of magnitude
```
That single ratio is the whole discipline: **put latency-critical, per-token
collectives (TP AllReduce, EP AllToAll) on NVLink inside the node, and put
bandwidth-tolerant, small-volume work (PP P2P, P/D KV transfer, cross-node EP) on
RDMA across the fabric** [I: matches `./Scale-Up-vs-Scale-Out.md` and `./Multi-GPU.md`].
The engineering below is all about *where each byte travels* and making sure the
hardware (GPUDirect RDMA, NUMA/NIC affinity, lossless RoCE) actually delivers the
ladder's top rung — because the failure modes of this page are "the fast path
silently degrades to the slow path," not "the math was wrong."

## The two-node diagram
```
                     NODE 0 (one rack)                         NODE 1 (one rack)
┌────────────────────────────────────────────┐   ┌────────────────────────────────────────────┐
│            NVSwitch — intra-node           │   │            NVSwitch — intra-node           │
│      any-to-any, 1 hop, ~900 GB/s/GPU      │   │      any-to-any, 1 hop, ~900 GB/s/GPU      │
│ ┌─────┐┌─────┐┌─────┐┌─────┐               │   │ ┌─────┐┌─────┐┌─────┐┌─────┐               │
│ │ G0  ││ G1  ││ G2  ││ G3  │  … G4..G7     │   │ │ G8  ││ G9  ││ G10 ││ G11 │  … G12..G15   │
│ └──┬──┘└──┬──┘└──┬──┘└──┬──┘               │   │ └──┬──┘└──┬──┘└──┬──┘└──┬──┘               │
│════╪══════╪══════╪══════╪═══════ NVLink ═══│   │════╪══════╪══════╪═══════ NVLink ═══════════│
│    │      │      │      │                   │   │    │      │      │                        │
│  ┌─┴──┐┌──┴──┐┌──┴──┐┌──┴──┐  one NIC/GPU  │   │  ┌─┴──┐┌──┴──┐┌──┴──┐┌──┴──┐  one NIC/GPU │
│  │N0  ││ N1  ││ N2  ││ N3  │ … N4..N7      │   │  │N8  ││ N9  ││N10  ││N11  │ … N12..N15    │
└──┴────┘└─────┘└─────┘└─────┘               │   └──┴────┘└─────┘└─────┘└─────┘               │
   │      │      │      │                     │   │      │      │      │                      │
   │      │      │      │   400G IB NDR ≈ 50 GB/s per link            │                        │
═══╧══════╧══════╧══════╧══════════════ IB / RoCE fabric (leaf–spine switches) ═══════════════
   ▲ 8 NICs per node; 16 links into the fabric in this 2-node sketch. Each GPU's KV/expert
     traffic exits via *its own* NIC — no in-node bounce for inter-node traffic [A: 8 NIC/GPU
     wiring is the common DGX/HGX reference layout; verify with `nvidia-smi topo -m`].
```
Read it as: **inside the box everything is ~900 GB/s; the moment a byte steps out a box
it is on a ~50 GB/s link** [E: 900/50 = 18× from the constants above].

## The performance ladder (fast → slow)
| # | Hop | ~Bandwidth (H100-class) | Latency character | Who pays for it |
|---|---|---|---|---|
| 1 | **Local HBM** (HBM3 on-package) | 3.35 TB/s [F: NVIDIA H100 spec] | ns | GEMM/GEMV weight+KV reads, every kernel |
| 2 | **GPU↔GPU NVLink** (intra-node) | ~900 GB/s aggregate [F: NVIDIA H100 spec] | ~µs/hop [A] | TP AllReduce (2×/layer, every token) |
| 3 | **NVSwitch node fabric** | same domain, any-to-all 1 hop | ~1 hop [F: NVIDIA NVSwitch] | wide AllToAll (intra-node EP), NVL72 = 72-GPU domain [F: NVIDIA] |
| 4 | **NIC (HCA)** — GPU HBM ↔ NIC | PCIe 5.0 x16 ~64 GB/s per path; GPUDirect skips the host [F: NVIDIA GPUDirect RDMA] | µs | **every byte leaving the node** |
| 5 | **Network fabric** (IB/RoCE leaf–spine) | ~50 GB/s per 400G NDR link; × N NICs aggregate [F: NDR 400G] | µs–10s µs/hop | PP P2P, cross-node EP, CP, P/D KV |
| 6 | **Remote GPU's NIC → remote HBM** | symmetric with hop 4 | + one more PCIe leg | arrives into the peer's HBM |

**The order-of-magnitude rule:** hop 1 → hop 2 already costs ~3.7× [E: 3350/900];
**hop 2 → hop 5 (the node boundary) costs ~18×** [E: 900/50]; and the PCIe last-mile
(64 GB/s) is 14× below NVLink [E: 900/64 ≈ 14]. So the practical hierarchy is
*HBM ≫ NVLink/NVSwitch ≫ NIC PCIe/IB*, and any design that can keep a byte one hop
up the ladder is leaving ~10× bandwidth on the table [I: this is the single most
recurring multi-node performance bug class — see Failure modes].

## 9-Field Template — RDMA & GPUDirect RDMA
- **What:** RDMA = **Remote Direct Memory Access**: the remote node's NIC reads/writes
  your memory *directly* — no kernel, no CPU, no copy (zero-copy, kernel-bypass)
  [F: vendor IB/RoCE docs; IEEE/RDMA semantics]. With **GPUDirect RDMA (GDR)** the
  NIC DMAs directly between the remote NIC and **GPU HBM**, skipping host RAM
  entirely [F: NVIDIA GPUDirect RDMA docs].
- **Why:** the collectives this fabric carries are small and tightly timed (8 KiB
  P2P activations, 112 KiB EP dispatch at B=1 — `./Pipeline-Parallelism.md`,
  `./MoE-Expert-Parallelism.md`). A TCP/IP + kernel path costs µs–ms of fixed
  latency plus CPU and cache traffic; RDMA issues a **one-sided** verb (the remote
  side is not woken up), so latency is set by the link, not the OS. For P/D
  disaggregation the whole handoff is a bulk copy — you want the copy to run at
  line rate with zero host involvement [I].
- **How:** NCCL talks to IB HCAs over verbs (RC connections); at init it enumerates
  the HCAs and pins channels to them (`./NCCL.md`). GDR requires the NIC to access
  GPU BAR space (IOMMU identity/allowlisting, BAR sizing, GDR kernel module)
  [F: NVIDIA GPUDirect RDMA docs]. Without GDR the path is
  GPU HBM → PCIe → host RAM → PCIe → NIC → wire → … → NIC → PCIe → host RAM →
  PCIe → HBM: two extra copies and host-BW contention on both ends [I: path
  decomposition].
- **When:** every hot-path inter-node transfer: PP P2P, cross-node EP AllToAll,
  CP AllToAll, P/D KV transfer. Bootstrap/control still uses TCP
  (`NCCL_SOCKET_IFNAME`) — that is correct and not a bug.
- **Hardware impact:** one NIC per GPU gives each rank an isolated 400G path
  (aggregate ~400 GB/s/node at 8× NDR [A: arithmetic on the constants]); pinned
  memory pools; the PCIe switch tree decides whether GPU↔NIC is 1 or 2 hops
  (`./Topology.md`).
- **Inference impact:** P2P handoff latency drops from ms-class (TCP) to µs-class
  (RDMA) — the difference between PP being viable and not; P/D KV becomes a
  bandwidth-bound copy instead of a CPU-bound pipeline [I: order-of-magnitude].
- **Example [E]:** P/D KV handoff, 4k-token context, d = 4096, BF16, 32 layers:
  per layer `2·S·d·b = 2·4096·4096·2 = 67,108,864 B = 64 MiB` (K and V, assuming
  KV spans the full hidden dim — GQA makes it *less* [A]); × 32 layers =
  **2 GiB = 2.147×10⁹ B**. At one 50 GB/s NDR link: `2.147e9 / 50e9 ≈ 42.9 ms`;
  over 8 NICs in parallel (~400 GB/s aggregate): `≈ 5.4 ms`; inside one NVL72
  NVLink domain at ~900 GB/s: `≈ 2.4 ms` [E: plain division of the above bytes by
  the STYLE-bank bandwidths].
- **Failure modes:** GDR off → host bounce (2 extra copies per direction;
  `NCCL_DEBUG=INFO` shows non-GDR transports); RoCE PFC misconfig → pauses,
  retransmits, latency spikes (`../Networking/README.md`); wrong HCA pinning
  (`NCCL_IB_HCA`) → one slow link shared by many ranks; P2P/GDR off on the
  *intra*-node leg too (IOMMU) → PCIe detour for NVLink-eligible pairs.
- **How to measure it:** `nccl-tests` busbw on 1 node vs 2 nodes (the ratio ≈ the
  ladder ratio when healthy); `ibstat`/PFC pause counters; DCGM per-NIC
  utilization; NCCL INFO trace transport lines (NET/IB vs SHM fallback).

## 9-Field Template — the multi-node performance hierarchy
- **What:** the ordered ladder **local HBM → NVLink (GPU↔GPU) → NVSwitch node
  fabric → NIC → IB/RoCE fabric → remote NIC → remote HBM**; each step down is
  ~1 order of magnitude slower, and the *dominant* step is the node boundary
  [E: 900/50 = 18×; 3350/900 ≈ 3.7×].
- **Why:** packaging physics — HBM is stacked on-package, NVLink is on the
  board, the NIC crosses a PCIe root, and the fabric crosses the rack. You cannot
  buy the top of the ladder outside the box; that is what `./Scale-Up-vs-Scale-Out.md`
  formalizes (scale-up = NVLink domain, scale-out = RDMA fabric).
- **How:** assign parallelism dimensions to hops so each byte rides the fastest hop
  that can carry it: TP AllReduce and intra-node AllToAll stay on hops 2–3; PP P2P,
  cross-node EP, CP, and P/D KV live on hops 4–5; DP is handled *above* the fabric
  (a router picks nodes, no per-layer collective). Placement (which TP group lives
  in which node, which P/D pool is co-located) is how you exploit the hierarchy.
- **When:** every capacity decision: TP degree ≤ node GPU count (≤8, or ≤72 on
  NVL72 [F: NVIDIA NVL72]); model too big for the node → PP/EP must cross hop 4;
  P/D pools co-located in one NVLink domain get a *fast* KV path, cross-fabric
  pools get the ms-class one (worked numbers in the RDMA Example above).
- **Hardware impact:** node anatomy (8 GPU + NVSwitch + 8 NIC + PCIe switch tree),
  NIC count and rate (NDR vs HDR per node), and whether the deployment has a
  72-GPU NVLink domain at all. The hierarchy is a property of the *machine*, not
  the software.
- **Inference impact:** ITL is set by hop 2 (TP AllReduce µs-class on NVLink,
  ms-class if it falls to the fabric [E: 32 MB AllReduce, 35.6 µs at 900 GB/s vs
  640 µs at 50 GB/s — arithmetic below]); TTFT picks up every PP hop (µs–10s µs
  each [A]); P/D TTFT adds one KV-transfer time (2.4 ms in-domain vs 42.9 ms on
  one link, Example above).
- **Example [E]:** move a 32 MB activation (e.g. one TP AllReduce payload at
  S=4096, d=4096, BF16): local HBM read `32e6 / 3.35e12 ≈ 9.6 µs`; NVLink
  `32e6 / 900e9 ≈ 35.6 µs`; PCIe x16 `32e6 / 64e9 = 500 µs`; one IB NDR link
  `32e6 / 50e9 = 640 µs` [E: bytes ÷ the STYLE-bank bandwidths, each step a
  ~10× jump — 3.7×, then 14×, then 18× NVLink→IB].
- **Failure modes:** any mechanism that demotes a byte one rung: NIC on the wrong
  NUMA node, GDR/P2P off, PFC storms, a straggler rank, the last-mile PCIe
  hop — all of them make "hop 2 work" run at "hop 4/5 speed" (Failure modes below).
- **How to measure it:** run the same `nccl-tests` collective on 1 node (NVLink)
  and across 2 nodes (RDMA) and tabulate busbw — you have directly measured the
  ladder; compare to the constants above (`../Hardware/README.md`).

## GPUDirect Storage (GDS)
**What/How:** GDS moves data **GPU HBM ↔ NVMe (via the NIC/DPU)** with no host-CPU
bounce — the GPU DMA engines read the disk directly [F: NVIDIA GPUDirect Storage
docs]. **When:** it is a *cold-path* feature — checkpoint/weight **load at startup**
and **weight streaming** for models that don't fit in HBM (FlexGen-style
offload [F: arXiv:2303.06865]); it is *not* on the hot inference path, because
hot inference reads weights and KV from HBM at hop-1 speed, and NVMe is ~2–3 orders
of magnitude slower than HBM3 [I: relative to the 3.35 TB/s constant — treat the
absolute NVMe figure as deployment-dependent]. Net: faster cold starts, cheaper
over-provisioned pools; irrelevant to ITL once the model is resident [I].

## Topology awareness: NUMA, NIC affinity, GPU affinity
The 8 GPUs, 8 NICs, and 2 CPUs in a node are **not** symmetric:
- **NUMA:** each NIC is wired to one CPU socket (NUMA node). A rank's inter-node
  traffic that exits through a NIC on the *other* socket crosses the inter-socket
  link (UPI/xGMI) — extra latency and stolen bandwidth for that rank alone [A:
  mechanism; `./Topology.md`].
- **GPU↔NIC affinity:** the PCIe switch tree pairs specific GPUs with specific
  NICs. `nvidia-smi topo -m` prints the matrix (PXN/PIX/NV/SYS labels); NCCL
  enumerates it at init and pins channels accordingly (`./NCCL.md`,
  `../Hardware/README.md`).
- **The practical rule:** keep *rank i, GPU i, NIC i* in one NUMA node, one PCIe
  switch. The failure of that rule is not "NIC i is a bit slow" — it is "rank i
  is the slowest participant in **every** inter-node collective, and a collective
  is a barrier: all 8 (or all 16) ranks wait for the slowest one" [I: barrier
  semantics, `./NCCL.md`].
Checklist: `nvidia-smi topo -m` (affinity matrix), `lscpu`/`numactl --hardware`
(NUMA map), process placement (run the rank on the right socket), and NCCL INFO
logs showing NET/IB channels bound to the expected HCAs.

## How the parallelism strategies map to the fabric
| Dimension | Collective / data | Volume per step | Fabric hop | Where |
|---|---|---|---|---|
| **TP** | 2 AllReduce/layer [F: arXiv:1909.08053] | `[B,S,d]` every layer — latency-critical | 2–3 (NVLink/NVSwitch) | **intra-node only** (`./Tensor-Parallelism.md`) |
| **PP** | P2P send/recv per stage boundary | `B·S·d·b` (8 KiB at B=1, d=4096 [E: 1·4096·2 B]) — small | 4–5 (RDMA) | **cross-node** (`./Pipeline-Parallelism.md`) |
| **EP** | 2 AllToAll/MoE layer | `B·k·d·b` each way (112 KiB @ B=1, d=7168, k=8 [E: 8·7168·2]) | 2–3 intra / 4–5 inter | NVSwitch intra-node; fast RDMA inter (`./MoE-Expert-Parallelism.md`) |
| **CP** | AllToAll (Ulysses) / ring rotations | bandwidth-hungry, ∝ S | 4–5 (fast RDMA / NVL72) | long context (`./Multi-GPU.md` §SP/CP) |
| **DP** | none per layer (router above the model) | request routing only | above the fabric (LB → node) | replicas across nodes (`./Load-Balancing.md`) |
| **P/D KV** | bulk KV copy at prefill→decode handoff | 2 GiB @ 4k ctx (worked above) | 2–3 if same NVL72 domain, else 4–5 RDMA | `./Prefill-Decode-Disaggregation.md` |

The rule, stated once: **latency-critical high-volume → top of the ladder;
small-volume bubble-tolerant → bottom of the ladder** — the same rule
`./Multi-GPU.md` and `./Scale-Up-vs-Scale-Out.md` state from the parallelism side.
NCCL is the thing that actually moves the bytes along whichever hop each
communicator sits on (`./NCCL.md`): a TP communicator over 8 GPUs inside one
NVLink domain pays an 8-GPU AllReduce even in a 1024-GPU cluster.

## Single-node vs multi-node (comparison)
| | Single node (8×H100, NVLink) | Multi-node (IB/RoCE fabric) |
|---|---|---|
| Practical TP | up to 8 (72 on NVL72) | TP across nodes is 18× slower per AllReduce [E: 900/50] → keep intra-node |
| EP degree | 8 (72 on NVL72) | 320-class only with many fast links + SHARP-class fabrics [I: DeepSeek-V3 ref deployment, `./MoE-Expert-Parallelism.md`] |
| PP | not needed (model fits) | the cross-node capacity axis; adds P2P hops to TTFT |
| P/D KV path | intra-node (NVLink/host path) | RDMA: ms-class per request (worked above) |
| Scaling limit | 8 GPUs (72 in NVL72 domain) | unbounded (fabric + power) |
| Failure domain | one PSU/PSU rail/rack | + network partitions, cross-node stragglers, PFC storms |
| Latency floor per hop | ~µs [A] | ~10s µs [A: RDMA hop; `../Networking/README.md`] |

The decision boundary is capacity: single node while the model (weights + KV +
batch) fits in 8×HBM and TP keeps ITL in budget; multi-node the moment it
doesn't — and the multi-node *shape* (TP+PP, TP+EP, P/D split) follows the
decision flow in `./Multi-GPU.md`. Full treatment of scale-up vs scale-out
economies: `./Scale-Up-vs-Scale-Out.md`.

## Failure modes (the multi-node bug catalog)
1. **NIC on the wrong NUMA node / PCIe switch.** Rank i's inter-node traffic
   crosses the inter-socket link; every inter-node collective waits for rank i
   (barrier semantics) → the *whole* communicator runs at the slow rank's speed.
   Symptom: multi-node busbw ≪ fabric peak, single-NIC DCGM counter hot. Fix:
   rank/GPU/NIC/NUMA alignment + `NCCL_IB_HCA`/topology env (`./Topology.md`).
2. **P2P or GDR off.** IOMMU, driver, or `NCCL_P2P_LEVEL` misconfig → NVLink
   pairs bounce through host memory (PCIe detour, ~14× slower [E: 900/64]);
   GDR off on the IB path → the double host bounce above. Symptom: NCCL INFO
   trace shows SHM/P2P fallback or non-GDR NET transports; busbw collapses to
   PCIe class. Fix: enable P2P + GPUDirect RDMA, verify in the INFO log
   (`./NCCL.md` §Debugging).
3. **IB vs RoCE PFC misconfig.** RoCE without correct PFC/ECN (priority flow
   control / lossless queue) → head-of-line blocking, PFC pause storms,
   retransmits — latency spikes under AllToAll shuffle; IB with the wrong HCAs
   pinned → one slow/overloaded link. Symptom: intermittent ITL tail + PFC
   pause counters climbing. Fix: lossless fabric config per vendor guidance
   (`../Networking/README.md`), verify with pause/retransmit counters.
4. **A slow node serializes the collective.** Every AllReduce/AllToAll is a
   barrier: one rank with a thermal throttle, power cap, ECC storm, or a slow
   NIC makes *all* ranks wait — with 64 ranks, your ITL tail is the 64th
   slowest machine in the cluster. Symptom: p99 ITL ≫ p50, one DCGM outlier.
   Fix: per-node health (clocks, ECC, NIC counters), evict the sick node
   (`./GPU-Metrics.md`, `./Diagnostics.md`).
5. **The "last-mile" PCIe hop.** Even with GDR, the GPU↔NIC leg is a PCIe 5.0
   x16 (~64 GB/s) path: a single NIC is ~50–64 GB/s, so one NIC is the ceiling
   for one rank's inter-node traffic; a NIC that *shares a PCIe switch* with
   another NIC or a storage NVMe splits bandwidth under overlap [A: PCIe switch
   topology is machine-specific — read `nvidia-smi topo -m`]. Symptom: one rank
   caps at ~50 GB/s while the fabric has 400 GB/s spare. Fix: dedicated NIC per
   GPU, spread ranks, move storage off the NIC's PCIe switch.

## How to measure it
- **Ladder ratio:** `all_reduce_perf` / `alltoall_perf` (nccl-tests) on 1 node
  vs 2 nodes at S = 32 MB — busbw(NVLink)/busbw(RDMA) ≈ 15–18× when healthy;
  much less → something is demoting a byte (Failure modes 1/2/5).
- **Topology ground truth:** `nvidia-smi topo -m` (GPU–NIC–NVLink matrix) before
  any tuning; NCCL INFO init block (which transport per channel).
- **Fabric health:** `ibstat` (link rate, state), PFC pause + retransmit
  counters (RoCE), DCGM per-NIC and per-NVLink utilization balanced across the
  communicator (a quiet NIC inside an active AllToAll = wrong path).
- **End-to-end:** sweep TP/PP/EP degree on the *same* cluster and plot ITL/TTFT
  (`Labs.md`, `Perf-Experiment-Template.md`); P/D KV time vs context length
  against the ladder model (2.4 ms in-domain vs ms-class cross-fabric, above).

## Key Takeaways
1. **One ratio runs the show:** NVLink ~900 GB/s vs IB NDR ~50 GB/s per link
   [E: 18×] — every byte crossing the node boundary loses ~an order of magnitude.
2. **Ladder = HBM → NVLink → NVSwitch → NIC → fabric → remote HBM**; place TP on
   the top rungs, PP/EP/P-D KV on the bottom, DP above the fabric entirely.
3. **RDMA + GPUDirect RDMA are what make the bottom rungs usable:** zero-copy,
   kernel-bypass, HBM-direct — without GDR every inter-node byte pays two host
   bounces.
4. **Multi-node bugs are locality bugs:** wrong NUMA NIC, P2P/GDR off, PFC
   misconfig, one straggler, the last-mile PCIe hop — all silently demote a byte
   one rung down the ladder.
5. **Single node until capacity forces the split**; then TP stays inside the
   NVLink domain and PP/EP/CP/P-D ride the RDMA fabric (`./Scale-Up-vs-Scale-Out.md`).

## Related
`./Multi-GPU.md` (the six dimensions + decision flow) · `./NCCL.md` (collectives +
tracing) · `./Scale-Up-vs-Scale-Out.md` (scale-up vs scale-out) · `./Topology.md`
(NUMA/PCIe/NIC placement) · `./Tensor-Parallelism.md` · `./Pipeline-Parallelism.md` ·
`./MoE-Expert-Parallelism.md` · `./Prefill-Decode-Disaggregation.md` (P/D KV over
the fabric) · `../Networking/README.md` (IB vs RoCE, SHARP, GPUDirect) ·
`../Hardware/README.md` (node + fabric constants).
