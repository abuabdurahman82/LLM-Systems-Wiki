# Troubleshooting RoCE & NCCL
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA DCQCN params & mlx5 counter docs, IETF RoCEv2 Fast-CNP draft, NCCL user guide env page, Meta RoCE blog; fetched 2026-08-25.

## 30-Second Explanation
RoCE runs *InfiniBand's transport inside a UDP/IP Ethernet frame* whose only way to be "lossless"
is engineered policy: **PFC** (per-priority pause) plus **ECN/DCQCN** (end-to-end rate reaction)
plus **QoS/DSCP** alignment. Because none of it is automatic, nearly every RoCE fault is a
*misalignment* between those three levers — and the failure almost always surfaces through NCCL as
collapsed bandwidth, retries, or a socket fallback rather than a clean error. This page is the
symptom → cause → validate → fix table, then the NCCL variables with what each actually changes.

## The knobs you are really debugging
The three levers and where each lives:
- **PFC** — per-priority pause, at the *priority* layer (802.1Qbb); decides when a buffer *pauses*.
- **ECN/DCQCN** — end-to-end rate control; the switch *marks* CE on a WRED curve (Kmin→Kmax), the
  receiver replies with a **CNP**, the sender backs off multiplicatively [F: IP Infusion / NVIDIA
  DCQCN params].
- **QoS/DSCP** — which priority/queue class the lossless machinery applies to *your* traffic
  (DSCP→TC→priority mapping) [F: mlnx_qos guide].

Every row below is a place where two of these stop agreeing.

## The symptom → cause → validate → fix table
RoCEv2 header = `14(Eth)+20(IPv4)+8(UDP)+12(BTH)+4(ICRC) = 58 B` [E]; UDP dst port **4791** [F:
IETF Fast-CNP]. All rows below are operational practice [I] grounded in the cited mechanisms.

| # | Symptom | Probable cause | Validation | Remediation |
|---|---|---|---|---|
| 1 | Packet drops, busbw << link under burst | Buffer/ECN threshold misconfig | `ecn_marked` vs `pfc_xoff` counters | Align Kmin/Kmax (ECN) below PFC XOFF |
| 2 | PFC storm (all BW tanks, jitter) | ECN threshold *above* PFC XOFF → pause fires before marking | `pfc_xon/xoff_rx` spiking; pause% | Lower Kmin/Kmax so ECN marks first [F: IP Infusion DCQCN] |
| 3 | Excessive PFC (PFC doing all the work) | ECN fires too late; PFC carries the burden | high `pfc_xoff`, low ECN marking | Reduce ECN thresholds / tune WRED curve |
| 4 | ZERO PFC, but drops/lossy behavior | Lossless TC not enabled → RDMA on lossy fabric | `pfc_xoff` never fires on the RoCE TC | Enable PFC on the RoCE TC/priority |
| 5 | No CE marks / constant CE marks | Bad ECN thresholds or DSCP mismatch | switch ECN-marked count ~0 or ~100% | Set Kmin/Kmax to start/stop marking correctly |
| 6 | Excessive CNP / rate oscillation | CNP feedback too aggressive | `np_cnp_sent` high; sawtooth BW | Raise `DcQcnMinTimeBetweenCnps` (min_time_between_cnps) [F: NVIDIA] |
| 7 | Silent inactivity cross-subnet | Wrong DSCP / trust mode / TC | host vs switch DSCP→TC mismatch | Match `mlnx_qos` DSCP→prio and switch trust DSCP [F: mlnx_qos] |
| 8 | MTU-related fragmentation or drops | Jumbo on one side only | mismatched MTU at one end | Set MTU 9000 end-to-end [F: NVIDIA guidance] |
| 9 | ECMP imbalance (one uplink hot) | Low entropy (dst port 4791, few QPs) | hash polarization; one path 100%+ | Vary UDP src-port per QP; move to DLB/MRC |
| 10 | Flow polarization (same flow same path) | Static hash, symmetric flows | two big flows collide path | Different hash seed / SL / flowlet spray |
| 11 | Low single-flow BW despite clean links | NIC rate-limiter or PCIe bottleneck | `nvidia-smi` + `ethtool -S` congestion | Check NUMA/NIC placement, PCIe gen width, rate limiter |
| 12 | Microburst drops at incast | Buffer exhaustion (headroom too small) | tail-drop on lossless queue | Increase headroom / buffer partition |

An implicit warning runs through rows 2–5: **PFC and ECN thresholds must be tuned as a system**.
If ECN marks *after* the buffer hits PFC XOFF, you get pause storms even with DCQCN configured
[F: IP Infusion DCQCN explainer]. The design goal is to spend fabric life on ECN/DCQCN feedback
and hold PFC in reserve as a backstop [I].

### Validation commands per lever
```text
# PFC — is my RoCE priority actually pausing?
ethtool -S <nf> | grep -iE 'pfc|xon|xoff'            # pause frames in/out
# ECN — is congestion signaling firing?
ethtool -S <nf> | grep -iE 'ecn|cnp'                 # np_ecn_marked, np_cnp_sent
# DSCP/TC mapping — does the host agree with the switch?
mlnx_qos -i <nf>                                     # DSCP->prio table (host side)
# switch side: "show qos rewrite dscp / pfc buffer" (vendor CLI)
# entropy — how many distinct flows am I presenting to ECMP?
rdma resource show qp                                # count QPs; check UDP sport scrambling
```
When counters look clean but the job is slow, the answer is almost always row 9/10 (entropy) or
row 11 (PCIe/NUMA) — invisible to PFC/ECN counts [I].

### Threshold sizing: why misalignment *happens* and the number that anchors it
PFC XOFF headroom must absorb the pause-propagation delay before *any* frame is dropped. That
headroom in bytes is `port_rate × one-way pause propagation` [E]:
```text
PFC headroom @ 400G, ~1 µs propagation  = 400e9/8 × 1e-6 ≈ 50 KB   [E]
PFC headroom @ 100G, ~1 µs propagation  = 100e9/8 × 1e-6 ≈ 12.5 KB  [E]
```
The ECN marking thresholds (Kmin/Kmax) must sit **below this XOFF waterline** so the sender slows
end-to-end *before* the queue is deep enough to pause. If Kmax is set *above* the PFC threshold,
ECN never marks in time and the fabric is all PFC (rows 2–3); if Kmin is far too low, you mark
prematurely and throttle healthy flows (row 5). The single most common RoCEv2 misconfig is this
ECN-vs-PFC misalignment, and it produces pause storms even with DCQCN configured [F: IP Infusion
DCQCN]. So the fix is a *chain*, not a knob: DSCP→TC→priority → buffer headroom → Kmin/Kmax below
XOFF → min_time_between_cnps sanity [I].

### Reading a DCQCN/CNP trace
```text
ethtool -S <nf> | grep -iE 'np_cnp_sent|rp_cnp_handled|rp_cnp_ignored'
  np_cnp_sent rising      -> congestion is being signalled (DCQCN active)
  rp_cnp_ignored rising   -> receiver gets CNPs but CC not enabled/configured on it
  np_ecn_marked rising    -> switch IS marking (ECN path works)
  pfc_xoff_rx rising      -> lossless pushback firing (PFC path works)
```
A healthy fabric shows low, sporadic CNP with clean PFC; a storming fabric shows high `np_cnp_sent`
+ `pfc_xoff` together — the "excessive PFC" signature of row 3 [I].

## NCCL debugging: variables and what each changes
Never set these blind — each one redirects how NCCL picks hardware, which changes what you are
debugging [F: NCCL user guide env page].

- **`NCCL_DEBUG=INFO` / `TRACE`** — raises the log level; INFO prints transport selection, HCA/GID
  choice, and surfaces drop/retransmit errors; TRACE dumps every low-level operation (very noisy,
  use for a single short run). This is the first switch you flip to *see* what transport NCCL
  actually picked.
- **`NCCL_DEBUG_SUBSYS=NET`** — filters `NCCL_DEBUG` output to the network subsystem only. Use
  with INFO/TRACE so the log shows the NET lines (transport, HCA, GID, socket vs IB) without
  drowning in everything else [F: NCCL env doc].
- **`NCCL_IB_HCA`** — pins which host channel adapters NCCL may use (e.g. `mlx5_0:1,mlx5_2:1`).
  Setting it changes *which NICs carry traffic*; wrong picks (remote-NUMA HCA, a VF with no path)
  give exactly the slow/hidden-fallback behavior you are debugging. Use `nvidia-smi topo -m` to
  bind to the HCA on the GPU's own NUMA node.
- **`NCCL_IB_GID_INDEX`** — selects the HCA's GID index used for RoCE. RoCEv2 needs the **global /
  IPv4 GID** (commonly **index 3** on mlx5), *not* the RoCEv1 link-local index 0. A wrong GID gives
  silent cross-subnet hang/inactivity. Recent NCCL auto-negotiates; set it when auto picks the
  wrong one [F: NCCL env doc; GID index 3 is [A] common-vendor default].
- **`NCCL_NET=Socket`** — forces NCCL onto TCP sockets instead of RDMA. Seeing "Using network:
  Socket" (via `NCCL_DEBUG_SUBSYS=NET`) means RDMA/IB is *not* engaged — usually wrong `NCCL_IB_HCA`,
  GID issue, or no IB plugin. This is a *diagnostic switch*, not a fix.
- **Socket fallback cost** — when NCCL falls back to TCP (no IB plugin, bad HCA/GID), throughput
  drops by a large factor. [I] expect **~10–100× slower** than RDMA at large message sizes, because
  TCP adds per-packet kernel, checksum, and ACK/reliability work that RDMA offloads, and it lacks
  the lossless data path's efficiency. See `NCCL_NET=Socket` + `NCCL_SOCKET_IFNAME` above.
- **`NCCL_IB_TC`** / **`NCCL_IB_SL`** — set the RoCE Traffic Class (DSCP) / IB Service Level that
  NCCL traffic carries, so it lands on the PFC-lossless TC/priority (see row 7/9). Changing this
  changes *which QoS queue* your data uses.
- **Multi-rail config** — `NCCL_CROSS_NIC=0` keeps a ring on a single rail (for rail fabrics);
  multi-rail spreads ranks across NICs (e.g. `NCCL_IB_HCA` listing several). Setting it changes
  how many parallel legs each collective can use → directly sets achievable busbw.
- **`NCCL_TOPO_FILE`** — inject a custom `topo.xml` when NCCL's topology detection is wrong (bad
  hierarchy/AST tables). Changes the *topology model* NCCL optimizes against.

A diagnostic arc that pins the transport in one log read [I]:
```text
NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=NET nccl-tests ... 2>&1 | grep -iE 'network|hca|gid|socket'
# "Using network: IB" + an HCA/GID line   → RDMA engaged; go fix PFC/ECN/entropy
# "Using network: Socket" or missing IB   → transport mismatch; fix HCA/GID/plugin first
```

## Two quick decision helpers
```text
Symptom "job ran but slow"           Symptom "silent hang / no data"
├── NCCL_DEBUG_SUBSYS=NET              ├── GID: show_gids ; NCCL_IB_GID_INDEX=3 (RoCEv2)
│     "Using network: IB" ?             ├── DSCP: mlnx_qos vs switch trust mode aligned?
│        yes → PFC/ECN/entropy table    └── P_Key / partition membership (IB)
│        no  → socket fallback (above)        → ./45-troubleshooting-rdma-infiniband.md
├── counters: pfc_xon/xoff, cnp_sent
└── nccl-tests busbw vs 0.95·link  [E]
```

## Related
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) — IB-native counterpart and counter family.
- [21-dcqcn.md](./21-dcqcn.md) — ECN/PFC/DCQCN closed loop and all thresholds.
- [22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md) — entropy limits, ECMP, DLB/MRC, DSCP↔TC.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — perftest vs nccl-tests, busbw.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL transport selection and traffic model.


## Key Takeaways
1. RoCE has no native losslessness — it is engineered from three levers (PFC pause, ECN/DCQCN rate
   reaction, QoS/DSCP class mapping), so nearly every fault is a *misalignment* between two of
   them, surfacing through NCCL as collapsed bandwidth, retries, or a socket fallback rather than
   a clean error.
2. Anchor thresholds as a chain, not a knob: DSCP→TC→priority → buffer headroom → Kmin/Kmax
   *below* PFC XOFF → sane `min_time_between_cnps`; if Kmax sits above the PFC waterline you get
   pause storms even with DCQCN configured — the single most common RoCEv2 misconfig.
3. Size headroom and thresholds to the pause-propagation delay — ~50 KB @ 400G and ~12.5 KB @ 100G
   at ~1 µs propagation [E] — so ECN marks before the XOFF waterline and the fabric spends its
   life on ECN/DCQCN with PFC held as a backstop.
4. When counters look clean but jobs are slow, suspect entropy and host path: fixed dst port 4791
   plus few QPs collapses ECMP (fix with UDP src-port entropy / DLB/MRC), and PCIe/NUMA
   rate-limiters are invisible to PFC/ECN counters.
5. Pin the transport in one log read: `NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=NET` — "Using network:
   IB" means go tune PFC/ECN/entropy; "Using network: Socket" (or missing IB) means a transport
   mismatch (HCA/GID/plugin) first — a socket fallback costs ~10–100× at large messages.

## References
- NVIDIA DCQCN parameter / mlx5 counter docs — np_cnp_sent, pfc_xon/xoff, min_time_between_cnps.
- IP Infusion DCQCN explainer — ECN-vs-PFC threshold misalignment → pause storms.
- IETF RoCEv2 Fast-CNP draft — UDP dst port 4791, CNP/ECN signaling.
- NVIDIA `mlnx_qos` guide — DSCP→TC→priority mapping, trust mode.
- NCCL user guide environment-variables page — NCCL_IB_HCA/GID/TC/SL, socket fallback.
- Meta "RoCE networks for distributed AI training at scale" blog — ECMP entropy / 4791 hash collapse.
- [E] Constants used: RoCEv2 header = 58 B (Eth14+IPv4+UDP8+BTH12+ICRC4); PFC headroom ≈ 50 KB @
  400G and ≈ 12.5 KB @ 100G at ~1 µs propagation; ring busbw target 0.95·link.
