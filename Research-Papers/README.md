# Research Paper Database
`LAST_UPDATED: 2026-08-16` · Status: structured index (§33 format). Core papers below;
add new papers to this index when they appear in `Latest-Research/`.

Format per paper:
```
Title / Authors / Year / Conference / URL / Category
Problem → Core Idea → Previous Limitation → Method → Key Equation → Setup → Results →
Limitations → Why It Matters → Follow-ups → Related wiki pages
```

## 1. Vaswani et al. — "Attention Is All You Need" (2017, NIPS; arXiv:1706.03762) [F]
- **Category:** architecture. **Problem:** RNN sequentiality + vanishing gradients.
  **Previous limitation:** no O(1)-depth sequence model. **Core idea:** self-attention
  (Q/K/V) + FFN + residuals + sinusoidal positions, fully parallel. **Key equation:**
  Attention(Q,K,V)=softmax(QKᵀ/√d_k)V. **Why it matters:** THE architecture of all LLMs.
  **Follow-ups:** RoPE, GQA, MLA, FlashAttention (all build on it).
  **Related:** `Transformer/`, `Attention/`.

## 2. Cho et al. 2014 (arXiv:1409.0473) / Bahdanau et al. 2015 (arXiv:1409.0473 seq2seq attention) [F]
- **Category:** seq models. **Problem:** fixed bottleneck vector. **Core idea:**
  encoder–decoder + attention alignment. **Why it matters:** attention was born here.
  **Related:** `Foundations/`.

## 3. Mikolov et al. — word2Vec (2013, arXiv:1301.3781) [F]
- **Category:** embeddings. **Problem:** count matrices don't scale. **Core idea:**
  skip-gram/negative-sampling sublinear training; semantic vector geometry.
  **Related:** `Transformer/` (embedding table).

## 4. Shazeer et al. 2017 "Outrageously Large Neural Networks: The Sparsely-Gated MoE" (arXiv:1701.06538) [F]
- **Category:** MoE. **Problem:** capacity vs compute. **Core idea:** sparse gated experts.
  **Follow-ups:** Switch (2021), Mixtral, DeepSeek. **Related:** `Model-Architectures/Mixture-of-Experts.md`.

## 5. Hoffmann et al. — "Training Compute-Optimal Large Language Models" (Chinchilla, 2022, arXiv:2203.15556) [F]
- **Problem:** how to split compute across params vs tokens. **Result:** tokens ≈ 7×
  params is compute-optimal. **Why it matters:** reshaped the industry toward
  under-parametrized/over-trained + MoE. **Related:** `Training/`.

## 6. Ouyang et al. — "Training LMs to Follow Instructions with Human Feedback" (InstructGPT, 2022, arXiv:2203.02155) [F]
- **Problem:** base LMs don't follow instructions / aren't safe. **Core idea:**
  SFT → RM → PPO (RLHF). **Why it matters:** the aligned-assistant paradigm (ChatGPT).
  **Follow-ups:** DPO, Constitutional AI, reasoning RL. **Related:** `Post-Training/`.

## 7. Wei et al. — "Chain-of-Thought Prompting" (2022, arXiv:2201.11903) [F]
- **Problem:** LLMs fail multi-step reasoning single-shot. **Core idea:** elicit
  intermediate steps. **Follow-ups:** Self-Consistency, ToT, o1/R1. **Related:** `Reasoning/`.

## 8. Lei et al. — "FlashAttention" (Dao et al., 2022, arXiv:2205.14135; FA2 arXiv:2307.08691; FA3 arXiv:2403.04951) [F]
- **Problem:** O(S²) HBM traffic for the score matrix. **Core idea:** exact attention
  tiled in SRAM, IO-aware. **Why it matters:** long-context inference unlocked; kernel,
  not math, changed. **Related:** `Attention/`.

## 9. Kwon et al. — "Efficiently Scaling LLM Inference with PagedAttention" (vLLM, 2023, SOSP'23, arXiv:2309.00032) [F]
- **Problem:** KV memory fragmentation wasted 60–80% of GPU. **Core idea:** paged KV
  (virtual-memory analogy) + continuous batching. **Why it matters:** the modern
  serving stack. **Follow-ups:** prefix caching, RadixAttention. **Related:**
  `KV-Cache/`, `Serving-Engines/vLLM.md`.

## 10. Yao et al. — "ReAct: Synergizing Reasoning and Acting" (2022, arXiv:2210.03629) [F]
- **Problem:** reasoning and acting were separate. **Core idea:** interleaved
  thought-action-observation. **Why it matters:** the agent-loop template. **Related:**
  `Agents/`, `Harness-Engineering/`.

## 11. Rafailov et al. — "Direct Preference Optimization" (DPO, 2023, arXiv:2305.18290, NeurIPS) [F]
- **Problem:** RLHF needs RM + PPO (complex, unstable). **Core idea:** closed-form
  policy from preference pairs; no RM/sampling. **Why it matters:** the research
  alignment default. **Related:** `Post-Training/`.

## 12. Zhang et al. — "H2O: Heavy-Hitter Oracle" (2023, ICLR'24, arXiv:2306.14048) [F] / Li et al. — SnapKV (2024, arXiv:2404.14469) [F] / Xiao et al. — StreamingLLM (2023, arXiv:2309.17453) [F]
- **Category:** KV eviction. **Problem:** KV grows unbounded. **Core ideas:** attention
  sinks + window (StreamingLLM); heavy-hitter retention (H2O); prompt-time selection
  (SnapKV). **Related:** `KV-Cache/Eviction.md`.

## 13. Leviathan et al. 2022 (arXiv:2211.17192) / Chen et al. 2023 (arXiv:2302.01318) — Speculative Decoding/Decoding [F]
- **Problem:** decode is bandwidth-bound. **Core idea:** draft-verify, distribution-
  preserving. **Follow-ups:** Medusa (arXiv:2401.10774), EAGLE (arXiv:2401.15077),
  MTP (DeepSeek). **Related:** `Speculative-Decoding/`.

## 14. Ainslie et al. — "GQA: Training Big Friendly LLMs" (2023, arXiv:2305.13245) / Shazeer 2019 "MQA" (arXiv:1911.06145) [F]
- **Problem:** MHA KV too big at scale. **Core idea:** shared KV heads. **Why it
  matters:** the default KV-shrinker; enabled long-context + concurrency. **Related:**
  `Model-Architectures/Attention-Head-Designs.md`.

## 15. Touvron et al. — LLaMA (2023, arXiv:2302.13971) / Llama 3 (2024, arXiv:2407.21783) [F]
- **Problem:** no strong open reference architecture. **Core idea:** pre-norm GQA/RoPE/
  SwiGLU, over-trained (post-Chinchilla). **Why it matters:** the open reference
  decoder-only design; the template for the open ecosystem. **Related:**
  `Open-Source-Models/`.

## 16. DeepSeek-V3 (2024, arXiv:2412.19437) & DeepSeek-R1 (2025, arXiv:2501.12948) [F]
- **Category:** open frontier + reasoning RL. **Core ideas:** MLA (latent attention,
  ~97% smaller KV) + MoE (V3); GRPO + rule-based rewards + reasoning distillation (R1).
  **Why it matters:** open frontier-class MoE; open reproduction of test-time-compute
  reasoning. **Related:** `Model-Architectures/`, `Reasoning/`.

## 17. Yu et al. — "Orca: High-throughput LLM Serving with SGLang... (Iteration-level
  Scheduling)" (OSDI'22, arXiv:2211.06863) [F]
- **Problem:** static batching wastes slots. **Core idea:** iteration-level
  continuous batching. **Why it matters:** the utilization unlock all engines share.
  **Related:** `Inference/Continuous-Batching.md`.

## 18. Zhong et al. — DistServe (OSDI'24, arXiv:2401.09670) / Patel et al. — Splitwise
(2024, arXiv:2311.18677) / Qin et al. — Mooncake (FAST'25 Best Paper, arXiv:2407.00079) [F]
- **Category:** P/D disaggregation. **Core ideas:** separate prefill/decode SLOs;
  KV over fabric; production KV-aware "context pool" (Mooncake). **Related:**
  `Inference/Prefill-Decode-Disaggregation.md`.

## 19. Sho et al. — Megatron-LM (2019, arXiv:1909.08053; Megatron-1/2/3 series 2021–2024) / Rajbhandari et al. — ZeRO (2020, arXiv:1910.02242) [F]
- **Category:** distributed training. **Core ideas:** tensor/pipeline/expert parallelism;
  ZeRO state sharding. **Related:** `Training/`, `Distributed-Inference/`.

## 20. Lightman et al. — "Let's Verify Step by Step" (2023, arXiv:2305.16896) [F]
- **Category:** process supervision. **Problem:** outcome-only rewards give sparse
  credit. **Core idea:** reward the steps. **Follow-ups:** reasoning RL, verifiers.
  **Related:** `Reasoning/`.

## 21. Bai et al. — "Constitutional AI" (2022, arXiv:2212.08073) / Lee et al. — RLAIF
(2023, arXiv:2309.00267) [F]
- **Category:** AI-feedback alignment. **Core ideas:** principles + critique/revision
  (Constitutional); AI-labels-instead-of-human (RLAIF). **Related:** `Post-Training/`,
  `Safety/`.

## 22. Asai et al. — Self-RAG (2023, arXiv:2310.11511, ICLR'24) / Microsoft GraphRAG
(2024, arXiv:2404.16135) [F]
- **Category:** advanced RAG. **Core ideas:** self-critiquing retrieval; graph +
  community summaries. **Related:** `RAG/`.

## 23. Su et al. — RoPE (2021, arXiv:2104.09864) / Press et al. — ALiBi (2022, arXiv:2108.12409) [F]
- **Category:** positional encodings. **Core ideas:** relative-position rotation;
  linear distance bias. **Related:** `Model-Architectures/Positional-Encodings.md`.

## 24. Frantar et al. — GPTQ (2022, arXiv:2210.17323) / Lin et al. — AWQ (2023,
arXiv:2306.00978) / Xiao et al. — SmoothQuant (2023, arXiv:2308.12388) [F]
- **Category:** quantization. **Core ideas:** Hessian-based 1D quant; activation-aware
  weight scaling; outlier migration. **Related:** `Quantization/`.

## 25. Zheng et al. — SGLang / RadixAttention (2023–24, arXiv:2312.07104; ICLS'24) [F]
- **Category:** serving. **Core ideas:** program-aware runtime; radix-tree prefix
  cache; zero-overhead-claimed scheduler. **Related:** `Serving-Engines/SGLang.md`.

---
*2026 preprints tracked in `Latest-Research/2026-08.md` (UNVERIFIED until reproduced):
DistillCache, RippleKV, CommitKV, SPECTRA, KVDiagnosis, DeaMoE, SPADE, MemSpec, DARTree,
OasisKV, vToken.*
