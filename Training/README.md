# Training LLMs
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
Pretraining = next-token prediction over trillions of tokens with a Transformer. The hard
parts are (a) data, (b) scaling (compute-optimal choice of N, D, batch), (c) distributed
training (splitting model+data across GPUs and keeping the network saturated), (d)
stability (mixed precision, checkpointing, recovery).

## Data pipeline
1. **Collection:** web crawl (Common Crawl-class), books, code, academic; licensing and
  consent vary (GPT-4-class data policies are closed [A]).
2. **Cleaning:** PII redaction, quality filters (perplexity, dedup), language ID.
3. **Deduplication:** exact + fuzzy (MinHash/SimHash) dedup — duplicate training data
  causes overfitting/memorization artifacts [F: Lee et al. 2022 "Deduplicating Training
  Data" arXiv:2107.00077].
4. **Mixture construction:** ratios of web/code/math/books; mixing is itself a research
  area (DoReMi 2023 arXiv:2109.04563 [F]).
5. **Tokenization:** BPE/SentencePiece; tokenizer choice affects everything (see
  `Transformer/README.md`).

## Objective & optimization
- **Next-token prediction:** minimize cross-entropy over the next token.
- **AdamW** (Loshchilov & Hutter 2019, ICLR, arXiv:1711.05101 [F]) with decoupled weight
  decay — the default optimizer.
- **LR schedule:** warmup (linear) + cosine decay to ~10% of peak [I: standard practice].
- **Gradient clipping** (e.g. 1.0 norm) — stability.
- **Mixed precision:** BF16 for forward/backward, FP32 master weights; loss scaling
  (FP16 era) [F: Mixed Precision paper arXiv:1712.05855; bf16 standard since 2020].
- **Checkpointing:** async, sharded; cost of recovery ∝ checkpoint interval × world size.

## Scaling laws
- **Kaplan et al. 2020** ("Scaling Laws for Neural Language Models", arXiv:2001.08361
  [F]): L = (C/C(N,D)) power-law; "scale everything equally" heuristic.
- **Chinchilla (Hoffmann et al. 2022, arXiv:2203.15556 [F]):** ~1:7 ratio — tokens ≈ 7×
  params is compute-optimal. GPT-3 (175B, 300B tokens) was *over-trained*; LLaMA (65B,
  1T tokens) was deliberately under-parametrized/over-trained [F: LLaMA paper]. Consequence:
  the industry moved to "more tokens, same params" — and to MoE (params without compute).
- **Test-time scaling** (2024–): inference compute as a scaling axis
  (`Reasoning/README.md`) — the third axis after model size and data.

## Curriculum
Data ordering (easy→hard), continued pretraining on new domains, "soul" fine-tunes —
all standard [I]. Curriculum research is thin; most effect comes from data quality/mix.

## Distributed training (the meat)
| Method | What's split | Comm | Notes |
|---|---|---|---|
| **Data parallel (DP)** | batch | AllReduce grads | every GPU holds full model; simple |
| **ZeRO (DeepSpeed)** (Rajbhandari 2020, arXiv:1909.08053 [F]) | optimizer state + grads + params (1/2/3) | AllReduce/AllGather/ReduceScatter | ZeRO-3 = no param duplication; the training workhorse |
| **FSDP** (PyTorch) | params+grads+optim (sharded) | AllGather | ZeRO-3 in PyTorch |
| **Tensor parallel (Megatron)** (Sho et al. 2019, arXiv:1909.08053 [F]; Megatron-1/2/3 papers 2021–2023 [F]) | layer matrices | AllReduce ×2/layer | NVLink-class fabric required |
| **Pipeline parallel** | layers | P2P activations | GPipe arXiv:1811.06965; 1F1B; bubble cost |
| **Sequence/context parallel** | sequence | AllToAll / ring | Long-context training (Megatron-SP arXiv:2205.05198; Ring arXiv:2211.12876) |
| **Expert parallel** | MoE experts | AllToAll | `Model-Architectures/Mixture-of-Experts.md` |

Real stacks compose: **DP × TP(intra-node NVLink) × PP/EP(cross-node)** [I: standard].
Megatron-LM (NVIDIA, arXiv:1909.08053 + 2021–2024 series [F]) and DeepSpeed (arXiv:2004.11302
[F: OSDI'20]) are the two reference toolkits.

## Communication ↔ hardware
AllReduce latency ∝ (2(n−1)/n)·msg + (n−1)·latency (ring); NVLink intra-node ≫ PCIe ≫
RDMA inter-node. 8-GPU NVSwitch node = the atomic unit; scaling out needs fast IB/RoCE
(`Networking/README.md`). **Why it matters:** at 100k+ GPUs, network is the bottleneck
for TP/EP; training cost ≈ FLOPs × MFU, and MFU is set by pipeline+comm efficiency
(~40–60% [I: reported ranges]).

## Stability in practice
NaNs, loss spikes, stragglers, hardware failures: expect 1000s of GPU-hours of
interruptions per 1T+ training run; checkpoint-every-N-steps + fast restart is table
stakes [I: industry experience consistent across labs].

## Related
`Training/Scaling-Laws.md` (expand) · `Distributed-Inference/README.md` ·
`Networking/README.md` · `Post-Training/README.md`.

## Key Takeaways
Pretraining = data quality × compute-optimal scaling × distributed efficiency. Chinchilla
shifted the axis from params to tokens; MoE broke the params-compute link; test-time
compute broke the train-inference link.
