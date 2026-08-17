# Open-Source / Open-Weights Models
`LAST_UPDATED: 2026-08-16` · Status: current-coverage page (verified live 2026-08-16 where noted;
UNVERIFIED where not)

## Ecosystem facts (HuggingFace *State of Open Models: Summer 2026*, 2026-08-14 [F: HF blog])
- Public model repos: 2.43M → 2.96M (Jan–Aug 2026); 85.6% of models have <200 lifetime
  downloads; **1.5% of repos account for 99.2% of downloads** (extreme concentration).
- **Chinese labs' open-model ceiling: 754B–2.78T parameters monthly** in 2026; US models
  <130B in 5 of 7 months, exceptions: NVIDIA **Nemotron 3 Ultra (561B, May–Jun)** and
  Thinking Machines **Inkling**.
- **Qwen is "the community's base model"** — full-size-spectrum coverage from <1B up
  (Tencent & Alibaba cover the whole range; Moonshot/MiniMax/Xiaomi/Z.ai publish mostly
  ≥70B).
- Hardware vendors now ship open models to sell chips: AMD & NVIDIA each >200 new repos
  in 2026; LiquidAI ~100 (LFM2.5-2.6B [F: HF blog]).

## Families (status as of 2026-08)
| Family | Org | 2026-08 state (verified) | Notes |
|---|---|---|---|
| **Qwen** | Alibaba | **Qwen3.6-27B** (thinking mode) referenced in Muse Glimmer benchmark table [F: HF blog 2026-08-10]; Qwen = community base model [F: HF state report] | GQA, RoPE, SwiGLU; strong long-context; MoE variants |
| **Meta** | Meta | **Muse Glimmer 30B** (2026-08-10 [F: HF blog]): dense 30B multimodal (2B ViT perception encoder + 28B text decoder), **Apache-2.0**, local-agentic focus; day-0 vLLM/llama.cpp/transformers. Distilled from "Muse". | Llama line (3/3.1/3.2, 2024) [F: arXiv:2407.21783] remains the reference open decoder-only architecture; Llama 4 era UNVERIFIED details |
| **DeepSeek** | DeepSeek | V3/R1 (2024–25, arXiv:2412.19437 / arXiv:2501.12948 [F]) remain open frontier-class MoE + reasoning RL; latest 2026 release UNVERIFIED | MLA + MoE + GRPO; the open "reasoning" reference |
| **Mistral** | Mistral | Mixtral (2023 MoE [F: arXiv:2401.00592]), Large-2 (2024); latest UNVERIFIED | |
| **Gemma** | Google | Gemma 3 (2024 [F: HF]); 2026 status UNVERIFIED | open flagship |
| **Nemotron** | NVIDIA | Nemotron 3 Ultra 561B (2026-05/06 [F: HF state report]); Nemotron 3.5 Lightning (vision SLM, HF blog 2026 [F]) | hardware-vendor open models |
| **LiquidAI LFM** | LiquidAI | LFM2.5-2.6B (2026 [F: HF blog]) | edge line |
| **Thinking Machines Inkling** | TML | 2026 open model [F: HF state report] | |
| OLMo / OLMo 2 | Ai2 | OLMo 2 (2024 [F: arXiv:2502.08794]) — fully open (data+weights+code); 2026 status UNVERIFIED | transparency reference |
| Falcon / BLOOM / DBRX | TII / BigScience / Databricks | 2023-era open models [F]; legacy in 2026 | |

## Open vs Closed — measurable comparison (avoid ideology; use data)
| Dimension | Open-weights | Closed API |
|---|---|---|
| Weights | yes (subject to license) | no |
| Training transparency | varies: OLMo = full (data+code); most = partial | minimal |
| License | Apache-2.0 (Gemma, Muse Glimmer, Llama-class), CC, custom (Qwen, DeepSeek permissive) | API ToS |
| Fine-tuning | full (LoRA/full) | limited (provider fine-tune only) |
| Deployment | anywhere (incl. air-gapped, edge) | provider infra or licensed self-host |
| Privacy | data stays local | data sent to provider |
| Cost | compute (inference + quantization layer makes big models runnable — HF 2026 report notes this dependency) | per-token pricing |
| Performance frontier | within ~1–2 gens of closed (2025–26: DeepSeek/Qwen competitive; Muse Glimmer agentic benchmarks close to frontier on some suites [F: HF table]) | top of the range |
| **Hardware reqs** | the real constraint: 2.78T-param open models need clusters; the *quantization layer* (GGUF/NVFP4-class) is what makes big open models runnable [F: HF report] | none (provider) |

Empirical rule [I]: at a fixed *task*, the best open model within your hardware budget
often beats the best closed model you can *afford per token* — the open/closed line is
mostly an economics line.

## Related
`Frontier-Models/README.md` · `Quantization/README.md` (the runnable layer) ·
`Serving-Engines/README.md`.

## Key Takeaways
2026 open-weights landscape: Chinese labs set the size ceiling; Qwen is the default base;
hardware vendors ship open models to sell silicon; and the *quantization layer* is what
makes the big ones runnable at all.
