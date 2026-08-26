# Physical Layer: Copper, Fiber, Optics, FEC and the Marginal-Link Chain
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: IEEE 802.3df/802.3dj context, IBTA/PHY, NVIDIA DGX SuperPOD widths-rates, NVIDIA mlx5 counters, section constants bank; fetched 2026-08-25.

## 30-Second Explanation
Beneath the RDMA transport, the AI fabric is a **PAM4 electrical/optical layer** whose
levers are reach, line rate, and bit-error rate. Every choice is a trade:
**DAC copper** is cheap but only covers <2–3 m [I]; **MMF (SR)** reaches ~100 m [F: 802.3];
**SMF (DR/FR)** reaches 500 m–2 km [F: 802.3]. At 100G/lane and above the signaling is
PAM4 with RS-FEC, and the numbers are humbling: a link runs at **pre-FEC BER ~1e-4 and
relies on FEC to hand the transport a post-FEC BER <1e-15** [A: typical]. A slightly
marginal fiber doesn't drop packets outright — it raises FEC corrected counts, then FEC
retries/LLR retransmits, then tail latency, then turns one collective into a straggler
and slows the *whole job*. This page covers the media, the rates, FEC, optical
budgets/transceiver telemetry (DOM), and the repair ladder (reseat → re-terminate →
replace).

## What — the media options, reach by reach
| Media | Form | Reach | Rate class | Notes |
|---|---|---|---|---|
| **DAC (copper)** | direct-attach copper cable | **<2–3 m** [I] | 400G/800G | cheapest, lowest power, no optics; rail-in-rack only |
| **AOC** | active optical cable | up to ~30–100 m | 400G/800G | optics built into cable ends; plug-and-play |
| **MMF (SR)** | multimode, SR4/SR8 | **~100 m @ 400G** [F: 802.3] | 400G | OM4/OM5; short leaf-to-leaf |
| **SMF (DR/FR)** | single-mode, DR4/FR8/2FR | **500 m – 2 km** [F: 802.3] | 400G+ | the spine/rail-workhorse; DR ~500 m, FR ~2 km |
| **Coherent (ZR)** | DWDM/coherent | 40–120 km | 400G-1.6T | DCI only, out of rack scope |
Rule of thumb: **under ~3 m use copper DAC; under ~100 m use MMF/AOC; anything farther is
single-mode SMF.** [I] For a rail-optimized fabric, most leaf↔spine and leaf↔NIC runs are
short and often DAC; the long leaf↔spine/rail-tie runs are SMF.

## Why — PAM4 and FEC are doing silent work at every rate
Modern high-rate signaling is **PAM4** (4 amplitude levels = 2 bits per symbol), which
doubles bits per symbol but tightens the eye and worsens BER. To survive, links run
**RS-FEC (Reed–Solomon Forward Error Correction)**: Ethernet 100G/lane uses
**256b/257b line coding + RS(544,514) FEC** [F: 802.3dj context]; IB HDR/NDR/XDR use
**PAM4 + 256b/257b + RS-FEC** [F: IBTA roadmap + bank note]. The FEC corrects bit
errors **in silicon, transparently** — which is exactly why a decaying link's first
symptom is a rising `fec_corrected` counter, not a drop.

## How — the BER ladder and what FEC buys you
```text
 raw link (pre-FEC) BER ≈ 1e-4      PAM4 eye is noisy
            │  RS(544,514) corrects burst errors in silicon
            ▼
         post-FEC BER < 1e-15       what the transport actually sees  [A: typical]
            │
 IB link spec target ≈ 1e-12; NVIDIA-qualified components ≈ 1e-15  [F: NVIDIA DGX SuperPOD]
            ▼
         transport: RoCE Go-Back-N / IB credit flow — effectively lossless
```
[A: typical] framing: 100G/lane PAM4 links are specified around a pre-FEC BER ~1e-4 and
the FEC is sized so the **post-FEC** error rate meets the transport's ~1e-12…1e-15
target. The practical consequence: **FEC corrected is a leading indicator** — it starts
climbing long before the link is uncorrectable, so you can re-terminate/replace *before*
your job absorbs a straggler.

## When — pick the rate and form factor
| Rate | Per-lane | Lines/encoding | Form factors |
|---|---|---|---|
| 100G | 25G/lane (older) | 64b/66b, NRZ | QSFP28 |
| 400G | 100G/lane × 4 or 4×100G | PAM4 + RS-FEC | QSFP-DD, OSFP |
| 800G | 4×200G or 8×100G | PAM4 (802.3dj) | OSFP, QSFP-DD |
| 1.6T | 8×200G | PAM4 (802.3dj) | OSFP |
[F: 802.3df/802.3dj context] **OSFP vs QSFP-DD:** both hold 8 electrical lanes. On OSFP the
8 lanes carry **2 independent 4-lane ports** — for InfiniBand, **one OSFP = 2× NDR400
ports** (NDR400 = 4 lanes × 100 Gb/s, `[F: vendor spec]`; per-port BW = 50 GB/s
`[E: NDR400 per port row]`); Quantum-2's "64 NDR ports over 32 OSFP" is exactly this.
QSFP-DD is the Ethernet MSA twin. So a 400G NIC takes one 4-lane sub-port of an OSFP, and
an OSFP cage can host two 400G links. [F: NVIDIA Quantum-2 hardware docs]

## How — signaling generations, 25G/lane to 200G/lane
The PHY has climbed from NRZ to PAM4, each step trading eye-height for rate:
```text
 25G era (NRZ, 25G/lane)        100G/lane PAM4               200G/lane PAM4 (802.3dj)
 1 bit/symbol, clean eye   ──►   2 bits/symbol, tight eye ──►  2 bits/symbol, noisier
 no RS-FEC needed                RS(544,514) FEC              RS(544,514) FEC, tighter budget
 100G = 4×25G                    100G = 1×100G, 400G=4×100G   800G=4×200G, 1.6T=8×200G
```
The [F: 802.3dj context] point: **100G/lane is the modern unit** — 400G is 4 lanes,
800G is 4×200G or 8×100G, 1.6T is 8×200G. PAM4's higher BER is why FEC is mandatory from
100G/lane up, and why the "corrected/uncorrected" counters exist at all.

## How much margin does an optical link actually have? — a worked budget
A link's health is its **power margin**: TX launch power minus insertion loss, against
the RX sensitivity.
```text
 TX launch (module spec)      e.g. -2.0 dBm       [F: module datasheet]
 connector + fiber loss       e.g. -3.5 dBm
 ─────────────────────────────
 RX received power            ≈ -5.5 dBm
 RX sensitivity (spec)        e.g. -8.0 dBm       [F: module datasheet]
 ─────────────────────────────
 margin                       2.5 dB    ← positive = healthy; near 0 = fragile
```
If DOM measures RX power drifting a few tenths of a dB down per quarter toward
sensitivity, the margin is eroding — the ASE/loss mechanism can be a dirty connector or
aging transmitter. **Re-seat and clean, then re-measure**; if the margin doesn't return,
re-terminate or replace before it flips `fec_corrected` into `fec_uncorrected`. [I]

## Hardware impact
Power and lane math [E from bank]: `[E] 400 Gb/s = 50 GB/s`, `[E] 800 Gb/s = 100 GB/s`,
`[E] 1600 Gb/s = 200 GB/s`. Each PAM4 lane is 100 Gb/s at the 400G/800G tier; a switch
radix like 64×800G = 64 ports × 100 GB/s = 6.4 TB/s of line rate
([E] 800 Gb/s = 100 GB/s). NICs must feed that from PCIe ([37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md)):
an 800G NIC wants PCIe Gen6 x16 (`[F: vendor spec]` ConnectX-8). On the cable side,
copper DAC saves transceiver power/cost but caps reach, which is why NVLink-scale rack
buses go copper while leaf↔spine goes SMF. [I]

## Inference impact
Physical-layer health is **latency health**: a marginal link means FEC corrections and
occasional retransmits that add µs-to-ms *on top of* a normal RTT — invisible to a
throughput test, brutal to a P99 decode step. Because an inference deployment usually has
slack per token, the first sign of a bad link may be a **slow token**, not a failure.
[I] Watch `fec_corrected` and D OM temperature drift as a pre-emptive signal.

## How to measure it — transceiver telemetry (DOM)
Modern optical transceivers expose **Digital Optical Monitoring (DOM)**: temperature,
laser bias / optical TX/RX power, and (on coherent) chromatic dispersion / CCD. Budge the
marginal-link theory into data:
- `ethtool -m eth3` (DOM) — per-lane RX power, temp; RX power drifting toward the floor
  is the classic aging-fiber warning.
- `ethtool --show-fec` / link stats — `fec_corrected` / `fec_uncorrected`.
- `perfquery`/`ibqueryerrors` (IB), `ethtool -S` (RoCE) — `symbol_error`, `link_downed`
  [F: NVIDIA mlx5 counters].
- Optical budget: compare measured RX power against the module's declared **sensitivity
  and overload** and the link's **power budget** (TX power − insertion loss − margin).
  If RX power is near sensitivity, the link has no margin — reseat/re-terminate now. [I]

## The causal chain — why one bad fiber slows the whole job
```text
 marginal fiber/connector
   → BER up (pre-FEC ~1e-4 worsens)
   → fec_corrected rises; occasional fec_uncorrected
   → FEC retries / LLR retransmits (a corrected frame is re-sent by transport)
   → packet_seq_err / out_of_sequence on that rail's NICs
   → that rail's AllReduce slice becomes a straggler
   → collective waits on the slowest rail
   → whole-job step time / JCT rises, for every GPU, from one cable
```
This is why physical-layer telemetry is a *top* AI-network priority: the failure is
**non-local** (one cable degrades every GPU's step). [I] → the trees in
[45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md).

## Failure modes — and the repair ladder
- **`fec_corrected` rising, links "up":** marginal but serviceable. **Repair ladder:
  (1) reseat** both ends (dirty/loose connector is the #1 cause), (2) **clean/re-terminate** the
  fiber end-face or connector, (3) **replace** the patch panel / cable / module.
- **`fec_uncorrected` / drops / `symbol_error` climbing:** past the FEC's correction window —
  **replace**, don't reseat-and-hope; the job is already paying in retransmits. [I]
- **RX power near sensitivity (DOM):** optics aging / high insertion loss — clean and
  replace the module, verify with a meter.
- **BER between 1e-4-pre-FEC and post-FEC target** is *normal*; only the *slope* of
  `fec_corrected` and the appearance of `uncorrected` mean trouble. [A]
- **Wrong reach/rate for the run:** DAC pushed past 3 m, or SMF optics on a too-long run,
  will live on FEC corrections forever. Re-pick the media to the reach and lane count
  (an 800G link that's really 400G-capable runs at half rate — check `link_down` rate
  negotiation). [I]

## Example — a hand-calculable case
A 400G SMF DR link should carry `[E] 50 GB/s` of payload. A marginal connector pushes
pre-FEC BER from 1e-4 to ~1e-3; RS(544,514) still corrects it, but `fec_corrected` climbs
from a low baseline to millions/sec ([E]: ~78M codewords/s at 400G × ~0.4–0.99 fraction
correction-required at BER 1e-4→1e-3). The transport now occasionally exceeds the FEC's
correction capability → retransmits on that rail. If that rail carries 1/8 of every node's
AllReduce (8-rail, [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md)), that ONE rail's added latency
becomes the **AllReduce critical path** for the entire job. Re-seating the connector
returns `fec_corrected` to ~0 and JCT to normal — measurable in `nccl-tests` busbw
before and after. [I: mechanism; [E]: 400G=50 GB/s]

## Key Takeaways
1. Media by reach: copper DAC <2–3 m, MMF (OM4/5) ~100 m, single-mode DR/FR 500 m–2 km — pick to the run or the link lives on FEC corrections forever ([../Hardware/README.md](../Hardware/README.md)).
2. 100G/lane is the modern unit (PAM4 + RS(544,514) FEC); PAM4's tighter eye is why FEC is mandatory from 100G/lane up and why corrected/uncorrected counters exist at all ([./40-network-telemetry.md](./40-network-telemetry.md)).
3. A link runs at pre-FEC BER ~1e-4 and only reaches <1e-15 post-FEC, so `fec_corrected` is the leading indicator that climbs long before a link becomes uncorrectable.
4. One marginal fiber raises FEC retries → retransmits on one rail → that rail's AllReduce slice becomes a straggler → step time rises for the *whole job*; PHY failure is non-local ([./38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md), [./45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md)).
5. Use DOM (`ethtool -m`) to track RX power vs module sensitivity — positive margin = healthy, near-zero = fragile; follow reseat → clean/re-terminate → replace before `fec_uncorrected` flips; rate↔GB/s arithmetic in [./43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md).

## Related
- [40-network-telemetry.md](./40-network-telemetry.md) — the FEC/link-error counters to watch.
- [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md) — line-rate ↔ GB/s and PPS ceilings.
- [37-nic-hca-supernic-dpu.md](./37-nic-hca-supernic-dpu.md) — PCIe-vs-fabric rates that the PHY must feed.
- [45-troubleshooting-rdma-infiniband.md](./45-troubleshooting-rdma-infiniband.md) / [46-troubleshooting-roce-nccl.md](./46-troubleshooting-roce-nccl.md) — the
  trees this page feeds.
- [README.md](../Hardware/README.md) — hardware cross-section (cabling/connectors).

## References
- [F] IEEE 802.3df (400G/800G, PAM4/RS-FEC) and 802.3dj (200G/lane) context; IBTA roadmap
  (PAM4 + 256b/257b + RS-FEC) — via section research notes.
- [F] NVIDIA Quantum-2 hardware docs (OSFP = 2 NDR ports); DGX SuperPOD
  widths-rates/reach; mlx5 counter articles.
- [A] pre-FEC ~1e-4 → post-FEC <1e-15 framing; DOM/repair-ladder guidance.
- [E] Rate↔GB/s rows (400G=50, 800G=100, 1600G=200 GB/s) and NDR400-per-port=50 GB/s,
  from the section constants bank, computed 2026-08-25.
