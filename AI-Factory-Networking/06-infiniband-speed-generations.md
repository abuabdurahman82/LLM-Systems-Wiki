# InfiniBand Speed Generations
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IBTA roadmap + InfiniBand Wikipedia table (cites IBTA/NVIDIA), IBTA XDR press release (R1.7, Oct 2023), NVIDIA Quantum/ConnectX docs; [E] figures quoted verbatim from section constants bank (2026-08-25).

## 30-Second Explanation
InfiniBand generations are defined by **per-lane signaling rate × line code (encoding)
× lane count**. Each "generation" doubles the *effective* per-lane rate and names a
port speed as lanes × per-lane: SDR 2 Gb/s/lane → DDR 4 → QDR 8 → FDR10 10 → FDR 13.64
→ EDR 25 → HDR 50 → NDR 100 → XDR 200. Ports are typically **4x** (four lanes):
**NDR400 = 4 × 100 Gb/s = 400 Gb/s**, **XDR800 = 4 × 200 Gb/s = 800 Gb/s**. The line
codes are **8b/10b** (SDR/DDR/QDR), **64b/66b** (FDR10/FDR/EDR), and **PAM4 +
256b/257b + Reed-Solomon FEC** (HDR/NDR/XDR) — **not** 128b/132b, which is an Ethernet
code. Connectors: QSFP then **OSFP** (8 electrical lanes = **2 ports per cage**, e.g.
2× NDR400 or 2× XDR800). [F: IBTA roadmap; [E] for the arithmetic]

## What
The speed ladder, with IBTA effective per-lane rates and the derived 4x/8x port rates
([E] figures from the constants bank; signaling + line code [F: IBTA/Wikipedia]):

| Gen | Year | Line code | Signaling /lane | Effective /lane | 4x port (line → nominal) | 8x port |
|---|---|---|---|---|---|---|
| **SDR** | 2001/03 | 8b/10b | 2.5 Gb/s | 2 Gb/s | 10 → **8 Gb/s** (1.0 GB/s) | 16 |
| **DDR** | 2005 | 8b/10b | 5.0 Gb/s | 4 Gb/s | 20 → **16 Gb/s** (2.0 GB/s) | 32 |
| **QDR** | 2007 | 8b/10b | 10.0 Gb/s | 8 Gb/s | 40 → **32 Gb/s** (4.0 GB/s) | 64 |
| **FDR10** | 2011 | 64b/66b | 10.3125 Gb/s | 10 Gb/s | 41.25 → **40 Gb/s** (5.0 GB/s) | 80 |
| **FDR** | 2011 | 64b/66b | 14.0625 Gb/s | 13.64 Gb/s | 56.25 → **55 Gb/s** (6.8 GB/s) | 109 |
| **EDR** | 2014 | 64b/66b | 25.78125 Gb/s | 25 Gb/s | 103.1 → **100 Gb/s** (12.5 GB/s) | 200 |
| **HDR** | 2018 | PAM4 256b/257b+RS-FEC | 53.125 Gb/s | 50 Gb/s | HDR200 = **200 Gb/s** (25.0 GB/s) | HDR400 |
| **NDR** | 2021/22 | PAM4 256b/257b+RS-FEC | 106.25 Gb/s | 100 Gb/s | **NDR400 = 400 Gb/s** (50.0 GB/s) | NDR800 |
| **XDR** | 2023/24 | PAM4 (224G SerDes) | 212.5 Gb/s | 200 Gb/s | **XDR800 = 800 Gb/s** (100.0 GB/s) | XDR1600 |
| GDR | future | (TBA) | ~425 | ~400 | 1600 | 3200 |

All port nominal figures are **[E]** derived this session as `effective-per-lane ×
lanes` [E: constants bank rows]. The **"line → nominal"** column shows that marketing
names (400/800 Gb/s) are the **effective** bit rate after encoding, not the raw signal
rate. The **8x** ports exist mainly as HDR400/NDR800/XDR1600 switch sides; the AI
server port you care about is the 4x (NDR400, XDR800).

### Roadmap and production status
The table mixes **shipping** and **announced** generations — keep them distinct [F:
IBTA roadmap + press; [A] for announced]:

| Gen | Status (as of 2026-08-25) |
|---|---|
| SDR–FDR | historical / legacy, mostly decommissioned |
| EDR | installed base, legacy HPC/AI |
| HDR / HDR200 | production but being superseded |
| NDR / NDR400 | **current production** (Quantum-2, ConnectX-7/8) |
| XDR / XDR800 | **announced GTC Mar 2024; shipping/ramping 2024–2026** — production parts exist (ConnectX-8 mass-prod, XDR switches P-Rel) but treat the ecosystem as ramping [F: NVIDIA XDR clusters doc] |
| GDR | **roadmap only** — no shipping parts; framing numbers (~425/400 Gb/s-lane) are IBTA-forward, not independent fact |

Never present GDR (or any roadmap rate) as available; it is not [I].

## Why
The IOPS/bandwidth race in AI is driven by **gradient-sync bandwidth per port** (page
[33-collective-communication.md](./33-collective-communication.md)) and by **per-port economics** — an NDR400 port at
50 GB/s costs far less per bit than the older stack. Each generation's purpose:
- **Denser per-port bandwidth** so an HGX-class server injects a full rail without
  multiplying NICs: 8 × NDR400 = 3.2 Tb/s (400 GB/s), 8 × XDR800 = 6.4 Tb/s (800 GB/s)
  [E: bank node-inject rows].
- **More bits per electrical lane** via better line codes (8b/10b → 64b/66b removes 20%
  vs 3% encoding overhead) and **PAM4 + RS-FEC** to push 100/200 Gb/s down a lane at
  1e-12-ish BER [F: widths-rates BER note].
- Smith economics: NDR400 (50 GB/s) and XDR800 (100 GB/s) fit the AI port math the
  collective workloads need (page [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md)).

## How — encoding math
The effective rate = signaling rate × **code efficiency** × (RS-FEC overhead factor):
- **8b/10b**: 10 bits on the wire carry 8 data bits → efficiency 0.8. E.g. SDR:
  2.5 × 0.8 = **2 Gb/s** [E: 2.5*0.8000=2.0].
- **64b/66b**: 66 bits carry 64 → efficiency 0.9697. E.g. FDR10: 10.3125 × 0.9697 =
  **10 Gb/s**; FDR: 14.0625 × 0.9697 = **13.64 Gb/s**; EDR: 25.78125 × 0.9697 =
  **25 Gb/s** [E: bank rows].
- **PAM4 + 256b/257b + RS-FEC**: the 257-wide block plus Reed-Solomon FEC parity gives
  an effective factor ≈ 0.9412. E.g. HDR: 53.125 × 0.9412 = **50 Gb/s**; NDR:
  106.25 × 0.9412 = **100 Gb/s**; XDR: 212.5 × 0.9412 = **200 Gb/s** [E: bank rows].
```text
line code  →  bits of payload per wire symbol
8b/10b     →  0.800  (SDR/DDR/QDR)
64b/66b    →  0.9697 (FDR10/FDR/EDR)
PAM4+RS    →  0.9412 (HDR/NDR/XDR)   (Implied 256b/257b ≈ 0.9961 × user data, RS-FEC the rest)
```
**Warning (common error):** `128b/132b` (efficiency ~0.9697) is an **Ethernet** line code
(10GBASE-T, 25G/40G 802.3); 100G Ethernet moves to 64b/66b, and 200G/400G+ to
256b/257b — and **InfiniBand does NOT use 128b/132b** at any generation. IB's codes are
exactly the three above [F: IBTA — "128b/132b is an Ethernet line code and is
NOT an IB encoding"].

Port = lanes × effective-per-lane:
```text
NDR400  = 4 lanes × 100 Gb/s = 400 Gb/s = 50.0 GB/s   [E: 400/8]
XDR800  = 4 lanes × 200 Gb/s = 800 Gb/s = 100.0 GB/s  [E: 800/8]
```
And node injection with ×8 ports [E: bank]:
```text
8 × 400G = 3.2 Tb/s = 400 GB/s     8 × 800G = 6.4 Tb/s = 800 GB/s
```

### Worked per-lane examples (all [E] from the bank)
```text
QDR 4x:  10.0 Gb/s lane × 0.8000 (8b/10b) =  8 Gb/s eff. × 4 =  32 Gb/s port =  4.0 GB/s
EDR 4x:  25.78125 × 0.9697 (64b/66b)        = 25 Gb/s eff. × 4 = 100 Gb/s port = 12.5 GB/s
HDR 4x:  53.125  × 0.9412 (PAM4+RS)        = 50 Gb/s eff. × 4 = 200 Gb/s port = 25.0 GB/s
NDR 4x:  106.25  × 0.9412                  =100 Gb/s eff. × 4 =400 Gb/s port = 50.0 GB/s
XDR 4x:  212.5   × 0.9412                  =200 Gb/s eff. × 4 =800 Gb/s port =100.0 GB/s
```
The pattern is a clean **doubling**: 2 → 4 → 8 → 10 → 13.6 → 25 → 50 → 100 → 200
Gb/s effective per lane (FDR10/FDR slightly off the doubling, hence the non-power-of-2
port nominal of 40/55 Gb/s).

## When
- **EDR (100G)** — the 2016–2020 HPC/AI generation; still common as the low-cost
  baseline and in older clusters.
- **HDR (HDR200)** — 2018–2022 AI supercomputer standard (DGX A100/H100-era pods,
  Quantum switches, SHARPv2).
- **NDR (NDR400)** — the current AI production generation (DGX H100/B200 pods,
  Quantum-2, ConnectX-7/8); **large-announced ramped since 2022–2024**.
- **XDR (XDR800)** — the Blackwell-era 800G generation (Quantum-X800, ConnectX-8
  SuperNIC); **announced GTC Mar 2024, shipping/ramping 2024–2026**; distinguish
  **production vs announced** — ConnectX-8 is listed mass-production, XDR switches P-Rel
  (production release) in the XDR clusters doc, but much of the *ecosystem* guidance is
  forward-looking [F: NVIDIA XDR clusters doc / press release].
Choose a generation by: installed DGX/SuperPOD generation, required per-GPU busbw
(≈ 0.9–0.95 × port rate), cable/connector budget, and whether the fabric must do
adaptive routing / SHARP in-network (Quantum-family features tied to generation).

## Product mapping — Quantum switch generations [F: NVIDIA docs]
NVIDIA's **InfiniBand switch families** track the generations and are where the PHY
speed turns into a product you actually spec (vendor numbers below are `[F: vendor
spec]`, not independent):

| Generation / rate | Switch family (product) | Ports / form | Notes |
|---|---|---|---|
| HDR (200G) | **Quantum (Quantum-1)** | 40-port HDR, first SHARPv2 | GTC-era HDR; port count per-page [A, exact UNVERIFIED] |
| NDR (NDR400) | **Quantum-2** (QM9700/QM9790) | **64 NDR 400G ports over 32 OSFP**; 51.2 Tb/s bidir; QM9700 managed / QM9790 unmanaged; QM9701 DGX edition | 2×NDR400 per OSFP; SHARPv3, adaptive routing |
| XDR (XDR800) | **Quantum-X800** (Q3200-RA, Q3400-RA) | Q3200-RA: 36 XDR ports / 18 OSFP; Q3400-RA: **144 XDR 800G ports / 72 OSFP**; ~115 Tb/s class; SHARPv4, rail-optimized (-RA) | 2×XDR800 per OSFP; ~14.4 TFLOPS in-network compute ≈9×NDR (vendor claim) |

Key mappings to remember:
- **NDR400 ↔ Quantum-2 ↔ ConnectX-7/-8**: the current production fabric (DGX H100/B200
  SuperPODs).
- **XDR800 ↔ Quantum-X800 ↔ ConnectX-8 SuperNIC**: the Blackwell-era 800G fabric —
  **announced Mar 2024**, ramping 2024–2026 [F: NVIDIA press release + XDR clusters doc].
- **OSFP = 2 ports**: an OSFP module/cage carries **8 electrical lanes = two 4x ports**,
  so 32 OSFP = 64 NDR ports (Quantum-2) and 72 OSFP = 144 XDR ports (Q3400-RA).
- **`-RA` = rail-optimized**: leaf switches whose ports map onto one GPU-NIC rail each,
  for rail fabrics [F: NVIDIA -RA docs; [A] for Quantum-2 RA variants (UNVERIFIED)].
- Distinguish **Spectrum (Ethernet) SN5600/SN5400** from these — those are Ethernet
  switches, not Quantum IB parts [I: research notes clarification].

## Packet flow / lane framing
A generation's "symbol" stream is organized into **4 (or 8) lanes**, each a serial PAM4
(HDR+) or NRZ (SDR–EDR) link. The HCA strips lane framing and hands the link layer an
ordered byte stream; the packet (LRH/BTH/payload/ICRC — see [09-infiniband-packet-format.md](./09-infiniband-packet-format.md))
is striped across the lanes. FEC (RS-FEC on HDR/NDR/XDR) is computed per lane to correct
transient bit errors without retransmit, which is what keeps the port usable at 1e-12-ish
BER (NVIDIA-qualified components tested to 1e-15) [F: DGX SuperPOD widths-rates].

```text
one 4x port (e.g. NDR400)
  ┌─────┬─────┬─────┬─────┐
  │lane0│lane1│lane2│lane3│   each 106.25 Gb/s PAM4
  └──┬──┴──┬──┴──┬──┴──┬──┘   RS-FEC per lane
     └─────┴──┬──┴─────┘
              │  aggregate 400 Gb/s effective
              ▼
        OSFP cage (8 electrical lanes)
        = TWO such 4x ports per cage (2×NDR400 or 2×XDR800)
```

## GPU relationship
Each GPU-to-fabric path in a DGX-like server is one or two HCAs; the HCA's port
generation must match (or upshift on) the switch generation. Rail-optimized fabrics wire
**one switch per rail** so every HCA port (NDR400 or XDR800) gets a full-speed, non-
oversubscribed uplink (page [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)). Per-GPU **NCCL
AllReduce busbw** over a healthy NDR rail lands near **~45–47.5 GB/s** (0.9–0.95 × the
50 GB/s link; community figures, config-dependent — tag [I]/[F: vendor-ecosystem]) [F:
research-workloads §5]. The generation thus bounds the *per-rank bytes/sec* term in the
ring-AllReduce wall time (page [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) Example). [I]

## Design — the evolution diagram
```text
SDR ── DDR ── QDR ── FDR10 ── FDR ── EDR ── HDR200 ── NDR400 ── XDR800 ── GDR(→)
2001    2005   2007   2011    2011  2014   2018      2021/22   2023/24   future
 8b/10b               │64b/66b                             │PAM4+RS
 2→4→8 Gb/s/lane      │10→13.6→25 Gb/s/lane             50→100→200 Gb/s/lane
 8→16→32 Gb/s/port  40→55→100 Gb/s/port          200→400→800 Gb/s/port
```
Design choices that come with generation [I; F: NVIDIA docs]:
- **OSFP takes over from QSFP** at 800G-class: an **OSFP cage holds 8 electrical lanes =
  2 InfiniBand ports** → **Quantum-2 = 64 NDR ports over 32 OSFP**, **Quantum-X800
  Q3400 = 144 XDR ports over 72 OSFP** [F: NVIDIA Quantum-2 / Q3400 docs].
- **NDR400 = 4 × 100, NDR800 = 8 × 100; XDR800 = 4 × 200** per IBTA (NDR = 100 Gb/s/lane, XDR =
  200 Gb/s/lane — so there is no 4-lane "XDR400"); the XDR PHY uses **224G SerDes**
  (= ≈212.5 Gb/s signaling per lane after overhead) [F: NVIDIA "800G via 224G serdes"; [E]
  for the 4×200 reading]. (One third-party table listing "XDR = 100×8" is inconsistent
  with NVIDIA's 224G SerDes + 2-ports-per-OSFP layout and is **rejected** here; the
  4×200 reading is weighted [I]/UNVERIFIED.)

## Connectors & form factors
Each generation ties a signaling rate to a physical interface standard:

| Gen | Signal /lane | Connector generation | Ports per module | Notes |
|---|---|---|---|---|
| SDR–QDR | 2.5–10 Gb/s NRZ | CX4 / QSFP (4x) | 1 | copper DAC era |
| FDR–EDR | 14–26 Gb/s | QSFP / QSFP+ | 1 | 4x ports throughout |
| HDR200 | 50 Gb/s PAM4 | QSFP56 | 4×50G | HDR100 = 2-lane option |
| NDR400 | 100 Gb/s PAM4 | **OSFP** | **2 × 4x ports** | OSFP = 8 electrical lanes |
| XDR800 | 200 Gb/s PAM4 | OSFP | **2 × 4x ports** | same cage, 224G SerDes |

The OSFP form factor is the enabler of 800G-class density: it carries **8 electrical
lanes**, exactly two 4-lane InfiniBand ports, so a switch doesn't double its cage count
to double its port count [F: NVIDIA Quantum-2/Q3400 physically lay 2 ports per OSFP;
[I] for the "why" framing]. Cabling: **DAC/AOC** up to a few meters for
rack/adjacent-rack rails, **active optical** for longer leaf-to-spine/spine-to-spine
reaches (page [41-physical-layer.md](./41-physical-layer.md)).

## Tuning
- **Match lane speed and width on both ends of a link**; mixing generations (HDR200 vs
  NDR400 vs XDR800) needs explicit cabling/port config — **auto-negotiation across
  generations is limited** [F: DGX SuperPOD widths-rates].
- **Use 4x ports** for the per-port nominal; don't run 1x/2x on AI ports unless
  constrained.
- **Keep BER low** — high-BER links burn RS-FEC/retransmit budget and add jitter; watch
  `symbol_error`/`link_error_recovery` [F: mlx5 counters; widths-rates].
- **Kernel/driver support must match generation** (MLNX_OFED for HDR/NDR, DOCA-era
  drivers for XDR) — an OS/driver mismatch shows up as capped link rate.
- **Plan OSFP inventory as 2-port modules** — a 144-port Q3400 needs 72 OSFP
  transceivers/cages, and each transceiver serves two rails; treat the OSFP, not the
  port, as the physical line item in BOM/power planning. [I]

## Troubleshooting
- **Link reports a lower rate than expected** (e.g. NDR400 port links at 200G) → lane
  width or the peer port's generation mismatch; verify with `ibstat`/`ibstatus`
  "ActiveWidth"/"ActiveSpeed".
- **Rate cap at driver level** → stale OFED/driver; confirm the driver supports the HCA
  and switch generation.
- **OSFP cage with 1 of 2 ports dead** → remember one OSFP = two 4x ports; a bad lane or
  module affects one port while the sibling looks fine.
- **High BER / CRC errors despite "LinkUp"** → fiber/cable damage or dirty optics at
  PAM4 densities; retrain / replace the module, check per-port FEC-corrected-error
  counters.
- **Full-rate "works" but collectives are slow** → verify the port negotiated the *wide*
  (4x) — a half-width link (2x at half rate) looks fine in `ibstat` "ActiveWidth" but
  caps busbw at 50%; confirm both ends negotiated the same width/rate before blaming the
  workload [I].

## Comparison — IB generations vs Ethernet rates (context)
Ethernet's 100/200/400/800 GbE count *physical* lanes differently: 800GbE = 8×100G
(802.3df) or 4×200G (802.3dj) — same lane math family but the **line codes differ**
(64b/66b + RS, and 802.3 uses 128b/132b-style framing on some rates — **that's Ethernet,
not IB**) [F: 802.3df / 802.3dj; IBTA]. RoCEv2 rides Ethernet and thus inherits
Ethernet's per-lane economics (page [16-roce-fundamentals.md](./16-roce-fundamentals.md)); IB generations keep
their own roadmap (NDR per-lane 106.25/100, XDR 212.5/200 — no Ethernet counterpart at
those exact figures; NDR≈400GE-class, XDR≈800GE-class). The practical head-to-head for
AI is **NDR400 / XDR800 (IB)** vs **400/800GbE (RoCE)** — comparable bits, different
fabric internals (losslessness/SM/IP); pick by the whole-fabric argument, not by the
number (page [49-design-decision-tree.md](./49-design-decision-tree.md)).

### The one-table generations recap
| Gen | eff/lane [E] | 4x port [E] | GB/s [E] | Code [F] | Shows up in |
|---|---|---|---|---|---|
| SDR | 2 | 8 Gb/s | 1.0 | 8b/10b | 2001-era |
| DDR | 4 | 16 | 2.0 | 8b/10b | 2005-era |
| QDR | 8 | 32 | 4.0 | 8b/10b | 2007-era |
| FDR10 | 10 | 40 | 5.0 | 64b/66b | 2011 FDR transition |
| FDR | 13.64 | 55 | 6.8 | 64b/66b | 2011–2014 HPC |
| EDR | 25 | 100 | 12.5 | 64b/66b | 2014–2020 HPC/AI |
| HDR | 50 | 200 | 25.0 | PAM4+RS | 2018–2022 AI |
| NDR | 100 | 400 | 50.0 | PAM4+RS | 2022–2026 AI |
| XDR | 200 | 800 | 100.0 | PAM4+RS | Blackwell-era (ramping) |

## Lab
1. **Read a live port's negotiated rate.** `ibstat` / `ibv_devinfo` on a modern HCA
   prints `ActiveSpeed: 50 Gb/s` per lane etc. — confirm this equals the IBTA per-lane
   effective (50 for HDR, 100 for NDR, 200 for XDR) × link width. [I: tool behavior]
2. **Encoding check by hand.** Compute EDR port nominal: 25.78125 × 4 × 0.9697 =
   100.0 Gb/s ✓ (matches `100 Gb/s` in the table) [E: bank]. Repeat for NDR400:
   106.25 × 4 × 0.9412 = 400.0 Gb/s ✓ [E: bank].
3. **Node-injection math.** 8 × XDR800 = 8 × 100 GB/s = 800 GB/s = 6.4 Tb/s [E: bank];
   sanity-check against a B200 HGX-class 8×800G documented config.
4. **OSFP 2-ports.** Verify on Quantum-2 (`64 NDR ports / 32 OSFP`) that 64 = 32 × 2
   ports-per-cage [E: division] — internalize that one cage serves two rails.
5. **Mixed-generation fail.** Attempt an NDR400↔EDR link and observe the reduced or
   failed negotiation — demonstrating limited auto-negotiation across generations [I].

## Key Takeaways
1. A generation = **per-lane signaling rate × line code (encoding) × lane count**; each generation doubles the *effective* per-lane rate (SDR 2 → … → NDR 100 → XDR 200 Gb/s/lane).
2. Line codes are **8b/10b** (SDR/DDR/QDR), **64b/66b** (FDR10/FDR/EDR), and **PAM4 + 256b/257b + Reed-Solomon FEC** (HDR/NDR/XDR) — **not** 128b/132b, which is an Ethernet code.
3. Ports are typically **4x**: NDR400 = 4 × 100 = **400 Gb/s (50 GB/s)**; XDR800 = 4 × 200 = **800 Gb/s (100 GB/s)** — marketing names are the effective rate, not the raw signal rate.
4. **OSFP** carries 8 electrical lanes = **2 ports per cage** (Quantum-2 = 64 NDR ports/32 OSFP; Quantum-X800 Q3400 = 144 XDR ports/72 OSFP).
5. Distinguish **shipping vs announced**: NDR400 is current production (Quantum-2, ConnectX-7/8); XDR800 was announced GTC Mar 2024 and is ramping 2024–2026; **GDR is roadmap-only** — never present it as available.

## Related
- [05-infiniband-architecture](./05-infiniband-architecture.md) — where these PHY generations sit in the stack.
- [09-infiniband-packet-format](./09-infiniband-packet-format.md) — the framing/headers these speeds carry.
- [41-physical-layer](./41-physical-layer.md) — DAC/AOC/fiber, PAM4, FEC, connectors in depth.
- [38-rail-optimized-multi-plane](./38-rail-optimized-multi-plane.md) — how per-port generation drives rail design.
- [42-clos-fat-tree-math](./42-clos-fat-tree-math.md) — port rates in the fabric-math [E] examples.
- [55-cheat-sheet](./55-cheat-sheet.md) — the one-table recap.
- [GPU-Communication/README](../GPU-Communication/README.md) — software (NCCL) that consumes the port bandwidth.

## References
- IBTA, InfiniBand Roadmap & speed table [F: `infinibandta.org/infiniband-roadmap/`;
  Wikipedia "InfiniBand" citing IBTA/NVIDIA].
- IBTA XDR press release (Vol 1 R1.7, Oct 2023) [F].
- NVIDIA Quantum-2 (NDR400) / Quantum-X800 (XDR800) platform docs [F: vendor docs].
- NVIDIA DGX SuperPOD "widths & rates" (BER, lane config) [F].
- [E] all port-rate figures from the section constants bank (computed 2026-08-25).
