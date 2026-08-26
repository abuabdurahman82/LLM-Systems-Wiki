# Network Telemetry for the AI Fabric
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA MLNX/UFM counters articles, IP Infusion / Cisco DCQCN-CC docs, P4.org INT spec, gNMI/OpenConfig, Arista CloudVision, section notes; fetched 2026-08-25.

## 30-Second Explanation
An AI fabric is *lossless*, so the usual packet counters lie: **zero drops can coexist
with a dying job**, because the damage hides as PFC pauses, ECN marks, CNPs, FEC retries
and queue occupancy — not as dropped packets. Telemetry is the practice of surfacing
those **early, lossless-era signals** (and the interface/utilization noise floor) so you
see a fabric decaying *before* the collective stalls. Every metric group below maps to a
failure in [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md):
when a job's tail latency rises, the telemetry tells you *which* layer twitched. This page
lists the counter family, the four delivery mechanisms (on-demand SNMP/gNMI, streaming
gNMI gRPC, in-band INT, sFlow), and a "first 10 dashboards" checklist.

## What — the counter family every AI fabric must watch
| Group | Key counters | What a rise means |
|---|---|---|
| **PFC** | `pause_xoff_rx/tx`, `pause_xon`, `duration`, `pfc_xoff_rx` | incast / backpressure; the first lossless sign |
| **ECN** | `np_ecn_marked_roce_packets`, switch ECN-marked | switch marking firing — CC active |
| **CNP** | `np_cnp_sent` / `np_cnp_handled`, `rp_cnp_ignored` | (receiver) congestion noticed / (ignore=CC misconf) |
| **Queue depth** | per-port occupancy, gNMI/INT | the buffer ladder position (Kmin/Kmax) |
| **Drops** | switch `discard`, NIC `xmit`/`rcv` drops | lossy-fabric drops, or watchdog action |
| **Link errors/BER** | `symbol_error`, `link_downed`, `local_link_integrity_errors`, `remote_physical_errors` | cable/fiber/connector at the PHY |
| **FEC** | `fec_corrected` / `fec_uncorrected` (Eth), IB RS-FEC | rising corrected = marginal link; uncorrected = on the edge |
| **Retransmit (IB)** | `link_recovery`, retrans counters, `packet_seq_err` | OOO / Go-Back-N pain on the transport |
| **Retransmit (RoCE)** | NIC-level `out_of_sequence`, `rx_icrc` | RDMA reorder / ICRC issues |
| **Congestion events** | queue build + CNP bursts correlated | the CC × buffer interaction |
| **Latency** | INT per-hop, NTP-confirmed host timers | queueing delay along a path |
| **Utilization** | interface `rx/tx` rate, `ifHCInOctets` | whether a link is even loaded |

## Why — zero-drop losslessness means the signal moved off the drop counter
On a lossless/credit-based fabric, the fabric achieves **no drops by delaying**. That
delay IS the signal: a PFC pause, an ECN mark, a CNP, a filled queue, a FEC-corrected
bit — all of them are the fabric saying *"something is congested/degrading"* *before*
anything fails. Operators who watch only `drop` counters are flying blind: the job can
slow 20% with every counter green. [I: standard lossless-operations judgment] The other
reason to watch the *whole* family: counter **correlations** (PFC rose *and then* CNP
rose *and then* queue drained) are what localize a fault to a leaf, spine, or cable.

## When — on-demand versus streaming versus in-band
| Mechanism | Pull or push | Latency to see it | Used for | Examples |
|---|---|---|---|---|
| **On-demand SNMP/gNMI Get** | pull | seconds–minutes | health checks, post-incident | SNMP MIBs, `gNMI Get` |
| **Streaming gNMI** (subscribe) | push | sub-second–s | dashboards, live alerting | gNMI/gRPC w/ OpenConfig |
| **In-band INT** (packet-carried) | push in-band | per-packet | precise queue/latency tracing | P4 INT (HPCC-style) |
| **sFlow** | sampled, push | seconds | flow/volume, coarse CC | standard sFlow |

**On-demand (SNMP, gNMI Get):** you ask and an agent answers. Fine for *magnitude*
counters (utilization, errors over an interval) and for validating a config change; too
slow and coarse for catching a 100 µs microburst. [F: standard]

**Streaming telemetry (gRPC/gNMI subscribe):** the switch *pushes* deltas on
timer/sample cadence without being polled — this is what fills live dashboards
(`gNMI Subscribe` / OpenConfig, Arista **CloudVision**/NetDL, NVIDIA **UFM**, Cisco
**Nexus Dashboard**). The dominant modern mechanism; nodes export OpenConfig paths and
collectors subscribe. [F: gNMI/OpenConfig + vendor platforms]

**In-band telemetry / INT:** the switch **stamps per-hop data into the packet itself**
(ingress/egress timestamps, queue occupancy, path id), which the receiver or a probe
collects. Because it rides the packets, it shows *actual per-hop queueing on the exact
path the flow took* — the only way to see where a collective's P99 delay accumulated.
INT is a **P4.org specification, not an IEEE 802.1 standard**, with vendor silicon
(Broadcom, Marvell Teralynx, Intel Tofino; Cisco "smart stamping"). It is the telemetry
base of **HPCC-style [A]** congestion control: HPCC (SIGCOMM'19) drives precise rate
control off INT-carried queue occupancy instead of ECN. [F: P4.org INT spec; [A]: HPCC]

**sFlow:** statistical sampled flow export — cheap, good for traffic-volume/flow
mapping, too lossy to *control* anything, useful for understanding which flows exist
before you chase a counter. [F: standard]

## How — the delivery stack, end to end
```text
 switch/NIC silicon ──► exporter (INT stamp / gNMI sub / sFlow agent)
      │                     │
      │  per-packet INT      └── gRPC/gNMI push ──► collector (Time-series DB)
      ▼                                                                 ▲
 probe/receiver collects INT → log      dashboards / alert / ML ───────┘
      └──► path queue-occupancy map         (Grafana, NetQ, CloudVision,
                                            UFM, Nexus Dashboard, Splunk)
```
The two halves: **push from the network** (gNMI/INT/sFlow) and **collect + render in a
TSDB** (OpenTSDB/Prometheus-adjacent, vendor dashboards). For an AI fabric the rendering
layer must keep *per-port, sub-second* occupancy and CNP/PFC deltas — 5-minute poll
granularity hides every event that matters. [I]

## Hardware impact
INT costs silicon: per-hop stamping adds bytes to each packet (a probe header) and needs
ASIC support; legacy 100G-era merchant chips often lack it, so fabrics built on them fall
back to gNMI+coarse counters. FEC counters (`fec_corrected`/`fec_uncorrected`) only exist
where RS-FEC is enabled (PAM4 100G/lane links, see [41-physical-layer.md](./41-physical-layer.md)). Streaming
gNMI is cheap — most modern switches do it natively. [I] Budget choice: modern ASICs
(51.2T, TH5/Spectrum-4/Teralynx-10) offer per-port occupancy + some form of INT; the
collector capacity, not the switch, is usually the constraint.

## Inference impact
For inference, telemetry's job is protecting **tail latency of the latency-critical class**
(decode/KV). Track **class-separated** PFC/queue counters: if the training class is
pausing the shared link, decode QPs on the same priority pay; watch the *latency*
dimension (host `rdma`/timestamps) of the decode class specifically. [I] →
[./18-data-center-bridging.md](./18-data-center-bridging.md).

## How to measure it — the "first 10 dashboards" checklist
An AI-fabric operator should stand up, in order:
1. **Per-leaf/spine utilization** (rx/tx, per-port) — the load map.
2. **PFC XOFF/XON + duration**, per priority — the backpressure alarm.
3. **ECN-marked / CNP sent+handled**, per port — is CC firing.
4. **Queue depth/occupancy**, per port vs Kmin/Kmax — where in the ladder.
5. **FEC corrected & uncorrected**, per link — the marginal-fiber early warning.
6. **Link error counters** (symbol, link_downed, integrity), per port/physical link.
7. **Retransmit / out-of-order / packet_seq_err**, per NIC+per QP class.
8. **Drops** (true discards) — should be near zero; spikes deserve an alert.
9. **Latency deltas** (INT where available, else host RTT) + P99/P99.9 tail per class.
10. **Per-rail / per-plane busbw** from nccl-tests runs (see [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md))
    — the application-level "are the collectives healthy" summary.

## Failure modes
- **All counters green while the job crawls:** you watched drops but not PFC/ECN/queue;
  the losslessness hid the problem inside mute counters. [I]
- **`rp_cnp_ignored` rising:** receiver sees CNPs but the adapter isn't configured to act
  on them (CC disabled) — asymmetry between NIC and switch ECN policy. [F: mlx5 counters]
- **FEC-corrected climbing but links "up":** the fiber/connector is marginal; correct
  before it becomes uncorrected and starts dropping. [F/I] → [41-physical-layer.md](./41-physical-layer.md).
- **Telemetry delay hides the event:** 5-minute polling of a µs-scale fabric event — the
  dashboard never moved during an incident. Sub-second streaming is non-negotiable. [I]

## Example — correlating to a fault
Symptoms ladder: **FEC corrected** rises on leaf-port 3 (marginal DAC) → that link drops a
fraction of FEC-unrecoverable words → RoCE sees a lossy patch → `packet_seq_err`/Go-Back-N
retransmits spike on rail-3 NICs → rail-3 AllReduce becomes a **straggler** → whole-job
step time rises, JCT balloons. One marginal cable, four telemetry layers, one JCT hit.
This exact chain is the spine of the troubleshooting trees in
[45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — the
dashboards tell you *which* layer the chain broke at. [I]

## How telemetry feeds the troubleshooting trees (45/46)
Each telemetry row is an *entry condition* into a decision tree. The dashboards don't
fix anything; they pick the branch:
| Telemetry you see | Tree it drives you down (45 = IB, 46 = RoCE/NCCL) |
|---|---|
| FEC corrected/uncorrected rising, `symbol_error` | 45/46 "PHY/cable" branch → reseat/re-terminate/replace ([41-physical-layer.md](./41-physical-layer.md)) |
| `packet_seq_err` / `out_of_sequence` / retrans | 45 "transport" branch → lossy patch, MTU, GID, adaptive-routing issue |
| PFC XOFF rising with ECN silent | 39 buffer/threshold branch → mis-spaced Kmax/XOFF, incast |
| ECN+CNP both firing | CC branch → DCQCN tuning, not the cable |
| `rp_cnp_ignored` rising | CC-config branch → NIC isn't acting on CNP |
| busbw ≈ 1 rail, not K rails | 44/38 topology branch → wrong rail mapping / `NCCL_CROSS_NIC` |
| queue occupancy pinned at XOFF | 39 buffer-sizing branch → shallow buffer on a congestion point |
So the operational loop is: **dashboards → narrow to a tree → act → re-confirm on the
same counters**. The telemetry is the *probe*, the trees are the *procedure*. [I]

## When to alert vs when to eyeball
- **Alert (pager):** FEC uncorrected, link_downed, any true drop spike on a lossless
  class, PFC duration crossing a threshold for >X, retrans rising, IPC/busbw dropping
  below a floor mid-run.
- **Trend/watch:** FEC corrected drift, ECN/CNP rising with job growth, utilization
  imbalance across rails/planes.
- Rule of thumb: **alert on the early layers (FEC, PFC, queue), eyeball the late ones
  (JCT, busbw)** — by the time JCT drops, the job already paid. [I]

## Where each counter lives (NIC vs switch) — read both
Knowing *which* device owns a counter is half the diagnosis:
- **NIC (host) side:** `ethtool -S eth3` (RoCE) for `np_cnp_sent`, `np_ecn_marked_roce_packets`,
  `rx_cnp_handled/ignored`, `out_of_sequence`, `pfc_xoff_rx`, `fec_corrected/(uncorrected)`;
  InfiniBand via `perfquery` / `ibqueryerrors` for `symbol_error`, `link_downed`,
  `packet_seq_err`, `rx_icrc_encapsulated` (IB/RoCE ICRC). [F: NVIDIA mlx5 counters]
- **Switch side:** `show / telemetry` per-port occupancy, ECN-marked, discard, pause
  duration — this is where the *queue ladder* lives (39), not visible on the NIC.
- The contact point that ties them: **a drop or retrans seen on the NIC is almost always
  a switch-side queue/buffer/ECN problem upstream**; the NIC is only the witness. [I]
→ [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) for the app-level numbers that close the loop.

## Key Takeaways
1. On a lossless fabric zero drops can coexist with a dying job — the true signal lives in PFC pauses, ECN marks, CNPs, queue occupancy and FEC corrected, not drop counters ([./45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md), [./46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md)).
2. Four mechanisms scale by need: on-demand SNMP/gNMI Get (health), streaming gNMI/gRPC (dashboards), in-band INT (per-packet queue/latency), sFlow (volume) — sub-second streaming is non-negotiable for µs-scale fabric events ([./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).
3. Correlate families to localize the fault: FEC-corrected rise → marginal cable → retrans on one rail → that rail becomes the AllReduce straggler → whole-job JCT balloons (one cable, four layers, one JCT hit) ([./41-physical-layer.md](./41-physical-layer.md)).
4. Read *both* sides: a NIC-side retransmit/drop is almost always a switch-side queue/buffer/ECN problem upstream — the NIC is the witness, the switch owns the queue ladder ([./39-buffer-architecture.md](./39-buffer-architecture.md)).
5. Alert on the early layers (FEC uncorrected, PFC duration, queue pinned at XOFF) and eyeball the late ones (JCT, busbw) — by the time the job slows you have already paid ([./37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)).

## Related
- [39-buffer-architecture.md](./39-buffer-architecture.md) — the queue/ECN/PFC ladder the counters report.
- [41-physical-layer.md](./41-physical-layer.md) — BER/FEC counters and the marginal-fiber chain.
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — trees fed by telemetry.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — app-level busbw telemetry.
- [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) — the SuperNIC in-NIC telemetry engine.
- [17-troubleshooting.md](../GPU-Communication/17-troubleshooting.md) — cross-section counterpart.

## References
- [F] NVIDIA "understanding mlx5 linux counters"; NVIDIA UFM platform docs; Arista
  CloudVision/NetDL; Cisco Nexus Dashboard; Juniper Mist/Apstra — as cited in research notes.
- [F] P4.org In-band Network Telemetry spec (`p4.org/assets/INT-current-spec.pdf`).
- [A] HPCC: High Precision Congestion Control, SIGCOMM 2019 (INT-driven CC).
- [F] gNMI/OpenConfig (`github.com/openconfig/gnmi`).
