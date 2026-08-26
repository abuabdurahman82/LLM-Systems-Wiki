# Clos / Fat-Tree Design Mathematics
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
All switch/port arithmetic below computed 2026-08-25 (section constants bank). Convention: GB = 10^9 bytes; Gb/s = bits (÷8 to get GB/s).

## 30-Second Explanation
A **Clos / fat-tree** fabric is a multistage interconnect where *no single link is ever the
only path between two endpoints*: endpoints attach to leaves, leaves uplink to spines, and
the spine layer has enough uplink capacity that any leaf-to-leaf transfer can use multiple
spines at once (non-blocking). The design questions are all arithmetic: given N GPUs,
NICs-per-GPU, per-NIC bandwidth, and switch radix, how many leaves, how many spines,
what bisection bandwidth, and what oversubscription do you get? This page gives the
formulas and five worked examples (32 → 32,768 GPUs). The headline results [E]:
a non-blocking 1:1 fabric for 1,024 GPUs at 400G/NIC needs **32 leaves + 32 spines
(radix 8)** and delivers **6.4 TB/s bisection**; 8,192 GPUs needs 256 leaves + 256 spines
(51.2 TB/s bisection); rail-optimization (8 NICs per node, 8 independent planes) scales
linearly in plane count, not in a single monster fabric.

## The three numbers that matter
```text
endpoints E      = N_nodes × NICs_per_node
leaf downlinks   = D (ports facing hosts)
leaf uplinks     = U (ports facing spines)
spine downlinks  = S_count (one per leaf, in simple 2-tier)
spine uplinks    = 0 (spines are the top layer in a 2-tier Clos)

inject bandwidth (total host-side injection) = E × BW_nic
bisection bandwidth (leaf↔leaf capacity)     = min over any cut; for symmetric 2-tier:
                                              = S × U × BW_uplink   (all spine uplinks
                                              that carry east-west traffic)
blocking/oversub = inject / bisection        (1.0 = 1:1 non-blocking)
```
The design rule: **bisection ≥ inject** (oversub = 1.0) when every pair of endpoints may
beat each other at full line rate — which is exactly the AI training condition
([01-why-ai-networking-is-different.md](./01-why-ai-networking-is-different.md)). [I: standard]

## The formulas
For a 2-tier leaf-spine Clos (the 99% case at ≤32k GPUs):

```text
leaves L  = ceil( E / D )                        # D downlinks per leaf
spines S  = ceil( L × U / U_s )                  # U_s = downlinks per spine; in
                                                 # symmetric Clos U_s = U, so S = L
oversub   = ( E × BW_nic ) / ( S × U × BW_up )
bisection = S × U × BW_up
```
In the common **balanced radix-R** switch (D = U = R/2) with `S = L` (symmetric, 1:1):

```text
L = S = ceil( 2E / R )
bisection = L × (R/2) × BW_up
inject    = E × BW_nic        (with BW_up = BW_nic: oversub = E / (L·R/2) = E·2/(L·R))
```
**Key property [E, derived]:** with `S = L` and `D = U`, the fabric is exactly 1:1:
oversub = `E × 2 / (L × R)` and `L = 2E/R` → oversub = 1.0 by construction. Any fewer
spines than L is deliberate oversubscription: e.g. S = L/2 → 2:1 [E: constants bank,
"1024 GPU 1:2 oversub (16 spines)" row: inject 6.4 TB/s vs bisection 3.2 TB/s].

## Radix: the hidden cost
`R` (radix) is the switch port count. Real numbers [F: vendor spec — check per generation]:
radix 8, 16, 32, 64 (400G generation), 128 (800G generation). Higher radix:
- fewer leaves and spines for the same E (S = 2E/R),
- **lower cost per endpoint** (fewer switch dollars),
- but: **lower resilience per plane** (one leaf loss removes more hosts; one spine loss
  removes more uplinks) and *harder to buy small* (a radix-64 switch with 8 hosts on it
  is 88% wasted ports).
AI fabrics therefore run **high-radix spine + medium-radix leaf** at scale, and accept
port waste at the edges in exchange for 1:1 bisection. [I: standard]

## Worked examples [E — all from the constants bank]
| Cluster | Nodes (8-GPU, 1×400G each) | E | Radix | Leaves | Spines | Inject | Bisection | Oversub |
|---|---|---|---|---|---|---|---|---|
| **32 GPUs** | 4 | 4 | 8 | 1 | 1 | 0.20 TB/s | 0.20 TB/s | 1.000 |
| **128 GPUs** | 16 | 16 | 8 | 4 | 4 | 0.80 TB/s | 0.80 TB/s | 1.000 |
| **1,024 GPUs** | 128 | 128 | 8 | 32 | 32 | 6.40 TB/s | 6.40 TB/s | 1.000 |
| **8,192 GPUs** | 1,024 | 1,024 | 8 | 256 | 256 | 51.2 TB/s | 51.2 TB/s | 1.000 |
| **32,768 GPUs** | 4,096 | 4,096 | 8 | 1,024 | 1,024 | 204.8 TB/s | 204.8 TB/s | 1.000 |

Derivations (n = nodes, R = 8 → D = U = 4):
- 32 GPU: E=4, L = ceil(2·4/8) = 1 leaf… note: with 1 leaf and 1 spine the "fabric"
  degenerates to a single switch (E ≤ D). True 2-tier starts at E > D. L = 1, S = 1,
  bisection = 1×4×50 GB/s = 200 GB/s = inject. ✓ [E]
- 128 GPU: E=16, D=U=4 → L = ceil(16/4) = 4 leaves; S = ceil(4×4/4) = 4 spines;
  bisection = 4 × 4 × 50 GB/s = 800 GB/s = 0.8 TB/s = inject. ✓ [E]
- 1,024 GPU: E=128, L = 32, S = 32, bisection = 32×4×50 GB/s = 6.4 TB/s. ✓
- 8,192 / 32,768: linear scaling. ✓

**32,768 GPUs at radix 8 needs 1,024 spines** — at this point the spine layer's own
crossbar becomes the constraint and real designs either (a) move to radix 128+ (fewer,
bigger spines: S = 2·4096/128 = 64 spines) or (b) adopt a **3-tier Clos / multi-plane
architecture** (the NVL72-era pattern: many 8-GPU-rail planes, each a small leaf-spine,
interconnected only at the very top for inter-plane traffic). →
[38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md), [52-reference-architectures.md](./52-reference-architectures.md). [I: standard]

## Why oversubscription is (almost) never acceptable in the GPU backend
In a web DC, 4:1 or 10:1 oversubscription is fine: most flows are short-lived,
asynchronous, and not synchronized — the cut is rarely saturated. In an AI training
job, every collective is **synchronized incast** toward the bisection at the same
instant; a 2:1 cut means every step pays a ~2× queueing factor on the spine layer, and
*tail latency scales with oversubscription* [I: standard, supported by incast literature].
So GPU backend fabrics target **1:1 (zero) oversubscription at the bisection**, and buy
themself back by spending more spines — that is precisely what the table above does.
Storage and management fabrics, by contrast, tolerate 4:1–10:1 (asynchronous I/O).
→ [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md) (fabric roles). [I: standard]

## Multi-rail math: the AI shortcut
Instead of one fabric with E endpoints, build **K = NICs-per-node independent fabrics**
("rails" or "planes"), each with E/K endpoints, and let NCCL stripe across them. Each
plane is a smaller Clos (radix 8, S = L), and total bisection = K × per-plane bisection
[E: constants bank "1024 GPU rail-opt 8×400G": E_plane=128, L=S=32 per plane, inject
= bisection = 51.2/8 = 6.4 TB/s per plane × 8 planes = 51.2 TB/s total]. The math is
identical to a single big fabric, but: (a) switches are smaller and commodity, (b) one
plane failure degrades by 1/K instead of taking the bisection down, (c) NCCL's multi-rail
striping uses the K paths in parallel for one collective. → [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
[E, derived]

## Bisection bandwidth — the definition, precisely
Bisection = minimum total link capacity across **any** cut that partitions the fabric
into two equal halves. For a 2-tier symmetric Clos the binding cut is the spine layer:
bisection = S × U × BW_up [E: derivation above]. Do NOT confuse with "aggregate switch
port capacity" (S×R×BW) — that counts the downlinks too, which a leaf-to-leaf bisection
cut does not cross. [I: standard definition]

## When Clos is *not* the right shape
- **≤ 1–2 racks**: direct-connect (fat switch or switchless all-to-all over NVLink/PCIe)
  beats any Clos; the fabric is the NVL domain ([02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md)).
- **> 32k GPUs single-plane**: spine count explodes → 3-tier or Dragonfly+ /
  rail-plane interconnects ([12-infiniband-routing-topology-partitions.md](./12-infiniband-routing-topology-partitions.md) covers
  Dragonfly; [52-reference-architectures.md](./52-reference-architectures.md) the 1,024-GPU four-option comparison).
- **HPC with extreme scale + IB**: the rail-optimized + multi-plane IB pattern is a
  Clos *per rail*, not one Clos.

## Tuning / design checklist
1. Fix the **workload's bisection demand** first: worst-case collective wire traffic /
   step time (from [33-collective-communication.md](./33-collective-communication.md) formulas) — the fabric must
   exceed it with headroom for incast. [I: standard]
2. Pick radix from switch generation (cost/availability), not from theory.
3. Compute L, S, oversub with the formulas above; **if oversub > 1.0, add spines before
   you add anything else** — spines are the bisection. [E]
4. Plan the **failure case**: one spine down → bisection = (S−1)×U×BW; one leaf down →
   its hosts are out (no partial loss in a 2-tier). [I: standard]
5. Separate the **front-end and storage fabrics** from the backend and give them their
   own (oversubscribed) Clos. [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md).

## Troubleshooting (design-level symptoms)
- **Measured bisection ≫ inject but P99 still bad** → the cut is fine; look at ECMP
  imbalance / incast at the leaves ([22-roce-cc-and-load-balancing.md](./22-roce-cc-and-load-balancing.md),
  [39-buffer-architecture.md](./39-buffer-architecture.md)), not at capacity.
- **One leaf "cold" in every test** → check that leaf's uplinks all up + same-speed
  ([45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)).
- **Spine-layer PFC storms at every collective start** → incast at spine downlinks;
  buffer sizing or CC tuning problem, not a Clos-shape problem. → [39-buffer-architecture.md](./39-buffer-architecture.md).

## Lab
Lab 21-style exercise (in [53-learning-labs.md](./53-learning-labs.md)): with a 16-port simulated leaf-spine
(4 up / 4 down × N), verify: (a) oversub = 1.0 when S = L; (b) forcing S = L/2 gives
measured ~0.5× cross-fabric throughput at full simultaneous load; (c) one spine down
degrades bisection to (S−1)/S. Compare measured against the formulas above. [E: expected
from derivation]

## Key Takeaways
1. The Clos is arithmetic: `L = S = ceil(2E/R)` for a symmetric 1:1 2-tier fabric. Applied numbers in [./43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md).
2. Bisection = `S × U × BW_up`; oversub = inject/bisection; GPU backends want 1.0. Why oversub harms synchronized collectives: [./39-buffer-architecture.md](./39-buffer-architecture.md).
3. Radix is the cost knob: bigger radix = fewer spines = cheaper, less resilient. Real radix choices in [./52-reference-architectures.md](./52-reference-architectures.md).
4. Multi-rail = K independent small Clos fabrics; total bisection scales with K. The multi-plane pattern: [./38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
5. Design the *failure case* (spine loss, leaf loss) with the same formulas. Symptom→cause mapping in [./45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md).

## Related
- [02-ai-networking-taxonomy.md](./02-ai-networking-taxonomy.md) — which network is which.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — the multi-rail pattern in detail.
- [52-reference-architectures.md](./52-reference-architectures.md) — 32/256/1,024-GPU designs applying these numbers.
- [./43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md) — the bandwidth formulas these examples use.
- [03-gpu-network-architecture.md](../GPU-Communication/03-gpu-network-architecture.md) — the physical topology ladder.

## References
- Classic Clos (C. D. Clos, 1953) and fat-tree (Al-Fares, Loukissas & Vahdat, "A
  Scalable, Commodity Data Center Network Architecture", SIGCOMM 2010) [F: cited by
  name/venue — verify the exact paper id before formal citation].
- [E] all switch/port numbers from the section constants bank (computed 2026-08-25).
- Radix values: vendor switch datasheets (radix is [F: vendor spec] per generation).
