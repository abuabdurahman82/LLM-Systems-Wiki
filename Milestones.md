# Major Milestones Dashboard

Only historically significant developments. Format: Date | Milestone | Area | Previous Limitation | Innovation | Long-Term Impact.
`LAST_UPDATED: 2026-08-16`. Pre-2017 entries are well-established history [F]; 2025–2026 entries are [F: verified live 2026-08-16] or UNVERIFIED.

| Date | Milestone | Area | Previous Limitation | Innovation | Long-Term Impact |
|---|---|---|---|---|---|
| 1948 | Shannon, "A Mathematical Theory of Communication" | Info theory | No quantitative theory of information | Entropy, channel capacity | The objective function every probabilistic LM optimizes is Shannon entropy |
| 1957/1958 | Rosenblatt perceptron | DL | No trainable machine "neuron" | Weighted sum + step activation, delta rule | The learning-rule lineage of all modern training |
| 1986 | Backpropagation (Rumelhart, Hinton, Williams) | DL | Training only shallow nets | Gradients through layers via chain rule | Made deep training feasible |
| 2003 | Neural word embeddings (Bengio, Ducharme, Vincent, Jauvin — "A Neural Probabilistic Language Model", JMLR) | Embeddings | Bag-of-words lost word meaning | Neural distributed representations | Direct ancestor of modern embeddings; Mikolov's word2vec (2013) built on this lineage |
| 2013 | word2vec / GloVe (Mikolov et al.; Pennington) | Embeddings | Count-based matrices don't scale | Sublinear training, skip-gram / n-grams | Showed geometry of vectors captures semantics |
| 2014 | Seq2Seq + attention (Cho et al., Bahdanau et al.) | Seq models | Fixed-length bottleneck vector | Encoder–decoder + attention alignment | The attention mechanism was born |
| 2017 | Transformer, "Attention Is All You Need" (Vaswani et al., Google) | Architecture | RNN sequentiality, vanishing gradients | Self-attention, fully parallel | The architecture of every LLM today |
| 2018 | GPT-1 / BERT | LLMs | Task-specific models | Large pretrained LM; bidirectional masked LM | Pretrain-then-fine-tune paradigm |
| 2019 | GPT-2 | LLMs | 117M-param LMs | 1.5B zero-shot capable model | Emergent abilities; first safety-held-back release |
| 2020 | GPT-3 (OpenAI) | LLMs | Fine-tuning per task | 175B in-context learning | Scaling + prompting paradigm |
| 2021 | Codex; GPT-3-era scaling research | LLMs/reasoning | — | Code LMs; early scaling studies | Scaling-law discipline matured with Kaplan 2020 + Chinchilla 2022 |
| 2022 | InstructGPT → ChatGPT (RLHF); PaLM; FlashAttention (Dao et al.) | Post-training/Inference | Unaligned base models; O(S²) attention HBM | PPO preference alignment; IO-aware exact attention | Aligned assistants; long-context inference unlocked |
| 2023 | LLaMA; GPT-4; Mistral/Mixtral (MoE); vLLM + PagedAttention (Kwon et al., SOSP'23); EAGLE; Medusa | Ecosystem | Closed frontier; KV memory fragmentation | Open LMs; MoE; paged KV; speculative decoding | Open-weights ecosystem; modern serving stack |
| 2024 | Llama 3; Claude 3; Gemini 1.5 (1M ctx); DeepSeek-V2/V3 (MoE); Qwen2; o1 (test-time compute); SGLang | Frontier/Inference/Reasoning | Context limits; dense scaling cost | 1M-token windows; MoE frontier; latent attention (MLA); CoT-by-RL | Reasoning models; test-time compute; open frontier-class MoE |
| 2025-01 | DeepSeek-R1 (reasoning RL, GRPO) [F: arXiv:2501.12948] | Reasoning | — | open reproduction of o1-class reasoning RL + distillation | "reasoning RL is a post-training technique" consensus |
| 2025 | GPT-4.5/5 family; Claude 4.x; Gemini 2.x/3; DeepSeek-V3/R1 open; KV quant & eviction work; NVFP4-class 4-bit datacenter | Frontier | — | 4-bit datacenter serving; learned/eviction KV; agentic coding | Inference economics; agent-era models |
| 2026-06 | Claude Sonnet 5 (Anthropic) [F: anthropic.com/news, 2026-06-30] | Frontier/agentic | Sonnet 4.6 below Opus 4.8 on agentic tasks | Agentic Sonnet: planning, browser/terminal tools, autonomous runs; $2/$10 per MTok | Agentic capability at mid-tier price |
| 2026-07 | Claude Opus 5 [F: anthropic.com/news, 2026-07-24] | Frontier | Opus 4.8 ceiling | New SOTA coding/knowledge-work (Frontier-Bench, GDPval-AA, ARC-AGI 3, OSWorld 2.0) at Opus 4.8 cost; effort-level tuning | Cost-performance frontier shifts to "effort" as first-class knob |
| 2026-08-02 | Gemini 3.7 Flash [F: deepmind.google] | Frontier | — | New Flash-tier generation | Cost-efficient frontier |
| 2026-08-10 | Meta Muse Glimmer 30B [F: HF blog 2026-08-10] | Open models | Meta Llama line paused | Dense 30B multimodal (2B ViT encoder + 28B decoder), Apache-2.0, local agentic focus, day-0 vLLM/llama.cpp/transformers | Open local-agentic models re-enter the race |
| 2026-08-13 | OpenAI GPT-5.6 series; "Ultrafast" GPT-5.6 Sol up to 14× speed [F: openai.com RSS 2026-08-13] | Frontier/inference | — | Latency-tiered frontier (Sol/Luna tiers; speed modes) | Speed as explicit product dimension |
| 2026-08-14 | HF State of Open Models: Summer 2026 [F: HF blog] | Open ecosystem | — | Data: Chinese-lab open ceiling 754B–2.78T params; US <130B in 5/7 months (excl. Nemotron 3 Ultra 561B); Qwen = community base model; 1.5% of repos = 99.2% of downloads | Open-weights geopolitics & distribution shape documented |
| 2026-08-23 | `Production-Operations/` Wiki section [I, this repo] | Operations/SRE | Serving/routing documented but reliability discipline not unified | 41-page LLM Reliability, SRE & Production Ops handbook (SLI/SLO/SLA, goodput, golden signals, failure taxonomy, GPU/distributed/KV reliability, incident/runbook/postmortem discipline, DR, cost/agent/RAG SRE) + 12 labs | Operations treated as a first-class LLM-engineering discipline |
| 2026-08-24 | `Platform-Economics/` Wiki section [I, this repo] | Economics/Governance | Shared LLM serving documented, but multi-tenant *economics & governance* not unified | 57-page Multi-Tenant LLM Platform Economics & Governance handbook (unit economics, utilization/queueing, token/KV/cache/batching economics, metering, showback/chargeback, pricing, tiers, SLO economics, fairness, noisy neighbor, quotas, admission, budget routing, isolation, data/model/policy governance, cloud burst, FinOps, waste, agents/evaluators/RAG/context/multimodal, goodput, energy, failure cost, GPUaaS/K8s, reference arch, 80/20 + Zero-to-Hero + decision framework + formulas + anti-patterns) + 15 labs + economic simulator | Cost / governance treated as a first-class discipline for shared AI infrastructure |

## 2026 entries (verified live against fetched primary-source pages on 2026-08-16:
anthropic.com/news/claude-opus-5, /claude-sonnet-5, deepmind.google/discover/blog,
openai.com RSS, huggingface.co/blog/state-of-open-models-summer-2026 and /muse-glimmer;
fetches retained in /tmp for audit). Benchmark names/dates below are as published in
those pages; performance numbers remain vendor-reported claims, not independent results.

## Notes
- 2017–2024 rows are well-established [F] (papers listed in `Research-Papers/`).
- 2025 rows are a compressed summary; per-item verification lives in `Latest-Research/` and the model-family pages (UNVERIFIED where not confirmed live).
- DeepSeek & xAI latest releases: UNVERIFIED as of 2026-08-16 (vendor sites not reachable at research time).
