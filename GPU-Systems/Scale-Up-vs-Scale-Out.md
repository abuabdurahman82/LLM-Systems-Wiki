# Scale-Up vs Scale-Out (PART XXV)
`LAST_UPDATED: 2026-08-22 · Status: core page` · The regimes page for `Multi-GPU.md`:
two distinct interconnect worlds — the **NVLink domain** (scale-up) and the **RDMA
fabric** (scale-out) — why every LLM cluster is built from them, and what breaks when
you mix them up. Constants from `../Hardware/README.md`: NVLink H100 ~900 GB/s
aggregate [F: vendor spec], NVL72 = 72-GPU NVLink domain [F: NVIDIA], IB NDR 400G
~50 GB/s per link [F: vendor spec], PCIe 5.0 x16 ~64 GB/s [F: vendor spec].

## 30-Second Explanation
There are exactly **two** ways to connect GPUs, and they differ by an order of
magnitude:
```
SCALE-UP:   GPUs on one system, wired by NVLink/NVSwitch — one ~900 GB/s
            domain; 72 GPUs can behave almost like one giant GPU.
SCALE-OUT:  GPU servers joined by a network (InfiniBand/RoCE) — ~50 GB/s
            per link; every byte crosses a NIC.
ratio: 900 / 50 = 18×  [E] — one hop across the node boundary loses ~an order of magnitude
```
The whole discipline: **put the latency-critical, per-token collectives (TP
AllReduce, intra-node EP AllToAll) on scale-up; put the bandwidth-tolerant,
small-volume work (PP P2P, cross-node EP, P/D KV transfer, DP routing) on
scale-out** [I: matches `./Multi-GPU.md`, `./Multi-Node.md`]. The "atomic unit" of
a cluster is the NVLink node — an 8×H100 HGX/DGX box, or one NVL72 tray-domain.
Everything else is a matter of *which bytes get to ride the fast fabric*.

## The two regimes, precisely
**Scale-up (NVLink domain).** Multiple GPUs are **tightly connected inside one
system** — one board, one backplane, or one rack-scale NVSwitch tray fabric. They
share a single NVLink/NVSwitch domain: any-to-any, 1 hop, ~900 GB/s per GPU on
H100 [F: NVIDIA H100 spec]. From software's viewpoint the domain behaves almost
like **one big GPU**: HBM is the only "memory", GPU-to-GPU moves are µs-class
[A: µs/hop, intra-domain], and NCCL picks NVLink/NVSwitch transports for the whole
group without ever touching a NIC (`./NCCL.md`). The domain has a hard edge:
it is **8 GPUs on an HGX/DGX node**, or **72 GPUs on NVL72** [F: NVIDIA] — and
the edge is physical, not configurable.

**Scale-out (RDMA fabric).** Multiple GPU **servers** are joined over a network:
InfiniBand or RoCE, ~50 GB/s per 400G NDR link [F: vendor spec], usually one NIC
per GPU so a node can aggregate ~400 GB/s outbound [E: 50 × 8 = 400 GB/s/node].
The GPUs are on **different nodes**: every inter-GPU byte crosses a PCIe root, a
NIC, the switch fabric, another NIC, another PCIe root. RDMA (Remote Direct
Memory Access) + GPUDirect RDMA make that path zero-copy and kernel-bypass
[ F: vendor docs — see `./Multi-Node.md` §RDMA & GPUDirect RDMA]; without it every
byte pays two host-memory bounces.

## The contrast table
| | **Scale-up (NVLink/NVSwitch)** | **Scale-out (IB/RoCE)** |
|---|---|---|
| **Bandwidth** | ~900 GB/s aggregate per H100 [F: vendor spec]; NVL72 = 72-GPU domain [F: NVIDIA] | ~50 GB/s per NDR link [F: vendor spec]; ~400 GB/s/node aggregate with 8 links [E: 50×8] |
| **Latency** | ~µs/hop, any-to-any in 1 hop [A: intra-domain] | ~µs–10s µs per hop, RDMA one-sided verbs [A: RDMA hop; `../Networking/README.md`] |
| **Domain size** | 8 (HGX/DGX node) or 72 (NVL72) [F: NVIDIA] | unbounded — fabric + power set the limit |
| **What it's good for** | **TP** (2 AllReduce/layer, latency-critical), intra-node **EP** AllToAll | **PP** P2P, cross-node **EP** AllToAll, **P/D** KV transfer, **DP** routing (above the model) |
| **Cost** | fixed at purchase: you buy the whole domain; the fast fabric is *inside* the box | pay-per-link: add NICs + switch capacity as you grow; cheaper per GPU, ~18× slower per byte [E: 900/50] |
| **Failure domain** | one PSU/rack/tray takes out ≤8 (or ≤72) GPUs at once; NVL72 = bigger single point | partitions, PFC storms, straggler nodes, NIC/NUMA misalignment (`./Multi-Node.md` §Failure modes) |

## Why NVLink matters: it is what makes TP practical
TP does **2 AllReduce per layer, every token** [F: Megatron-LM arXiv:1909.08053]
— the most latency-critical traffic in inference (`./Tensor-Parallelism.md`).
Those collectives run at ~900 GB/s *inside* the NVLink domain; move the same
AllReduce onto one NDR link and it costs 18× longer [E: 900/50] — per layer, per
token, every request. That is not "a bit slower"; at TP=8 it turns a
compute-bound model comm-bound and ITL stops scaling with TP at all. Hence the
rule: **TP degree ≤ NVLink-domain size** (≤8 on HGX/DGX, ≤72 on NVL72 [F:
NVIDIA]), and TP crossing the domain boundary is a design error, not a tuning
knob.

## NVL72 / the "scale-up domain": when 72 GPUs become one GPU
NVL72 puts **72 GPUs in one NVLink domain** [F: NVIDIA]. Consequences:
- **TP up to 72.** A single model layer can be split across the whole domain at
  intra-domain bandwidth — previously the "TP ≤ 8" rule came from the *box*, not
  from the collective; NVL72 removes the box. [I: arithmetic — 72-GPU AllReduce
  on a 1-hop switch fabric costs little more than 8-GPU AllReduce; the ring
  lengthens but the fabric does not.]
- **EP AllToAll within the domain is nearly free.** A 72-way expert shuffle
  rides the same 1-hop NVSwitch fabric instead of the RDMA fabric [I: mechanism,
  `./MoE-Expert-Parallelism.md`]. This **changes the MoE and TP calculus**: MoE
  models that previously needed wide cross-node EP (320-class expert groups
  [A: DeepSeek-V3 reference deployment]) can now keep their entire expert group
  *inside* the domain; and a dense model that fits the 72 GPUs' combined HBM can
  run pure TP at the top of the ladder. The domain edge moves from 8 to 72 —
  so does the atomic unit.
- **The 18× ratio still applies at the domain edge.** Cross-domain traffic still
  crosses a NIC [E: 900/50] — NVL72 is a bigger scale-up domain, not a
  cluster-replacing one.

## Scale-out: IB/RoCE for the bandwidth-tolerant collectives
The fabric carries what *doesn't* need to run at TP frequency:
- **PP P2P:** activations between stages — small (`B·S·d·b`, 8 KiB at B=1,
  d=4096 [E: 1·4096·2 B]) and latency-tolerant to the pipeline bubble
  (`./Pipeline-Parallelism.md`).
- **EP AllToAll cross-node:** dispatch/combine per MoE layer — bandwidth-hungry
  but once per token, not twice per layer (`./MoE-Expert-Parallelism.md`).
- **P/D KV transfer:** bulk KV copy at the prefill→decode handoff — a
  bandwidth-bound copy, ideally GPUDirect at line rate
  (`./Prefill-Decode-Disaggregation.md`).
- **DP routing:** the load balancer picks a node; no per-layer collective
  crosses the fabric at all.
RDMA is what keeps these tolerable: one-sided verbs, zero-copy, kernel-bypass,
NIC pinned per rank (`./NCCL.md`, `./Multi-Node.md` §RDMA & GPUDirect RDMA). IB
is lossless with adaptive routing out of the box; RoCE needs PFC/ECN tuning to
stay lossless [F: vendor docs; `../Networking/README.md`].

## 9-Field Template — scale-up (NVLink domain)
- **What:** an 8-GPU (HGX/DGX) or 72-GPU (NVL72) **NVLink/NVSwitch domain**: a
  single system where every GPU pair is 1 hop apart at ~900 GB/s per GPU
  [F: NVIDIA H100 / NVL72 specs]; NCCL uses P2P/NVLink transports exclusively,
  no NIC involved.
- **Why:** the collectives with the worst latency profile live here — TP's 2
  AllReduce/layer every token, and intra-node EP AllToAll. At ~900 GB/s a 32 MB
  AllReduce payload costs ~35.6 µs [E: 3.2e7 / 9e11]; on one NDR link the same
  move is ~640 µs [E: 3.2e7 / 5e10] — 18× [E: 900/50], paid 64 times per forward
  pass at 32 layers.
- **How:** hardware: NVLink links + NVSwitch trays; software: NCCL auto-detects
  the domain (`nvidia-smi topo -m` shows NV links), TP groups are built inside
  the domain boundary, engines (vLLM/TRT-LLM/SGLang) set TP ≤ domain size.
  `./Topology.md` covers the intra-node wiring; `../Hardware/README.md` the
  specs.
- **When:** the first split, always. Model doesn't fit 1 GPU → TP within the
  domain; MoE with ≤72 experts-in-domain → intra-domain EP; P/D pools
  co-located in one domain get a µs-class KV path (`./Multi-Node.md` example).
- **Hardware impact:** the domain size (8 vs 72) is a *machine property*; TP/EP
  degree and KV-transfer times are all bounded by it; power/cooling are
  consolidated per domain.
- **Inference impact:** ITL floor is set here (AllReduce µs-class, not
  ms-class); TTFT scales with TP until comm dominates; intra-domain P/D KV is
  the ~2.4 ms handoff in `./Multi-Node.md`'s worked example.
- **Example [E]:** 32 MB TP AllReduce payload (S=4096, d=4096, BF16 ≈ 32 MB):
  NVLink `32e6 / 900e9 ≈ 35.6 µs`; one PCIe 5.0 x16 link `32e6 / 64e9 = 500 µs`
  [E: 900/64 ≈ 14× slower]; one IB NDR link `32e6 / 50e9 = 640 µs`.
- **Failure modes:** TP set above domain size (falls to scale-out, 18× [E]);
  P2P/NVLink pair disabled by IOMMU misconfig → PCIe detour, ~14× [E: 900/64]
  (`./Multi-Node.md` §Failure modes); NVL72 tray fault taking out the whole 72-GPU
  domain at once.
- **How to measure it:** `nccl-tests all_reduce_perf` on 1 node (busbw ≈ line
  rate); `nvidia-smi topo -m`; DCGM per-NVLink utilization balanced across the
  group.

## 9-Field Template — scale-out (RDMA fabric)
- **What:** the inter-node network: IB/RoCE leaf–spine with one NIC per GPU
  (400G NDR ≈ 50 GB/s/link [F: vendor spec], ~400 GB/s/node aggregate [E: 50×8]),
  RDMA + GPUDirect RDMA moving bytes HBM↔HBM with zero host copy.
- **Why:** capacity beyond the domain: PP stages, cross-node EP, P/D KV, and DP
  node selection. These are *bandwidth-tolerant* or *small-volume* collectives,
  so ~50 GB/s/link is acceptable where ~900 GB/s would be essential.
- **How:** NCCL NET/IB channels pinned per rank (`NCCL_IB_HCA`), rank/GPU/NIC
  NUMA alignment (`./Topology.md`), GDR enabled, lossless config (IB adaptive
  routing; RoCE PFC/ECN) [F: vendor docs; `../Networking/README.md`].
- **When:** the moment the model (weights + KV + batch) stops fitting one
  domain — PP crosses the fabric, wide EP crosses the fabric, P/D pools on
  different domains cross the fabric.
- **Hardware impact:** NIC count/rate per node, switch radix and leaf–spine
  depth, and whether the NIC-to-GPU pairing is 1-hop or 2-hop PCIe
  (`./Multi-Node.md` §Topology awareness).
- **Inference impact:** PP adds µs–10s µs of hop latency to TTFT [A]; cross-node
  EP AllToAll sets the MoE step floor; P/D KV costs ms-class per request
  (42.9 ms on one link, 5.4 ms over 8 NICs [E] — `./Multi-Node.md` worked
  example); DP adds nothing per layer.
- **Example [E]:** P/D KV handoff, 4k-token context, 32 layers, d=4096, BF16 =
  2 GiB: one NDR link `2.147e9 / 50e9 ≈ 42.9 ms`; 8 NICs in parallel
  (~400 GB/s) `≈ 5.4 ms` [E: plain division, from `./Multi-Node.md` constants].
- **Failure modes:** PFC storms (RoCE), wrong-HCA pinning, GDR off (double host
  bounce), one straggler node serializing every barrier, NIC on the wrong NUMA
  node (`./Multi-Node.md` §Failure modes 1–5, `../Networking/README.md`).
- **How to measure it:** `nccl-tests` busbw 1-node vs 2-node (healthy ratio ≈
  15–18× [E: 900/50, minus overhead]); `ibstat`, PFC/retransmit counters, DCGM
  per-NIC utilization.

## Topology: the two physical worlds
**8-GPU NVSwitch node (HGX/DGX — scale-up):**
```
        ┌─────────────── NVSwitch (any-to-any, 1 hop, ~900 GB/s/GPU) ───────────────┐
        │                                                                          │
 ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
 │  GPU 0      │═│  GPU 1      │═│  GPU 2      │═│  GPU 3      │   … GPUs 4–7
 └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
        │ PCIe           │ PCIe           │ PCIe           │ PCIe
 ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
 │   NIC 0     │  │   NIC 1     │  │   NIC 2     │  │   NIC 3     │   … NICs 4–7
 └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
   intra-node: any-to-any over NVLink, ~900 GB/s/GPU; TP=8, EP=8 all intra-domain
   outbound: one NDR link per GPU (~50 GB/s each) → this is where scale-out starts
```
**4× PCIe GPU (no NVLink — the anti-pattern):**
```
        ┌────────────── CPU root complex (single PCIe tree) ────────────┐
        │                                                              │
 ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
 │  GPU 0      │  │  GPU 1      │  │  GPU 2      │  │  GPU 3      │
 └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
   every GPU-to-GPU transfer: ~64 GB/s PCIe, through the root, no peer-to-peer
   shortcut (or PCIe P2P if the root allows it); TP=4 AllReduce ~14× slower
   than over NVLink [E: 900/64] — TP is effectively not an option
```
The HGX/DGX node "behaves like one big GPU" because **all 8 GPUs share the
NVSwitch fabric at full bandwidth, any-to-all** [F: NVIDIA]; "several
independent PCIe GPUs" have **no shared domain at all** — each GPU sees the
others only through ~64 GB/s PCIe paths, so a TP AllReduce pays ~14× the time
[E: 900/64] and a collective is barrier-synchronized on the slowest of them.
`nvidia-smi topo -m` tells you which world you actually bought (NV vs SYS
labels); `./Topology.md` maps it.

**Multi-node scale-out mesh (scale-out):**
```
  NODE 0 (8×H100, NVSwitch)      NODE 1 (8×H100, NVSwitch)      NODE 2 … NODE 255
┌─────────────────────────────┐ ┌─────────────────────────────┐ ┌──────────┐
│  G0..G7 ── NVLink ~900 GB/s │ │  G8..G15 ─ NVLink ~900 GB/s │ │  G16…   │
│  N0..N7 ── 1 NIC per GPU    │ │  N8..N15 ─ 1 NIC per GPU    │ │  …       │
└──┬────┬────┬────┬───────────┘ └──┬────┬────┬────┬───────────┘ └────┬─────┘
   │    │    │    │  400G NDR       │    │    │    │                  │
   ▼    ▼    ▼    ▼   ≈50 GB/s     ▼    ▼    ▼    ▼                  ▼
══════════════ leaf–spine IB/RoCE fabric (each GPU's own NIC into the fabric) ════════
   cross-node: every byte pays a NIC + ~50 GB/s link + switch hop(s)
   carries: PP P2P · cross-node EP AllToAll · P/D KV · (DP = router, above the model)
```

## The practical stack (which bytes ride which fabric)
```
latency-critical, high-volume (per-token, per-layer)
  TP AllReduce (2×/layer)          → SCALE-UP (NVLink)      ./Tensor-Parallelism.md
  intra-node EP AllToAll           → SCALE-UP (NVSwitch)    ./MoE-Expert-Parallelism.md
───────────────────────────────────────────────────────────────────────────────────
bandwidth-tolerant or small-volume
  PP P2P (stage activations)       → SCALE-OUT (RDMA)       ./Pipeline-Parallelism.md
  cross-node EP AllToAll           → SCALE-OUT (fast RDMA)
  P/D KV transfer                  → SCALE-OUT (GDR, line rate)  ./Prefill-Decode-Disaggregation.md
  DP node routing                  → ABOVE the fabric (load balancer)
```
The **atomic unit** is the NVLink node — an 8×H100 HGX/DGX box, or one NVL72
tray-domain: the smallest thing that "behaves like one GPU". Design
top-down from it: pack the model so TP groups and P/D pools sit *inside* one
domain (`./Multi-GPU.md` decision flow), and let PP/EP/DP span domains over the
fabric. `NCCL.md` is the engine that runs each communicator on the hop its
ranks sit on.

## Failure modes (mixing the two regimes)
1. **TP across a PCIe boundary / across the node boundary.** The classic
   "mixing" error: a 4-GPU PCIe box with TP=4 (AllReduce ~14× slower than
   NVLink [E: 900/64]), or TP=16 across two HGX nodes (AllReduce 18× slower
   [E: 900/50]). Symptom: ITL stops improving past small TP; NCCL INFO shows
   NET/SHM channels where P2P/NVLink was expected. Fix: TP ≤ domain size; move
   the overflow to PP/EP.
2. **Assuming a multi-node box behaves like one NVLink domain.** Two HGX nodes
   are *not* a 16-GPU domain: the byte that crosses the node boundary is on a
   ~50 GB/s link whether or not the GPUs "look" identical. Symptom: busbw
   collapses the moment the communicator spans nodes [E: 900/50]. Fix: treat
   each domain as one unit (`./Multi-Node.md` §Single-node vs multi-node).
3. **NVL72 vs HGX confusion.** An NVL72 is a **72-GPU single NVLink domain**
   [F: NVIDIA] — TP up to 72, EP AllToAll intra-domain; an HGX is an **8-GPU
   domain** that must scale out for anything bigger. Treating NVL72 as "9 HGX
   nodes in one rack" (or an HGX as a small NVL72) leads to wrong TP/EP degree,
   wrong capacity estimates (72×HBM vs 8×HBM), and wrong P/D placement.
   Symptom: capacity/latency models that don't match measured ITL. Fix: read
   the domain size from the platform docs, not the GPU count.
4. **Slow-path demotion inside a "fast" regime** (both regimes suffer this):
   P2P/GDR off → NVLink-eligible pairs bounce over PCIe (~14× [E: 900/64]);
   PFC misconfig on RoCE → latency spikes on the scale-out fabric
   (`./Multi-Node.md` §Failure modes, `../Networking/README.md`).

## How to measure it
- **Ladder ratio:** `all_reduce_perf` on 1 node (NVLink) vs 2 nodes (RDMA) at
  32 MB — healthy ≈ 15–18× [E: 900/50]; much less → a byte is being demoted.
- **Domain ground truth:** `nvidia-smi topo -m` (NV vs SYS labels), NCCL INFO
  init block (which transport per channel: NVLS/P2P/SHM vs NET/IB).
- **Fabric health:** `ibstat`, PFC/retransmit counters, DCGM per-NIC and
  per-NVLink utilization (`./Multi-Node.md` §How to measure it).
- **End-to-end:** sweep TP/PP/EP degree on the same cluster; ITL/TTFT should
  bend exactly where the parallelism dimension crosses from scale-up to
  scale-out.

## Key Takeaways
1. **Two regimes, one order of magnitude apart:** NVLink domain ~900 GB/s vs
   IB NDR ~50 GB/s per link [E: 900/50 = 18×]; the node boundary is the cliff.
2. **Scale-up carries the latency-critical splits** (TP, intra-node EP);
   **scale-out carries the bandwidth-tolerant ones** (PP, cross-node EP, P/D KV,
   DP routing).
3. **The atomic unit is the NVLink node** — 8×H100 (HGX/DGX) or the 72-GPU NVL72
   domain [F: NVIDIA]; design around it, not around raw GPU counts.
4. **PCIe is neither regime:** 4 PCIe GPUs with no NVLink get ~64 GB/s
   peer paths [E: 900/64 ≈ 14× below NVLink] and cannot run TP.
5. **The failure modes are boundary errors:** TP across a domain edge,
   multi-node boxes assumed to be one domain, NVL72 vs HGX confusion, and
   slow-path demotion (P2P/GDR/PFC) inside a fast regime.

## Related
`./Multi-GPU.md` (the six dimensions + decision flow) · `./Tensor-Parallelism.md`
(TP's 2 AllReduce/layer) · `./Pipeline-Parallelism.md` (PP P2P on the fabric) ·
`./MoE-Expert-Parallelism.md` (EP AllToAll, intra- vs inter-domain) · `./NCCL.md`
(collectives + transports) · `./Multi-Node.md` (the node/fabric detail, RDMA,
ladder) · `./Topology.md` (NUMA/PCIe/NIC placement) ·
`./Prefill-Decode-Disaggregation.md` (P/D KV over the fabric) ·
`../Hardware/README.md` (NVLink/NVSwitch/IB/PCIe constants) ·
`../Networking/README.md` (IB vs RoCE, SHARP, GPUDirect).
