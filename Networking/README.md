# LLM Networking
`LAST_UPDATED: 2026-08-25` · Status: core section

> **The full communication-stack deep-dive now lives in `../GPU-Communication/`
> (21 pages, added 2026-08-25):** the three-branch taxonomy, NCCL (2.31.2),
> NIXL (v1.4.0), UCCL (UC Berkeley/Davis, OSDI'26), the adjacent libraries,
> RDMA/IB/RoCE/EFA benchmarking, troubleshooting, and the decision guide.
> This page remains the one-page networking primer; start there, then follow
> the cross-links below.

## 30-Second Explanation
Distributed LLMs are **communication-bound systems**. The model is split across GPUs; every
layer, every expert dispatch, every KV transfer is a network operation. Networking quality
(especially latency + fabric bandwidth) directly sets achievable MFU (training) and
parallelism depth (inference).

## Why it matters (the core insight)
- **TP** does an AllReduce *twice per layer, every step* → it must run on the fastest
  fabric (NVLink). Cross-node TP is why people avoid it. [I: standard]
- **EP/CP** do AllToAll → bandwidth-hungry; needs fast RDMA or NVL72.
- **P/D disaggregation** moves the KV cache across the fabric → KV transfer time competes
  with decode start.
- **Training** at 100k+ GPUs is dominated by collective communication efficiency.

## The communication primitives
| Primitive | Used by | Pattern | Sensitive to |
|---|---|---|---|
| **AllReduce** | TP (2×/layer), ZeRO-1 grads | ring: 2(n−1) steps | latency × n |
| **AllGather** | ZeRO-3 / FSDP param gather | gather to all | bandwidth |
| **ReduceScatter** | ZeRO-1 gradient partition | scatter + reduce | bandwidth |
| **AllToAll** | EP dispatch/combine, CP | full shuffle | bandwidth + latency |
| **P2P (Send/Recv)** | PP stages | point-to-point | latency |
| **KV transfer** | P/D disaggregation | bulk copy | bandwidth (RDMA) |

## The stack
- **NCCL** (NVIDIA Collective Communications Library) — the de-facto collective engine
  (AllReduce/AllToAll/AllGather) over NVLink/PCIe/InfiniBand. [F: nccl repo]
- **RDMA** — remote direct memory access; zero-copy, kernel-bypass.
- **InfiniBand (NDR 400G)** vs **RoCE (RDMA over Converged Ethernet)** — the two inter-node
  fabrics; IB = lossless + adaptive routing out of the box; RoCE = needs PFC/ECN tuning.
- **ECMP / adaptive routing** — spread flows to avoid hotspots; adaptive routing (IB)
  reacts to congestion in-network.
- **SHARP** — in-network (switch) in-network reduction for AllReduce; offloads the last
  hop onto the switch. [F: NVIDIA SHARP]
- **GPUDirect RDMA** — GPU memory ↔ NIC without host bounce; essential for low-latency
  KV transfer and P2P. [F: NVIDIA]

## Mapping to the workloads
| Workload | Dominant primitive | Fabric need |
|---|---|---|
| Training (large) | AllReduce + AllToAll (MoE) | NVLink intra + IB/RoCE inter; SHARP helps |
| TP inference | AllReduce ×2/layer | NVLink (intra-node) — avoid cross-node |
| EP inference | AllToAll | fast RDMA / NVL72 |
| CP (long context) | AllToAll / ring | fast fabric |
| P/D disaggregation | KV bulk transfer | RDMA (IB/RoCE) + GPUDirect |

## Bottlenecks & open problems
1. **Cross-node TP** — latency kills it; keep TP intra-node. [I]
2. **AllToAll under load** — EP dispatch can become the MoE bottleneck; routing placement
   matters (expert placement, `Model-Architectures/Mixture-of-Experts.md`).
3. **KV transfer at 128k ctx** — ~16 GiB/request cross-node is non-trivial; NVL72-class
   fabrics make it nearly free intra-pod. [I]
4. **Lossless vs lossy** — IB is lossless by design; RoCE needs careful PFC config to avoid
   head-of-line blocking. [I: networking practice]

## Related
`../GPU-Communication/README.md` (the full 21-page communication-stack section,
2026-08-25) · `../Hardware/README.md` · `../Distributed-Inference/README.md` ·
`../Inference/Prefill-Decode-Disaggregation.md`.

 NCCL collectives + the multi-GPU/multi-node fabric detail:
`../GPU-Systems/NCCL.md` and `../GPU-Communication/04-nccl-deep-dive.md`.

## Key Takeaways
Network = the difference between "the model fits" and "the model runs fast." AllReduce
wants NVLink; AllToAll wants bandwidth; KV transfer wants RDMA. Match the parallelism
strategy to the fabric you actually have.
