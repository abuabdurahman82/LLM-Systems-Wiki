# GPU Topology Matters (PART XXVI)
`LAST_UPDATED: 2026-08-22 · Status: core page` · Source note: topology semantics
cross-checked against `nvidia-smi`/NVIDIA docs [F]; bandwidth constants from
`../Hardware/README.md` (NVLink ~900 GB/s H100 aggregate, PCIe 5.0 x16 ~64 GB/s,
IB NDR ~50 GB/s/link). The fabric this page sits under: `./Multi-Node.md`.

## 30-Second Explanation
**Topology** is the physical/interconnect layout inside one machine: which GPUs are
joined by NVLink, which GPUs/NICs hang off which PCIe switches, and which CPU socket
(NUMA node) each of them belongs to. It determines the bandwidth and latency of
**every** GPU↔GPU and GPU↔NIC path in the box [I]:
```
fastest → slowest (intra-node):   NVLink (~900 GB/s)  >  PCIe same switch (~64 GB/s)
                                  >  PCIe across root/NUMA  >  cross-socket (UPI/xGMI hop)
one misrouted path → the SLOWEST path sets the pace of every collective that
touches it, because a collective is a barrier: all ranks wait for the slowest rank [I].
```
The tool that prints this is `nvidia-smi topo -m`: a matrix where each cell is a code
(NV#x / PIX / PHB / NODE / SYS) naming the fastest path between the two endpoints.
**Reading that matrix correctly is the difference between NVLink-class NCCL
throughput and a silent 10–15× collapse** [E: 76 µs → 889 µs AllReduce, below] —
the single most common multi-GPU performance bug class in this handbook
(`./Multi-Node.md` §Failure modes, `./NCCL.md` §Failure modes).

## What "topology" means, precisely
A node's fast fabric is a **tree + mesh hybrid**:
- **NVLink/NVSwitch:** an explicit GPU-to-GPU fabric, independent of PCIe. On an
  8-GPU SXM node with NVSwitch, every GPU pair talks through the switch fabric at
  ~900 GB/s aggregate [F: NVIDIA H100 spec; `../Hardware/README.md`].
- **PCIe:** a switch tree. Each GPU and each NIC sits under some PCIe switch,
  which sits under some PCIe root on some CPU socket. Two endpoints under the same
  leaf switch get a **P2P** (peer-to-peer DMA) path at full PCIe speed; across
  switches/root complex they cross the host bridge; across CPU sockets they cross
  the inter-socket link (UPI/xGMI) [F: PCIe/NVLink topology docs].
- **NUMA nodes:** each CPU socket owns a half of the PCIe tree (and its own memory).
  A NIC or GPU whose PCIe root lives on the *other* socket pays an extra hop for
  every byte the host touches [A: mechanism; socket-to-socket links are a small
  fraction of local memory bandwidth].

Software (NCCL, the kernel scheduler, your rank placement) can only *choose among
the paths the hardware offers*. The topology is the constraint set; `nvidia-smi
topo -m` is the printed map of it.

## `nvidia-smi topo -m` — representative output
**REPRESENTATIVE OUTPUT — illustrative 8-GPU SXM/HGX-style node (8 GPUs + 8 NICs,
2 sockets, GPU i wired to NIC i); NOT a capture from a real machine. Your real
matrix has your own device names and possibly different codes (e.g. NV4 vs NV6,
PXB entries).**
```
$ nvidia-smi topo -m
  	GPU0	GPU1	GPU2	GPU3	GPU4	GPU5	GPU6	GPU7	NIC0	NIC1	NIC2	NIC3	NIC4	NIC5	NIC6	NIC7
GPU0	 X	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	 PIX	PHB	PHB	NODE	NODE	NODE	NODE	NODE
GPU1	 NV4	 X	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	PHB	PIX	PHB	NODE	NODE	NODE	NODE	NODE
GPU2	 NV4	 NV4	 X	 NV4	 NV4	 NV4	 NV4	 NV4	PHB	PHB	PIX	NODE	NODE	NODE	NODE	NODE
GPU3	 NV4	 NV4	 NV4	 X	 NV4	 NV4	 NV4	 NV4	PHB	PHB	PHB	PIX	NODE	NODE	NODE	NODE
GPU4	 NV4	 NV4	 NV4	 NV4	 X	 NV4	 NV4	 NV4	NODE	NODE	NODE	NODE	PIX	PHB	PHB	PHB
GPU5	 NV4	 NV4	 NV4	 NV4	 NV4	 X	 NV4	 NV4	NODE	NODE	NODE	NODE	PHB	PIX	PHB	PHB
GPU6	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	 X	 NV4	NODE	NODE	NODE	NODE	PHB	PHB	PIX	PHB
GPU7	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	 NV4	 X	NODE	NODE	NODE	NODE	PHB	PHB	PHB	PIX
NIC0	 PIX	PHB	PHB	NODE	NODE	NODE	NODE	NODE	 X	PHB	PHB	NODE	NODE	NODE	NODE	NODE
NIC1	PHB	PIX	PHB	NODE	NODE	NODE	NODE	NODE	PHB	 X	PHB	NODE	NODE	NODE	NODE	NODE
NIC2	PHB	PHB	PIX	NODE	NODE	NODE	NODE	NODE	PHB	PHB	 X	NODE	NODE	NODE	NODE	NODE
NIC3	PHB	PHB	PHB	PIX	NODE	NODE	NODE	NODE	NODE	NODE	NODE	 X	PHB	PHB	PHB	PHB
NIC4	NODE	NODE	NODE	NODE	PIX	PHB	PHB	PHB	NODE	NODE	NODE	PHB	 X	PHB	PHB	PHB
NIC5	NODE	NODE	NODE	NODE	PHB	PIX	PHB	PHB	NODE	NODE	NODE	PHB	PHB	 X	PHB	PHB
NIC6	NODE	NODE	NODE	NODE	PHB	PHB	PIX	PHB	NODE	NODE	NODE	PHB	PHB	PHB	 X	PHB
NIC7	NODE	NODE	NODE	NODE	PHB	PHB	PHB	PIX	NODE	NODE	NODE	PHB	PHB	PHB	PHB	 X
LEGEND:
  X	= GPU/NIC is the same device
  NV#x= NVLink, x = number of links (here: 4) between the two GPUs
  PIX = connected via a PCIe switch
  PHB = connected via two hosts with the PCIe host bridge (same socket)
  NODE= connected via NUMA nodes (inter-socket)
  SYS = connected via a system (socket) interconnect
```

## Legend — the codes, fastest to slowest
| Code | Meaning (GPU↔GPU) | Meaning (GPU↔NIC) | Path character |
|---|---|---|---|
| **NV#x / NVx** | NVLink, x = link count (more links = more BW) | (n/a — NICs don't do NVLink) | on-board fabric, ~900 GB/s aggregate [F] |
| **PIX** | same PCIe switch (leaf) | NIC and GPU under the **same PCIe switch** | P2P at full PCIe x16 speed, ~64 GB/s [F] |
| **PXB** | different PCIe switches, same PCIe host bridge | same host bridge, different leaf switch | P2P, slightly less efficient than PIX [F: nvidia-smi docs] |
| **PHB** | across the PCIe host bridge / root complex, **same** CPU socket | NIC on the GPU's own NUMA node, different switch tree | host-bridge hop; P2P often still possible |
| **NODE** | different NUMA node (crosses the socket interconnect) | NIC on the **other** CPU socket | inter-socket hop; P2P usually degraded/off |
| **SYS** | different system (socket) interconnect | NIC on another system/socket | slowest intra-node class [F: nvidia-smi docs] |

**Reading rule: the lower a code in this list, the faster the path.** A matrix where
GPU rows say NV4 everywhere is a healthy NVSwitch node; a matrix full of
PIX/PHB/NODE is a PCIe box [A: the two dominant topologies in the field].

## Interpretation examples
- **Full 8-GPU NVSwitch node:** every GPU↔GPU cell is `NV4` (or the generation's
  link count) — any-to-any all-to-all NVLink; intra-node path choice barely matters
  because every pair is equal and fast [I: this is why TP≤8 is "free" on HGX/DGX].
- **PCIe box (no NVLink):** the GPU↔GPU cells are a mix of `PIX` (same leaf
  switch — P2P works at full speed), `PHB` (same socket, across the root), `NODE`
  (other socket). NCCL will happily run TP=8 on this, but at PCIe-class bandwidth
  (~64 GB/s vs ~900 GB/s — 14× [E: 900/64]).
- **NIC on the wrong NUMA node:** the NIC's row shows `NODE` (not `PIX`/`PHB`) for
  the GPU it was *supposed* to serve — e.g. NIC0 wired under socket-1's tree while
  GPU0's root is on socket 0. In the representative matrix above, GPU0's own NIC
  (NIC0) is `PIX`; look at GPU0 vs NIC4..NIC7 and you see `NODE`: those are the
  "far" NICs, and a rank that is forced to use one pays the inter-socket hop on
  every inter-node byte [I].
- **Hybrid box (uneven NVLink):** some GPU pairs `NV4`, others `PIX`/`PHB` (e.g. a
  4-GPU NVLink domain with 4 PCIe-only GPUs). NCCL's ring/tree for a comm spanning
  all 8 will pick the slow path for some ranks' legs — a subtle, per-channel
  degradation rather than a hard failure [I].

## NUMA locality, PCIe switches, NVLink paths
- **NUMA:** each socket owns half the PCIe tree. A NIC on the far socket adds a
  host-bridge/inter-socket hop to every byte the host (or the far PCIe path)
  touches — and for RDMA it means the GPU↔NIC leg is a longer, shared PCIe route
  [A: mechanism; `./Multi-Node.md` §Topology awareness].
- **PCIe switches:** GPUs/NICs behind the *same* leaf switch get P2P at full speed
  (the `PIX` cell). Across leaves or roots the path goes through the host bridge
  (`PHB`) and P2P may be unavailable at all — NCCL then falls back to shared
  memory / host copies (`./NCCL.md` §Failure modes 1–2).
- **NVLink paths:** on an NVSwitch node all intra-node pairs are NVLink, so
  *intra*-node path choice matters little; the matrix matters enormously for
  (a) confirming NVLink is actually present (a dead link shows fewer `NV` links or
  PCIe codes), and (b) the GPU↔NIC half — because the *last mile out of the node*
  is PCIe, and the cross-node byte pays it (`./Multi-Node.md` ladder hops 4–5).

## 9-Field Template — `nvidia-smi topo -m` (how to read it)
- **What:** the NVIDIA CLI command that prints the node's topology matrix:
  rows/columns = every GPU and (with default flags) every NIC/HCA; each cell =
  the code for the fastest path between the two endpoints (legend above)
  [F: nvidia-smi docs].
- **Why:** it is the machine's *ground truth* for intra-node paths, and it is what
  NCCL enumerates at init to pick transports (`./NCCL.md`). If the matrix says
  `SYS` where your design assumed `NV4`, your expected AllReduce time is wrong by
  an order of magnitude — before a single kernel runs.
- **How:** (1) read the GPU↔GPU block: all `NV#x` → NVSwitch domain; mixed codes
  → PCIe/hybrid box. (2) For each NIC, find which GPU(s) it is `PIX` to — that's
  the NIC's "home" GPU. (3) Check `NODE`/`SYS` cells: every one is a place a byte
  can be demoted. (4) Cross-check link counts with `nvidia-smi nvlink -s` and the
  device list with `lspci` / `ibstat` (`NICx` names in the matrix are the same
  devices `NCCL_IB_HCA` selects) [I].
- **When:** at cluster/node bring-up, after any hardware swap, driver or IOMMU
  change, or NCCL upgrade, and the moment NCCL busbw regresses — it is step 0 of
  the debugging tree in `./Diagnostics.md`.
- **Hardware impact:** the matrix *is* the PCIe switch tree + NVLink map + NIC
  placement of this machine; two otherwise-identical servers can differ here
  (cable swaps, NIC populated in the wrong riser) [A: observed failure mode].
- **Inference impact:** it decides which rung of the ladder in `./Multi-Node.md`
  each rank's collective lands on. A rank whose AllReduce leg is `PHB` instead of
  `NV4` runs at PCIe-class speed — and the collective barrier means the whole TP
  group runs with it [I: barrier semantics].
- **Example [E]:** 32 MB AllReduce, n=8, ring-traffic wire = 2·(7/8)·32 MB = 56 MB:
  all-`NV4` matrix → 56 MB ÷ 900 GB/s ≈ 62.2 µs (+14 µs latency ≈ 76 µs); the same
  comm on a `PIX`-only (PCIe ~64 GB/s) matrix → 56 MB ÷ 64 GB/s ≈ 875 µs (+14 µs ≈
  889 µs). The matrix alone predicts a 11.7× per-AllReduce spread [E: 875/62.2;
  arithmetic consistent with `./NCCL.md` §Cost model].
- **Failure modes:** misreading it — treating `NV4` as "NVLink present" without
  checking link count (fewer links = less BW); assuming `PIX` implies P2P when
  IOMMU/driver disables it; trusting a matrix from a different machine than the
  one you benchmarked [I].
- **How to measure it:** re-run `nvidia-smi topo -m` + `nvidia-smi nvlink -s`
  before/after every change; compare `nccl-tests` busbw to the ladder
  (`../Hardware/README.md` constants); DCGM per-NVLink/per-NIC counters to confirm
  the *actual* path NCCL uses matches the matrix (`./NCCL.md` §How to measure it).

## 9-Field Template — the topology mistakes that kill NCCL
- **What:** the recurring set of intra-node topology misconfigurations that
  silently demote NCCL paths [I: well-known failure mode; `./Multi-Node.md`
  §Failure modes 1, 2, 5]:
  1. **P2P disabled** (IOMMU, `NCCL_P2P_LEVEL`, driver) → NVLink/PCIe pairs bounce
     through host memory.
  2. **GDR off** on the RDMA path → double host bounce on every inter-node byte
     [F: NVIDIA GPUDirect RDMA docs; `../Networking/README.md`].
  3. **NIC on the wrong NUMA node / PCIe switch** → the RDMA path crosses the host
     bridge; one rank's inter-node leg runs slower than its peers.
  4. **GPU pair on different PCIe domains with no P2P** → NCCL falls back to host
     bounce for that pair.
  5. **Uneven (hybrid) NVLink** → some ring/tree legs take PCIe while others take
     NVLink; NCCL picks the slow path for some ranks.
- **Why:** collectives are barriers over a fixed ring/tree: the slowest leg of the
  slowest rank caps the whole group's time, and every layer pays it
  (TP: 2×/layer × 32 layers × every token) [I: barrier semantics, `./NCCL.md`].
- **How:** each mistake is detectable *before* it costs you a week:
  `nvidia-smi topo -m` (matrix sanity), `nvidia-smi nvlink -s` (link count/status),
  `lspci` (NIC placement), `numactl --hardware` (NUMA map), `NCCL_DEBUG=INFO`
  trace (which transport each channel actually got — "P2P disabled" or `SHM`/
  non-GDR `NET/IB` lines are the smoking gun) [F: nccl docs].
- **When:** bring-up and any change event (new node, re-cabling, BIOS/IOMMU flip,
  driver update, NIC repopulation); also the first stop when multi-node busbw ≪
  fabric peak with no fabric-side fault (`./Diagnostics.md`).
- **Hardware impact:** which boxes can even *have* these bugs — PCIe-only boxes
  have no NVLink to lose; hybrid boxes have the uneven-NVLink mode; every box
  with NICs on both sockets can have the NUMA-mismatch mode [I].
- **Inference impact:** a TP group demoted from NVLink to PCIe-class: one 32 MB
  AllReduce goes 76 µs → ~889 µs [E], and per 32-layer forward pass the comm term
  goes 2·32·76 µs ≈ 4.9 ms → 2·32·889 µs ≈ 56.9 ms [E: arithmetic above] —
  ITL balloons by the comm delta alone; cross-node, a wrong-NUMA NIC caps one
  rank at its NIC's slower PCIe leg while the fabric idles [I].
- **Example [E]:** 32 MB AllReduce, n=8 (ring-traffic wire = 56 MB): NVLink path
  56/900 ≈ 62.2 µs; PCIe x16 path 56/64 ≈ 875 µs; one IB NDR link 56/50 ≈ 1120 µs
  [E: style-bank bandwidths, `../Hardware/README.md`; identical to `./NCCL.md` §
  Cost model] — one wrong cell in the `topo -m` matrix moves you a full rung.
- **Failure modes:** the five items in "What"; plus the meta-mode: **the machine
  changed after bring-up** (hot-plug, firmware, IOMMU default flip) so the matrix
  you validated no longer describes the box [I].
- **How to measure it:** `all_reduce_perf` busbw vs ladder ratio (healthy
  NVLink/RDMA ≈ 15–18× [E: 900/50 = 18]; much less → a byte is being demoted);
  DCGM per-NIC utilization during a known AllToAll (a quiet NIC = wrong path);
  per-rank NCCL INFO logs (`./NCCL.md` §Debugging).

## How to fix it (the short list)
1. **`nvidia-smi topo -m`** — validate the matrix against what the machine spec
   claims; any `NODE`/`SYS` where you expected `PIX`/`NV` is a finding.
2. **`nvidia-smi nvlink -s`** — confirm NVLink link counts and no error status.
3. **`lspci` / `numactl --hardware`** — confirm NIC placement and which socket
   each NIC/GPU's PCIe root lives under.
4. **Enable P2P + GDR** (IOMMU settings, driver, `NCCL_P2P_LEVEL`, GDR kernel
   module) — then verify in the `NCCL_DEBUG=INFO` init block that P2P is *on* and
   NET channels use GDR (`./NCCL.md` §Debugging and Tuning).
5. **Align rank/GPU/NIC/NUMA** — run rank i on GPU i with NIC i; pin with
   `numactl` and `NCCL_IB_HCA` if the fabric or placement is asymmetric
   [I: `./Multi-Node.md` §Topology awareness].
6. **Cross-ref the fabric side** — IB/RoCE, PFC, SHARP are out of scope here
   (`../Networking/README.md`); topology is the intra-node half of the same
   decision (`./Scale-Up-vs-Scale-Out.md`).

## Topology checklist (new cluster / new node)
1. Run `nvidia-smi topo -m`; save the matrix to the cluster's records.
2. **Verify NVLink pairs:** every intra-node GPU pair should show the expected
   `NV#x` (8-GPU SXM node: all 28 pairs). Any non-NV cell = investigate before
   first burn-in.
3. **Verify NIC↔GPU affinity:** each NIC should be `PIX` (or `PXB`/`PHB` per the
   vendor reference layout) to its home GPU; flag every `NODE`/`SYS` GPU↔NIC cell.
4. **Verify P2P + GDR enabled:** `NCCL_DEBUG=INFO` init block shows P2P enabled
   and GDR on the NET channels; no "P2P disabled" lines on an NVLink box.
5. **Verify NUMA placement:** ranks scheduled on the socket that owns their
   GPU+NIC (`numactl`); no cross-socket assignments.
6. **Measure, don't assume:** run `all_reduce_perf` (nccl-tests) intra-node and
   across two nodes; achieved busbw should be within a sane fraction of the spec
   constants (~900 / ~50 GB/s [F: `../Hardware/README.md`]) — if it isn't, go back
   to step 1 with the DCGM + NCCL logs (`./Diagnostics.md`,
   `./Perf-Experiment-Template.md`).

## Key Takeaways
1. **Topology = the machine's path map:** NVLink mesh + PCIe switch tree + NUMA
   ownership; it bounds the BW/latency of every intra-node GPU↔GPU and GPU↔NIC
   transfer [I].
2. **`nvidia-smi topo -m` is the map, and it is cheap to read:** lowest code =
   fastest path (NV#x < PIX < PXB < PHB < NODE < SYS); a NIC's `PIX` cell names
   its home GPU.
3. **One slow cell demotes the whole collective:** barriers + ring/tree mean the
   slowest leg sets the group's pace — NVLink-to-PCIe demotion costs ~12× per
   AllReduce [E: 889/76 µs].
4. **The kill list is short and pre-detectable:** P2P off, GDR off, wrong-NUMA NIC,
   cross-domain P2P, uneven NVLink — all visible in the matrix + one INFO log.
5. **Bring-up discipline:** matrix → NVLink links → NIC affinity → P2P/GDR → NUMA
   placement → measured busbw vs spec. Skip any step and you are benchmarking on
   a possibly-wrong map (`./Multi-Node.md`, `./NCCL.md`).

## Related
`./Multi-Node.md` (node anatomy, performance ladder, RDMA/GDR) ·
`./Scale-Up-vs-Scale-Out.md` (NVLink domain vs RDMA fabric) · `./NCCL.md`
(collectives, transports, debugging) · `../Hardware/README.md` (bandwidth
constants) · `../Networking/README.md` (IB/RoCE, GDR, SHARP) ·
`./Diagnostics.md` (performance decision tree) · `./Multi-GPU.md` (parallelism ↔
fabric mapping).
