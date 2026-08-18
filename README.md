# LLM Wiki — A Living Encyclopedia of Large Language Models

> **Status:** LIVING · **LAST_UPDATED:** 2026-08-16 · **SOURCE_DATE:** 2026-08-16 · **RESEARCH_STATUS:** initial build complete; current-coverage sections verified against live sources on 2026-08-16
>
> How it reads: `MATH → TRANSFORMERS → TRAINING → POST-TRAINING → REASONING → INFERENCE → OPTIMIZATION → DISTRIBUTED SYSTEMS → AGENTS → HARNESS ENGINEERING → CURRENT RESEARCH`

---

## What this is

A structured, cross-linked technical knowledge base covering the evolution of LLMs from
foundational ideas (information theory, perceptrons, backpropagation, word embeddings, RNNs,
seq2seq, attention) to the state of the art as of **2026-08-16** (verified against live
primary sources on that date).

For every major topic the wiki answers:
- **what** happened / what it is
- **why** it mattered — the technical problem it solved
- **how** it works — mechanism + mathematics
- **what limitations remained**
- **what research followed** (see `Research-Lineage/`)
- **how it changed** modern architecture, training, inference, agents, or deployment

## Audience
AI engineers · inference engineers · researchers · infrastructure architects · graduate students · zero-to-advanced learners.
`Learning-Path/` gives a levelled route through everything.

## Source policy (strict)
Claims carry a tag:

| Tag | Meaning |
|---|---|
| `[F]` | Verified primary source (paper / official docs / official blog / repo) — link given |
| `[E]` | Empirically verified in this environment (measurement / computation) |
| `[I]` | Inference by the author (stated as such, not presented as fact) |
| `[A]` | Assumption |
| `UNVERIFIED` | Could not be verified at research time — do not rely on it |

**Never:** invented paper names, authors, dates, model sizes, benchmark scores, or citations.
Marketing claims are labelled *vendor claim* and are never presented as independent results.

## Source tiers
1. Original research papers (peer-reviewed first: NeurIPS, ICML, ICLR, ACL, EMNLP, MLSys, OSDI, SOSP, USENIX)
2. arXiv preprints (labelled preprint)
3. Official model technical reports
4. Official GitHub repos
5. Official engineering documentation
6. Official company research blogs
7. Reputable secondary analysis (only when 1–6 are insufficient, labelled as such)

Key source orgs: arXiv · OpenAI · Anthropic · Google DeepMind · Meta AI · Microsoft · Alibaba/Qwen · DeepSeek · Mistral · xAI · Hugging Face · vLLM · SGLang · NVIDIA TRT-LLM/Dynamo · llm-d · PyTorch · JAX · Megatron-LM · DeepSpeed.

## Layout (top level)

```
LLM-Wiki/
├── README.md                  ← you are here
├── CHANGELOG.md               ← maintenance log (required per protocol §48)
├── Milestones.md              ← major milestones dashboard (§36)
├── Foundations/               ← pre-LLM history: information theory → RNN → seq2seq → attention
├── Transformer/               ← first-principles learning path (tokens→logits, math, toy examples)
├── Model-Architectures/       ← encoder/decoder, MoE, MHA/MQA/GQA, RoPE/ALiBi, RMSNorm, SwiGLU, SSM, hybrids
├── Training/                  ← data, pretraining, scaling laws, distributed training, comms
├── Post-Training/             ← SFT, RLHF/PPO, DPO, GRPO, RLAIF, distillation, alignment & RLHF lineage
├── Reasoning/                 ← CoT, ToT, ReAct, process supervision, test-time compute, RL for reasoning
├── Inference/                 ← The Life of a Token, Roofline, continuous batching, P/D disaggregation (+ Deep-Dives/), metrics, inference optimization
├── KV-Cache/                  ← shapes, memory equation, PagedAttention, eviction, compression, offloading
├── Attention/                 ← attention taxonomy (architecture vs kernel vs memory strategy)
├── Quantization/              ← FP16/BF16/FP8/INT8/INT4/FP4, GPTQ/AWQ/SmoothQuant/GGUF/NVFP4
├── Speculative-Decoding/      ← draft-verify, Medusa, EAGLE, MTP, production practice
├── Serving-Engines/           ← vLLM, SGLang, TensorRT-LLM, llama.cpp, TGI, MLC
├── Distributed-Inference/     ← DP/TP/PP/EP/CP/SP with comm patterns + hardware
├── Agents/                    ← LLM→tool use→agent→multi-agent
├── Harness-Engineering/       ← system scaffolding; model-vs-harness question
├── Context-Engineering/       ← prompt vs context vs harness; memory, retrieval, prefix caching
├── RAG/                       ← full pipeline + advanced RAG (hybrid, graph, agentic, self-RAG)
├── Multimodal/                ← text/image/audio/video/speech/robotics strategies
├── Evaluation/                ← benchmark families, contamination, saturation
├── Open-Source-Models/        ← Qwen, Llama/Meta, DeepSeek, Mistral, Gemma, OLMo, Falcon, BLOOM…
├── Frontier-Models/           ← GPT-5.x, Claude (Opus 5/Sonnet 5/Fable 5/Mythos 5), Gemini 3.x (verified 2026-08)
├── Hardware/                  ← GPU archs, HBM, NVLink/NVSwitch, PCIe, InfiniBand, RoCE, DPU
├── Networking/                ← NCCL, RDMA, collectives, SHARP, GPUDirect — tied to TP/EP/PD
├── Research-Papers/           ← structured paper database (§33 format)
├── Research-Lineage/          ← idea-influence maps (Transformer→MHA→MQA→GQA, etc.)
├── Latest-Research/           ← rolling dashboard (7/30/90 days) + monthly pages (YYYY-MM.md)
├── Benchmarks/                ← what each benchmark tests / does not test
├── Glossary/                  ← cross-linked term index
├── Learning-Path/             ← Zero-to-Hero levels 0–8 + 80/20 guide
└── Labs/                      ← 12 hands-on research labs (hypothesis→commands→interpretation)
```

## Reading guide
- **Zero to hero:** start `Foundations/` → `Transformer/` → `Inference/The-Life-of-a-Token.md` → `KV-Cache/` → `Training/` → `Post-Training/` → `Reasoning/` → `Agents/` → `Latest-Research/`.
- **Inference engineer:** `Inference/The-Life-of-a-Token.md` → `Inference/Roofline.md` → `Inference/Inference-Optimization.md` (what to apply FIRST, measured) → `Attention/` → `KV-Cache/` → `Serving-Engines/` → `Distributed-Inference/` → `Quantization/` → `Speculative-Decoding/`.
- **Researcher:** `Research-Papers/` → `Research-Lineage/` → `Evaluation/` → `Latest-Research/` → open questions in each section.

## The ten questions this wiki must answer
1. How did modern LLMs evolve? → `Milestones.md`, `Foundations/`, `Model-Architectures/`
2. Why were the important innovations invented? → every page's *Why This Exists / Problem It Solves*
3. How do modern LLMs work internally? → `Transformer/`, `Inference/The-Life-of-a-Token.md`
4. How are they trained? → `Training/`
5. How are they served efficiently? → `Inference/`, `Serving-Engines/`, `Distributed-Inference/`
6. How do reasoning models work? → `Reasoning/`
7. How do agents extend models? → `Agents/`, `Harness-Engineering/`, `Context-Engineering/`
8. What are the major research milestones? → `Milestones.md`
9. What is the current state of the art? → `Latest-Research/`, `Frontier-Models/`, `Open-Source-Models/`
10. What directions are emerging next? → `Latest-Research/README.md` radar, open-question lists

## Maintenance protocol (living wiki, §48)
On any update:
1. discover new research (arXiv API + vendor news); 2. diff against existing pages; 3. update **only affected sections**; 4. preserve historical context; 5. add new papers to `Research-Papers/`; 6. update `Milestones.md` when justified; 7. update lineage maps; 8. run the evaluator model (DeepSeek class, independent endpoint) on important changed pages and record its verdict; 9. record the change in `CHANGELOG.md` with `LAST_UPDATED` on the page.

## Verified-current snapshot (2026-08-16)
Frontier (primary sources): OpenAI GPT-5.6 series incl. "Ultrafast" Sol mode (openai.com RSS, 2026-08-13); Anthropic Claude Opus 5 (2026-07-24), Sonnet 5 (2026-06-30), plus Fable 5 / Mythos 5 tiers (anthropic.com/news); Google Gemini 3.7 Flash (Aug 2026, deepmind.google). Open-weights: Meta Muse Glimmer 30B Apache-2.0 (2026-08-10, HF blog); HuggingFace *State of Open Models: Summer 2026* (2026-08-14): Chinese-lab open model ceiling 754B–2.78T params; NVIDIA Nemotron 3 Ultra 561B; Qwen as de-facto community base model. DeepSeeK/xAI latest releases: UNVERIFIED at research time.
