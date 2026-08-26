# NIC, HCA, SmartNIC, DPU and SuperNIC: The Endpoint Taxonomy
`LAST_UPDATED: 2026-08-26 · Status: core page · Claims tagged [F]/[A]/[I]/[E]/UNVERIFIED.`
Primary sources: NVIDIA networking docs (ConnectX/BlueField/Spectrum-X datasheets), AMD Pensando product pages, linux-rdma/perftest docs; fetched 2026-08-25.

## 30-Second Explanation
The device that terminates the backend fabric has five increasingly capable names —
**conventional NIC, RDMA (RoCE) NIC, HCA, SmartNIC, DPU, SuperNIC** — and the industry
uses them loosely. The useful axis is **what work the card does beyond moving bytes**:
a plain NIC moves packets with CPU involvement; an **RDMA NIC (RoCE NIC)** moves data
directly reactor-to-memory with no CPU on the data path and ships the RDMA engine; an
**HCA** is the InfiniBand name for the same thing with IB-native transport; a **SmartNIC**
adds a CPU/FPGA for offload; a **DPU** is a SmartNIC turned into its own server (CPU + many
engines, owns the host's data-plane); and a **SuperNIC** is currently marketing-speak for
a high-bandwidth RoCE/IB NIC whose silicon also contains the **congestion-control,
reorder and telemetry engines** that make an AI fabric behave [I]. For an AI backend the
practical truth is: the card must (1) DMA to/from GPU HBM at PCIe speed, (2) execute work
queues without the CPU, and (3) if it wants to be "AI-native", tolerate packet spraying
by reordering in silicon. This page maps the names to those capabilities.

## What — the naming ladder, generation by generation
```text
                    CPU on data path?   RDMA engine?   On-card CPU?   Owns host DP?   Reorders spray?
conventional NIC        yes                no             no             no             no
RDMA NIC (RoCE)         no (K-bypass)      yes            no             no             no
HCA (InfiniBand)        no (K-bypass)      yes (IB)       no             no             no
SmartNIC                no                 optional       yes (small)    partial        optional
DPU                     no                 yes            yes (many)     yes            no (L2 classify)
SuperNIC                no                 yes            yes            no             yes  [I]
```
Each column is a "what it adds" over the previous rung. All of it sits on one or more
**PCIe links** that are themselves the bandwidth ceiling (`[E]`: PCIe 5.0 x16 ≈ 63 GB/s
one-way; a 400 Gb/s NIC needs 50 GB/s — see [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md)).

### What — the six device classes, precisely
- **Conventional NIC (LOM / Ethernet card):** L2/L3 offload, interrupt-driven or NAPI
  receive, no RDMA. Every packet crosses the CPU/OS. Fine for management/front-end,
  useless for GPU-to-GPU. [F: standard]
- **RDMA NIC (RoCE):** adds the **RDMA engine** — direct placement of data into
  registered memory via the verbs interface, kernel-bypass, so the CPU is off the data
  path. RDMA-capable ConnectX parts expose both Ethernet (RoCEv2) and IB modes. [F: NVIDIA docs]
- **HCA (Host Channel Adapter):** the InfiniBand endpoint card. Functionally an RDMA NIC
  whose transport is native IB (credit-based flow control, QP/PSN, LRH/BTH — see
  [05-infiniband-architecture.md](./05-infiniband-architecture.md)). "HCA" vs "RoCE NIC" is fabric, not capability. [F: IBTA]
- **SmartNIC:** a NIC with a small programmable core (FPGA or low-core CPU) that
  implements **extra packet processing** — filtering, crypto, NAT, telemetry — without a
  full server behind it. [F: standard]
- **DPU (Data Processing Unit):** a SmartNIC promoted to a *co-processor owning the
  host's data plane*: multiple Arm cores plus hardened engines (network, crypto, storage,
  security, SDN), runs its own operating system (e.g. NVIDIA DOCA/BlueField, Marvell
  OCTEON, Intel IPU, Azure Boost). It is a server *on the NIC*, isolating tenants via
  SR-IOV VFs. [F: NVIDIA / vendor docs]
- **SuperNIC:** NVIDIA's branding for a high-end RoCE/IB NIC (BlueField-3 SuperNIC,
  ConnectX-8 SuperNIC) whose ASIC carries **AI congestion control (TCC), per-packet reorder, and
  per-flow telemetry** — the closed-loop endpoint of Spectrum-X (see below). Other
  vendors (AMD Pollara/Vulcano AI NICs) sell the same *AI-endpoint* role under different
  names. [F: vendor spec] [I]

## Why — what each capability is actually buying you
| Capability | What it does | Where it lives on the card | Why an AI fabric needs it |
|---|---|---|---|
| DMA engine | moves data PCIe↔memory without CPU | HCA/NIC core | GPU HBM access (GPUDirect) |
| RDMA engine | kernel-bypass send/recv + QP state | verbs engine | 0 CPU per collective |
| HW congestion control | rate/mark decision in silicon | CC block (TCC/DCQCN) | avoid PFC storms at scale |
| in-NIC telemetry | counters/occupancy at line rate | telemetry engine | feed dashboards (40) |
| crypto | MACsec/IPsec/TLS inline | crypto engine | secure storage/conf VMs |
| SR-IOV (VF/PF) | carve NIC into virtual functions | virt engine | multi-tenant, containers |
| reorder engine | resequences sprayed packets | OOO block | allows per-packet spray |
| GPU connectivity | P2P DMA to CXL/NVLink-attached GPU | PCIe/GDR path | GPUDirect RDMA |

## How — the work-queue execution model (the core of every RDMA NIC)
An RDMA NIC/HCA runs on **Work Queues (WQ)**. The host posts Work Queue Entries (WQEs)
into a memory ring; the NIC fetches and executes them. This is the two-sided vs
one-sided distinction behind every operation:
```text
host CPU                       NIC silicon                      remote CPU
   |  1. post WQE to SQ ring     |                                 |
   |  2. write doorbell (MMIO)   |                                 |
   |---------------------->------|  3. fetch WQE (PCIe read)        |
   |                               |  4. parse opcode + rkey/addr    |
   |                               |  5. DMA payload from registered |
   |                               |     host buffer (PCIe read) -->| (RDMA_WRITE: no recv)
   |                               |  6. build LRH/GRH/BTH headers   |
   |                               |  7. place on fabric -------->   | DMA into remote memory
   |                               |  (RDMA_READ: reverse, response  |
   |  CQE (completion event)       |   returns data + AETH)         |
   |<------ generated on completion|                               |
```
The key pieces, all silicon, none CPU:
- **Fetch:** the NIC reads the WQE from the **send queue** ring in host memory (a PCIe
  read) — triggered by the doorbell, which is why the queue must live in registered/pinned memory.
- **Doorbell:** after posting, the host rings a **doorbell MMIO write** to the NIC so it
  knows a new WQE is ready; modern NICs support *sender-bypass* where the NIC polls or
  the app skips the ring to cut a µs. [F: NVIDIA verbs docs]
- **DMA:** the NIC DMAs the payload from the source buffer (and, for RDMA_READ, the
  remote NIC reads local memory and returns data) — symmetric with GPUDirect for GPU
  HBM. Completion goes back up as a **Complet ion Queue (CQ)** entry.
- **One-sided ops (RDMA_WRITE/READ)** consume **no remote receive WQE** — the remote CPU
  is never touched. Two-sided ops (SEND) need a receive queue pre-posted. [F: IBTA/verbs]

## When — pick the card for the role
- **GPU backend (the 4-8 NICs beside a GPU server):** HCA or RoCE/SuperNIC with GPUDirect
  RDMA; rank 0 of the decision is **GDR + PCIe topology**, not the card's CPU count. → [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md).
- **Virtualized / multi-tenant front-end:** DPU (SR-IOV VF/PF) so one physical NIC serves
  many pods/VMs with isolation. → [./47-security-multitenancy.md](./47-security-multitenancy.md).
- **Storage node / NVMe-oF target:** DPU or RDMA NIC with GDS for storage→GPU. → [README.md](../Hardware/README.md).
- **Management/IPMI sideband:** a low-end conventional NIC is fine; keep it off the
  backend fabric entirely.

## Hardware impact
The NIC is braced between two bandwidth numbers: the **PCIe root-complex ceiling**
(`[E]` PCIe 5.0 x16 ≈ 63 GB/s) and the **fabrics' line rate** (`[E]` 400 Gb/s = 50 GB/s,
NDR400 per port = 50 GB/s). A single 400G NIC fits under one PCIe 5.0 x16; an **800G NIC
(~100 GB/s, [E] 800 Gb/s = 100 GB/s)** needs PCIe **6.0** x16 to avoid becoming
PCIe-bound — that is the concrete reason "PCIe Gen6" shows up in ConnectX-8 datasheets
(`[F: vendor spec]`: ConnectX-8 SuperNIC = 800 Gb/s on PCIe Gen6 x16). Practical rule:
match NIC rate to a PCIe link whose one-way BW ≥ NIC line rate, else you measure PCIe,
not the fabric. [E from bank + [F: vendor spec]]

## Inference impact
Same NIC, same receive path, different traffic. For **inference** the pressure is
**latency**, not sustained BW: tiny KV-cache transfers per token crossing the NIC must
not queue behind big training bursts. Run inference QPs on a **separate SL/VL or DSCP
priority** (see [./10-infiniband-flow-control-and-qos.md](./10-infiniband-flow-control-and-qos.md)), and put decode traffic on its own traffic
class so a PFC/ECN event on the training class doesn't add tail latency to a token.
[I] → [40-network-telemetry.md](./40-network-telemetry.md) for the counters that expose this.

## Example — three vendor families, one row each
| Family | Part (generation) | Role | Notable "what it adds" | Tag |
|---|---|---|---|---|
| NVIDIA | **ConnectX-6/7** HCA (RDMA/IB; CX-6 = 200G, CX-7 = 400G) | HCA | RDMA engine, GDR, SR-IOV, HW CC | [F: vendor spec] |
| NVIDIA | **ConnectX-8 SuperNIC** (800G, PCIe Gen6 x16) | SuperNIC | 800G endpoint + native SHARP for XDR | [F: vendor spec] |
| NVIDIA | **BlueField-3 SuperNIC** (400 Gb/s max: 1×400GbE or 2×200GbE; 800 Gb/s is ConnectX-8 SuperNIC) | SuperNIC/DPU | Arm A78 + ConnectX-7 inline; reorders sprayed packets, HW AI CC (TCC), per-flow telemetry; the Spectrum-X endpoint | [F: vendor spec] |
| NVIDIA | **BlueField-3 DPU** | DPU | DOCA, virtualization, storage/crypto/SDN, not the spray-reorder role | [F: vendor spec] |
| AMD | **Pensando Salina-400 DPU** | DPU | 232 P4 MPU engines, 16× Arm N1, up to 128 GB DDR5, SDN/firewall/encryption/storage offload | [F: vendor spec] |
| AMD | **Pensando Pollara-400 / Vulcano-800 AI NIC** | AI endpoint | path-aware CC, UEC-ready, up to 2.4 Tb/s scale-out per GPU (vendor claim) | [F: vendor claim] |
| Marvell | **OCTEON 10 DPU** | DPU | Arm-based DPU for cloud/virtualized tenant networking | [F: vendor spec] |
| Microsoft | **Azure Boost DPU** (200G) | DPU | FPGA+ASIC tenant networking | [F] |

## Failure modes
- **Buying a DPU where you needed an HCA:** GPU-backend traffic doesn't use the DPU's
  CPU — you pay for virtualization you never touch, and the heavy offload path can add
  latency. Pick by the traffic, not the logo. [I]
- **NIC rate > PCIe capacity:** an 800G NIC on one PCIe 5.0 x16 links at ~63 GB/s, i.e.
  ~63% of line rate on paper; symptoms = perftest caps below wire rate with no loss. Check
  `lspci`/topo before blaming the fabric. [E]
- **No GPUDirect / wrong GID:** GDR not engaged (IOMMU, ACS, peermem) makes host CPU a
  bounce point and halves effective BW. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).
- **Doorbell storm / bad WQE ring:** mis-sized SQ ring or lost doorbell → timeouts
  ("Got completion with error"). Tune `mlx5` queue depths, not the cable. [I]

## How to measure it
- `ibstat` / `ibstatus` — HCA port state, link_layer (IB vs Ethernet), rate.
- `ibv_devinfo` (`rdma link show`) — port capabilities, GIDs, whether RDMA is live.
- `perftest` (`ib_write_bw -c`, `-R`, `--report_gbits`) — the card's raw wire behavior;
  `-c` engages GPUDirect CUDA, `-d <dev>` picks the HCA. → [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md).
- Compare `ib_write_bw` (host) vs `ib_write_bw -c` (CUDA): if GPU is much lower, GDR is
  not engaging. [I]

## Why "SuperNIC" is (mostly) a marketing term
Strictly, a "SuperNIC" is just a NIC with a higher port count and faster PCIe — that is
true of any 800G card. What the AI hangars actually need from "the endpoint in an AI
fabric" is the **closed control loop**: a NIC that (a) faithfully meets line rate,
(b) **reorders** packets the switch sprayed across many paths (so the fabric can do
per-packet load-balancing), (c) runs **congestion control in hardware** rather than
awkward ECN/CNP in firmware, and (d) emits **per-flow telemetry** cheaply. NVIDIA assigns
the *SuperNIC* name to exactly that combination (BlueField-3/ConnectX-8 +
Spectrum-X/TCC); AMD's "AI NIC" line is the same job. So the term is a *marketing label*,
but the *capability it points at — NIC + CC + reorder + telemetry engine — is real and is
the correct procurement target for a lossless-spray RoCE fabric*. [I] If you only need IB
fat-tree without spraying, a plain HCA is enough; buy "SuperNIC-class" when your Ethernet
fabric sprays. → [40-network-telemetry.md](./40-network-telemetry.md), [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md).

## Key Takeaways
1. The five names are a capability ladder, not five products: conventional NIC (CPU on the data path) → RDMA NIC/HCA (kernel-bypass, RDMA engine) → SmartNIC (small on-card CPU) → DPU (own server, owns host data-plane) → SuperNIC (HW AI-CC + reorder + telemetry).
2. Every RDMA NIC runs on Work Queues: it fetches WQEs from host memory and DMAs payloads itself, so one-sided RDMA_WRITE/READ never touch the remote CPU — the basis of zero-CPU collectives ([./03-rdma-fundamentals.md](./03-rdma-fundamentals.md)).
3. Always brace the card between two ceilings — PCIe 5.0 x16 ≈ 63 GB/s and line rate (400G = 50 GB/s): a single 400G fits, an 800G (100 GB/s) needs PCIe Gen6 x16 ([./43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md)).
4. Pick by traffic, not logo: the GPU backend needs GPUDirect + the right PCIe topology (an HCA/RoCE-SuperNIC), while a DPU earns its cost only for virtualized/storage roles ([./38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md), [../Hardware/README.md](../Hardware/README.md)).
5. "SuperNIC" is a marketing label for a real capability: buy it when your Ethernet fabric sprays and needs in-silicon reorder + HW congestion control + per-flow telemetry; a plain HCA suffices for fat-tree IB ([./40-network-telemetry.md](./40-network-telemetry.md), [./44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md)).

## Related
- [03-rdma-fundamentals.md](./03-rdma-fundamentals.md) — the verbs/WQ/DMA model in depth.
- [38-rail-optimized-multi-plane.md](./38-rail-optimized-multi-plane.md) — how these NICs wire into rails.
- [40-network-telemetry.md](./40-network-telemetry.md) — the telemetry the SuperNIC emits.
- [43-network-bandwidth-calculations.md](./43-network-bandwidth-calculations.md) — PCIe vs fabric bandwidth ceiling.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — how to prove the NIC is fine.
- [16-performance-benchmarking.md](../GPU-Communication/16-performance-benchmarking.md) — cross-section GPU-side view.

## References
- [F] NVIDIA ConnectX / BlueField datasheets and SuperNIC pages; Spectrum-X platform
  (`nvidia.com/en-us/networking/spectrumx`), fetched 2026-08-25.
- [F: vendor spec] AMD Pensando Salina/Pollara/Vulcano pages; Marvell OCTEON 10; Microsoft
  Azure Boost (secondary via SemiAnalysis in research notes).
- [E] PCIe 5.0 x16 = ~63 GB/s; 400 Gb/s = 50 GB/s; 800 Gb/s = 100 GB/s; NDR400 = 50 GB/s —
  section constants bank, computed 2026-08-25.
