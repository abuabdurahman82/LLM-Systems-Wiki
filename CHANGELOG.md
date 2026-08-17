# CHANGELOG

## 2026-08-16 — Initial build
- Created wiki skeleton (33 sections → 48 content pages), master README, source policy, maintenance protocol.
- Live research pass (arXiv API + vendor news pages) on 2026-08-16; verified current frontier/open model landscape (Claude Opus 5/Sonnet 5/Fable 5, GPT-5.6 + Sol "Ultrafast", Gemini 3.7 Flash, Meta Muse Glimmer 30B, HF State of Open Models Summer 2026); recorded in `Latest-Research/2026-08.md`. Fetches retained in /tmp for audit.
- Core depth pages: Transformer fundamentals; The Life of a Token; Roofline; KV cache (+ eviction); Attention taxonomy; Quantization; Speculative decoding; Continuous batching; P/D disaggregation; Distributed inference; Inference metrics.
- Serving engine pages (vLLM / SGLang / TensorRT-LLM) written from an adversarially-reviewed architecture comparison (independent evaluator: FAIL on first draft → revised; 8/9 findings accepted after independent re-verification, 1 refuted).
- Milestones timeline (1948–2026), structured research paper index (25 papers), 10 lineage maps, glossary (~90 terms), Zero-to-Hero path (L0–L8), 80/20 guide, 12 hands-on labs.
- Sections: Foundations, Training, Post-Training, Reasoning, Agents, Harness Engineering, Context Engineering, RAG, Multimodal, Safety, Hardware, Networking, Evaluation, Benchmarks, Frontier-Models, Open-Source-Models.

### Evaluator review pass (independent evaluator, deepseek-v4-flash-0731 @ 10.1.1.51:8888)
- Scope: The Life of a Token, Transformer Fundamentals, Milestones, Attention taxonomy.
- Evaluator verdict: FAIL (confidence 90). Adjudication after independent re-verification:
  - **Accepted & fixed (5):** (a) 2003 word-embedding attribution → Bengio et al. (was mis-attributed to Mikolov/Schwenk); (b) attention per-layer complexity → O(S²·d + S·d²); (c) Chinchilla misdated on 2021 row → corrected; (d) DeepSeek-R1 moved from 2024 to 2025-01 row; (e) FlashInfer 2024 → 2025 (arXiv:2501.15907, ICLR'25).
  - **Partially accepted (2):** NVFP4 14.1 GiB clarified (4.5 bit/param incl. block-scale overhead; pure 4-bit = 12.6 GiB — original figure was a convention, now documented); missing seminal refs added (speculative decoding + Orca to Life-of-a-Token; LayerNorm + ALiBi to Transformer).
  - **Refuted (2):** (a) "NVFP4 is arithmetic-wrong" — 14.1 GiB was intentional 4.5-bit/param convention; (b) "2026 entries fabricated/fake URLs" — all six 2026 entries verified live on 2026-08-16 against fetched primary-source pages (audit trail added to Milestones.md); the evaluator (no web access) simply could not verify them, but they are [F]-tagged with real, reachable URLs.
- Post-fix status: key pages consistent; no known factual errors remaining in the reviewed set. Residual known gaps: DeepSeek/xAI 2026 releases UNVERIFIED; some 2025 rows compressed (per-item detail deferred to family pages).

## (template)
- date
- Added:
- Updated:
- Corrected:
- New papers:
