# Quantization
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
Run a model with fewer bits per number. Weights, activations, and KV can each be
quantized independently. The payoff is mostly **decode bandwidth** (fewer bytes/token) and
**capacity** (more KV / more models per GPU); the cost is accuracy risk and calibration
complexity.

## Why This Exists
Decode is memory-bandwidth-bound (`Inference/Roofline.md`): halving weight bytes ≈ ~2×
decode speed until the compute ridge. Quantization is the cheapest "hardware upgrade."

## Number formats
| Format | Bits | Notes |
|---|---|---|
| FP32 | 32 | training reference |
| TF32 | 19 | 10-bit mantissa; default for many GEMMs on Ampere+ |
| FP16 | 16 | 5 exp, 10 mantissa; needs loss scaling |
| **BF16** | 16 | 8 exp, 7 mantissa; same range as FP32, coarser precision; LLM training/inference default [F] |
| **FP8 (E4M3/E5M2)** | 8 | Hopper+ hardware [F]; near-lossless for weights+activations with per-block scales [I: widely reported] |
| INT8 | 8 | per-tensor/channel scales; mature on CPUs |
| INT4 / NF4 | 4 | weight-only territory; GPTQ/AWQ/bitsandbytes |
| **NVFP4 / MXFP4** | ~4.5 (incl. block scale) | Blackwell datacenter 4-bit; ~3.5× smaller than BF16; NVFP4 is the 2025–2026 datacenter workhorse [F: NVIDIA docs] |

## What can be quantized (independent axes)
1. **Weight-only** (W4A16, W8A16): smallest deploy complexity; decode GEMV bytes drop;
   activation stays 16-bit. [F]
2. **Weight+activation** (W8A8, W4A4/W8A8): GEMM becomes 8/4-bit tensor-core; helps
   prefill compute too; needs calibration or dynamic scales. [F]
3. **KV-cache quantization** (FP8/INT8 KV): halves KV bytes → more concurrency at long
   context; vLLM `--kv-cache-dtype` [F].

## Major methods
| Method | Type | Calibration | Notes |
|---|---|---|---|
| **GPTQ** (Frantar 2022, arXiv:2210.17323, ICML'23) [F] | weight 4/8-bit, 1D (or GPTQ+GPTQ 2D) | one-shot, ~512 calibration samples | Hessian-based; standard W4A16 path |
| **AWQ** (Lin 2023, arXiv:2306.00978, DAC'23) [F] | weight 4-bit | per-channel; finds salient weights via activation magnitudes | often ≤ GPTQ at W4; no Hessian |
| **SmoothQuant** (Xiao 2023, arXiv:2308.12388, ICML'24) [F] | W8A8 | per-channel migration of outlier from activation to weight | makes INT8 GEMM practical |
| **bitsandbytes / NF4** (Li 2023, arXiv:2302.03048, ICLR'23) [F] | 8/4-bit weight-only (Q-LoRA) | none | 8-bit optimizer + 4-bit LoRA training |
| **GGUF / llama.cpp quant** (Jorgensen; arXiv:2304.09143 "LLM.int8()"; GGUF formats Q4_K/Q5_K/Q8_0) [F] | mixed k-quant, CPU/edge | none | the de-facto edge standard; per-block k-quant is better than naive uniform INT4 |
| **FP8 inference** (Hopper) [F: NVIDIA] | W8A8 / KV FP8 | dynamic or per-block | near-lossless; the 2024–2025 default for H100/B200 serving |
| **NVFP4 / FP4** (Blackwell) [F: NVIDIA] | W4 (block-scaled) | per-block scale | 2025–2026 datacenter workhorse; ~3.5× BF16 memory & bandwidth win |
| **QuaRot / QLoRA / SpinQuant / KIVI** | rotation / mixed | vary | 2024-era research on robustness at 4-bit (KIVI arXiv:2402.02750 [F]) |

## Accuracy / VRAM / bandwidth / compute (the four effects)
- **VRAM:** bytes/param × N. BF16 50.3 GiB (27B) → FP8 ~25 → NVFP4 ~14.1 GiB [E: computed].
- **Bandwidth (decode):** same ratio → tok/s up until the ridge.
- **Compute:** only when GEMM dtype drops (W8A8/W4A4); weight-only W4A16 barely changes
  compute (activations still 16-bit FMA path) [I].
- **Accuracy:** W8 ≈ lossless; W4 ≈ small drop on most tasks; KV FP8 ≈ lossless;
  W4+KV-FP8+FP4 simultaneously is where quality risk compounds [I].

## Hardware support & deployment complexity
- CPU (llama.cpp GGUF): trivial, day-one.
- Consumer GPU (RTX 40/50): FP8 on Ada (limited), FP4 on RTX 50 [F: specs].
- Datacenter: FP8 on Hopper, FP4+FP8 on Blackwell [F: NVIDIA].
- Calibration cost: GPTQ/AWQ = one-shot offline (minutes–hours); SmoothQuant = needs
  activation stats; FP8/NVFP4 = runtime scales, minimal offline work.

## When it helps / hurts
- Helps: decode latency, capacity, long-context KV, edge, cost.
- Hurts: (a) accuracy-sensitive tasks at aggressive bit-widths; (b) prefill on
  compute-bound hardware where the kernel path is worse; (c) calibration mismatch at
  distribution shift [I].

## Related
`Inference/Roofline.md` · `Inference/The-Life-of-a-Token.md` · `Inference/Inference-Optimization.md` · `Labs/Lab-4`.

 Tensor-Core precision (FP32→NVFP4) and quantized GEMMs: `GPU-Systems/Tensor-Cores.md`.

## Key Takeaways
Quantization is a **bandwidth/capacity** tool first, a **compute** tool second. NVFP4/FP8
are the 2025–2026 datacenter defaults; GGUF is the edge standard; W4A16 (GPTQ/AWQ) is the
classic weight-only path.
