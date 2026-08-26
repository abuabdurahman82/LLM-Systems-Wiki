# Rail-Optimized & Multi-Plane Topologies
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA rail-optimized / multi-plane networking docs, NCCL user guide (CROSS_NIC, multi-rail), section constants bank; fetched 2026-08-25.

## 30-Second Explanation
In a GPU server the NICs are **not** interchangeable: NIC *i* is the one closest to GPU
*i* by PCIe topology, and the fastest gradient path is GPU*i* → NIC*i* → the leaf that
owns **rail i** → NIC*i* of the peer. Rail-optimization wires the fabric so that all the
"rail-0" NICs across every node land on the *same leaves*: a transfer between two GPUs
that both use their rail-0 NIC stays inside the rail-0 leaves **and never crosses the
spine**. That collapses the traffic each collective generates into mostly-local,
per-rail flows and cuts cross-rail traffic to a small fraction. **Multi-plane** pushes
this to the limit: build K = NICs-per-node *independent* fabrics (planes), let NCCL
strip one collective across all K NICs in parallel (`8 × 400G = 400 GB/s` injection,
`[E] 8x400G node inject row`), and a plane failure degrades the job by 1/K, not by the
whole bisection. This page is the topology backbone under [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).

## What — the 8-GPU node, rail by rail
An HGX-class 8-GPU node pairs each GPU with exactly one backend NIC, in order:
```text
   GPU0  GPU1  GPU2  GPU3  GPU4  GPU5  GPU6  GPU7        (NVLink mesh within node)
   NIC0  NIC1  NIC2  NIC3  NIC4  NIC5  NIC6  NIC7        (PCIe: GPUi best→NICi)
     │     │     │     │     │     │     │     │
   ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐
   │L0 │ │L1 │ │L2 │ │L3 │ │L4 │ │L5 │ │L6 │ │L7 │   leaves: NICi → leaf i
   └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘
     │     │     │     │             ...               (each leaf uplinks to spines)
     └─── spines (carry only inter-rail traffic) ───┘
   rail 0 = {NIC0 of all nodes} = leaf L0's domain
```
Key affinity rule [F: NVIDIA rail-optimized guidance]: **NIC of GPU i always terminates
on a rail-i leaf.** So all nodes' NIC0s share leaf L0, all NIC1s share L1, etc. Then a
ring step that stays on rail 0 (GPU0→NIC0→L0→NIC0→GPU0 of peers) involves **one leaf and
no spine**. Cross-rail traffic (NIC0→NIC3) must climb to a spine.

## Why — most collective traffic can be made local
A ring AllReduce on 8 GPUs of one node already passes GPU0→GPU1→…→GPU7 over **NVLink**
intra-node ([04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md)). The *inter*-node portion sends
each node's shard over the **one NIC per rail**, and NCCL assigns each ring a single rail
(`NCCL_CROSS_NIC=0`). Result: the heavy gradient bytes flow **within one rail's leaves**,
and only the final accumulation crosses the spine. [F: NVIDIA rail-optimized doc]
Concretely, for a large AllReduce over n nodes the per-rail payload is
`2(n-1)/n × M` (see [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)), and
**almost all of it stays rail-local**, so the fabric does not need full bisection for
that traffic — it needs per-rail bisection plus headroom for the small cross-rail tail.

## How — the two architectures differ
| Dimension | Flat Clos (one fabric) | Rail-optimized (per-rail Clos) |
|---|---|---|
| NIC assignment | NICi lands on any leaf | NICi **always** on rail-i leaf |
| Same-rail transfer | may cross spine | stays local (leaf-only) |
| Cross-rail traffic | normal ecmp | small tail fraction |
| Switch failure | leaf drops its hosts | leaf drops **one rail of all hosts** |
| NCCL config | default | `NCCL_CROSS_NIC=0` / rail-aware topo |
| Bisection needed | full inject | per-rail inject + cross-rail headroom |

## How — the gradient path through the rails (one collective, step by step)
Follow one shard of an 8-node AllReduce living on **rail 2** only; every node sends its
local slice down its rail-2 NIC and the leaf reduces/forwards it:
```text
node A                          rail-2 leaf L2                  node B (peer)
GPU2 --(NVLink mesh)--> GPU?   ┌─────────────────┐
   | NIC2                      │  forward shard   │              GPU2
   | (PCIe local)              │  (no spine!)     │              |
   v                           └────────┬────────┘              v
 send shard A ---------------->        │  shard B <-- NIC2 (PCIe local)
                          all rail-2 NICs share this leaf
   only the *summed* result (post-reduce) crosses to a spine for the last hop
```
The data-plane point: **the reduce happens inside the rail**, the spine only sees the
tiny per-rail aggregate. [I: standard ring/rail behavior]

## When — choose the pattern
- **1 NIC per GPU, ≤ a few hundred GPUs:** rail-optimized single-plane leaf-spine, full
  bisection (the 42 page's balanced Clos) — simplest, no multi-plane complexity. [I]
- **2 NICs per GPU or NIC pairs on dedicated rails:** dual-rail (2 planes) balances
  resilience vs switch cost; common for mid pods. [I]
- **8 NICs per 8-GPU node (the NVL72-era pattern):** 8-rail / 8-plane so each collective
  stripes across all 8 NICs → `8 × 50 GB/s = 400 GB/s` per node injection
  (`[E] 8x400G node inject row`). → [52-reference-architectures.md](./52-reference-architectures.md). [F: vendor patterns]

## NCCL topology awareness — rails are preferred, cross-rail only when needed
NCCL builds its communication plan from the **topology** (`topo.xml`), which encodes
which NIC is nearest which GPU and how NICs group into rails. Two behaviors make this
"rail-aware":
- **Channel↔rail pairing:** for a multi-rail node, NCCL creates one channel per NIC and
  assigns each ring/tree a channel — i.e. a ring that needs inter-node traffic uses *one*
  NIC per node, all on the same rail, so every hop is rail-local. [F: NCCL docs]
- **`NCCL_CROSS_NIC`:** with `=0` (the rail-optimized setting), NCCL keeps all
  traffic within a NIC/rail per ring and only crosses rails when the collective demands
  more paths; the default allows crossing, which on a non-railed fabric is fine but on a
  railed one wastes the locality. [F: NCCL env guide]
- **When cross-rail happens at all:** (a) ring/tree algorithms that need >K ranks than a
  single rail holds, (b) AllToAll/expert dispatch that must reach any node regardless of
  rail, (c) a rail with a failed leaf temporarily steering onto a neighbor. In each case
  the fabric must have *some* cross-rail capacity — that is headroom, not the main line. [I]

## Example — reducing the cross-rail fraction
Consider an 8-node AllReduce with `M = 100 MB` per rank on an **8-rail** fabric
(so each ring carries `M/8 = 12.5 MB`). Ring mathematics
(`2(n-1)/n × M`, see [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)) say each rank moves
175 MB total. With rail-optimized wiring, ~7/8 of that byte volume rides **inside a
single rail's leaves**; only the cross-rail portion (the shards a rail's ring must
exchange with other rails' rings) actually climbs a spine. Practical ratios are
config-specific, but the design intent is that **cross-rail traffic is a small fraction
(<~25% for AllReduce/AllGather, more for AllToAll)** of the wire volume, which is why a
slightly oversubscribed spine layer rarely shows up in AllReduce busbw but shows up
immediately in AllToAll. [I] The counter-example that needs full cross-rail: **AllToAll /
MoE dispatch**, which is a permutation with no locality — budget full bisection there or
accept incast. [I] → [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).

## Multi-plane = independent fabrics per NIC set
Multi-plane is the strict form of rail-optimization: **K completely independent Clos
fabrics**, one per NIC position. Plane k serves exactly the rail-k NIC of every node.
NCCL maps **channels** to planes: with K NICs NCCL opens K channels and stripes each
collective across them, so one collective uses all K fabrics in parallel. Because the
planes are disjoint, per-plane Clos at P planes has K× the injection of one plane, and a
single-plane failure at most halves/quarter-s the allreduce *for the rest of the job*
while the other planes keep carrying. [F: NVIDIA multi-plane doc]

### Hardware impact
Per-node injection: `NIC count × per-NIC rate`. For 8 × 400G that is **400 GB/s
(`[E] 8x400G node inject = 400 GB/s = 3.2 Tb/s`)**; the same node at 8 × 800G is 800 GB/s
(`[E] 8x800G node inject row`). This is what the PCIe topology must feed (see [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)):
8 × 400G needs 8 × 50 GB/s of PCIe — comfortably under an 8-GPU box's aggregated Gen5
links; 8 × 800G at 100 GB/s each needs Gen6 or dual links. [E]

### Inference impact
Rail locality helps inference less than training: decode/prefill KV transfers are
**latency-bound point-to-point**, not bandwidth-bound collectives, so whether they ride
one rail or spray across planes matters less than keeping them out of queueing behind
training bursts (→ [./10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md)). But multi-plane *does* give fault
tolerance and lets a routing layer shift a failing plane's QPs to a healthy one with less
blast radius. [I]

## Example — 1,024 GPUs, 8 planes, the numbers from page 42
Cross-ref the `[E]` rows in [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md):
- Single fabric, 1,024 GPUs × 1×400G, radix 8 → 128 endpoints/leaf level… wait: 128 leaves,
  **32 leaves + 32 spines**, inject = bisection = 6.4 TB/s, oversub 1.000. [E: bank 1024 GPU row]
- Rail/multi-plane: 1,024 GPUs × 8×400G on 8 planes → **each plane is a 1,024-GPU/8 = 128-GPU
  railed Clos**, i.e. per-plane E=128, L=S=32, per-plane inject=bisection=6.4 TB/s, **×8
  planes = 51.2 TB/s total** (the bank row "1024 GPU rail 8×400G 8 planes": inject =
  bisection = 51.2 TB/s, oversub 1.000). [E]
- One plane (8 leaves) failing on the 8-plane design removes 1/8 of every node's NICs →
  allreduce runs at ~7/8 bandwidth, job survives; the same failure in a single-fabric
  1×400G design removes a full eighth of the *fabric* → same relative loss but no other
  plane to fall back on. [E derivation / I]

## Failure modes
- **Wrong NIC mapping (NIC of GPU2 on leaf 0):** silently turns a "railed" fabric into a
  flat Clos — same-rail shortcuts vanish, cross-rail spikes. Verify with `nvidia-smi topo -m`
  and a per-rail perftest. [I]
- **`NCCL_CROSS_NIC` unset / wrong:** NCCL may choose a cross-rail ring and push
  traffic through the spine even when a rail-clean ring exists; symptom = busbw drops for
  no loss. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).
- **Plane imbalance (ECMP hash collision within a plane):** two rings hash to the same
  uplink of a plane; one uplink saturates while its sibling idles. Fix SL/source-port
  entropy or per-plane hashing. [I]
- **Single-plane test on a multi-plane fabric:** a benchmark that uses one NIC only
  underreports the node's actual injection; always size benches at K rails.
  → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).

## How to measure it
- `ib_write_bw -c` per rail: confirm rail k achieves line rate (NDR400 = 50 GB/s
  `[E: NDR400 per port row]`). If rail 3 is half rate, its leaf/plane is the suspect.
- `nccl-tests` busbw: `all_reduce_perf` at 8 rails should approach
  `algbw × 2(n-1)/n` (the `[E] busbw relation row`), i.e. near the `0.95 × link` saturation.
- `ibnetdiscover`/`ibdiagnet -r`: confirm each rail's NICs sit under the rail-k leaves.
- `nvidia-smi topo -m`: confirm GPU↔NIC labels are NODE/NVB (same PCIe tree), not SYS.

## Comparison table — plane count
| Config | BW aggregation | Fault domain / switch fail impact | NIC distribution | Path diversity | NCCL config |
|---|---|---|---|---|---|
| Single-rail (1×400G) | 50 GB/s/node | one leaf down → all its hosts out | all NICs → 1 plane | ECMP within 1 Clos | default |
| Dual-rail (2×400G) | 100 GB/s/node [E] | 2 planes; leaf fail drops 1/2 of each node | NIC0→plane0, NIC1→plane1 | 2 disjoint paths | `NCCL_CROSS_NIC` may help |
| 8-rail (8×400G) | 400 GB/s/node [E] | 8 planes; leaf fail drops 1/8 of each node | NICi→plane i | 8 disjoint paths | 8 channels, cross-NIC=0 |
| 8-rail 8×800G | 800 GB/s/node [E] | 8 planes, larger per-plane BW | NICi→plane i | 8 wide paths | GDR + Gen6 PCIe |

[E] values from bank: 8x400G inject 400 GB/s, 8x800G inject 800 GB/s, NDR400 50 GB/s.

## Key Takeaways
1. NIC of GPU *i* always terminates on the rail-*i* leaf, so ring AllReduce bytes stay inside one leaf domain and never cross the spine — rail locality is what removes bisection pressure ([./42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)).
2. Multi-plane builds K = NICs-per-node independent Clos fabrics; NCCL stripes one collective across all K NICs (8×400G = 400 GB/s injection), and a plane failure degrades the job by only 1/K ([./37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)).
3. Set `NCCL_CROSS_NIC=0` so each ring stays on one rail; crossing happens only for algorithms needing >K ranks, AllToAll/MoE dispatch, or failed-rail fallback — budget cross-rail *headroom*, not full bisection ([./33-collective-communication.md](./33-collective-communication.md)).
4. AllToAll/MoE is a permutation with no locality and needs full cross-rail bisection; AllReduce/AllGather is mostly rail-local, which is why a slightly oversubscribed spine rarely shows up in AllReduce busbw ([./52-reference-architectures.md](./52-reference-architectures.md)).
5. Verify rails with `nvidia-smi topo -m`, `ibnetdiscover`, and per-rail `ib_write_bw -c` — a wrong NIC→leaf mapping silently turns a railed fabric back into a flat Clos ([./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Related
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — the per-plane Clos arithmetic.
- [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) — the NICs this wires.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — measuring rail/plane correctness.
- [52-reference-architectures.md](./52-reference-architectures.md) — 32/256/1,024-GPU designs applying rails.
- [53-learning-labs.md](./53-learning-labs.md) — Lab-22 rail/busbw exercise.
- [04-nccl-deep-dive.md](../GPU-Communication/04-nccl-deep-dive.md) — NCCL channel/rail mapping.

## References
- [F] NVIDIA rail-optimized & multi-plane networking docs; NCCL env guide
  (`NCCL_CROSS_NIC`); fetched 2026-08-25.
- [E] All topology/inject/bisection numbers from the section constants bank
  (8x400G, 8x800G, NDR400, 1024-GPU rail 8-plane, busbw relation), computed 2026-08-25.
