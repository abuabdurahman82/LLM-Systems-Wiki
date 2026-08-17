# Research Lineage Maps
`LAST_UPDATED: 2026-08-16` · How ideas influenced one another. (All [F] except marked.)

## 1. Attention head lineage
```
MHA (Vaswani 2017) → MQA (Shazeer 2019) → GQA (Ainslie 2023) → MLA (DeepSeek-V2 2024)
```
Each step: shrink KV bytes, keep quality; GQA became the default; MLA changes *what is
cached* (latent).

## 2. Exact-attention kernel lineage
```
Standard O(S²) attention → FlashAttention (2022) → FA-2 (2023) → FA-3 (2024, Hopper/FP8)
                                   ↘ FlashInfer (2024: paged/ragged prefill+decode)
                                   ↘ FlashMLA (DeepSeek, MLA-optimized)
```
All *kernels* (same math). Distinct from architecture changes.

## 3. KV-cache lineage
```
Standard KV cache → PagedAttention (vLLM 2023) → prefix caching (APC 2023 / RadixAttention
→ 2023-24) → KV quantization (2023-24) → eviction (StreamingLLM/H2O/SnapKV/PyramidKV 2023-24)
→ learned/lifecycle-aware KV (2025-26: DistillCache, RippleKV, CommitKV, SPECTRA)
→ offloading/disaggregated KV (Mooncake 2024; Dynamo/llm-d 2025)
```
The spine of serving optimization; each node = a memory-strategy change.

## 4. Batching lineage
```
Static batching → dynamic batching → continuous/iteration-level (Orca 2022) → in-flight
batching (DeepSpeed-MI) → chunked-prefill co-scheduling (2023-24) → P/D disaggregation
(DistServe 2024, Splitwise 2024, Mooncake 2024, Dynamo/llm-d 2025)
```

## 5. Speculative decoding lineage
```
Classical draft-verify (Leviathan/Chen 2022-23) → n-gram/self-draft → Medusa (2024,
heads) → EAGLE (2024, feature-level draft) → MTP (trained multi-token) → STAGE/DFlash/
Spec V2 (tree/layer-wise) → edge/diffusion variants (2026)
```

## 6. Alignment lineage
```
SFT → RLHF (InstructGPT 2022) → Constitutional AI (2022) / RLAIF (2023) → DPO (2023) →
IPO/ORPO/KTO/SimPO variants (2023-24) → reasoning RL (o1 2024; R1/GRPO 2025) → adaptive
thinking budgets (2025-26)
```

## 7. Reasoning lineage
```
CoT prompting (2022) → Self-Consistency (2022) → ToT (2023) → process supervision
(2023) → RLVR long-CoT (o1 2024) → open reasoning RL (R1 2025) → agentic reasoning
systems (2025-26)
```

## 8. Architecture lineage
```
RNN/LSTM (1997) → seq2seq+attention (2014-15) → Transformer (2017) → GPT/BERT (2018)
→ GPT-3 (2020) → Switch/MoE (2021) → LLaMA-class conventions (RoPE+GQA+RMSNorm+SwiGLU,
2023) → MoE frontier (Mixtral 2023, DeepSeek-V3 2024) → MLA (2024) → SSM hybrids
(Mamba-2 2024, Jamba 2024) → native multimodal (2024-26)
```

## 9. Scaling lineage
```
Kaplan scaling (2020) → Chinchilla (2022: tokens≈7×params) → over-trained open models
(LLaMA 2023) → MoE (decouples params from compute) → test-time scaling (o1/R1 2024-25)
→ effort tiers (2026 product)
```

## 10. Agents lineage
```
ReAct (2022) → tool-use APIs (2023) → Reflexion/Plan-Execute (2023) → MemGPT (2023) →
multi-agent debate (2023) → SWE-agent (2024) → computer-use (2024) → coding-agent era
(2025-26) → harness engineering as a discipline (2025-26)
```

## Related
`Research-Papers/README.md` · each topic section.
