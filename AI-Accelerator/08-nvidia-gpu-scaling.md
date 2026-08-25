# NVIDIA GPU Scaling: NVLink, NVSwitch, and the Rack
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F: vendor spec]` = NVIDIA datasheets/GTC.

## 30-Second Explanation
Scaling an NVIDIA machine has two tiers with a cliff between them: **scale-up** (NVLink +
NVSwitch — a domain of up to 72 GPUs that behaves like one coherent, high-bandwidth
machine) and **scale-out** (InfiniBand or Spectrum-X Ethernet — the cluster beyond the
rack). NVLink is ~5–20× faster per GPU than a scale-out NIC; the moment a workload crosses
the domain boundary, communication latency and per-byte cost jump. That boundary is the
most important architectural fact about any distributed LLM deployment, and it is why [I]
NVIDIA sells *racks*, not chips.

## The interconnect stack
```
ON-PACKAGE:
  (Blackwell+ B200) two reticle dies inside one package, bonded, sharing one HBM pool
  + NVLink-C2C class links where a CPU package is attached (Grace-Hopper: 900 GB/s C2C)
GPU <-> GPU (within a node, up to 8 GPUs):
  NVLink point-to-point (NVSwitch crossbar in DGX/HGX nodes)
NODE:
  8x GPU + CPU(s) + NVSwitch tray; PCIe to host
RACK (scale-up domain):
  GB200 NVL72: 72 GPUs + 36 Grace CPUs, all in ONE NVLink domain via NVSwitch
  (18 NVSwitch trays; ~130 TB/s aggregate all-to-all bandwidth across the 72 GPUs [F])
CLUSTER (scale-out):
  InfiniBand NDR/XDR or Spectrum-X Ethernet, ConnectX NICs (CX-7 400G, CX-8 800G,
  CX-9 1.6T [F: vendor spec]); BlueField DPUs for offload
```
[E: NVL72 aggregate 130 TB/s = 72 GPUs × 1.8 TB/s NVLink per GPU / 2 for bidirectional
convention — NVIDIA quotes "130 TB/s" as the all-to-all figure; treat as vendor-aggregate.]

## NVLink generations (per-GPU bandwidth)
| Gen | Per-GPU aggregate | Node shape |
|---|---|---|
| NVLink 3 (A100) | 600 GB/s | 8-GPU NVSwitch |
| NVLink 4 (H100) | 900 GB/s | 8-GPU NVSwitch (DGX H100) |
| NVLink 5 (B200/GB200) | 1.8 TB/s | 8-GPU node; **NVL72 rack domain** |
| NVLink 6 (Rubin NVL144) | 3.6 TB/s | **NVL144** (2x NVL72-scale) |
| (Rubin Ultra NVL576) | 3.6 TB/s | NVL576 "Kyber" (576 GPUs) [ANNOUNCED] |

NVSwitch is the on-rack crossbar that makes the domain *all-to-all* (any GPU to any GPU at
full NVLink rate, one hop). A torus would give the same bisection for cheaper wiring but
with multi-hop diameter; NVIDIA chose the crossbar — more power, more ASIC, but
**deterministic one-hop latency across the whole domain** (deep: `18`).

## Scale-up vs scale-out (the cliff)
| Property | Scale-up (NVLink domain) | Scale-out (IB/Spectrum-X) |
|---|---|---|
| Per-GPU bandwidth | 900 GB/s – 3.6 TB/s | 400 Gbps – 1.6 Tbps = 50 – 200 GB/s |
| Latency | ~us (one switch hop) [A] | ~5–10 us per hop, RTT higher [A] |
| Memory model | load/store over the fabric (GPUDirect) | message-passing (RDMA) |
| Domain size | 8 → 72 → 144 → 576 GPUs | 10^3–10^5+ GPUs |
| Cost | ~20× the NIC's $/GB/s | commodity |
The cliff: NVLink5 gives 1.8 TB/s per GPU; a ConnectX-8 gives 800 Gb/s = 100 GB/s. Same
chip, **18× bandwidth gap** at the domain boundary. [E: 1.8e12/1e11 = 18; both figures
[F: vendor spec].]

## What the parallelism strategies need
The mapping from `../Distributed-Inference/README.md` and `../GPU-Systems/`:
| Parallelism | Traffic | Where it lives |
|---|---|---|
| **Tensor Parallelism (TP)** | all-reduce every layer, ALL activations | MUST be scale-up (NVLink) — the hottest traffic |
| **Pipeline Parallelism (PP)** | activation P2P between stages | scale-up preferred; can straddle scale-out (slow, but P2P is small) |
| **Data Parallelism (DP)** | gradient all-reduce per step | can be scale-out (ZeRO/FSDP reduce the volume; see `../Training-Engineering/Parallelism.md`) |
| **Expert Parallelism (EP, MoE)** | all-to-all every MoE layer | wants high-radix scale-up; worst case for low-radix fabrics (`18`) |
**Rule of thumb:** TP radius ≤ scale-up domain; everything else can spill to scale-out.
A 72-GPU NVL72 domain therefore supports TP up to 72 (in practice TP 8 per node +
intra-rack TP up to the switch's all-to-all budget), which is why frontier training runs
put tensor-parallel inside the rack and expert/data-parallel across racks.

## ConnectX, InfiniBand, Spectrum-X, BlueField
- **ConnectX (CX-7/8/9):** the scale-out NIC; 400/800/1600 Gb/s; doubles per NVIDIA gen
  [F: vendor spec].
- **InfiniBand:** NVIDIA's RDMA fabric (NDR 400G → XDR 800G); the traditional choice for
  training clusters; low tail latency, proprietary.
- **Spectrum-X:** NVIDIA's Ethernet answer (Ethernet switches + ConnectX + software
  telemetry) for AI scale-out; the industry's Ethernet push (AMD, UEC) is the competitive
  force — see `18-ai-accelerator-interconnects.md` and `../Networking/README.md`.
- **BlueField (DPU):** offloads storage/SDN/security from the host CPU so the GPU node can
  dedicate its bandwidth to the model; the "infrastructure side" of the rack.

## The rack as the product
GB200 NVL72 ≈ 72 GPUs + 36 Grace CPUs + 18 NVSwitch trays + ~120 kW, liquid-cooled
[F: vendor spec]. The sales unit is the rack because: (1) the 72-GPU NVLink domain only
exists at rack scale, (2) power/cooling are rack-scale problems above ~1 kW/GPU, and (3)
the *compiler/runtime* (CUDA + NCCL + the serving engine) is tuned to the domain shape.
Deep dive: `24-the-rack-is-the-ai-computer.md`.

## Key Takeaways
1. NVLink (scale-up) and IB/Ethernet (scale-out) differ ~10–20× per-GPU; the domain
   boundary is the most expensive line in a distributed deployment.
2. NVSwitch makes the domain all-to-all at one hop — the reason TP runs inside the rack.
3. NVL72→NVL144→NVL576 is NVIDIA's scale-up roadmap; the domain grows ~3× every two
   generations while per-GPU bandwidth doubles.
4. Parallelism strategies map to tiers: TP in-scale-up, DP/EP can spill to scale-out.
5. Above ~1 kW/GPU, the rack (power, liquid cooling, optics) — not the chip — is the
   engineering product.

## Related
- `05-nvidia-gpu-overview.md`, `08` companion pages
- `../GPU-Systems/Scale-Up-vs-Scale-Out.md`, `../GPU-Systems/NCCL.md`, `../GPU-Systems/Topology.md`
- `../Distributed-Inference/README.md` — the parallelism strategies themselves
- `18-ai-accelerator-interconnects.md` — cross-vendor interconnect comparison
- `24-the-rack-is-the-ai-computer.md` — the rack as design unit

## References
- NVIDIA NVLink/NVSwitch/GB200 NVL72 datasheets (1.8 TB/s/GPU, 130 TB/s, ~120 kW [F: vendor spec])
- NVIDIA ConnectX-7/8/9 datasheets [F: vendor spec]
- GTC 2025 roadmap keynote (Rubin NVL144, Rubin Ultra NVL576 [F: vendor spec/announced])
- NCCL (open-source collective library [F: repo])
- `../Networking/README.md` — RDMA/RoCE/InfiniBand fundamentals
