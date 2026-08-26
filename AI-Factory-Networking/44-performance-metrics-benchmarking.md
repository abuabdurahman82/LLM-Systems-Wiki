# Performance Metrics & Benchmarking
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: perftest (linux-rdma), nccl-tests PERFORMANCE.md, NVIDIA mlx5 counters article; all [E] from the section constants bank (2026-08-25).

## 30-Second Explanation
An AI fabric is judged by **Job Completion Time (JCT)**, not by one peak number. The
healthy vocabulary is: *throughput vs goodput* (bits on the wire vs useful progress),
*link utilization* (never 100% of application bandwidth), *message rate* (PPS, the
hidden ceiling), *latency percentiles* (P50/P95/P99 and the **tail** — the value that
actually stalls a synchronized collective), *bandwidth efficiency*, and *stall time*
(congestion and GPU idle). The rule you carry out: **the best AI network is not the one
with the fastest ports — it is the one whose worst-case, tail-of-the-distribution,
under-load performance keeps every GPU busy**, i.e. minimizes JCT [I: standard systems
argument]. This page defines each metric, gives exact fenced commands to measure them,
and tells you what "correct" looks like and when a benchmark is invalid.

## The metric hierarchy
```text
            JCT  (steps/sec end-to-end)      <- the ONLY number a business cares about
                 |
        +--------+---------+---------+---------+---------+
        |        |         |         |         |         |
   throughput  goodput  utilization  msg_rate  latency   stall_time
      [bits]    [useful]   [w.r.t.    [Mpps]   (P50/95/  (congestion
                bytes]     line]              P99/tail)   + GPU idle)
```
Every lower-level metric is only worth measuring because it predicts JCT. A link that
is 95% utilized can still produce terrible JCT if that utilization is spent on
retransmits, CC backoff, or one congested 5% [I]. [T] the coupling between percentiles
and stragglers is the reason AI nets are designed "lossless."

### What / Why / How / When / Failure modes / How to measure it
- **What**: the six metrics below plus JCT.
- **Why**: you need a common yardstick across NIC, switch, and collective.
- **How**: perftest for raw verbs, nccl-tests for collectives, counters for congestion.
- **When**: on bring-up, after any change, and whenever a step time regresses.
- **Failure modes**: measuring the wrong layer (perftest says great, collective terrible
  = the problem is topology/CC, not the NIC); reading utilization as progress.
  [I]
- **How to measure**: the fenced command groups further down.

## Throughput vs goodput
- **Throughput** = raw data rate on the wire, including protocol overhead — the number
  `ib_write_bw`'s "BW average" reports. **[I] definition**
- **Goodput** = useful application bytes delivered per second, *after* headers and
  retransmission and CC backoff. The gap is quantifiable: RoCEv2 carries a fixed `[E]
  58 B/packet` of header (Ethernet 14 + IPv4 20 + UDP 8 + BTH 12 + ICRC 4), so at a 4 KB
  payload the *payload ceiling* is `[E] 1.42%` below line rate; at `[E] 1500 B payload`
  it is `[E] 3.87%` below. On top of the structural overhead, a lossy/backed-off fabric
  wastes goodput on Go-Back-N retransmits ([17-why-roce-is-harder.md](./17-why-roce-is-harder.md)).
- **Example**: a 400G link is `[E] 50.0 GB/s`. A perftest showing `[E]` ~47–49 GB/s at
  4 KB messages is at the payload ceiling — *correct*. A NIC "at line rate" is `[E]`
  never delivering 50 GB/s of application bytes. [E]

## Link utilization
- **Definition** `U = app_BW / link_BW`. The trap (worked on [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md)):
  a link can sit at ~95%+ *wire* utilization while delivering far fewer *application*
  bytes, because the payload share is what's left after headers. [E]
- **When it matters**: utilization tells you you're *not* leaving the port idle; it does
  *not* tell you the collective finished. High utilization + bad JCT = traffic is being
  spent badly (incast, imbalance, retransmit).
- **Healthy look**: single flow at ~`[E]` line-rate × 0.95+ at large messages (≥1 MB);
  many-flow/collective case governed by the busbw formula below, not by line rate. [I]

## Message rate (PPS)
- The frame-count ceiling is separate from bandwidth: each frame has fixed overhead, so
  small messages are *PPS-bound*, not byte-bound. `[E] 400GbE @1518B = 32.94 Mpps`,
  `[E] 400GbE @9018B = 5.54 Mpps`; `[E] 100GbE @1518B = 8.23 Mpps`. A 256 B-payload
  stream is header-dominated (`[E] 22.66%` overhead) and lives near the Mpps wall, which
  is why AI fabrics run jumbo/IB-MTU-4096 frames ([41-physical-layer.md](./41-physical-layer.md)). [E]
- **Where you see it**: perftest prints `MsgRate[Mpps]` in the rightmost column.

## Latency: P50/P95/P99 and the tail
- P50 = median, P95/P99 = the slowest few percent. For a *synchronized* collective the
  whole step waits for the **last** rank, so the relevant figure is the **tail**, not the
  median. A +1 µs tail × `2(n-1)` ring steps × hundreds of AllReduces per step is
  milliseconds of added step time ([33-collective-communication.md](./33-collective-communication.md)). [I]
- Healthy IB single-pair latency is **single-digit µs** [A: widely observed verbs
  latency]; RoCE adds PFC/ECN machinery. Percentile *spread* (jitter) is as important as
  the median for straggler behavior [40-network-telemetry.md](./40-network-telemetry.md).

## Bandwidth efficiency (busbw)
- For collectives the honest number is **busbw** = algorithm-adjusted per-GPU bandwidth.
  For AllReduce `[E] busbw = algbw × 2(n-1)/n` (bank row "busbw relation"). A ring AllReduce
  moves `[E] 2(n-1)/n × M` wire bytes per rank (n=8, 100 MB → `[E] 175 MB/rank`, `[E]`
  3.53 ms at 50 GB/s) — the `2(n-1)/n` factor is the efficiency tax. algbw is the raw
  "messages/sec over the algorithm"; busbw is "how well you're using the fabric." [F:
  nccl-tests PERFORMANCE.md]

## Congestion / stall time and GPU stall time
- **Congestion/stall time**: seconds any flow spends queueing or rate-limited (PFC
  XOFF, ECN/CNP backoff, incast). Read it from PFC/ECN/CNP counters and per-QP completion
  gaps. [I]
- **GPU stall time**: time a GPU sits idle waiting on a remote collective — the direct
  JCT killer. NVIDIA profilers report it (e.g. `ncu`/Nsight "gpu idle %", NCCL timings).
  The relationship is causal: slower fabric → more GPU stall → higher JCT. [I]
- **Why it beats peak BW as a metric**: two fabrics with identical line rate can differ
  enormously in stall time under incast/CC churn. [I]

## JCT — the ultimate metric
- **Definition**: wall-clock time to finish a job (or one training step × steps). Every
  lower metric is only a proxy for JCT. "**Best AI network ≠ fastest ports**": a fabric
  with the highest single-flow BW but bad tail latency, imbalance, or PFC storms loses
  to a slower-port fabric that keeps all ranks busy. [I]
- **How to measure**: run the real workload (or a representative collective mix) and
  time it; express as steps/sec or time-to-converge. Then attribute any gap to a specific
  lower metric via [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).

## Benchmarking methodology — RDMA perftest (NIC/QP level)
`ib_write_bw`, `ib_read_bw`, `ib_send_bw`, `ib_write_lat`, `ib_read_lat` share a
server/client model. Run the **server first**, then the client pointing at it. Key flags:
`-d <dev>` device, `-F` force (ignore peer warnings), `-s <bytes>` message size,
`-x <gid>` GID index (RoCEv2), `-c` use CUDA/GPUDirect, `--report_gbits`, `-q <n>` QPs.
[F: perftest man]

```bash
# bandwidth (IB). Node A (server):
ib_write_bw -d mlx5_0 -F -s 1048576
# Node B (client):
ib_write_bw -d mlx5_0 -F -s 1048576 <nodeA-ip>

# read & send variants (same shape):
ib_read_bw -d mlx5_0 -F -s 1048576 <nodeA-ip>
ib_send_bw -d mlx5_0 -F -s 1048576 <nodeA-ip>

# latency:
ib_write_lat -d mlx5_0 -F -s 16         # server, then
ib_write_lat -d mlx5_0 -F -s 16 <nodeA-ip>
ib_read_lat  -d mlx5_0 -F -s 16 <nodeA-ip>

# GPUDirect check: run with -c; compare GPU-to-GPU vs host-to-host.
ib_write_bw -d mlx5_0 -F -s 1048576 -c
```
Expected output shape (bandwidth) — rightmost two columns are the numbers that matter:
```text
 #bytes     #iterations    BW peak[MB/sec]    BW average[MB/sec]   MsgRate[Mpps]
 1048576    1000             49870.12             49726.40            0.0474
```
Latency output: `#bytes #iterations t_min[usec] t_max[usec] t_typical[usec]`. [F: perftest
man]

## Benchmarking methodology — IB fabric health
```bash
ibstat                       # per-HCA: state/phys state, link_layer, rate
ibstatus                     # quick health summary (all CA ports)
iblinkinfo                   # full fabric link inventory: LID, speed, width, state
ibnetdiscover / ibnetdiscover -p   # fabric topology (ports/SM/P_Key), -p = partitions
perfquery -x -G <lid>        # extended port counters (symbol, link_downed, phys errs)
ibdiagnet -r                 # fabric lint: link errors, route dump, cable checks
```
What to look for: `State: Active`/`Physical state: LinkUp`, correct `Rate: 400` (=NDR400
`[E]`), zero rising `symbol_error`/`link_downed`/`local_link_integrity_errors`.
[I; counts from research-workloads §7]

## Benchmarking methodology — Ethernet / RoCE
```bash
ethtool -S <iface>      # driver counters: pfc_xon/xoff, rx_cnp, rx_ecn, drop, icrc...
ip -s link show <iface> # byte/packet/drop/error totals per iface
rdma link show          # RDMA link state per mlx5 device
rdma resource show qp   # QP states + which dev/link each QP lives on
ethtool -i <iface>      # driver info (firmware, bus, module)
```
Watch for `[I]`-noted RoCE-CC counters: `np_cnp_sent`, `np_ecn_marked_roce_packets`,
`rp_cnp_handled`/`rp_cnp_ignored`, `rx_icrc_encapsulated`, and `pfc_xoff_rx`. Rising
`rp_cnp_ignored` = CC not configured on the adapter. [F: NVIDIA mlx5 counters article]

## Benchmarking methodology — NCCL collectives
```bash
# AllReduce, sizes 8 B -> 8 GB, power-of-2 steps, 8 GPUs:
all_reduce_perf -b 8 -e 8G -f 2 -g 8
all_gather_perf  -b 8 -e 8G -f 2 -g 8
reduce_scatter_perf -b 8 -e 8G -f 2 -g 8
broadcast_perf   -b 8 -e 8G -f 2 -g 8
alltoall_perf    -b 8 -e 8G -f 2 -g 8
```
Per size the output prints `algbw` and `busbw` columns. **Read `busbw`**, not `algbw`:
for AllReduce healthy busbw ≈ `[E] 0.95 × link` (busbw = algbw × 2(n-1)/n normalizes to link at saturation). Single-dash flags (`-b/-e/
-f/-n/-g/-N`) per [F: nccl-tests]. GGDR-aware runs need the NIC on the same socket as the
GPU (`nvidia-smi topo -m`; see [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)).

## Interpretation guide — what "correct" looks like
| Test | Healthy | Suspect |
|---|---|---|
| ib_write_bw 1 MB, RC, no CC | ≥ ~`[E] line × 0.95` | «0.95 line → PCIe/NUMA/GID issue |
| ib_write_lat small | single-digit µs IB [A] | double-digit µs → queuing/path |
| AllReduce busbw | `[E] 0.95 × link` | ≪ → topology/imbalance/CC |
| Message rate | near `[E] PPS ceiling` | gapped → small-frame PPS wall |
| JCT end-to-end | matches step-time model | gap → attribute via `./46-...` |
Line-rate ×0.95+ at large message sizes, less at small sizes (PPS/header bound). [I]

## When a benchmark is invalid
1. **Wrong GID index** — GID idx 0 is RoCEv1 (link-local, non-routable); cross-subnet
   tests silently hang. Fix `-x` / `NCCL_IB_GID_INDEX`. [I]
2. **GPUDirect not engaged** — host-to-host `ib_write_bw` is fast but `-c` (GPU) is slow:
   IOMMU/ACS/`nvidia-peermem`/NUMA problem, not a fabric problem. [F: NVIDIA troubleshooting]
3. **Single-rail test on a multi-rail fabric** — with 8 NICs/node, one port tested
   "1/8 of node BW" is not the collective's real throughput; NCCL stripes across rails.
   [I]
4. **MTU mismatch** — IB "Invalid MTU"/mismatched announce, or RoCE 1500 vs 9000 split,
   yields drops and falsely low BW. Verify MTU at both ends. [I]
5. **Measuring the wrong layer** — perftest proves the NIC, nccl-tests prove the
   collective; conflating them is the most common benchmarking error. [I]

## Key Takeaways
1. JCT is the ultimate metric; every other number predicts it. "Best ports" ≠ best network. [I]
2. Link utilization ≈ 95%+ is *not* 95% application bandwidth — headers and CC eat the rest. [E]
3. Read `busbw` (not `algbw`) for collectives: AllReduce busbw = algbw × 2(n-1)/n. [E]
4. Small messages are PPS-bound; jumbo/MTU-4096 dilutes the fixed `[E] 58 B` header. [E]
5. Validate invariance first (GID, GDR, rail count, MTU) before trusting any number. [I]

## Related
- [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md) — the math behind "95% ≠ 95%".
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).
- [40-network-telemetry.md](./40-network-telemetry.md) — the counters used to read congestion/stall time.
- [53-learning-labs.md](./53-learning-labs.md) — 16 hands-on labs exercising every command here.
- [16-performance-benchmarking.md](../GPU-Communication/16-performance-benchmarking.md) — software-side benchmarking.

## References
- perftest (linux-rdma) manpages: ib_write_bw(1), ib_read_lat(1); `perftest --help` [F].
- nccl-tests doc/PERFORMANCE.md (busbw = algbw × 2(n-1)/n) [F].
- research-workloads §6–8; research-roce §4–5 (counter semantics) [F/I].
- [E] all figures from the section constants bank (computed 2026-08-25).
