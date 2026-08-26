# Learning Labs: 16 Hands-On Exercises, Beginner → Advanced
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: perftest/nccl-tests manpages, NVIDIA mlx5 counters, infiniband-diags; all [E] from the section constants bank (2026-08-25).

## 30-Second Explanation
This page is 16 labs that take you from "can I see my NIC?" to "why did a fabric under-perform
under incast?" Every lab has the same eight sections — **Objective / Topology / Prerequisites /
Commands / Expected results / Interpretation / Troubleshooting / Cleanup** — so you can run any
of them in isolation. Two are **config-changing** (Lab 8 partitions, Lab 12 ECN thresholds) and
are explicitly labeled as such; by default they describe **read-only** observation so you can run
them safely on a live fabric. Everything else is read-only measurement. Commands are exact and
fenced; run them from a host with `ofed`/`rdma-core`, `infiniband-diags`, `perftest`, and
`nccl-tests` installed. The companion command catalog is [55-cheat-sheet.md](./55-cheat-sheet.md).

```text
Lab  1  ─┐  see the NIC, the QPs, the link           (read-only)
Lab  2  ─┤  raw RDMA bandwidth                        (read-only)
Lab  3  ─┤  raw RDMA latency                          (read-only)
Lab  4  ─┤  collective busbw                          (read-only)   <- Beginner
Lab  5  ─┘  GPU/NIC PCIe placement
Lab  6  ─┐  IB topology & SM                          (read-only)
Lab  7  ─┤  IB error counters                         (read-only)
Lab  8  ─┘  IB partition/P_Key (READ-ONLY by default)                <- Intermediate
Lab  9  ─┐  PFC counters during load
Lab 10  ─┤  ECN / CNP counters
Lab 11  ─┼  generate RoCE incast congestion
Lab 12  ─┘  ECN thresholds (READ-ONLY by default)     (config-changing)
Lab 13  ─┐  ECMP imbalance & entropy               (read-only)
Lab 14  ─┤  TCP vs RDMA                               (read-only)
Lab 15  ─┼  single-rail vs multi-rail                 (read-only)
Lab 16  ─┘  NCCL ring vs tree                         (read-only)   <- Advanced
```
**Safety contract (all labs):** no destructive operations; nothing tears down config; the two
config-changing labs (8, 12) are read-only by default; every lab ends with a Cleanup step.

---

## Lab 1 — Inspect NIC and RDMA Interfaces
### Objective
Identify each HCA/RoCE NIC, its link state, speed/encoding, and active Queue Pairs (QPs).
### Topology
Single host; one or more HCAs/NICs. No peer needed.
### Prerequisites
`rdma-core`, `infiniband-diags`, `ethtool`, root or CAP_NET_ADMIN on the host.
### Commands
```bash
ibv_devinfo                       # per-device: node/port GUIDs, port state, rate, MTU
rdma link show                    # RDMA link state per mlx5 device
rdma dev show                     # each dev: state, port, link_layer
rdma resource show qp             # active QPs + which link each lives on
ethtool <iface>                   # e.g. ethtool enp3s0f0: speed, duplex, module
ethtool -S <iface> | head -40     # driver counters (PFC/ECN/drop/ICRC once you scroll)
lspci | grep -i mellanox          # HCA BDFs
```
### Expected results
- `ibv_devinfo` shows `Port state: Active`, `Physical state: LinkUp`, a **nominal rate**
  matching the generation — `[E]` NDR400 = 400 Gb/s, HDR200 = 200 Gb/s, EDR(100G) = 100 Gb/s.
- `rdma link show` line like `link mlx5_0/1 state ACTIVE physical_state LINK_UP
  netdev enp3s0f0`. [I]
- `rdma resource show qp` shows QPs in `RTS` (ready-to-send) state once a workload runs.
### Interpretation
`Active + LinkUp` at the right rate means the physical and link layer are healthy; if the
collective is still slow, the problem is above this layer (topology, CC, imbalance).
[I]
### Troubleshooting
"`Port state: Down`" → cable/transceiver or peer silence; check both ends. Link coming up at
the wrong `Rate` (e.g. `Rate: 200` when you expect 400 — or 800G-capable optics negotiating
half rate) → check cable/encoding ([06-infiniband-speed-generations.md](./06-infiniband-speed-generations.md),
[41-physical-layer.md](./41-physical-layer.md)).
### Cleanup
None — this is read-only. Close no sockets; your QPs come and go with their workloads.

---

## Lab 2 — RDMA Bandwidth (ib_write_bw / ib_read_bw)
### Objective
Measure raw single-QP RDMA bandwidth between two hosts at large message size.
### Topology
Two hosts on the same leaf/RoCE subnet; HCA on each; a routable IP over the RDMA link.
### Prerequisites
`perftest` on both; correct GID index for RoCEv2 if Ethernet (`-x`); both ports Active.
### Commands
```bash
# Host A (server):
ib_write_bw -d mlx5_0 -F -s 1048576
# Host B (client):
ib_write_bw -d mlx5_0 -F -s 1048576 <hostA-ip>

# read variant (same shape):
ib_read_bw -d mlx5_0 -F -s 1048576 <hostA-ip>

# sweep message sizes to see the small-message cliff:
for s in 256 4096 65536 1048576; do
  ib_write_bw -d mlx5_0 -F -s $s <hostA-ip> | tail -1
done
```
### Expected results
At `-s 1048576` (1 MB) on a healthy `[E]` NDR400 (50 GB/s) link: **~47–49 GB/s, i.e.
≈ line-rate × 0.95+**. At 256 B expect a large drop (header/PPS bound, `[E]` 22.66%
overhead). [I]
### Interpretation
A 1 MB result well above 0.9× the `[E]` port rate means the NIC+link+PCIe path is sound; a
big gap at small sizes is the expected PPS/header effects, not a fault. [E][I]
### Troubleshooting
Low large-message BW → check PCIe generation/width (`lspci -vvv`), NUMA binding of the NIC
([37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)), GID index (`-x`), or go back to Lab 1 to confirm the link
rate.
### Cleanup
Kill the perftest processes (`pkill ib_write_bw` on both hosts). No config touched.

---

## Lab 3 — RDMA Latency (ib_write_lat / ib_read_lat)
### Objective
Measure one-sided write/read latency at small messages; learn to read percentiles.
### Topology
Same two hosts as Lab 2.
### Prerequisites
`perftest`; ports Active (Lab 1).
### Commands
```bash
# Host A:
ib_write_lat -d mlx5_0 -F -s 16
# Host B:
ib_write_lat -d mlx5_0 -F -s 16 <hostA-ip>
ib_read_lat  -d mlx5_0 -F -s 16 <hostA-ip>
```
### Expected results
On InfiniBand, `t_typical` (and t_min) in the **single-digit µs** range at 16 B; RoCE with
PFC/ECN machinery tends a bit higher; observe `t_max` far above `t_typical` when anything
concurrent runs. [A]
### Interpretation
Median (typical) tells the steady-state cost; **t_max = the tail**, and the tail is what a
synchronized collective actually waits on. A low median with a high tail points to queuing
or PFC pauses, not to the raw transport. [I]
### Troubleshooting
Latency >> single-digit µs → verify the hosts are on the same subnet (no router hop),
NUMA/NIC affinity, and that nothing else saturates the link (Re-run Lab 2). PFC inflow
spikes → see Lab 9/11.
### Cleanup
`pkill ib_write_lat` on both hosts.

---

## Lab 4 — NCCL AllReduce (algbw vs busbw)
### Objective
Run a collective benchmark and learn to read algbw **and** busbw.
### Topology
A multi-GPU node (or multi-node), CUDA GPUs, RDMA interconnect.
### Prerequisites
`nccl-tests` built; NCCL able to use IB/RoCE (`NCCL_DEBUG=INFO` shows `NET/IB`).
### Commands
```bash
all_reduce_perf -b 8 -e 8G -f 2 -g 8
# force IB transport explicitly to confirm you're not falling back to TCP:
NCCL_NET=IB all_reduce_perf -b 8 -e 8G -f 2 -g 8
# diagnostics: which transport/HCA/gid are selected
NCCL_DEBUG=INFO NCCL_DEBUG_SUBSYS=NET all_reduce_perf -b 1M -e 1M -f 2 -g 8
```
### Expected results
`Broadcast`-style rows print `algbw` and `busbw` per size. For large messages, healthy
AllReduce `busbw ≈ [E] 0.95 × link` — a saturated ring's busbw normalizes back to the
raw link rate (nccl-tests defines `busbw = algbw × 2(n-1)/n` (bank row "busbw relation",
×1.75 at n=8), and `algbw` at a saturated ring is `link × n/(2(n-1))`, so the product is
the link rate itself). E.g. 45–48 GB/s on one 400 Gb/s = 50 GB/s rail. The `algbw` column
is lower by exactly the `2(n-1)/n` factor — that gap is the normalization, not a loss.
[F: nccl-tests PERFORMANCE.md][E]
### Interpretation
**busbw, not algbw, is "how well the fabric is used."** The relation `[E] busbw = algbw ×
2(n-1)/n` (bank row "busbw relation") is the check: if you see algbw ≈ busbw, that's wrong
for AllReduce (unless n is tiny). [F: nccl-tests PERFORMANCE.md]
### Troubleshooting
busbw far below theoretical → topology/NIC-affinity problem or fallback to Socket — the
`NET` lines will say "Using network: IB" or "Socket". `NCCL_IB_HCA`, `NCCL_IB_GID_INDEX`
per [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).
### Cleanup
No persistent state; kill any leftover `all_reduce_perf`.

---

## Lab 5 — GPU/NIC PCIe Topology (nvidia-smi topo -m)
### Objective
Map GPU↔GPU and GPU↔NIC PCIe distances to predict GPUDirect RDMA (GDR) performance.
### Topology
One GPU server.
### Prerequisites
NVIDIA drivers + `nvidia-smi`; a NIC on the same PCIe tree.
### Commands
```bash
nvidia-smi topo -m
nvidia-smi topo -p2p r   # per-GPU-pair P2P capabilities (PIX/PXB/PHB/SYS/NV)
lstopo-no-graphics       # full PCIe hierarchy if hwloc installed
```
### Expected results
A GPU↔GPU matrix with labels: **`NV#`** (NVLink), **`PIX`** (same PCIe switch), **`PXB`**
(across PCIe switches), **`PHB`** (same NUMA node/root port), **`SYS`** (different NUMA /
SMP). NVIDIA prefers PCIe paths `PIX`/`PXB` for GDR; `SYS` is the worst (no direct P2P
benefit). [F: NVIDIA input/output docs; [I]]
### Interpretation
For GPUDirect RDMA you want the NIC on the **same socket** as the GPU (GPU↔NIC `PIX`/
`PXB`, not `SYS`). If the GPU and NIC are `SYS`-apart, GDR still "works" but crosses QPI/UPI
and halves effective bandwidth. [I]
### Troubleshooting
"Peer to peer not allowed" → IOMMU on, ACS enabled, `nvidia-peermem` not loaded —
[37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) and [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).
### Cleanup
None (read-only).

---

## Lab 6 — Inspect IB Topology & the Subnet Manager
### Objective
Discover the IB fabric: links, LIDs, switches, and which Subnet Manager (SM) runs.
### Topology
IB fabric (at least a switch + hosts); SM (OpenSM or UFM) running.
### Prerequisites
`infiniband-diags`; SM in the fabric; permissions to send SMPs (root).
### Commands
```bash
ibnetdiscover                     # full topology tree (CA/switch/SM, LIDs, sizes)
ibnetdiscover -p                  # include P_Key partitions
ibstatus                          # quick CA health
ibswitches                        # list of switches and their GUIDs
ibchecknet                        # consistency: paths to every node
perfquery -G -L <lid>             # queue/port info for a specific LID from the SM
```
### Expected results
`ibnetdiscover` prints hosts as `CA` and switches as `Switch` entries with `lid`, `ports`,
`Speed: 400`/`Width: 4x`, and the SM node. `ibchecknet` should report "no errors found" on a
clean fabric. [I]
### Interpretation
The SM assigns the LID/GID topology and shortest-path routes; a missing switch or wrong
speed in `ibnetdiscover` explains cross-node failures before you blame NCCL.
[11-infiniband-subnet-manager.md](./11-infiniband-subnet-manager.md), [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md).
### Troubleshooting
"No SM" errors → OpenSM/UFM not running or LID-range exhausted; check the SM host and
`opensm` status. Duplicate LIDs → SM misconfig.
### Cleanup
None (read-only; you are only querying the SM).

---

## Lab 7 — Inspect IB Error Counters
### Objective
Read per-port error counters and identify physical-layer vs routing issues.
### Topology
IB fabric + at least one host doing traffic.
### Prerequisites
`infiniband-diags`; root; a running job (or run Lab 2) so counters have traffic to show.
### Commands
```bash
ibqueryerrors                     # per-port error counters across the fabric
perfquery -x -G <lid>             # extended counters for one port
ibdiagnet -r                      # fabric lint + route dump + link error check
# spot a specific bad pair:
ibping -G -L <lid>                # LID reachability / health
```
### Expected results
Healthy fabric: all error counters flat/zero — **`symbol_error`, `link_error_recovery`,
`link_downed`, `local_link_integrity_errors`, `remote_physical_errors`** all low or 0.
[F: NVIDIA mlx5 counters article]
### Interpretation
Rising `symbol_error`/`local_link_integrity` → physical-layer (cable/fiber/connector,
signal integrity) — not a routing or software issue. `link_downed` → a link actually went
down. These are the numbers that surface a "slow but up" NIC. [I]
### Troubleshooting
Symbol errors concentrated on one cable → reseat/replace (DAC/AOC/fiber) — [41-physical-layer.md](./41-physical-layer.md).
Persistent `link_downed` on a port → SM or port-training instability; capture with
`ibdiagnet`.
### Cleanup
None (read-only reads; no counters are cleared).

---

## Lab 8 — Create an IB Partition (P_Key) — ⚠️ CONFIG-CHANGING
### Objective
Understand how P_Key partitions isolate tenant traffic. **READ-ONLY BY DEFAULT**: this
section describes inspecting existing P_Key tables; actually changing partitions is a
config-changing operation that requires SM authority and is **not** something you run
casually.
### Topology
IB fabric under OpenSM or UFM control.
### Prerequisites
Read-only path: SM access + `infiniband-diags`. To actually *change* partition membership you
need SM admin (UFM GUI/API or OpenSM partition config) — flag with your fabric owner first.
### Commands
```bash
# READ-ONLY: inspect the current partition table the SM advertises
umad_devinfo                       # per-CA P_Key table (0xFFFF = full membership)
ibnetdiscover -p                   # partitions in the map (-p)
# To CHANGE (example, requires SM authority — do NOT run without approval):
#   OpenSM: edit /etc/opensm/partitions.conf with the pkey + GUIDs, then restart
#   UFM:    partition manager web UI / REST API (creates the partition + membership)
```
### Expected results
Every port lists at least **0xFFFF** (full membership, default partition). Additional
partitions appear as 16-bit `pkey` values with their member GUID lists. Two ports sharing a
partition can exchange; ports with disjoint partitions cannot. [F: IBTA P_Key semantics]
### Interpretation
P_Key is the IB-native multi-tenancy/isolation boundary — analogous to a VLAN but enforced
at the subnet/CA layer. [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md),
[47-security-multitenancy.md](./47-security-multitenancy.md).
### Troubleshooting
"Isolation not working" → a partition was left with 0xFFFF everywhere; members added to the
wrong partition; SM not restarted. Verify with `ibnetdiscover -p`.
### Cleanup
Read-only path: nothing to clean. If you actually changed partitions (with approval), remove
any test partition/membership you added and restore the default `0xFFFF` membership.

---

## Lab 9 — Observe PFC Counters During Load
### Objective
Watch PFC pause counters climb in real time while saturating a RoCE link.
### Topology
Two RoCE hosts on a PFC-enabled lossless fabric (lab its own switches, or a test pair).
### Prerequisites
`ethtool`; `iperf3`; `perftest`; PFC configured on the fabric (lossless priority).
### Commands
```bash
# baseline (no load):
ethtool -S <iface> | grep -iE 'pfc|xon|xoff'
# create RDMA load: Host A server, Host B client
ib_write_bw -d mlx5_0 -F -s 1048576 <hostA-ip> &
# create competing TCP load to force contention / pause:
iperf3 -s &        # Host A
iperf3 -c <hostA-ip> -t 30 -P 8   # Host B
# re-read counters mid-load:
ethtool -S <iface> | grep -iE 'pfc|xon|xoff'
```
### Expected results
`pfc_xon_tx`/`pfc_xoff_rx` (and mlx5 `tx_xon`/`rx_xoff`) counters **increase** from their
baseline when lossless-priority traffic contends for the same egress queue. [I]
### Interpretation
Rising XOFF frames = a remote queue told the sender to pause = the fabric is doing its
lossless job, *and* it tells you a buffer threshold was crossed. PFC firing routinely (not
just at steady saturation) hints the ECN thresholds are misaligned (Lab 12). [I]
### Troubleshooting
PFC counters explode on the *first* byte of traffic → thresholds too aggressive/coupling to
TCP; review [18-data-center-bridging.md](./18-data-center-bridging.md), [19-why-pfc-is-dangerous.md](./19-why-pfc-is-dangerous.md).
### Cleanup
Kill `ib_write_bw`, `iperf3`; counters are read-only (they reset on NIC reset only).

---

## Lab 10 — Observe ECN / CNP Counters
### Objective
See congestion signaling (ECN CE marks + CNP) fire on a RoCE fabric.
### Topology
RoCE fabric with ECN+DCQCN configured; two hosts saturating a shared link.
### Prerequisites
`ethtool`; `perftest` or `nccl-tests`; ECN/WRED (Lab 12) enabled on the path.
### Commands
```bash
# baseline:
ethtool -S <iface> | grep -iE 'ecn|cnp|mark'
# generate congestion (two senders to one receiver = incast):
#   two client hosts run:
ib_write_bw -d mlx5_0 -F -s 1048576 <server-ip> &
# re-read — the receiver NIC is where CNP counts live:
ethtool -S <iface> | grep -iE 'ecn|cnp|mark'
```
### Expected results
`np_ecn_marked_roce_packets` (ECN-marked ingress at the switch/NIC), `np_cnp_sent`,
`rp_cnp_handled`/`rp_cnp_ignored` counters rise when congestion causes WRED to mark and the
receiver to emit CNPs back. [F: NVIDIA mlx5 counters article]
### Interpretation
`rp_cnp_ignored` rising fast → the sender is **not** acting on CNPs (DCQCN not configured /
disabled on the adapter) — the leading symptom of a "lossless but unresponsive" fabric.
[I][F]
### Troubleshooting
No CNP counters despite obvious congestion → ECN not marked (Lab 12 thresholds), or wrong
DSCP→TC mapping so the CC queue isn't marked. [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md).
### Cleanup
Kill perftest processes; counters read-only.

---

## Lab 11 — Generate RoCE Congestion (N-to-1 Incast)
### Objective
Create a controlled **incast** (N senders → 1 receiver) and watch drops/PFC/CNP.
### Topology
A RoCE leaf with several hosts (N senders → 1 receiver), ideally in the same lossless VLAN.
### Prerequisites
`perftest`/`nccl-tests` on N+1 hosts; PFC+ECN (Labs 9–10); a receiver whose single NIC
absorbs all N streams.
### Commands
```bash
# on the ONE receiver: run server
ib_write_bw -d mlx5_0 -F -s 1048576
# on EACH of N senders:
ib_write_bw -d mlx5_0 -F -s 1048576 <receiver-ip> &
# watch the receiver's drop / PFC / CNP counters live:
watch -n1 'ethtool -S <iface> | grep -iE "drop|pfc|ecn|cnp|out_of_seq" '
```
### Expected results
The receiver's single inbound port saturates at `[E]` its link rate; as N grows you see
PFC/CNP counters climb and, on lossy configs or when headroom is exhausted, `drop`/
`out_of_seq`/`packet_seq_err`. Aggregate goodput stops scaling at the receiver's NIC line. [I]
### Interpretation
Incast is where lossless + CC earn their keep: without ECN/BDP headroom the receiver drips
traffic and RC's Go-Back-N amplifies each loss ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)) → throughput
collapse. This is the *mechanism* behind "tail latency," and the reason `[E]` buffer/PFC
thresholds must sit above the burst volume.
### Troubleshooting
Hard packet loss under incast → ECN marks too late (thresholds too high) or lossless
headroom too small; see Lab 12 and [39-buffer-architecture.md](./39-buffer-architecture.md).
### Cleanup
Kill all perftest processes on every host (`pkill ib_write_bw`). No config changed.

---

## Lab 12 — Tune ECN Thresholds (Kmin / Kmax) — ⚠️ CONFIG-CHANGING
### Objective
Understand WRED ECN thresholds (Kmin/Kmax) and the PFC interaction. **READ-ONLY BY
DEFAULT**: default is to *observe* the current thresholds and their counter effects; changing
them is config-changing and needs fabric-owner approval.
### Topology
RoCE fabric with switch (or NIC) ECN marking; two hosts to load it.
### Prerequisites
Switch CLI or NIC `mlnx_qos`-style tooling (read-only path just reads config); `ethtool`;
Lab 10 counter reads.
### Commands
```bash
# READ-ONLY: current ECN / pause threshold config
mlnx_qos -i <iface>        # per-iface QoS: DSCP->TC, ECN enabled?, PFC priorities
ethtool --show-pause <iface>
# READ-ONLY: baseline CC counters
ethtool -S <iface> | grep -iE 'ecn|cnp|pfc'
# CHANGE (config-changing — do NOT run without approval):
#   switch ECN WRED: set Kmin/Kmax/Pmax for the RoCE queue
#   NIC: mlnx_qos --dscp2prio set,26,3 ; --ecn enable ; tune alpha/g
```
### Expected results
Read-only: you see ECN enabled on the RoCE DSCP/TC with a Kmin/Kmax curve, and a
PFC-priority mapping. Lowering Kmin makes marking (and CNP-driven rate cuts) fire *sooner*,
so PFC pauses fall and counter behavior shifts from `pfc_xoff` toward `np_cnp_sent`. [I][F:
vendor refs]
### Interpretation
The whole RoCE tuning game is aligning ECN (mark before the queue overflows) with PFC
(backstop). Kmin too high → PFC carries the whole burden (pause storms); Kmin too low →
premature throttling. [20-ecn-wred.md](./20-ecn-wred.md), [21-dcqcn.md](./21-dcqcn.md).
### Troubleshooting
Pause storms persist after moving Kmin down → check PFC headroom math, not just ECN:
`[E]` a 1 µs pause at 100 Gb/s needs ~12.5 KB (400 Gb/s → `[E]` 50 KB) of headroom per link
of propagation. [39-buffer-architecture.md](./39-buffer-architecture.md).
### Cleanup
Read-only path: nothing. If you changed thresholds (with approval), restore the previous
Kmin/Kmax/Pmax and confirm counters return to baseline.

---

## Lab 13 — Test ECMP Imbalance (Same-Hash Flows, 2 Spines)
### Objective
Demonstrate ECMP hash polarization: many identical flows collide onto one of two spines.
### Topology
Leaf-spine RoCE fabric with exactly 2 spines; many QPs from one leaf to another leaf.
### Prerequisites
`perftest` with `-q` (many QPs); switch counters per-uplink (or spine per-port counters).
### Commands
```bash
# same src->dst, many QPs so ECMP hashes each QP:
ib_write_bw -d mlx5_0 -F -q 32 -s 1048576 <dst-ip>
# on each spine, watch per-uplink utilization:
# (switch CLI or per-port counters — e.g. `cl-acl`/vendor `show interfaces counters`)
```
### Expected results
Because RoCEv2's dst UDP port is fixed at `[E]` 4791 [F], entropy collapses to (src IP, dst
IP, src UDP port); with few distinct flows you can see a gross **80/20 (or worse) split**
between the two spines — one uplink saturated, the other idle. [I]
### Interpretation
That imbalance ≈ "2:1-looking" throughput loss with *no* PFC storm — the classic ECMP
polarization signature. Fixes: per-QP UDP source-port entropy (NIC side), different SL /
hash seeds, or adaptive/DLB spraying ([22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md)).
### Troubleshooting
No imbalance with 2 flows → try a flowlet gap or more QPs; verify the hash isn't symmetric
(same 5-tuple reversed hashes to the same member on return).
### Cleanup
Kill perftest; per-port counters read-only (they reset on switch reboot only).

---

## Lab 14 — Compare TCP vs RDMA
### Objective
Quantify the overhead/latency and CPU-cost delta of TCP transport vs RDMA on the same hosts.
### Topology
Two hosts with both an RDMA-capable NIC path and a TCP-capable IP path.
### Prerequisites
`iperf3`, `perftest`; note both paths' NICs (often the same mlx5 port's `netdev`).
### Commands
```bash
# TCP: A server, B client
iperf3 -s &                    # A
iperf3 -c <hostA-ip> -t 30 -P 4   # B -> records sender/receiver bitrate + retr
# RDMA: A server, B client
ib_write_bw -d mlx5_0 -F -s 1048576 <hostA-ip>
# CPU cost: measure per-protocol CPU while the test runs
top -b -n1 | head -20   # or `mpstat -P ALL 1` during each test
```
### Expected results
TCP on the same link shows meaningful gap below RDMA goodput (kernel stack + ACK processing
+ ~`[E]` TCP/IP header 20+20 B matters at small messages), and much higher per-core CPU.
RDMA `ib_write_bw` reaches `[E]` ~0.95× line with near-zero CPU (kernel bypass). [I][E]
### Interpretation
The CPU delta is the whole story: RDMA moves data in Silicon (HCA DMA, kernel bypass),
TCP burns cores per byte — why RDMA dominates AI fabrics where CPU is precious.
[03-rdma-fundamentals.md](./03-rdma-fundamentals.md), [04-rdma-operations-and-transports.md](./04-rdma-operations-and-transports.md).
### Troubleshooting
"RDMA not faster" → you may be limited by PCIe/NUMA (Lab 5) or measuring small messages
where PPS, not transport, binds. Compare at ≥1 MB.
### Cleanup
Kill `iperf3`/`ib_write_bw`. No config changed.

---

## Lab 15 — Single-Rail vs Multi-Rail (NCCL Rail Pinning)
### Objective
See the busbw delta between pinning NCCL to one HCA (single-rail) vs using all rails.
### Topology
A node with multiple HCAs (e.g. 8×400G) and the GPUs, on a multi-rail fabric.
### Prerequisites
`nccl-tests`; correct `NCCL_IB_HCA` syntax; a multi-rail (multi-plane) fabric
([38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)).
### Commands
```bash
# single-rail: pin NCCL to ONE hca
NCCL_IB_HCA=mlx5_0 all_reduce_perf -b 1M -e 1G -f 2 -g 8
# multi-rail (default): let NCCL use all HCAs
NCCL_IB_HCA=mlx5_0,mlx5_1,mlx5_2,mlx5_3,mlx5_4,mlx5_5,mlx5_6,mlx5_7 \
  all_reduce_perf -b 1M -e 1G -f 2 -g 8
# or explicitly "use all":
NCCL_IB_HCA=all all_reduce_perf -b 1M -e 1G -f 2 -g 8
```
### Expected results
Single-rail busbw ≈ one rail's worth (e.g. ~`[E]` one 400G = ~45–48 GB/s per GPU range).
Multi-rail busbw climbs toward the full node NIC aggregate (≈ `[E]` 8×400G = 400 GB/s)
because NCCL stripes the collective across all HCAs in parallel. [I][E]
### Interpretation
Rail optimization exists because each rank can feed ~`[E]` one NIC worth of traffic; using
K NICs in parallel multiplies effective AllReduce busbw up to ~K×. A pedestrian single-rail
NCCL_IB_HCA pin on a multi-plane fabric is exactly the "single-rail test on multi-rail
fabric" invalidation from [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).
### Troubleshooting
Multi-rail not faster → NCCL didn't see multiple rails (check `NCCL_DEBUG=INFO` HCA list),
or the fabric isn't actually multi-plane (single shared spine). Rail affinity in
[38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
### Cleanup
Unset the env overrides (`unset NCCL_IB_HCA`); no config changed.

---

## Lab 16 — NCCL Ring vs Tree
### Objective
Compare `NCCL_ALGO=Ring` vs `Tree` and learn when the tree wins.
### Topology
Multi-node GPU cluster with RDMA (more nodes makes the latency term matter).
### Prerequisites
`nccl-tests`; NCCL with both algorithms compiled; ≥2 nodes ideal.
### Commands
```bash
# ring (default, bandwidth-optimal at large messages):
NCCL_ALGO=Ring all_reduce_perf -b 8 -e 1G -f 2 -g 8
# tree (latency-optimal):
NCCL_ALGO=Tree all_reduce_perf -b 8 -e 1G -f 2 -g 8
# sweep size to see the crossover:
for a in Ring Tree; do
  NCCL_ALGO=$a all_reduce_perf -b 1K -e 8M -f 4 -g 8 2>/dev/null | grep -E '^[0-9]' | \
    awk '{print $1, $4, $5}' 
done
```
### Expected results
At **large messages**, Ring gives higher busbw (it's bandwidth-optimal — `[E]`
2(n-1)/n wire per rank); at **small messages** (latency-bound) and especially at **large
node counts**, Tree wins because its latency is `O(log n)` steps vs ring's `O(n)`. [I; [F]
NCCL analysis, mlsysbook]
### Interpretation
NCCL doesn't hardcode a threshold — it models `{Ring,Tree,…} × {LL,LL128,Simple}` per message
size and picks the fastest (`NCCL_ALGO` force just overrides the choice). The rule "tree for
small/large-n, ring for large-messages" is heuristic, not a fixed constant. [F: NCCL issue
#457, analysis paper]
### Troubleshooting
Tree slower even for small messages → your α (per-step latency) is already tiny and the
message isn't small enough; re-sweep. Fallback to Socket (not IB) defeats the comparison —
check `NET` lines.
### Cleanup
`unset NCCL_ALGO`; no config changed.

---

## Key Takeaways
1. Every lab is read-only except the two labeled config-changing (8, 12), and those default
   to observation; each has a Cleanup step.
2. The metric chain is NIC (perftest) → collective (nccl-tests busbw) → JCT: test each layer
   in order.
3. Healthy numbers: `[E]` ~0.95× line at 1 MB RDMA BW; single-digit µs IB latency [A];
   AllReduce busbw ≈ `[E]` 0.95 × link (the `busbw = algbw × 2(n-1)/n` definition
   normalizes a saturated ring back to raw line rate).
4. Congestion shows up as PFC/ECN/CNP counters before it shows up as drops — read them
   [40-network-telemetry.md](./40-network-telemetry.md).
5. Never trust a benchmark until you rule out GID/GDR/rail/MTU invalidity
   ([44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Related
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — definitions + interpretation guide.
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md), [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).
- [40-network-telemetry.md](./40-network-telemetry.md), [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md), [16-performance-benchmarking.md](../GPU-Communication/16-performance-benchmarking.md).

## References
- perftest / nccl-tests manpages and PERFORMANCE.md [F].
- NVIDIA mlx5 counters article (PFC/ECN/CNP semantics) [F].
- NCCL env docs (`NCCL_IB_HCA`, `NCCL_ALGO`) [F]; NCCL issue #457 (algo modeling) [F].
- [E] all figures from the section constants bank (computed 2026-08-25).
