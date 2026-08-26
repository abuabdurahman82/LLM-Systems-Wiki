# Reference Architectures: 32 / 256 / 1,024-GPU Design Stories
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Three worked reference designs (32 / 256 / 1,024 GPUs). All Clos counts, injection rates, node-inject budgets and oversubscription figures quote the section constants bank verbatim (computed 2026-08-25). Conventions: GB = 10^9 bytes, GB/s bytes/s, Gb/s bits/s, GiB = 2^30 bytes. Where a claim rests on vendor marketing it is tagged `[F: vendor claim]` or `[A]`/`[I]`; no product scale numbers are fabricated.

## 30-Second Explanation
A GPU fabric design is five coupled decisions: **how many edge ports** (GPUs × NICs-per-GPU), **how many leaves and spines** (the Clos math), **which cable at what reach** (DAC vs AOC vs active fiber), **how much oversubscription** to accept, and **how the management + storage planes sit** relative to the compute plane. This page works three concrete designs end to end with real numbers. **Design A** is a small 32-GPU research cluster — the minimum that is still 1:1 non-blocking is **1 leaf + 1 spine at radix 8 [E]**, and the comfortable build is **4 leaves + 4 spines [A]**. **Design B** is a 256-GPU cluster where the **single-rail vs multi-rail** decision starts to bite. **Design C** is a 1,024-GPU AI factory compared across four fabric technologies (NDR/XDR InfiniBand, NVIDIA Spectrum-X, multi-vendor RoCE, a UET-ready design). The headline lesson: **topology counts are technology-independent** — the 32+32 leaf/spine arithmetic is set by GPU count × NIC rate, not by the vendor; the fabric choice changes cables, congestion control, tooling and operations, not the sheet-of-paper topology. Work the math mechanically ([42](./42-clos-fat-tree-math.md)), then pick a fabric ([49](./49-design-decision-tree.md)).

### Assumptions used throughout
- **Node model:** 8-GPU HGX-style server; scale-up is NVLink per node [F: vendor], the 400G/800G ports are pure scale-out.
- **1×400G per GPU** unless said otherwise; 400 Gb/s = **50 GB/s [E]**, 800 Gb/s = **100 GB/s [E]**.
- **Radix-8 leaf** in the bank model carries `ep` edge ports; the bank's pattern is `leaves = GPUs/32`, `spines = leaves` for 1:1 [E across 32→1, 128→4, 1024→32; extended to 256 as [A]].
- **Two-hop fabric:** any leaf reaches any other through one spine hop — the shape used at every scale here.
- **Healthy AllReduce ring ceiling:** busbw ≈ `0.95 × link × rails` (busbw is algbw ×
  2(n-1)/n, which at ring saturation equals the per-rank link rate); at realistic sizes
  ≈ 0.90–0.95× line rate [E-context; Lab 4, [53](./53-learning-labs.md)].

### The five decisions, stated as questions you must answer before ordering
1. **Edge ports:** how many GPUs, how many NICs per GPU, at what rate → fixes EVERYTHING downstream.
2. **Leaf/spine:** from edge and radix; 1:1 or oversubscribed.
3. **Cable:** DAC under ~3 m, AOC to ~100 m, active fiber beyond [A].
4. **Oversubscription:** 1:1 for inert fabrics/collective-heavy, 2:1+ if AllToAll is rare and cost is binding.
5. **Plane split:** compute / management / storage kept physically separate.

---

## Design A — 32-GPU research cluster
**Shape:** 4 × 8-GPU HGX-style nodes, 1×400G NIC per GPU, 1:1 non-blocking. Typical use: a research group validating a training run, a benchmark lab, or a first pilot before a larger build.

### A.1 The Clos arithmetic (from the bank)
- **32 GPU, 1×400G at radix 8 [E]:** the *minimum* non-blocking build is **1 leaf + 1 spine**, oversubscription **1.000**, injection = bisection = **0.200 TB/s [E]**.
- That 1+1 minimum is a single point of failure (one leaf, one spine: any switch restart or port fault halves or zeros connectivity) and leaves no headroom for rail or plane expansion. The **comfortable** build is **4 leaves + 4 spines [A]** — one leaf per node's ports, one spine per leaf, still strictly 1:1.
- **Two abstractions, do not mix [E-class this session]:** the bank's [E] Clos rows (ep = nodes, `leaves = GPUs/32`) model **one 400G uplink per 8-GPU node** — Design A's 4 nodes → edge = bisection = 4 × 400G = **0.200 TB/s [E]**. The *physical* fabric in A.5b/A.6 is **1×400G per GPU** (8 NICs/node, 32 edge ports): its edge = bisection = 32 × 400G = **12.8 Tb/s** — exactly 8× the per-node figure, because each node has 8 NICs. Both are 1:1 non-blocking; they differ only in NICs-per-node. (A.5b's "Bisection = 12.8 Tb/s" is the per-GPU value; A.1's "0.200 TB/s" is the per-node value.)

| Build | Leaves | Spines | Injection | Bisection | Oversub | SPOF? |
|---|---|---|---|---|---|---|
| minimum [E] | 1 | 1 | 0.200 TB/s | 0.200 TB/s | 1.000 [E] | yes |
| comfortable [A] | 4 | 4 | 0.800 TB/s | 0.800 TB/s | 1.000 [A] | no |

### A.2 Topology
```
                  SPINES  (4 x 400G, radix-8)
              s1            s2             s3             s4
             /|\           /|\            /|\            /|\
            / | \         / | \          / | \          / | \
   leaves  l1  l2  l3    l4 ...          ...            ...
   (one leaf per node)
        |\  |  |  |       each leaf:  8 x 400G down (1 node)
        | \ |  |  |                  4 x 400G up   (4 spines)
       n1  n2 n3 n4
   (4 x HGX-8 nodes, 8 x 400G NICs each; NVLink inside)
```
Four spines (s1–s4), four leaves (l1–l4). Each leaf attaches **one HGX node** (8 × 400G down) and uplinks **4 × 400G** to the spines — this is the **per-node abstraction** (bank [E] rows; radix-8 leaf = 4 down + 4 up). Any GPU-NIC reaches any other via **leaf→spine→leaf** = two hops — the same two-hop shape as every larger fabric in this section ([42](./42-clos-fat-tree-math.md)). The **per-GPU physical fabric** (1×400G/GPU) is 8× denser in edge ports — see the "two fabrics" note below.

> **Note on the two fabrics.** The A.2 sketch and the bank's [E] rows are the **per-node**
> abstraction (one 400G uplink per 8-GPU node). The **physical 1×400G-per-GPU** fabric in
> A.5b/A.6 has 8 NICs/node, so it needs 8× as many edge ports and bisection (32 edge ports,
> 12.8 Tb/s) as the per-node model (4 edge ports, 0.200 TB/s). Both are 1:1 non-blocking;
> the 0.200 TB/s vs 12.8 Tb/s gap is exactly that 8 NICs/node factor (A.1 "two abstractions").
> Leaf/spine counts for the physical per-GPU build follow from `edge = 8 × nodes` — work it in
> [42](./42-clos-fat-tree-math.md) with the convention you pick (the bank rows use the per-node one).

### A.3 NIC layout
- **Per node:** 8 GPUs × 1×400G NIC = **8 NICs, 8 × 400G = 3.2 Tb/s node injection [E]** (bank: 8×400G node inject = 400 GB/s = 3.2 Tb/s).
- **Per cluster:** 32 NICs. Leaf `l1` down-links all 8 NICs of node `n1`, etc.
- **NUMA/PCIe placement matters even here:** bind each NIC to the PCIe switch / socket that owns its GPU, or GPUDirect RDMA (GDR) quietly underperforms. Check with `nvidia-smi topo -m` (Lab 5, [53](./53-learning-labs.md)). A GPU-NIC pair on different sockets crosses QPI/UPI and halves effective GDR bandwidth.

### A.4 What 1:1 actually buys you — an AllReduce timing
For a 512 MiB AllReduce across all 32 GPUs, single 400G (50 GB/s), ring:
```
ring traffic/rank = 2(31/32)·512 MiB ≈ 31.5 GiB/rank
T_ring ≈ 2(31/32)·(512 MiB)/50 GB/s + 2(31)·α
       ≈ 661  ms  +  (latency term), α ≈ 2 µs => +0.124 ms
       ≈ ~661 ms  (bandwidth-dominated at this size)
busbw = algbw · 2(31/32) ≈ 48.4 GB/s  (≈ 97% of the 50 GB/s link)
```
So for large AllReduce the fabric is bandwidth-bound and 1:1 keeps busbw near the NIC limit; the latency term `2(n-1)α` only dominates for small messages. Mechanically worth having this in your head for any size — see [44](./44-performance-metrics-benchmarking.md).

### A.5 Cables — 400G DAC vs AOC reach
Reach is vendor-module-dependent; these are planning bands [A], not fixed specs:
| Media | Reach (typical) | Power/cost | Use at this scale |
|---|---|---|---|
| **DAC** (QSFP-DD/OSFP direct-attach copper) | ≤ ~3 m | lowest | **NIC↔leaf** (in-rack) |
| **AOC** (active optical cable) | ~3–100 m | mid | **leaf↔spine** across rows; long in-rack |
| **Active fiber + transceiver (DR4/FR4)** | 100 m–2 km | highest | cross-row / cross-room only |

A 32-GPU cluster in one rack can be **close to all-DAC**: every NIC↔leaf run is <3 m; only leaf↔spine hops (if the spine lives in another rack/row) and any cross-row runs need AOC.

#### A.5.1 Cable selection appendix (400G port types)
- **QSFP-DD / OSFP** are the two 400G (and 800G) pluggable form factors. Which cage your NIC and leaf expose fixes the cable family — check both ends before ordering.
- **Power budget intuition [A]:** DAC ≈ 1–3 W, AOC ≈ 5–10 W, active fiber transceiver ≈ 10–15 W per link. At 32 links (Design A) the difference is tens of watts — negligible; at 1,024 GPUs × 1 NIC it is meaningful (see C.7 / appendix).
- **BER/link-quality:** long copper and old fiber are where link errors hide; always run a link-ber / `ibdiagnet` scan at commissioning ([45](./45-troubleshooting-rdma-infiniband.md)).

### A.5b Full bandwidth accounting (Design A, 1:1, per-GPU fabric)
Every GPU-NIC has an identical path budget; here is the whole-cluster sum. With **32 edge ports** (1×400G/GPU), a 1:1 leaf is **radix-16 = 8 down + 8 up** (4 leaves × 8 down = 32 ≥ 32 ports; each of the 4 spines carries 8 uplinks to each of the 4 leaves = 32 spine ports = 12.8 Tb/s):
| Plane | Links | Rate | Aggregate |
|---|---|---|---|
| Node→leaf down | 32 NICs | 400G | 12.8 Tb/s |
| leaf→spine up | 4 leaves × 8 = 32 | 400G | **12.8 Tb/s** each way |
| Bisection (min-cut) | — | — | **12.8 Tb/s (1:1)** |
| Node injection/node | 8 | 400G | **3.2 Tb/s [E]** |
| Total node inject ×4 nodes | 32 | 400G | 12.8 Tb/s |

The point: at 1:1 the **leaf→spine layer carries all of the edge injection**, so bisection = edge. That equality is the definition of non-blocking. (The bank's [E] "0.200 TB/s" figure is the **per-node** abstraction — 4 nodes × 400G — see the "two fabrics" note above A.2.)

### A.6 Bandwidth budget (node inject)
| Node | NICs | Inject/node | Cluster edge (4 nodes) | Bisection needed (1:1) |
|---|---|---|---|---|
| 8-GPU HGX, 1×400G/GPU | 8 × 400G | **3.2 Tb/s [E]** | **12.8 Tb/s** | **12.8 Tb/s** |

At 1:1 the fabric is non-blocking for any single message, so NCCL AllReduce busbw is bounded only by the NIC — expect ~48 GB/s of 50 GB/s under a healthy ring [E-context].

### A.7 Management + storage network separation
- **Compute/backend plane:** the 4+4 fabric above, carrying **only** NCCL/collective traffic. Lossless by IB credits (InfiniBand) or PFC+ECN (RoCE).
- **Management plane:** separate out-of-band **1/10GbE** to BMC/iDRAC, console, PXE, and the fabric manager host (OpenSM/UFM or switch mgmt IPs). **Never** share with RDMA.
- **Storage plane:** separate (or lightly shared) **100/200GbE NVMe-oF / RDMA** to the parallel filesystem. Reason: checkpoint *incast* — every GPU simultaneously writes a checkpoint, a many-to-one burst that would perturb collectives (see [23](./23-roce-lossless-fabric-design.md), [50](./50-ai-networking-myths.md)).
- Practical line: a research box *can* share compute NICs for storage if checkpoint volume is tiny and jumbo + a dedicated QoS class are set; the clean separate-plane rule costs the same cabling and removes a whole failure class.

```
                 THREE PLANES (Design A, logical)
   COMPUTE (lossless)          STORAGE (RDMA/NVMe-oF)      MANAGEMENT (OOB 1/10G)
   4 leaves : 4 spines         2-4 x 100/200G switches      mgmt switch
        |                              |                        |
   [4 HGX nodes, 8x400G]         [parallel FS nodes]       [BMC/iDRAC, switch mgmt,
        |                              |                  PXE, console, OpenSM host]
   NCCL / collectives           checkpoint+dataset     provisioning + fabric mgmt
```
The compute plane carries **only** NCCL; storage and management are physically separate fabrics. Any shortcut that multiplexes them onto the compute NICs is a PFC-storm / loss risk under checkpoint incast ([23](./23-roce-lossless-fabric-design.md)).

### A.8 IB and RoCE variants side by side
| | **InfiniBand (NDR400) variant** | **RoCEv2 (400G) variant** |
|---|---|---|
| Losslessness | credit-based per-VL (native) | PFC + DCQCN/ECN |
| Congestion control | IB built-in, adaptive routing | DCQCN: switch WRED-ECN + receiver CNP |
| Fabric manager | OpenSM / UFM (subnet manager) | none — Ethernet QoS config |
| Key tools | `ibdiagnet`, `perfquery`, `opensm` | `ethtool -S`, PFC/ECN counters |
| Determinism | high, zero PFC tuning | requires threshold tuning |
| Lock-in | NVIDIA-ecosystem heavy | open, any NIC/switch |
| Pick when | "just works lossless" priority | shop already runs Ethernet |

RoCE is the *default* for a small research cluster when the operator already runs Ethernet and accepts one QoS pass; InfiniBand wins when "no PFC threshold to babysit" is the priority. Neither changes the 4+4 topology. Decision logic in [49](./49-design-decision-tree.md); packet-level difference in [51](./51-complete-packet-journeys.md).

### A.9 Failure modes to budget for
- **Single-leaf / single-spine minimum:** switch or SM/management fault takes it down; build 4+4 and add a **redundant OpenSM/UFM** (primary + standby) for the IB variant ([45](./45-troubleshooting-rdma-infiniband.md)).
- **GDR not engaging:** GPU↔NIC on different NUMA → halved GDR bandwidth; verify `nvidia-smi topo -m` early.
- **RoCE PFC storm from a storage burst:** canonical incast failure — keep storage off the compute plane (A.7).

### A.10 Commissioning checklist (Design A)
```
1. ibstatus / ethtool link up on all 32 NICs
2. nvidia-smi topo -m : confirm each NIC is NODE/PIX to its GPU (NUMA-correct)
3. ib_write_bw host-host : per-QP ~48 GB/s (400G) -> validates NIC/link (Lab 2)
4. all_reduce_perf across 32 GPUs : busbw ~48 GB/s (Lab 4)
5. ibdiagnet (IB) or PFC/ECN counter parity (RoCE) : fabric health scan (Lab 7/9)
6. Verify a checkpoint burst does NOT perturb AllReduce (storage-plane isolation)
```

---

## Design B — 256-GPU cluster
**Shape:** 32 × 8-GPU nodes, 400G, with the **multi-rail vs single-rail** decision explicit. Typical use: departmental/startup training cluster running LLM pretraining with real parallelism (TP+DP/FSDP).

### Bridge: the 128-GPU step (fully in the bank)
Before 256, note the bank's clean 128-GPU rung, useful as the parse of one increment:
- **128 GPU, 1×400G, radix 8 → 4 leaves + 4 spines [E]**, injection = bisection = **0.800 TB/s [E]**, oversubscription 1.000 [E] (ep=16).
- This is the exact structure of the "4+4 comfortable" Design A *doubled*: 128 GPUs attach to 4 leaves (32 GPU/leaf), which uplink to 4 spines.
- 256 GPU is two of these (8+8) [A, scaled]. Keeping the 128 rung in mind makes 256 (8+8) and 64 (2+2) trivial extensions of the same E/32 pattern.

### B.1 Clos counts
Scaling the bank's radix-8 1×400G pattern (`leaves = GPUs/32`, 1:1 ⇒ spines = leaves):
- **256 GPU → 8 leaves + 8 spines**, oversubscription 1.000 **[A — not an [E] row; scaled from the [E] pattern 32→1, 128→4, 1024→32 [I]]**.
- Edge = 256 × 400G = **102.4 Tb/s**; strict 1:1 carries 102.4 Tb/s bisection.
- **2:1 alternative:** 8 leaves / 4 spines → bisection 51.2 Tb/s. Acceptable only if the mix is overwhelmingly AllReduce/AllGather (evenly spread) and AllToAll is rare.

| Config | Leaves | Spines | Injection | Bisection | Oversub |
|---|---|---|---|---|---|
| 1:1 single-rail [A] | 8 | 8 | 102.4 Tb/s | 102.4 Tb/s | 1.000 |
| 2:1 single-rail [A] | 8 | 4 | 102.4 Tb/s | 51.2 Tb/s | 2.000 |
| 1:1 two-rail (2×400G/GPU) [A] | 16 | 16 | 204.8 Tb/s | 204.8 Tb/s | 1.000 |

### B.2 The multi-rail decision
- **Single-rail:** every GPU has **1×400G**; one NIC caps per-GPU busbw at one 400G link (~48 GB/s healthy). Cheapest; enough for most DP/TP mixes at this size.
- **Two-rail (2×400G/GPU):** each GPU gets **2 NICs**; NICs split into **rail 0 / rail 1**, each rail its own independent leaf/spine plane (8+8 per rail → 16+16 total). NCCL stripes across rails (multi-HCA, `NCCL_CROSS_NIC`), so per-GPU aggregate busbw approaches **2× single-rail (~96 GB/s)**. Cost: 2× NICs, ports, cabling, switch ports. Rail count × GPU count — see the `1024GPU rail 8x400G 8 planes → 256+256 [E]` shape at larger scale in [42](./42-clos-fat-tree-math.md).
- **Rail-optimized wiring:** all nodes' "rail 0" NICs attach to the *same* leaf/spine plane so one collective stays within a plane with no cross-plane hops. NCCL keeps this with `NCCL_CROSS_NIC=0` [F: NCCL docs].
- **Verdict rules of thumb [A]:**
  - Multi-rail when: collective-heavy pretraining, per-GPU busbw is the bottleneck, oversubscription unacceptable.
  - Single-rail when: TP-heavy, compute dominates step time, or budget forces it.

### B.3 Topology (two-rail version)
```
   PLANE 0 (rail 0)          PLANE 1 (rail 1)
   8 leaves : 8 spines        8 leaves : 8 spines
        |                           |
  node NIC#0  = rail-0          node NIC#1 = rail-1
  (per GPU: 400G NIC #0)       (per GPU: 400G NIC #1)

  node n1:  [GPU0-NIC0, ... GPU7-NIC0] -> plane 0
            [GPU0-NIC1, ... GPU7-NIC1] -> plane 1
```
Each node injects **2 × 3.2 = 6.4 Tb/s** [A] across two planes (16 × 400G/node). Cluster total = **204.8 Tb/s**.

### B.4 Blocking analysis
- **1:1 (8+8 single, or 16+16 two-rail):** non-blocking for any permutation; ring AllReduce at `0.95 × link` per rail, multi-rail stacks per rail.
- **2:1 (8 leaves / 4 spines):** bisection = injection/2. **AllReduce** still near-optimal (spreads evenly); **AllToAll / MoE dispatch** (many-to-many permutation, no reduction saving) and **incast** to a hot destination suffer — the hot receiver/spine shares half capacity. Bank precedent at scale: `1024GPU 1:2 oversub → 32 leaves/16 spines/bis 3.2 TB/s/ov 2.000 [E]`.
- **Incast in 256-GPU MoE:** expert-parallel dispatch makes many sources converge on the hot-expert node; 1:1 gives full bisection, 2:1 exposes it. See MoE skew in [54](./54-interview-design-questions.md) and [23](./23-roce-lossless-fabric-design.md).

### B.5 NCCL traffic expectations
| Collective | math | 1:1 single (400G) | 1:1 two-rail | 2:1 single |
|---|---|---|---|---|
| AllReduce ring | `0.95·link` | ~45–48 GB/s | ~90–95 GB/s | ~45–48 GB/s |
| AllToAll (per hot recv) | incast-bound | full bisection | hidden but bursty | half bisection |
| AllGather | `(n-1)/n·link` | ~45–48 GB/s | ~90–95 | ~45–48 |

Diagnostic rule: run `all_reduce_perf`; compare busbw to `0.95 × link × rails`; a shortfall points to rail imbalance, ECMP polarization, or oversubscription ([44](./44-performance-metrics-benchmarking.md), [46](./46-troubleshooting-roce-nccl.md)).

### B.6 Management, storage, scheduling
- Plane-separation rules from A.7; at 256 GPUs the **storage plane should definitely be independent** (256 GPUs checkpointing at once is a large incast burst).
- **Scheduling placement:** Slurm topology-aware allocation (`--switches`, `--exclusive=topo`) or Kubernetes topology-aware scheduling keeps a job's ranks under the same leaves/spines. Co-locating ranks keeps the latency term `2(n-1)α` small; scattering ranks across planes adds cross-plane hops (see [50](./50-ai-networking-myths.md)).

### B.7 Two design sketches
- **Sketch 1 (cost-optimized):** 8+8 single-rail, 1×400G, 1:1. Edge 102.4 Tb/s. Good for a 256 GPU shop whose DP/TP mix is bandwidth-modest.
- **Sketch 2 (performance):** 16+16 two-rail, 2×400G/GPU, 1:1. Edge 204.8 Tb/s. Choose when per-GPU busbw must double and AllToAll/incast headroom matters.

### B.8 Economics of the rail decision
Cost scales with **switch ports and NICs**, not raw bandwidth. Going two-rail roughly doubles NICs, cables, and leaf/spine ports for 2× per-GPU bandwidth. The trade is usually stated as:
- **Per-GPU bandwidth is the scarce, expensive resource** in LLM training — two-rail often pays for itself in faster step time if the workload is bandwidth-bound [A].
- But if the step is compute-bound (small TP, big batch, low comm fraction), the extra rails sit idle → money spent on nothing [A].
- **Decision heuristic [A]:** measure the comm-to-compute ratio on a single-rail pilot; if NCCL busbw is the wall (busbw ≈ 100% theoretical yet step time still fabric-limited), buy rails; if compute dominates, don't.

### B.9 NCCL tuning knobs for a 256-GPU fabric
- `NCCL_IB_HCA` — pin HCAs (e.g. `mlx5_0:1,mlx5_1:1`) to use both rails; default may pick one.
- `NCCL_CROSS_NIC=0` — keep each ring on one NIC/rail for rail-optimized fabrics [F: NCCL docs].
- `NCCL_IB_SL` / `NCCL_IB_TC` — service level (IB) / traffic class (RoCE) mapping to the lossless queue.
- `NCCL_IB_GID_INDEX` — RoCEv2 GID index (often 3 on mlx5 [A]); wrong index silently drops cross-subnet traffic.
- `NCCL_ALGO`, `NCCL_PROTO` — force Ring vs Tree, LL/LL128/Simple for benchmarking (Lab 16, [53](./53-learning-labs.md)).
- `NCCL_NET=Socket` — forces TCP; a classic diagnostic to prove IB vs sockets is the problem ([46](./46-troubleshooting-roce-nccl.md)).

---

## Design C — 1,024-GPU AI factory
**Shape:** bank's **1024 GPU 1×400G radix-8 → 32 leaves + 32 spines [E]**, bisection **6.4 TB/s [E]**, oversub **1.000 [E]**. (Full 8×400G-per-GPU rail build becomes 16–64 planes — see the `8 planes → 256+256` [E] shape in [42](./42-clos-fat-tree-math.md).) The **technology** is the variable here: the topology count is fixed at 32+32 by GPU count × NIC rate, **not** by vendor. Typical use: production AI factory / cloud training pod.

### C.0 Fixed topology, four technologies
| | Leaves | Spines | Edge | Bisection | Oversub |
|---|---|---|---|---|---|
| 1024 × 1×400G, radix-8 [E] | **32** | **32** | 1024 × 400G | **6.4 TB/s [E]** | 1.000 [E] |

The four options in C.1–C.4 all hang on this same 32+32 sheet. They differ in **switch silicon, NIC, congestion control, losslessness model, tooling, lock-in** — not leaf/spine arithmetic.

### C.1 Option A — NVIDIA InfiniBand NDR/XDR
- **Hardware:** Quantum-2 (NDR400, 64 ports / 32 OSFP [F: vendor]) or Quantum-X800 (XDR800, 144 ports [F: vendor]) + ConnectX-7/8 HCAs. **Vendor scale/perf claims are [A]/[I], not independent — no fabricated product-scale numbers appear here.**
- **Losslessness:** native per-VL credits; no PFC to tune.
- **Congestion control:** IB built-in + adaptive routing (ConnectX-5+ OOO placement, DC transport) — [03](./03-rdma-fundamentals.md), [45](./45-troubleshooting-rdma-infiniband.md).
- **In-network:** SHARP offloads AllReduce into Quantum switches (v2 HDR → v3 Quantum-2/NDR → v4 XDR [F: vendor-claimed generations]); NCCL uses it via `NCCL_COLLNET_ENABLE` [F: NCCL docs].
- **Scale to note:** NVIDIA positions Quantum for >100k-GPU single-fabric claims **[A]**; independent hyperscale deployments are real but the specific scale numbers are vendor-announced, not measured [I].
- **Ops:** OpenSM/UFM (SM HA), `ibdiagnet`/`perfquery`, P_Key partitioning.
- **Best fit:** NVIDIA-infrastructure shops wanting maximum per-QP determinism + in-network reduction, accepting NVIDIA-dominant tooling.

### C.2 Option B — NVIDIA Spectrum-X (Ethernet)
- **Hardware:** Spectrum-4 / SN5600 (64×800G [F: vendor spec]) + BlueField-3/ConnectX-8 **SuperNIC**; switch+NIC pair jointly implement AI-optimized RoCE extensions.
- **Differentiators [F: vendor spec]:** per-packet spraying (adaptive routing) of RoCE elephant flows; receiver-side reorder in the SuperNIC; hardware congestion control (TCC-class); MRC multipath (co-developed AMD/Broadcom/Intel/Microsoft/OpenAI [F]); **Spectrum-X Multiplane** for cross-plane load balancing [A].
- **Marketing numbers are claims, not fact:** "~1.6–1.9× gen-AI perf vs standard Ethernet" **[F: vendor claim]**; ">100,000 GPUs" multi-plane / MRC two-tier **[A — announcement/paper claim]**.
- **PFC status UNVERIFIED:** packaged as deterministic-lossless with reduced PFC reliance, but a blanket "PFC disabled" is **not confirmed** by a primary source here (research-roce reverify #3). Treat exact PFC policy as **UNVERIFIED**.
- **Ops:** NVIDIA NetQ / AI-Enterprise, DOCA, Base Command integration.
- **Best fit:** NVIDIA GPU factories (HGX/NVL), hyperscale training on NVIDIA networking; operator accepts NVIDIA switch+NIC pairing and resulting coupling.

### C.3 Option C — Multi-vendor RoCE (merchant silicon)
- **Hardware:** Broadcom Tomahawk-5 (BCM78900, 51.2 Tb/s, 64×800G [F: vendor IR]) or Marvell Teralynx-10 (51.2 Tb/s, 1.6T-capable [F: vendor]) + any RoCE NIC, run by Arista EOS / Cisco / Juniper / SONiC.
- **Losslessness:** PFC + DCQCN (switch WRED-ECN + receiver CNP); the tuning burden is real ([23](./23-roce-lossless-fabric-design.md), [46](./46-troubleshooting-roce-nccl.md)).
- **Load balancing:** ECMP flow hashing; Dynamic Load Balancing (DLB)/flowlet on TH5-class silicon fights hash polarization. **Meta's production RoCE fabric runs without DCQCN** — collective co-tuning + PFC [E: Meta SIGCOMM'24], a notable non-vendor datapoint ([50](./50-ai-networking-myths.md)).
- **Openness:** best-in-class — any NIC, any adequate switch, SONiC/merchant NOS; the "anti-NVIDIA-lock" default [I].
- **Best fit:** multi-vendor / open-Ethernet shops (AMD MI300/400, Intel Gaudi, generic x86+GPU), hyperscalers building commodity fabric, operators valuing choice over turnkey.

### C.4 Option D — UET-ready (Ultra Ethernet Transport)
- **Spec:** UEC UET **1.0 (June 11 2025) → 1.0.1 (Sep 5 2025) → 1.0.2 (Jan 2026) → 1.0.3 (July 16 2026, current) [F]**; UDP port **4793** (IANA) [F: author paper].
- **Transport:** connectionless ephemeral PDCs (0-RTT, no QP handshake); **RUD** (reliable unordered) enables per-packet spraying; receiver-side zero-copy direct data placement, no reorder buffer [F: spec/author paper].
- **Congestion control:** **NSCC** (sender, ECN+RTT+trimming) mandatory on every UET NIC; **RCCC** (receiver credits) optional; designed **lossy/best-effort-friendly**, overcoming RoCE's PFC head-of-line blocking [F: spec]. "CCv1/CCv2/TACC" are **non-spec terms** [F].
- **Link layer:** LLR (link-level retry ~1 µs) + optional CBFC [F].
- **Silicon status 2026 [I]:** spec complete, hardware **shipping but early**. AMD Pensando Pollara 400 (first UET-compliant NIC [F: vendor/announc.]); Broadcom TH6 / Tomahawk Ultra "UEC-compliant" shipping [F: vendor/I]; NVIDIA has **not** shipped UET silicon [F/I]; switch vendors (Arista/EOS, Juniper, Nokia) validating UET [I]. Adoption expected to ramp **2026–2027** [I: third-party].
- **In-network compute:** UEC INC standardized in-spec ($fi_collective$ [F]), optional; early silicon (Tomahawk Ultra switch-side AllReduce [F: vendor]) — the open counterpart to SHARP [I].
- **Best fit:** the **spec-conformant, early-silicon option** — choose for open multi-vendor Ethernet with a modern transport and tolerance for leading-edge ops; not the conservative 2026 production choice [I].

### C.5 Comparison table (all four)
| Dimension | A: IB NDR/XDR | B: Spectrum-X | C: multi-vendor RoCE | D: UET-ready |
|---|---|---|---|---|
| **Complexity** | medium (SM, LID, P_Key, QoS) | low–med (NVIDIA turnkey) | high (PFC/DCQCN tuning) | medium (new transport, early ops) |
| **Scalability** | proven large [A: vendor claim] | multi-plane >100k [A: claim] | proven hyperscale (Meta) [E] | spec: millions [F]; hw early [I] |
| **Operations** | OpenSM/UFM, mature | NVIDIA NetQ / AI-Enterprise | EOS/CloudVision, SONiC, Junos | nascent ops corpus |
| **Performance** | top busbw, SHARP | ~1.6–1.9× vs std Eth [F: vendor claim] | tuning-dependent; DLB helps | designed lossy+spray; early |
| **Interoperability** | NVIDIA-dominant ecosystem | **proprietary (NV switch+NIC)** | **most open, multi-vendor** | **most open, UEC multi-vendor** |
| **Maturity** | production 2026 [F] | production, hyperscale [F] | production 2026 [F] | **spec 1.0.3 [F]; hw early [I]** |

*No fabricated product-scale numbers. Every vendor scale/perf figure above is tagged `[F: vendor claim]` or `[A]`/`[I]`. UET is explicitly spec-conformant with 2026 early silicon [I].*

#### C.5b High-level trade table (when each wins)
| You are… | …pick |
|---|---|
| NVIDIA shop, want determinism + in-network reduce | A (IB NDR/XDR) |
| NVIDIA shop, want Ethernet + turnkey spray/CC | B (Spectrum-X) |
| multi-vendor / open-Ethernet, accept tuning | C (RoCE merchant) |
| open standard, forward-looking, tolerate early hw | D (UET-ready) |
| You care most about *not* being locked in | C or D (never A/B for lock-in) |

### C.6 Per-option failure modes
- **A (IB):** SM HA gap (single master SM is a SPOF — add standby); P_Key misconfig → nodes reach SM but not each other; rising BER → retries/stalls in a lossless fabric ([45](./45-troubleshooting-rdma-infiniband.md)).
- **B (Spectrum-X):** lock-in (NV switch+NIC required for full features); PFC/CC policy `UNVERIFIED`; proprietary vs UEC.
- **C (RoCE):** PFC storm from ECN/PFC threshold misalignment; ECMP hash polarization; DCQCN over/under-reaction ([46](./46-troubleshooting-roce-nccl.md), [23](./23-roce-lossless-fabric-design.md)).
- **D (UET):** early-silicon bugs, immature ops/knowledge base, vendor validation gaps [I].

### C.7 Telemetry, storage, management at scale
- **Compute 32+32 fabric is strictly NCCL.** Never mount storage or management on it.
- **Storage fabric:** separate 400/800G NVMe-oF plane; checkpoint bursts (a 100B model needs ~1.6 TB written per checkpoint [E]) stay off the compute plane ([23](./23-roce-lossless-fabric-design.md)).
- **Management:** OOB 1/10G + fabric-controller telemetry (gNMI/INT — INT is a **P4.org** spec, not IEEE [F]) into a dashboard with **capacity + PFC/ECN threshold SLO**. See [51](./51-complete-packet-journeys.md) for the control-loop picture.

### C.8 Capacity-planning worked example (checkpoint incast)
A 1,024-GPU cluster writing a **1.6 TB checkpoint in 60 s [E]** needs **26.7 GB/s = 213.3 Gb/s aggregate** storage write (bank: ckpt write in 60s = 26.7 GB/s). Per-GPU that is only ~16 MB/s — trivial per-port; the actual problem is the **simultaneous incast burst** and metadata, not per-port wire rate (see research-topology B.1). This is why the storage plane must be independent and why adaptive routing / congestion control is marketed for checkpoint loads.

### C.9 Operations tooling per option
| Task | A: IB | B: Spectrum-X | C: RoCE | D: UET |
|---|---|---|---|---|
| Link/NIC health | `ibstatus`, `ibv_devinfo` | `ethtool`, vendor tools | `ethtool -S` | same as C (early) |
| Fabric scan | `ibdiagnet`, `perfquery` | vendor telemetry | `ibdiagnet` (RoCE), switch gNMI | switch gNMI (early) |
| Congestion readout | IB counters | NVIDIA telemetry | PFC/ECN/CNP counters | ACK-echoed CC telemetry [I] |
| Collectives gate | `all_reduce_perf` | `all_reduce_perf` | `all_reduce_perf` | `all_reduce_perf` (libfabric path) |
| Logical isolation | P_Key | VLAN/tenant tooling | VLAN/tenant tooling | Secure Domains [F] |
| Config lifecycle | OpenSM/UFM intent | NetQ/AI-Enterprise | EOS/CloudVision, SONiC, Junos | new/immature [I] |

Hands-on for the first row of commands: [53](./53-learning-labs.md); conceptual packet/control flow: [51](./51-complete-packet-journeys.md).

### C.10 A 1,024-GPU commissioning / validation plan
Production fabrics do not "just work" at this scale; gate every phase ([44](./44-performance-metrics-benchmarking.md), [53](./53-learning-labs.md)):
```
Phase 0  Provisioning  : OS/Drivers/NCCL on all nodes; 32+32 leaves up.
Phase 1  Link soak      : ibdiagnet / ethtool link scan; 0 symbol errors,
                         0 flaps over 24h (Appendix F).
Phase 2  NIC-to-NIC     : ib_write_bw host-host on every NIC ~0.95x line.
Phase 3  Node-to-node   : all_reduce_perf within one leaf node; busbw ~ link.
Phase 4  Cross-plane    : all_reduce_perf across 32 leaves; busbw vs 0.95 × link × rails.
Phase 5  Incast probe   : alltoall_perf -- 1:1 should NOT show hot-spot collapse.
Phase 6  Storage burst  : a real checkpoint; verify compute plane stays clean.
Phase 7  Failure drill  : pull a spine / SM standby; job must survive.
Phase 8  SLO baseline   : record JCT + busbw for a fixed workload = the regression gate.
```
Each phase has a pass/fail numeric gate. Do not start Phase 5 until Phase 1 is clean — a single bad link at scale wastes days.

### C.11 Why this is one fabric, not three
A 1,024-GPU design is frequently drawn as "one big leaf-spine" but operated as **planes**: each rail/plane is itself a 1:1 fabric; the topology sheet is the set of planes plus their interconnections ([42](./42-clos-fat-tree-math.md)). This is why the 32+32 [E] count is a *plane-level* fact and why "1,024 GPUs" needs a rail/plane decision before the leaf count is meaningful. Keep Appendix A's rail/plane vocabulary in view when reading any vendor rack diagram.

---

## Design-parameters cheat table
| GPUs | Nodes (8-GPU) | NICs/GPU | Leaf/Spine (radix-8, 1×400G) | Node inject | Aggregate edge (per-GPU, ×NICs) | Bisection (bank [E] = per-node fabric) | Oversub |
|---|---|---|---|---|---|---|---|
| **32** | 4 | 1 | **1+1 min [E] · 4+4 comfy [A]** | 3.2 Tb/s [E] | 12.8 Tb/s | **0.2 TB/s [E]** (per-node: 4×400G) | 1.000 [E] |
| **128** | 16 | 1 | **4 + 4 [E]** | 3.2 Tb/s [E] | 51.2 Tb/s | 0.8 TB/s [E] (per-node: 16×400G) | 1.000 [E] |
| **256** | 32 | 1 (or 2) | **8 + 8 [A]** (16+16 two-rail) | 3.2 / 6.4 Tb/s [E] | 102.4 / 204.8 Tb/s | 1.6 TB/s [E] (per-node: 32×400G) | 1.000 [A] |
| **1,024** | 128 | 1 | **32 + 32 [E]** | 3.2 Tb/s [E] | 409.6 Tb/s | **6.4 TB/s [E]** (per-node: 128×400G) | 1.000 [E] |
| **8,192 [E]** | 1,024 | 1 | 256 + 256 [E] | 3.2 Tb/s | 3.28 Pb/s | **51.2 TB/s [E]** (per-node: 1024×400G) | 1.000 [E] |
| **32,768 [E]** | 4,096 | 1 | 1024 + 1024 [E] | 3.2 Tb/s | 13.1 Pb/s | 204.8 TB/s [E] (per-node: 4096×400G) | 1.000 [E] |

*The Bisection column quotes the bank's [E] rows, whose leaf/spine counts are in
**nodes** (ep = nodes, one 400G uplink/node); the Aggregate edge column counts the
**per-GPU** NICs (8× more). Both are 1:1 non-blocking in their own unit; the factor of 8
is NICs-per-node. Halving spines (e.g. 16 of 32) doubles oversubscription to 2:1
[E-pattern: 1024/16-spine = ov 2.000].*

**Scaling rules:** leaves = GPUs/32 (radix-8, 1×400G); spines = leaves for 1:1. NIC count multiplies (2 rails → 2×; 8×400G/GPU → 8×). NIC rate multiplies too: 800G doubles per-port injection; an 8×800G node injects **6.4 Tb/s [E]** (bank: 800 GB/s).

### Worked scaling examples from the cheat table
- **32 GPU at 800G (double the NIC rate):** leaves unchanged (GPUs/32 = 1 min, 4+4 comfy [A]); per-port 50→100 GB/s [E]; node inject 3.2→**6.4 Tb/s [E]**; edge 12.8→25.6 Tb/s. Same topology, double the bandwidth — the classic free lunch of a faster NIC on identical leaf/spine counts.
- **1,024 GPU at 8×400G, 8 planes [E]:** the bank's rail row gives leaves 256 / spines 256, injection = bisection = **51.2 TB/s [E]** (8× the 6.4 TB/s of the single-plane row). This is the shape an NVIDIA-class flagship actually uses ([42](./42-clos-fat-tree-math.md)).
- **1,024 GPU at 2:1 oversub [E]:** 32 leaves / 16 spines, injection 6.4 TB/s, bisection **3.2 TB/s**, ov **2.000 [E]** — the cost-cutting baseline for AllReduce-heavy training.

### A 12-step design procedure (any scale)
1. Count GPUs and NICs-per-GPU → edge ports.
2. Pick NIC rate → per-port GB/s (50 @400G, 100 @800G [E]).
3. Compute leaves = GPUs/32 and spines (= leaves for 1:1) [E/A].
4. Decide rail/plane count (how many NICs per GPU to use for scale-out).
5. Multiply injection by rails and NIC rate.
6. Choose oversubscription (1:1 vs 2:1) from the collective mix.
7. Select fabric technology → losslessness/CC model (IB, RoCE, Spectrum-X, UET).
8. Choose cables by reach (DAC/AOC/fiber) [A].
9. Split compute/management/storage planes.
10. Compute bandwidth budget (injection, bisection, checkpoint incast).
11. Add redundancy: switch HA, SM HA (IB), out-of-band mgmt.
12. Plan the benchmark gate `all_reduce_perf` busbw vs theoretical ([44](./44-performance-metrics-benchmarking.md)).

---

## Appendix A — Rail, plane, and multi-plane taxonomy
Terms get conflated; keep these straight:
- **Rail:** for a given NIC slot across nodes — "rail 0" = every node's NIC #0. One rail per NIC-per-GPU. Rail-optimized wiring sends all rail-0 NICs to the *same* leaves so a collective stays in one plane.
- **Plane:** an independent leaf/spine fabric. 1 rail per plane in simple builds; **multi-plane** = several planes with cross-plane routing/spraying to use all paths (Spectrum-X Multiplane, or IB/adaptive routing across planes).
- **Rail-optimized vs multi-plane:** rail-optimized *pins* traffic to a plane (NCCL `NCCL_CROSS_NIC=0`); multi-plane *spreads* across planes for load balancing and fault tolerance. The bank models both — see `1024GPU rail 8x400G 8 planes → 256+256 [E]`.
- **Why it matters:** a single 1:1 plane is the simplest correct answer; rails buy per-GPU bandwidth; multi-plane buys resilience and better statistical utilization at the cost of cross-plane hops. Choose based on whether your bottleneck is per-GPU bandwidth (rails) or incast/tail latency (multi-plane) [A].

## Appendix B — Storage & management fabric sizing
- **Compute plane:** strictly NCCL (0% storage/management traffic).
- **Management plane:** 1/10G OOB; a handful of management hosts + switch mgmt; negligible bandwidth, **isolation is the goal** (a management loop or SNMP poll storm must never induce RDMA loss).
- **Storage plane:** sized for the **checkpoint peak**, not the average:
  - A 100B-param model checkpoint ≈ **1.6 TB [E]** (params + BF16 grads).
  - Write in 60 s ⇒ **26.7 GB/s = 213.3 Gb/s aggregate [E]**; across 1,024 GPUs ~16 MB/s each — trivial per-port, the real pressure is the **simultaneous incast burst** and metadata (research-topology B.1).
  - Dataset streaming can be 1–10s TB/s aggregate ⇒ e.g. 8 TB/s = **64 Tb/s [E]** of read fabric (×8 vs bytes).
- **Separation justification:** a checkpoint burst is a many-to-one **all-to-storage incast**; shared with compute it perturbs every in-flight collective ([23](./23-roce-lossless-fabric-design.md), [50](./50-ai-networking-myths.md)).

## Appendix C — Oversubscription trade, quantified
Oversubscription **ov = injection / bisection**. `ov = 2` (half the spines) means the worst-case permutation and any incast to a hot spine carry only 50% of bisection.
- **What still runs fine at 2:1:** AllReduce / AllGather / ReduceScatter — these spread traffic evenly across the fabric, so each link sees uniform load.
- **What degrades at 2:1:** AllToAll (MoE dispatch, sequence-parallel K/V rotation) and any many-to-one incast — the hot destination/spine pays the ratio directly.
- **Decision [A]:** if your workload is ≥90% bandwidth-tame collectives, 2:1 saves spine cost with modest impact; if MoE/AllToAll/incast is core to the workload, stay 1:1. Measure with an `alltoall_perf` backbone before committing (Lab 16 / [44](./44-performance-metrics-benchmarking.md)).

## Appendix D — Power/thermal note (≥800G fabrics)
High-radix 800G leaves and coherent/spine optics draw real power; 1,024-GPU designs are liquid-cooled range (an NVL72-class rack is ~120–132 kW [F: publisher/secondary]). Budget per-port power at the switch and per-link power at the cable before you choose all-AOC vs all-DAC — see A.5.1. Not a topology decision, but a binding one at this scale.

## Appendix E — Management plane, concretely
- **OOB network:** a separate 1/10G L2/L3 to every BMC/iDRAC, switch mgmt port, and the fabric-manager/console hosts. PXE for provisioning.
- **Fabric manager placement:** OpenSM/UFM (IB) or switch NOS (RoCE) on a dedicated management host, **redundant** — IB has one master SM; add a standby to close the SPOF ([45](./45-troubleshooting-rdma-infiniband.md)).
- **Telemetry path:** gNMI/OpenConfig streaming from switches to a dashboard; INT (P4.org spec [F]) for per-hop where supported. Set alerting on: link flaps, symbol errors, PFC XOFF rate, ECN mark rate, job busbw.
- **Never route RDMA control or data over the management plane.** Isolation, not bandwidth, is the goal.

## Appendix F — Fabric-health baseline & SLO
Define a health gate before going live so a regression is visible ([44](./44-performance-metrics-benchmarking.md), [51](./51-complete-packet-journeys.md)):
- **Link health:** 0 symbol errors / link flaps over a soak window; IB target BER ≈ 1e-12 fabric, NVIDIA-qualified components 1e-15 [F: NVIDIA DGX SuperPOD doc].
- **Per-QP performance:** `ib_write_bw` host-host ≈ 0.95× line rate at 1 MiB [E-context].
- **Collective health:** `all_reduce_perf` busbw ≈ `0.95 × link × rails`; any persistent shortfall is a ticket ([46](./46-troubleshooting-roce-nccl.md)).
- **Congestion health (RoCE):** PFC XOFF rate and ECN/CNP counters should stay low during a clean job; spikes indicate threshold misalignment ([23](./23-roce-lossless-fabric-design.md)).
- **Job SLO:** fabric telemetry feeds a JCT/capacity model (see [54](./54-interview-design-questions.md) Architect scenario "capacity planning from JCT SLO").

## Appendix G — When NOT to use each design
- **Design A (1:1 32-GPU) is over-built** if you only need loose experimentation — a 2:1 or even spine-less single-leaf topology could suffice. Use 1:1 if you will benchmark against published numbers (which assume 1:1).
- **Design B 2:1** is a mistake if MoE/AllToAll/incast is core to the workload; keep 1:1 (Appendix C).
- **Design C UET** in 2026 is only for forward-looking operators; if you need a known-good 1,024-GPU production baseline today, A/B/C are safer than D [I].

## Appendix H — Frequently-asked design questions
- **Q: Can I mix 400G and 800G in one fabric?** A: Not cleanly at the same leaf radix — mixing NIC rates complicates the 1:1 math and cable plan. Prefer a single NIC rate per plane; add a faster plane for the tier that needs it [A].
- **Q: Do I need 1:1, really?** A: Only if you benchmark against published 1:1 numbers or run AllToAll/incast-heavy workloads (Appendix C). Pure AllReduce shops can often live at 2:1 [A].
- **Q: One giant leaf-spine or many small planes?** A: Planes give smaller blast radius on failure (Appendix A). Start 1:1 single-plane; split into planes as the failure domain must shrink [A].
- **Q: IB or RoCE for the *same* 4+4?** A: Identical topology; RoCE needs PFC/ECN tuning, IB needs an SM. The fabric manager and the tuning burden, not the ports, decide (A.8, [49](./49-design-decision-tree.md)).
- **Q: Does storage really need its own fabric?** A: Yes at any nontrivial checkpoint rate — a burst incast will perturb in-flight collectives (Appendix B, [23](./23-roce-lossless-fabric-design.md)).
- **Q: How do I find a bad cable before it bites?** A: `ibdiagnet`/BER scan + symbol-error watch at commissioning (Appendix F, [45](./45-troubleshooting-rdma-infiniband.md)).
- **Q: What is the cheapest safe first build?** A: Design A at 4+4, single 400G, 1:1, RoCE if you run Ethernet — the minimum that is both non-blocking and redundant [A].

---

## Further reading
- Clos / fat-tree math and all [E] shapes: [42](./42-clos-fat-tree-math.md)
- Benchmark it: [44](./44-performance-metrics-benchmarking.md), [16](../GPU-Communication/16-performance-benchmarking.md)
- Fix it: [45](./45-troubleshooting-rdma-infiniband.md), [46](./46-troubleshooting-roce-nccl.md)
- Choose the fabric: [49](./49-design-decision-tree.md); myths: [50](./50-ai-networking-myths.md)
- Packet journeys end to end: [51](./51-complete-packet-journeys.md); lossless RoCE: [23](./23-roce-lossless-fabric-design.md)
- Hands-on: [53](./53-learning-labs.md); interview prep: [54](./54-interview-design-questions.md)
- One-page recap: [55](./55-cheat-sheet.md)

## Key Takeaways
1. Topology counts are technology-independent — the 32+32 leaf/spine arithmetic is set by GPU count × NIC rate, not vendor; the fabric choice changes cables, congestion control, tooling and ops, not the sheet-of-paper topology.
2. Edge ports (GPUs × NICs-per-GPU at a chosen rate) fix everything downstream: radix-8 1×400G 1:1 gives leaves = GPUs/32, spines = leaves (32→1+1 min / 4+4 comfy, 128→4+4, 256→8+8, 1,024→32+32, all [E]/[A]).
3. Multi-rail (2×400G/GPU) roughly doubles per-GPU busbw (~48→~96 GB/s) at ~2× NICs, cables and switch ports — buy rails only when NCCL busbw is the wall, not when the step is compute-bound.
4. Oversubscription ov = injection/bisection; 1:1 for inert fabrics/collective-heavy, 2:1 only if AllToAll is rare — AllReduce/AllGather survive 2:1, but AllToAll/MoE dispatch and checkpoint incast pay the ratio directly.
5. Keep compute/management/storage planes separate — compute carries strictly NCCL; a 1.6-TB checkpoint in 60 s is 26.7 GB/s of all-to-storage incast that must never share the compute fabric, and every build gates on `all_reduce_perf` busbw vs 0.95 × link × rails.

## Related
- [42](./42-clos-fat-tree-math.md) — Clos/fat-tree math and the full [E] shape bank behind every count on this page.
- [49](./49-design-decision-tree.md) — the IB vs RoCEv2 vs Spectrum-X vs UET decision framework.
- [55](./55-cheat-sheet.md) — the section's one-page cheat sheet and final architecture.
- [23](./23-roce-lossless-fabric-design.md) — lossless RoCE design and the checkpoint-incast / plane-separation rationale.
- [44](./44-performance-metrics-benchmarking.md) — benchmarking gates and busbw-vs-theoretical validation.
- [53](./53-learning-labs.md) — hands-on labs the commissioning checklists cite (Labs 4, 5, 7, 9, 16).
- [../GPU-Communication/README.md](../GPU-Communication/README.md) — the scale-up / GPU-communication side of the fabric.
- [../Networking/README.md](../Networking/README.md) — the one-page general networking primer.

## References
- UEC / UET specification v1.0 → 1.0.3 (2025-06-11 → 2026-07-16), including UDP port 4793 (IANA) [F], referenced for the UET-ready option (C.4).
- Meta's production RoCE fabric running without DCQCN (collective co-tuning + PFC) — SIGCOMM 2024 datapoint [E], cited in C.3.
- NVIDIA vendor specs and claims: Quantum-2 (NDR400) / Quantum-X800 (XDR800), Spectrum-4 / SN5600, ConnectX-7/8 and BlueField-3/ConnectX-8 SuperNIC, SHARP/adaptiverouting generations; NCCL docs (NCCL_CROSS_NIC, NCCL_COLLNET_ENABLE) [F: vendor / NCCL docs].
- Merchant-silicon datasheets: Broadcom Tomahawk-5 (BCM78900), Marvell Teralynx-10; NVIDIA DGX SuperPOD fabric-health BER targets (1e-12 / 1e-15) [F: vendor IR / NVIDIA DGX doc].
- INT (in-band network telemetry) is a P4.org specification, not IEEE [F]; NVL72-class rack power ~120–132 kW [F: publisher/secondary].
- [E] all figures from the section constants bank (computed 2026-08-25).
