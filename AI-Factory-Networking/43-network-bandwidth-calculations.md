# Network Bandwidth Calculations: From PCIe to Bisection to the Wire
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
All [E] numbers computed 2026-08-25 in the section constants bank; GB = 10^9 bytes, Gb/s = bits (÷8 for GB/s). Companion math: [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md).

## 30-Second Explanation
Every "is this fabric fast enough?" question is arithmetic over three ceilings that must
line up: **PCIe** (what the NIC can physically pull from the GPU — `[E]` PCIe 5.0 x16 ≈ 63
GB/s), **fabric** (what the port ships — `[E]` 400 Gb/s = 50 GB/s), and **application**
(what the collective actually needs — e.g. AllReduce moves `2(n-1)/n × M` bytes per rank
`[E]`). For one 400G NIC, PCIe (≈63 GB/s) comfortably beats the port (50 GB/s), so a 400G
NIC is *not* PCIe-bound; an 800G NIC (100 GB/s `[E]`) is, on a single Gen5 x16. A node's
whole backend is `[E] 8 × 400G = 3.2 Tb/s = 400 GB/s`. This page gives the formulas and
worked examples, then shows the gap between **line rate, per-packet throughput, and
achievable application bandwidth** — which is why 95% link utilization is not 95% usable
progress.

## The four ceilings, one page
```text
 1. PCIe (GPU→NIC):   PCIe 5.0 x16 ≈ 63 GB/s one-way   [E]
 2. Per-port fabric:  400 Gb/s = 50 GB/s                [E]
 3. Node aggregate:   8 × 400G = 3.2 Tb/s = 400 GB/s    [E]
 4. Cluster bisection: see table = 42's rows            [E]
 application need:    AllReduce ring = 2(n-1)/n × M      [E]
```
Rule: design so **PCIe ≥ fabric ≥ application** at every hop; the binding link is the
smallest of the three.

## 1. GPU-to-NIC — is the NIC PCIe-bound?
`[E]` PCIe 5.0 x16 = **~63 GB/s** one-way (64 GB/s raw, ×128b/130b). `[E]` 400 Gb/s =
50 GB/s, `[E]` NDR400 per port = 50 GB/s. Since **50 < 63**, a single 400G NIC fits under
one PCIe 5.0 x16 with headroom — the NIC is *not* PCIe-bound at 400G. `[E]` 800 Gb/s =
100 GB/s, though, exceeds 63 GB/s: an 800G NIC on one PCIe 5.0 x16 is capped at ~63 GB/s
(~63% of line rate) → **it needs PCIe Gen6 x16** (≈ `[E]`-class bandwidth for 100 GB/s)
or two Gen5 links, which is exactly why 800G NICs ship with PCIe Gen6 (`[F: vendor spec]`
ConnectX-8 x16 Gen6). [E]

## 2. Server aggregate
8 backend NICs of 400G each: `8 × 50 GB/s = 400 GB/s = 3.2 Tb/s` `[E: 8x400G node inject row]`.
Same node at 8 × 800G: `8 × 100 GB/s = 800 GB/s = 6.4 Tb/s` `[E: 8x800G node inject row]`.
This aggregate must come from the GPU PCIe topology, so an 8×800G node needs 8 × 100 GB/s
of Gen6-speed links. [E]

## 3. Cluster bisection — the numbers from page 42
Bisection and topology (leaves/spines/oversub) are worked in [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md);
here is the bandwidth summary, all `[E]` rows from the bank (1×400G/NIC, radix-8,
non-blocking):
| Cluster | E (NICs) | Inject | Bisection | Oversub |
|---|---|---|---|---|
| 32 GPUs | 4 | 0.200 TB/s | 0.200 TB/s | 1.000 |
| 128 GPUs | 16 | 0.800 TB/s | 0.800 TB/s | 1.000 |
| 1,024 GPUs | 128 | 6.400 TB/s | 6.400 TB/s | 1.000 |
| 8,192 GPUs | 1,024 | 51.200 TB/s | 51.200 TB/s | 1.000 |
| 32,768 GPUs | 4,096 | 204.800 TB/s | 204.800 TB/s | 1.000 |
For a railed/multi-plane fabric, total bisection = planes × per-plane bisection (see
[38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)): `1024 GPU rail 8×400G 8 planes` = inject = bisection
= 51.2 TB/s, oversub 1.000 [E].

## 4. Collective volume — what a step actually moves
- **AllReduce (ring):** traffic per rank = `2(n-1)/n × M` `[E]`. n=8, M=100 MB, 50 GB/s,
  α=2 µs → **175 MB/rank**, `t = 3.53 ms` `[E: bank row]`; busbw = algbw × 2(n-1)/n `[E: busbw relation]`.
- **AllGather / ReduceScatter (single phase):** `(n-1)/n × M` `[E]`. n=8, 100 MB → **87.5
  MB/rank**, `t = 1.76 ms` `[E: AllGather row]`.
- **AllToAll:** no reduction saving — each rank sends and receives `M` `[E row: "send M +
  recv M per rank; no reduction saving"]`; the cost is congestion, not bytes. → [33-collective-communication.md](./33-collective-communication.md).

## 5. Serialization delay — how long one blob takes to get out the door
`T_ser = bytes / BW`. `[E] 100 MB @ 50 GB/s (400G) = 2.0 ms`; `[E] 1 GB @ 50 GB/s =
20 ms`. Serialization is the *minimum* time for a payload regardless of distance — the
floor under any round trip. Use it to sanity-check a benchmark (nothing beats 2.0 ms for
100 MB on a 400G link) and to size pipeline/sharding. [E]

## Utilization = app bandwidth / link bandwidth
`U = app_BW / link_BW`. The trap: utilization measures *bits on the wire*, not *useful
progress*. A link at 95% wire utilization can be delivering far less application
throughput because of overhead, CC backoff, contention and tail effects — quantified next.

## Theoretical vs application bandwidth — the gap table
| Loss source | Magnitude | Why |
|---|---|---|
| PCIe/overhead & descriptor | a few % | DMA/queuing overhead above payload |
| **Header overhead** | `[E] 58 B/packet` (RoCEv2), `[E] 24 B/packet` (IB) | Ethernet+IP+UDP+BTH+ICRC vs IB LRH+BTH+ICRC |
| Header %, large frames | `[E]` RoCEv2 @1500B payload = 3.87%; @4096B = 1.42% | fewer, bigger frames dilute the header |
| **PPS ceiling** | `[E] 400GbE @1518B = 32.94 Mpps; @9018B = 5.54 Mpps` | frame count caps payload, not rate |
| CC backoff | variable | DCQCN/TCC slows sends on ECN/CNP |
| Contention/incast | variable | queueing at congestion points |
| Tail effects | variable | one straggler stalls the collective |
The *structural* loss (header + framing) is computable; the *dynamic* loss (CC, cont.) is
what your tuning and topology buy back.

### Worked example — the 400G / 1500B PPS cap and "95% ≠ 95%"
A 400G link (`[E] 400 Gb/s = 50 GB/s`) with **1500B frames**: `[E] 400GbE PPS @1518B =
32.94 Mpps`. At 1518B/frame that's `32.94e6 × 1518 B = 50.0 GB/s` of *frames* — full
wire rate — **but the RoCE payload inside each frame is only 1442 B** (1500 − 58 `[E]`),
so *application* bytes = `32.94e6 × 1442 B ≈ 47.5 GB/s ≈ 95% of 50` **before any CC or
contention**. Therefore:
```text
 wire utilization   ≈ 95%+  ("full line rate")
 application rate   ≈ 47.5 GB/s  (the payload ceiling, before CC)
 with 5% CC/contention loss → ~45 GB/s usable
```
So a NIC reporting 95% wire utilization is **not** delivering 95% of application
bandwidth — payload+overhead already costs ~5%, and CC/contention eats the rest. To
recover payload share: use **jumbo frames** (`[E]` RoCEv2 @4096B payload = 1.42% overhead
vs 3.87% at 1500B) or IB MTU 4096 (`[E]` IB hdr 24 B, @4096B = 0.59%). [E]

## Failure modes — when the math is wrong in practice
- **NIC at 400G but perftest shows ~50 GB/s and no loss:** that may *be* correct — you're
  at the port ceiling; don't chase 55. Bind to PCIe/NUMA first. [I]
- **800G NIC on Gen5 x16:** hard-capped near 63 GB/s (~63% of 100); the "slow fabric" is a
  PCIe-neck, visible in `lspci`/`nvidia-smi topo`. [E]
- **Small-frame PPS surprise:** a 1500B 400G fabric is PPS-ceiling'd at 32.94 Mpps `[E]`;
  if the NIC can't sustain it, per-packet overhead (not bandwidth) binds. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).
- **Misreading utilization:** 95% wire ≠ 95% app; always convert to *application* bytes
  (payload after headers) before calling something "at line rate". [I]

## Key Takeaways
1. Bandwidth is arithmetic over three ceilings that must line up: PCIe (Gen5 x16 ≈ 63 GB/s), per-port fabric (400G = 50 GB/s), and application (AllReduce moves `2(n-1)/n × M` per rank) — the binding one is the smallest ([./42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)).
2. A single 400G NIC fits under one PCIe 5.0 x16 with headroom and is not PCIe-bound; an 800G NIC (100 GB/s) exceeds it and needs PCIe Gen6 x16 or two Gen5 links ([./37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)).
3. Node aggregate scales with NICs: 8×400G = 400 GB/s, 8×800G = 800 GB/s, fed from the GPU PCIe topology; cluster bisection = the page-42 rows ([./38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)).
4. Utilization measures bits on the wire, not useful progress — at 1500B frames the RoCE payload inside a 400G link tops out near ~47.5 GB/s before any CC/contention, so "95% wire" ≠ 95% application ([./33-collective-communication.md](./33-collective-communication.md)).
5. Recover payload share with jumbo frames or IB MTU 4096 (header overhead drops from ~3.9% to ~1.4%/~0.6%); sanity-check every benchmark against the serialization floor (100 MB @ 50 GB/s = 2.0 ms) ([./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Related
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — bisection/leaves/spines arithmetic.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — multi-plane aggregates.
- [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) — PCIe-vs-fabric ceiling.
- [33-collective-communication.md](./33-collective-communication.md) — where the collective-volume formulas come from.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — measuring whether the math holds.

## References
- All [E]: section constants bank (computed 2026-08-25) — PCIe 5.0 x16 63 GB/s; 400/800/1600
  Gb/s → 50/100/200 GB/s; NDR400 50 GB/s; 8x400G/8x800G node inject; 32…32768-GPU
  bisection rows; 1024-GPU rail 8-plane; AllReduce/AllGather/busbw/serialization rows;
  RoCEv2 hdr 58 B / IB hdr 24 B overheads; 400GbE PPS @1518B/9018B.
- `[F: vendor spec]` ConnectX-8 PCIe Gen6 x16 (800G NIC).
