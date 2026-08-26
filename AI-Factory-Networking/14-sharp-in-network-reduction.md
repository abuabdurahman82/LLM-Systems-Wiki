# SHARP: In-Network Reduction
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA SHARP developer blog, NVIDIA SHARP User Manual, NVIDIA/NCCL environment docs, NVIDIA broadcast of JP Morgan/Introl SHARP-v4 notes; precision/float support and performance extrapolations marked [I]; fetched 2026-08-25.

## 30-Second Explanation
**SHARP** — Scalable Hierarchical Aggregation and Reduction Protocol — moves the reduction
step of collectives (AllReduce, Reduce, Broadcast) **out of the endpoint GPUs and into the
switches**. Normally an N-rank AllReduce shuttles every rank's tensor around the ring
(`2(n−1)/n·M` bytes per rank [E: bank]). SHARP instead streams the tensors **up toward a
switch that runs an aggregation engine**: as chunks of a message pass through, the switch
reduces them in-network, so only a *reduced* result (one message worth, not N copies) crosses
the fabric — and the aggregation tree can be hierarchical (many switches combine upward).
The GPUs send once and receive the reduced result; repeated endpoint data transfer
disappears [F: NVIDIA SHARP blog]. Enabling it in NCCL is `NCCL_COLLNET_ENABLE=1`
(`NCCL_SHARP_ENABLE` is the older/legacy name); it requires **Quantum switches** (the reduction
engines live in switch silicon) plus compatible HCAs (ConnectX-6 and above) [F: NVIDIA SHARP
doc; vendor claim]. Serializing when: large, synchronized AllReduce across many nodes —
bandwidth saved at scale is the whole point.

## Without SHARP (ring AllReduce in the fabric)
```text
 rank0 ──┐
 rank1 ──┼──► switches move 2(n−1)/n·M bytes/rank around the RING
 rank2 ──┘     (each rank sends AND receives full tensors; no in-network reduction)
 Each step: recv prev chunk, reduce locally, send onward. Endpoints do ALL the math.
```

## With SHARP (in-network AllReduce/Reduce/Broadcast)
```text
                ┌────────────────────────────┐
                │  SWITCH aggregation engine │  reduce 1/2 of pairs, forward up
                └─▲───────────────▲──────────┘
                  │ reduced       │ reduced
         ┌────────┴───┐    ┌──────┴────────┐
         │ switch     │    │ switch        │   each switch reduces its child chunks
         └─▲──▲──▲────┘    └─▲──▲──▲───────┘
           │  │  │            │  │  │
         rank0 1 2          rank3 4 5       GPUs stream once; switch returns reduced result
```
The **aggregation tree** is a tree of switch engines. Chunks of a tensor flow up the tree,
getting reduced at each level, and the (much smaller) reduced result (for AllReduce, the
final sums) flows back down. NVIDIA calls the engines in the switch "**SHARP aggregation
engines**"; the **aggregation manager(s)** (part of the fabric/SM + SHARP stack) build and
book the aggregation trees per job [F: NVIDIA SHARP doc].

## What/Why/How
- **What**: an in-network-computing offload — switches perform the combine (add/mul/min/max)
  that collectives need, instead of endpoints.
- **Why**: endpoint reductions force every rank to move a full tensor; in-network reduction
  collapses the traffic to ~one message worth, and merging it *while* data flows up cuts both
  bytes and latency for large synchronized AllReduce/MoE-gradient jobs [F: NVIDIA SHARP blog;
  [I] implications].
- **How**: the reduction-capable HCA streams message chunks; switches between source and the
  aggregation point reduce pairwise and pass on; the tree is arranged by aggregation
  managers, and NCCL/MPI select SHARP as the collective transport when enabled and eligible.

## NCCL integration
NCCL talks to SHARP through its **collnet / in-network** path:
```text
NCCL_COLLNET_ENABLE=1     # use in-network (SHARP) collectives  [F: NCCL docs]
NCCL_NVLS_ENABLE=...      # NVLink SHARP (intra-node, NVSwitch) — separate from IB SHARP
NCCL_SHARP_ENABLE=1       # legacy/historical name for the same control [A: research notes
                          #  mark it superseded by COLLNET/NVLS in current NCCL]
```
The research notes flag that current NCCL exposes **COLLNET + NVLS** as the canonical knobs
and that `NCCL_SHARP_ENABLE` is the older form (`UNVERIFIED` as current) [F: NCCL env doc; [A]
NCCL 2.2x-era usage]. On a Quantum fabric with NCCL gradients, setting COLLNET lets NCCL choose
SHARP-accelerated AllReduce for large messages.

## MPI-3 integration
MPI-3 added non-blocking collectives and a general API; MPI libraries (Open MPI / Spectrum MPI /
HPC-X) can route their **Ibarrier/Allreduce/Iallreduce** through SHARP when the fabric exposes
it, so MPI jobs on a Quantum + HCA stack get the same in-network reduction NCCL does [F: NVIDIA
SHARP blog; [A] MPI-HPCX integration].

## Use cases
- **Large synchronized AllReduce** (the headline): big gradient all-reduce across hundreds+
  ranks; the tensor is streamed and reduced in-network, so aggregate fabric bytes drop
  sharply and straggler tails shrink [F: NVIDIA SHARP blog; [I]].
- Reduce / Broadcast of large payloads, and MoE / checkpoint-style reductions that pipeline
  well through the streaming engines.
- Multi-tenant shared fabrics: SHARPv3+ supports **multiple aggregation trees over one
  topology**, so several jobs' collectives don't collide [F: NVIDIA SHARP doc].

## Limitations
```text
1. Fabric requirement: reduction lives in the SWITCH — needs NVIDIA Quantum switches
   (HDR/NDR/XDR + SHARP engines) [F: vendor]. It is not a generic-IB feature.
2. Endpoint requirement: reduction-capable HCA (ConnectX-6 and above; ConnectX-8 native
   SHARP for XDR) [F: vendor claim].
3. Precision / float support: in-switch arithmetic is fixed-point/typed per SHARP
   generation; whether a given dtype (e.g. BF16/FP16 intermediates, exact accumulation)
   is supported depends on switch generation — marked [I] because exact per-generation
   dtype/precision tables were not captured in the research notes (UNVERIFIED).
4. SHARPv1-3 generation limits: e.g. Quantum supports up to 126 aggregation trees
   (63 low-latency + 63 streaming; one active streaming tree per switch) [F: NVIDIA SHARP
   UM]. Streaming (SHARPv2, HDR+) targets large AI messages; SHARPv1 was HPC-oriented.
```

## Generations (production vs announced — keep straight)
| Gen | Era / switch | Notable property |
|---|---|---|
| SHARPv1 | scientific/HPC | initial aggregation |
| SHARPv2 | HDR 200G Quantum | + AI large-message streaming (single job) [F] |
| SHARPv3 | Quantum-2 / NDR | multi-tenant, multiple aggregation trees [F] |
| SHARPv4 | Quantum-X800 / XDR (announced GTC 2024) | named in press release; shipping with XDR [F: vendor] |

**Production as of 2026-08-25:** SHARPv3 in production on Quantum-2/NDR; SHARPv4 announced with
XDR (Quantum-X800 + ConnectX-8) and listed as production/release in NVIDIA's 2026 docs [F:
NVIDIA XDR clusters doc — vendor claim]. Don't present SHARPv4 as universal: it needs the XDR
stack.

## Performance impact
- **Bandwidth saved at scale**: ring AllReduce moves `2(n−1)/n·M` bytes per rank [E: bank]; for
  n=128, M=1 GiB that's ~2.0 GiB/rank across the fabric. In-network reduction collapses the
  reduce phase to roughly one message worth of *reduced* data flowing (and the broadcast back),
  so aggregate fabric bytes for the reduction approximate the message size, not n× it [E-derived,
  [I] approximation]. The exact multiplier depends on tree layout and is **UNVERIFIED as a
  universal constant** ("3x faster" claims from NVIDIA are [F: vendor]); treat the *direction*
  (fewer bytes, less latency at scale) as the reliable claim.
- **Latency benefits**: reduction overlaps with data movement and the tree depth is O(log tree)
  rather than O(n) ring steps, so straggler tails shrink as nodes grow [F: NVIDIA SHARP blog;
  [I] reasoning].
- **Measure**: compare `nccl-tests all_reduce_perf` busbw and step time with
  `NCCL_COLLNET_ENABLE=1` vs `=0` on the exact fabric. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).

## How to measure it
`nccl-tests` with/without collnet to see if SHARP engages and its busbw effect; `NCCL_DEBUG=INFO`
shows the collective algorithm/protocol chosen; SHARP/fabric logs and UFM show aggregation-tree
activity. If enabling COLLNET does nothing, the fabric isn't Quantum + compatible HCA, or the
engine didn't support the message/dtype → re-check precision support ([I]).

## Key Takeaways
1. SHARP = **in-network reduction in the switch**, collapsing AllReduce/Reduce/Broadcast
   traffic at scale [F].
2. Needs **Quantum switches + reduction-capable HCA** (ConnectX-6+, ConnectX-8 native) [F: vendor].
3. NCCL knob is `NCCL_COLLNET_ENABLE=1` (`NCCL_SHARP_ENABLE` is the legacy name) [F: NCCL docs].
4. SHARPv3 production on Quantum-2; SHARPv4 with XDR is the announced current gen (vendor claim).
5. Precision/float support is per-generation and **UNVERIFIED** in the notes — validate the
   dtype on your fabric.

## Related
- [13-infiniband-congestion-adaptive-routing.md](./13-infiniband-congestion-adaptive-routing.md) — how switches also manage congestion.
- [05-infiniband-architecture.md](./05-infiniband-architecture.md) — HCA/switch roles in the IB stack.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL collectives, algorithm/protocol selection.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — nccl-tests busbw for the with/without-SHARP test.
- [12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) — the topology the tree lives on.

## References
- NVIDIA SHARP developer blog (generations, mechanics): developer.nvidia.com/blog/advancing-performance-with-nvidia-sharp-in-network-computing/ [F].
- NVIDIA SHARP User Manual (trees, ConnectX, engines): networking-docs.nvidia.com/sharpum/3150/general-information [F: vendor].
- NCCL env docs (COLLNET/NVLS/SHARP name history): docs.nvidia.com/deeplearning/nccl/user-guide/docs/env.html [F: NCCL docs].
- Quantum-X800/XDR + SHARPv4 press (announced): nvidianews.nvidia.com/news/networking-switches-gpu-computing-ai [F: vendor].
- [E] ring AllReduce traffic `2(n−1)/n·M` from the section constants bank (2026-08-25).
