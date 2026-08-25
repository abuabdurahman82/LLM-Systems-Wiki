# Performance Benchmarking (and the network layer)
`LAST_UPDATED: 2026-08-25` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
This page bundles the measurement layer: **how to benchmark communication
fairly**, the **network fabric comparisons** (IB/RoCE/Ethernet/EFA) including
RoCE's PFC/ECN/DCQCN machinery, **multi-rail topology**, **compute/communication
overlap**, the **metrics**, and **why small vs large messages behave
differently**. The through-line: maximum bandwidth alone does not determine
performance — the *unoverlapped* communication is what the job pays for.

## 1. Microbenchmark vs application benchmark
```text
Microbenchmark      → measures the communication subsystem
   (nccl-tests allreduce, NIXLBench, ib_write_bw, ucx_perftest)

Application benchmark → measures actual LLM performance
   (tokens/sec, TTFT, ITL, training step time, MoE throughput, MFU)
```
The bridge is *translation*: a microbenchmark says "AllReduce busbw = 28 GB/s
inter-node"; the application question is "does that make step time 12% slower
than the all-NVLink baseline?" Connect every comm benchmark to its app metric:
- AllReduce busbw → **training step time** & **MFU**
- TP AllReduce latency → **ITL** (decode) / **TTFT** (prefill)
- KV transfer latency → **TTFT** of disaggregated serving
- All-to-All dispatch time → **MoE layer time** → tokens/sec
- Setup/registration overhead → **cold-start & elasticity** (scale-to-zero,
  worker add/remove) [I: the mapping every benchmark should state].

## 2. The measurement battery
**What to measure:** latency (α), algorithm bandwidth (algbw), bus bandwidth
(busbw), goodput, GPU utilization, NIC utilization, CPU utilization, tail
latency (p99/p999), transfer setup overhead.
**Message sizes** (the canonical sweep): 1 KB, 4 KB, 16 KB, 64 KB, 256 KB,
1 MB, 4 MB, 16 MB, 64 MB, 256 MB, 1 GB.
**Scales:** 2 GPUs, 8 GPUs, 2 nodes, 4 nodes, larger when data exists.
**Workloads — do not benchmark only synthetic AllReduce:**
- **Training**: gradient AllReduce (large, every step) + ZeRO
  ReduceScatter/AllGather.
- **TP inference**: AllReduce/AllGather at activation sizes (KiB–MB, every
  layer, every token).
- **MoE**: All-to-All / dispatch-combine at token sizes, *with and without*
  imbalance.
- **Disaggregated inference**: KV-cache transfer at request sizes (MiB–GiB,
  once per request) [08].
A fair framework fixes: the fabric (same switches, MTU, PFC config), the
topology (same GPU↔NIC distance), the library build (same version), the
protocol (default vs pinned), and the overlap policy (sync vs async/chunked)
[I: benchmark hygiene].

## 3. Metrics, precisely
- **Latency** — time for the smallest meaningful transfer (α estimate).
- **Bandwidth** — bytes/sec sustained for large transfers.
- **Algorithm bandwidth (algbw)** — `size / time` — the app's visible
  throughput.
- **Bus bandwidth (busbw)** — `algbw × 2(N−1)/N` for AllReduce — the *link*
  utilization (each link's share of the total traffic). busbw ≤ physical link
  bandwidth; algbw grows with N but busbw is N-invariant
  [E: factors from 02 — 1.0/1.75/1.969/1.998 at N=2/8/64/1024; F: nccl-tests
  README].
- **Goodput** — useful application progress per wall-clock (tok/s, samples/s),
  net of everything.
- **Scaling efficiency** —
  `Observed Performance / Ideal Linear Performance`
  (ideal = single-unit performance × N). Example [E]: 8× at 64% of ideal, 128×
  at 45% — the decline is communication + sync + contention; plot it, don't
  average it away.
- **Tail latency** — p99/p999 of per-op time; collectives are
  *synchronous*, so the tail is set by the slowest participant (straggler,
  hotspot, congestion episode).
- **Setup overhead** — registration + metadata + first transfer; dominates
  short-lived workers (elasticity) [08 §6].

## 4. Small vs large messages (why the regime changes)
```text
Small Messages              Large Messages
     │                          │
Latency dominated           Bandwidth dominated
     │                          │
Protocol overhead matters   Link utilization matters
```
- **Small** (≲ a few KB): α dominates; the winner is the path with the fewest
  hops and lowest protocol overhead (NVLink, LL protocol, in-network
  reduction). Doubling bandwidth does nothing; halving α wins
  [02 §3: 1 KiB ≈ 2 µs on NVLink vs ~10 µs over a RDMA hop, both "latency"].
- **Large** (≳ a few MB): β dominates; the winner is the highest effective
  bandwidth path (GDR over NDR; 16 MiB on NVLink ≈ 18.6 µs vs 16 MiB on
  100 GbE ≈ 1.3 ms [E]).
- **Different algorithms win at different sizes** — NCCL's auto-tuner is
  exactly this: ring+Simple at large, tree+LL at small, NVLS inside an
  NVLink4 domain; the crossover is *measured*, not assumed
  ([05 §4](05-nccl-algorithms-transport.md)).

## 5. Compute/communication overlap (max bandwidth ≠ max performance)
```text
BAD
Compute ████████
                  Comm ████████        (serial: pays full comm time)

BETTER
Compute ███████████████
       Comm   █████████                   (overlapped: pays the remainder)
```
The job time is the **unoverlapped remainder + synchronization**, not the sum
[01 §2]. Levers, in increasing order of sophistication:
1. **CUDA streams** — comm on a side stream while compute runs on the main
   stream (NCCL joins streams; [04 §1]).
2. **Asynchronous operations** — NIXL `postXfer` returns immediately; poll/
   notify ([07 §4](07-nixl-deep-dive.md)).
3. **Chunking** — split a large transfer into chunks; move chunk 1 while
   producing chunk 2 (KV block-level pipelining in P/D serving [08 §4]).
4. **Pipelining** — the ZeRO-3/FSDP pattern: gather the *next* parameter shard
   while computing the *current* layer.
5. **Fused communication kernels** — MSCCL++/DeepEP: communication expressed
   as a kernel fused with computation; SMs do both
   ([11 §6](11-ucx-rccl-ucc-nvshmem-deepep.md)).
6. **Device-initiated communication** — GIN/GDA/IBGDA: the GPU posts network
   work itself; no proxy thread, no stream handoff
   ([04 §7](04-nccl-deep-dive.md); [14 §4](14-moe-communication.md)).
Rule of thumb: overlap buys the *difference between link time and prefill/
compute time* — [08 §4](08-nixl-kv-cache-transfer.md) shows the 85.9 ms KV
transfer hidden under a ~0.5–1 s prefill [I].

## 6. Network fabric deep-dive
### 6.1 InfiniBand
Lossless by design (credit-based), **adaptive routing** in-switch (reacts to
congestion, load-balances at the packet level), native GDR, SHARP in-network
reduction, highest operational maturity [F: NVIDIA IB docs]. Cost:
vendor-locked fabric.
### 6.2 RoCEv2
RDMA over Ethernet (L2 or L3). The fabric must be engineered to be
"lossless-ish":
- **PFC** (Priority Flow Control) — per-queue pause frames; prevents drops but
  risks *head-of-line blocking* and PFC storms if misconfigured
  [I: standard DC practice].
- **ECN** (Explicit Congestion Notification) — marks packets at the switch
  when the queue builds; the receiver tells the sender.
- **DCQCN** — the IB-standard ECN-driven rate control pairing: sender backs
  off on ECN marks (with an AI/HD-like response) — the workhorse CC for RoCE
  [F: Mellanox DCX/ConnectX docs; I: tuning lore].
- **Adaptive routing / packet spraying** — load-spreading; IB does it in the
  switch; RoCE gets it from the NIC (connectx packet spraying) or the fabric
  (ECMP).
- **ECMP** — Ethernet's L3 multipath: hash-based, static — good for spreading
  flows, blind to congestion (the exact weakness UCCL-Tran's software spraying
  attacks) [09 §3].
### 6.3 Ethernet (non-RDMA)
Plain TCP/ENA-class fabrics: the lossy, commodity path. UCCL-Tran/AFXDP and
libfabric make this usable for collectives [09; 11 §8].
### 6.4 AWS EFA
**SRD** (Scalable Reliable Delivery): lossy-tolerant (no PFC), adaptive
routing inside the NIC/ENI stack, GDA offload (GPU posts work directly)
[F: AWS EFA docs]. NCCL supports EFA via libfabric (aws-ofi-nccl plugin) and,
since 2.31, **EFA GDA inside GIN** [04 §7; F: NCCL 2.31 release notes].
### 6.5 Comparison
| Property | InfiniBand | RoCEv2 | EFA |
|---|---|---|---|
| Loss behavior | lossless (credits) | engineered lossless (PFC) or lossy+retransmit | lossy-tolerant (SRD) |
| Congestion control | adaptive routing + PFC-free | PFC + ECN + DCQCN | built-in SRD CC |
| Routing | adaptive, in-switch | ECMP static / NIC spraying | adaptive, in-NIC |
| GDR/GDA | native | native | GDA (2.31 GIN) |
| Op complexity | medium (vendor stack) | **high** (PFC/ECN tuning, storms) | low (cloud-native) |
Software libraries interact with these fabrics *rather than treating the
fabric as a black box*: NCCL's transport selection, UCCL-Tran's spray+CC, and
NIXL's backend choice all read the fabric's properties and adapt
[../Networking/README.md; I].

## 7. Multi-rail networking
```text
             GPU
              │
       ┌──────┴──────┐
       ▼             ▼
     NIC0           NIC1
      │               │
Fabric Rail A     Fabric Rail B
```
- **Rail optimization** — GPU i ↔ remote GPU i through NIC i; flows stay in
  their rail; congestion is bounded per rail [03 §3].
- **NIC affinity / GPU-NIC locality** — same-PCIe-switch pairing (PIX in
  `topo -m`) beats cross-socket (SYS) [03 §4].
- **NUMA** — register memory on the NIC's socket; cross-NUMA adds the UPI hop.
- **Rail-local routing** — the fabric (or the library) keeps traffic
  rail-local; cross-rail is a last resort.
- Libraries exploit multiple NICs: NCCL `nChannelsPerNetPeers`/`NCCL_MAX_NCHANNELS`
  striping [05 §5]; UCCL-Tran spraying across paths; NIXL backends pick per
  transfer [07].

## 8. Topology matters (reading `nvidia-smi topo -m`)
```bash
nvidia-smi topo -m     # what it does: prints the GPU/GPU/GPU-NIC distance matrix
                       # expected: a matrix of X / NV# / PIX / PXB / PHB / NUMA / SYS
                       # look for: your GPUs' distances to their NICs (want PIX/PXB)
                       # failure mode: NICs show SYS to all GPUs → cross-socket
                       #   placement; every GDR transfer pays the UPI hop
```
- **NV#** — NVLink link count (NV18 on full NVSwitch domains).
- **PIX/PXB** — PCIe same/different switch: P2P & GDR-friendly.
- **NUMA/PHB** — host-bridge hops.
- **SYS** — inter-socket: the worst rung [03 §4].
The principle: `GPU → local NIC` beats `GPU → CPU socket → PCIe → remote-NUMA
NIC` — roughly a 2–4× bandwidth haircut per extra rung [I: measured P2P
degradation].

## 9. Practical architectures (the four canonical stacks)
1. **Distributed training** — 8×GPU node, NCCL over NVLink intra-node, one
   NIC per GPU, GDR over IB inter-node; SHARP if the switch supports it
   ([12 §1](12-training-communication.md)).
2. **TP inference** — multi-GPU TP on NVLink; NCCL AllReduce ×2/layer; the
   fabric carries DP/PP/EP traffic only ([13 §2](13-distributed-inference-communication.md)).
3. **Disaggregated inference** — Prefill → NIXL → UCX/UCCL → GDR → Decode
   ([08](08-nixl-kv-cache-transfer.md)); layer-by-layer in [13 §6].
4. **Large MoE cluster** — router → token dispatch → UCCL-EP/DeepEP → GPU-driven
   IBGDA-class all-to-all over IB/RoCE/EFA ([14 §6](14-moe-communication.md)).

## Key Takeaways
1. Microbenchmarks measure the subsystem; app benchmarks measure the job —
   every comm number must state its app-metric translation (step time, TTFT,
   tok/s).
2. algbw vs busbw: algbw is the app view, busbw is the link view; busbw is the
   one that must fit under the physical link.
3. Small messages die on latency, large on bandwidth; the algorithm/protocol
   crossover is measured, per fabric.
4. Overlap (streams → async → chunk → pipeline → fused → device-initiated) is
   what converts "the link is 50 GB/s" into "the job is not 50 GB/s-bound".
5. Fabric differences (IB lossless+AR, RoCE PFC/ECN/DCQCN, EFA SRD) gate what
   the software can do — the libraries read the fabric, not the other way.
6. Multi-rail + NIC locality + `topo -m` literacy: the topology is a first-order
   performance variable.

## Related
[17 Troubleshooting](17-troubleshooting.md) · [19 Practical Labs](19-practical-labs.md) ·
[05 NCCL Algorithms & Transport](05-nccl-algorithms-transport.md) ·
`../Benchmarks/README.md`

## References
- nccl-tests README (algbw/busbw definitions, test matrix) —
  https://github.com/NVIDIA/nccl-tests (fetched 2026-08-25) [F]
- AWS EFA documentation (SRD, GDA) [F]; Mellanox/ConnectX RoCE docs (PFC/ECN/DCQCN,
  adaptive routing, packet spraying) [F]
- NIXLBench/KVBench docs — https://github.com/ai-dynamo/nixl/tree/main/benchmark [F]
- `../Networking/README.md`, `../GPU-Systems/Topology.md` (internal)
