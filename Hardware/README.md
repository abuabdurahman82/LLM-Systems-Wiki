# Hardware for LLMs
`LAST_UPDATED: 2026-08-16` · Status: core section (specs marked [F: vendor spec] where available;
UNVERIFIED where not confirmed live)

## 30-Second Explanation
An LLM accelerator is defined by three numbers: **peak FLOPS** (prefill), **HBM bandwidth**
(decode), and **fabric** (parallelism). Everything in the roofline (`Inference/Roofline.md`)
flows from these. The interconnect (NVLink/NVSwitch intra-node, InfiniBand/RoCE inter-node)
determines what parallelism strategies are practical.

## GPU generations (NVIDIA datacenter)
| Gen | Era | HBM | Notes |
|---|---|---|---|
| **Volta** V100 | 2017 | HBM2 ~900 GB/s | first tensor-core; Transformer training era begins |
| **Turing** T4 | 2018 | GDDR6 320 GB/s | inference, no HBM |
| **Ampere** A100 | 2020 | HBM2 800 GB/s (40/80GB) | BF16/TF32; 8-GPU NVSwitch node; GPT-3-class training |
| **Hopper** H100 | 2022 | HBM3 3.35 TB/s (SXM) | FP8, transformer engine; 989 TFLOPS BF16 dense [F: spec] |
| **Blackwell** B200/B100, GB200 | 2024–25 | HBM3e ~8 TB/s (B200) | FP4/FP8; NVL72 (72-GPU NVLink domain) [F: spec] |
| **Blackwell Ultra / Rubin** | 2026+ | HBM3e/HBM4 | next-gen; UNVERIFIED specs at research time |

Consumer/edge: RTX 40 (Ada, GDDR6), **RTX 50 (Blackwell, GDDR7 1.79 TB/s [F: spec])**,
DGX Spark/GB10 (~273 GB/s [A: spec-sheet]).

## Key components
- **Tensor Cores** — mixed-precision FMA (FP16/BF16/FP8/FP4); the source of the peak-FLOPS
  number. Utilization (MFU) is the practical metric.
- **HBM** — high-bandwidth memory; the decode bottleneck. Bandwidth, not capacity, usually
  binds decode.
- **NVLink / NVSwitch** — intra-node GPU-to-GPU fabric (H100: ~900 GB/s aggregate; NVL72:
  a 72-GPU NVLink domain). This is what makes TP practical within a node.
- **PCIe** — GPU↔host; ~64 GB/s (5.0 x16); the fallback when NVLink absent.
- **InfiniBand / RoCE** — inter-node RDMA; 400G NDR ≈ 50 GB/s per link. The bottleneck for
  cross-node TP/EP/CP and P/D KV transfer.
- **DPUs / SmartNICs** — offload networking/storage/security; relevant at scale.
- **SHARP** — in-network (switch-side) collective reduction; cuts AllReduce latency for
  training.

## The three-number mental model
For any accelerator, write down: `peak FLOPS`, `HBM BW`, `fabric BW (intra / inter)`.
Then every design decision (quantize? batch? TP? EP? disaggregate?) is a roofline +
fabric question. [I]

## Cost / economics
- $/token at the frontier is the product metric; hardware generation shifts it (FP4 +
  HBM3e → ~3–5× decode bandwidth per dollar, roughly [I]).
- The 2024–26 trend: **FP4/FP8 datacenter serving** is the default new-build path; HBM4
  and custom ASICs (Google TPU, AWS Trainium, AMD MI-series) are the alternatives.

## Related
`Networking/README.md` · `Inference/Roofline.md` · `Distributed-Inference/README.md` ·
`Quantization/README.md` · `GPU-Communication/README.md`.

 GPU-Systems handbook (architecture → CUDA → kernels → engines → multi-GPU): `GPU-Systems/README.md`.

## Key Takeaways
Three numbers define an accelerator. HBM bandwidth = decode; tensor cores = prefill;
fabric = parallelism. Generations shift all three; the roofline tells you which one your
workload actually cares about.
