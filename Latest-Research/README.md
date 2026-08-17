# Latest Research Dashboard
`LAST_UPDATED: 2026-08-16` · Status: rolling dashboard (refresh weekly via arXiv API + vendor
news; significance-rated)

## Significance scale
- ★★★★★ Potential paradigm shift
- ★★★★ Major development
- ★★★ Important incremental advance
- ★★ Specialized contribution
- ★ Early / uncertain

Classification honesty rule: a preprint is ★★-★★★ at best until independently reproduced.
Vendor announcements are not research results.

## Where the buckets live
- **Last 7 days / 30 days / 90 days:** the current monthly page
  (`2026-08.md`) is the live bucket; rotate monthly (new `YYYY-MM.md`).
- **Major 2026 developments:** see below (cumulative).
- **Emerging research directions:** see "Radar" below.

## Major 2026 developments (verified live, [F])
1. **Frontier "effort tiers"** — Opus 5 / Sonnet 5 (Anthropic), GPT-5.6 + Sol "Ultrafast"
   (OpenAI), Gemini 3.7 Flash (Google): test-time compute as an explicit product knob
   (effort levels, speed modes). ★★★★
2. **Meta back with open multimodal** — Muse Glimmer 30B Apache-2.0 (2026-08-10): local
   agentic multimodal (2B ViT encoder + 28B decoder), day-0 vLLM/llama.cpp. ★★★★
3. **Open-weights geopolitics documented** — HF State of Open Models Summer 2026
   (2026-08-14): Chinese-lab open ceiling 754B–2.78T; US <130B in 5/7 months; Qwen =
   community base model; 1.5% of repos = 99.2% of downloads. ★★★★
4. **Reproducibility at agent scale** — HF "Reproducing 2,200 ICML papers" (2026-08-13):
   1,200+ contributors, 6,816 logbooks, 2,226 of 6,352 accepted papers reproduced in
   19 days; falsifications found that human review missed. ★★★ (meta-science)
5. **KV-cache research accelerating** (2026-08 preprints, ★★ each, UNVERIFIED):
   transform-coding KV (SPECTRA, "2-bit cliff"), lifecycle-aware agent KV (CommitKV),
   cross-layer allocation (RippleKV), diagnostic benchmark (KVDiagnosis),
   virtualized reclaimable KV (vToken).
6. **MoE systems research** (2026-08, ★★ UNVERIFIED): small-batch-friendly MoE
   (DeaMoE), high-bandwidth-flash MoE serving, expert placement for MoE-RL (RoutePack),
   systems-aware (not just compute-optimal) MoE scaling.
7. **Speculative decoding edge/edge-cloud** (2026-08, ★★ UNVERIFIED): SPADE, MemSpec,
   DARTree (diffusion drafting), LibraSpec.

## Emerging research radar (§38; MATURE / GROWING / EMERGING / EXPERIMENTAL)
| Topic | Status (2026-08) | Note |
|---|---|---|
| Prefill/decode disaggregation | MATURE | Mooncake/Dynamo/llm-d production [F] |
| Paged KV + prefix caching | MATURE | vLLM/SGLang/TRT-LLM [F] |
| FP8/NVFP4 quantized serving | MATURE | datacenter default [F] |
| Speculative decoding | GROWING | EAGLE/MTP production; edge variants experimental |
| KV eviction/compression | GROWING | heuristics (H2O/SnapKV) mature; learned/lifecycle-aware emerging (2026 preprints) |
| Reasoning RL (GRPO/RLVR) | MATURE | R1-line consensus [F] |
| Adaptive thinking budgets | GROWING | effort-levels shipped [F]; optimal-scheduling research open |
| Agentic AI / coding agents | GROWING | dominant 2025–26 category [F: vendors] |
| Harness engineering | GROWING | no consensus metrics yet; model-vs-harness split open [I] |
| Context engineering | GROWING | compaction/retrieval-as-tool standard in harnesses |
| Long context (>128k) | GROWING | 1M+ windows exist [F: Gemini 1.5+]; usable-length gap persists [I] |
| MLA / latent attention | GROWING | DeepSeek-line; adoption spreading [I] |
| SSM / hybrid architectures | EMERGING | Mamba-2, Jamba; long-ctx recall contested [I] |
| MoE at 1T+ open | GROWING | 2026 open ceiling 2.78T [F: HF] |
| P/D disaggregation on NVL72 | GROWING | NVL72 makes KV transfer cheap intra-pod [I] |
| World models / embodied | EMERGING | Genie 3, SIMA 2, Gemini Robotics ER 2 [F] |
| Inference on HBF / near-memory | EXPERIMENTAL | 2026-08 preprints (HBF serving, ReRAM near-memory MoE) |
| Deterministic/reproducible inference | EMERGING | CoRun (padding for determinism, 2026-08 preprint) |
| Operator-level autoscaling | EMERGING | OpScale (2026-08 preprint) |

## Maintenance
Refresh: run arXiv scan (serving/kv/specdec/reasoning/moe/attention queries, descending
date) + vendor news (openai.com RSS, anthropic.com/news, deepmind.google, huggingface.co/blog)
→ triage into buckets → rate significance → move last month's page to archive. Log in
CHANGELOG.

## Related
`2026-08.md` · `Milestones.md` · `Research-Papers/README.md`.
