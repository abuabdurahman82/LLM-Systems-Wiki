# CHANGELOG

## 2026-08-17 — P/D disaggregation deep dive (quantitative + adversarially-reviewed)
- **New:** `Inference/Deep-Dives/pd-disaggregation-deep-dive-2026-08-17.md` — full deep-dive on prefill/decode disaggregation: hardware-characteristics first-principles, monolithic-vs-disaggregated data path, KV-transfer fabric physics (RDMA/RoCE/IB/NVLink/PCIe/GPUDirect), KV-aware routing, a Python-verified break-even model (KV size, 10→400 GbE transfer, prefill time, decode ITL, break-even prompt length, prefix-hit effect), a 6-experiment measurement design, recommended telemetry, break-even analysis, and a deployment decision tree.
- **Live research pass (2026-08-17):** re-verified primary sources — DistServe (arXiv:2401.09670, OSDI'24), Splitwise (arXiv:**2311.18677**), Mooncake (arXiv:2407.00079, **FAST'25 Best Paper**), vLLM disagg docs, Dynamo README, llm-d README; OPT-66B architecture verified from HF config (L=64, 72 MHA heads, d_h=128). Fetches + PDFs retained in /tmp/disagg for audit.
- **Corrected:** `Inference/Prefill-Decode-Disaggregation.md` — deepened with break-even model; **Splitwise arXiv ID fixed 2311.18698 → 2311.18677**; added Mooncake FAST'25 venue + DistServe low-node-affinity (same-node NVLink) placement detail.
- **Corrected:** `Research-Papers/README.md` item 18 — Splitwise arXiv ID → 2311.18677; Mooncake venue → FAST'25 Best Paper (was "(2024)").
- **Evaluator review pass (independent evaluator, deepseek-v4-flash-0731 @ 10.1.1.51:8888, two-pass):** Net **5 accepted / 2 refuted** after independent re-verification.
  - **Accepted & fixed (5):** (a) "invisible bandwidth" Gb/s off-by-8 unit error → all Gb/s figures re-expressed (16 GB/s = 128 Gb/s @ S=4k); (b) "100 GbE makes transfer effectively free for all prompt lengths" overstated → reworded to "13–16% at S≤16k, 7–12% at S≥64k"; (c) OPT-66B "1.13 GB is K-only, L=96" misreading → corrected to full K+V @ L=64/72heads/128 (verified from HF config); (d) DistServe 2.1×/1.6-vs-3.3-rps/90-Gbps figures verified correct as cited; (e) low-node-affinity label kept + counter-intuitive-naming clarifier added.
  - **Refuted (2):** (a) "70B Regime-1 rows wrong (1.84/1.16 → 0.46/0.29)" — evaluator computed 70B prefill at TP=1; draft explicitly uses TP=4, and at TP=4 the ratios are exactly 1.84/1.16; (b) "high-affinity = same-node" — the DistServe paper's §4.2 low-node-affinity algorithm *is* the same-node NVLink one; evaluator's reverse reading is wrong. Both documented in the deep-dive's §13 adjudication table.
- **Status:** P/D disaggregation is now a first-class, quantitatively-grounded, adversarially-reviewed topic in the wiki. Residual gaps: H1–H7 are labelled unverified experimental hypotheses; MFU/TP-eff/line-rate/RTT are stated [A] assumptions; vendor benchmarks tagged vendor-reported.

## 2026-08-18 — Inference-optimization content promoted into the wiki
- Added `Inference/Inference-Optimization.md` (core page: measured ground-truth table, technique×effect summary, 7 workload profiles, evidence-challenged ladder, scorecard, TOP-5 experiments, limitations) and `Inference/Deep-Dives/inference-optimization-ladder-2026-08-17.md` (full 402-line two-pass-evaluated deliverable, copied from `~/inference-optimization-2026-08-17.md`).
- `_sidebar.md`: new Inference sub-entries (Inference-Optimization + both deep dives); removed the temporary top-level deliverable symlink.

## 2026-08-17 — Inference-optimization research session (external doc)
- Ran a live measurement suite against the local vLLM endpoint (DeepSeek-V4-Flash-0731, TP=2/2-nodes): prefill sweep 447→97k tokens, prefix-cache cold/warm pair, 12-concurrent throughput, 3×16k concurrent-prefill staircase, long-decode at 32k. Raw JSON: /tmp/infopt/results/ (session-scoped; kept out of the wiki per evidence hygiene).
- Added `Labs/Lab 13` (executed prefix-cache causal-delta measurement, 2026-08-17): 8.7× TTFT cold→warm on an 8k identical prefix; cached-prefix processing ~17.6k tok/s vs ~2.0k cold.
- Full optimization-ladder research document (technique effect table, 7 workload profiles, evidence-challenged ladder, scorecard, TOP-5 experiments) produced under /tmp/infopt/draft.md and sent through the independent-evaluator pipeline (two-pass, deepseek-v4-flash-0731 @ 10.1.1.51:8888). **8 flags adjudicated: 6 accepted (as fixes or convention-clarifications), 2 refuted** after independent re-verification. Refuted: (a) "experts 278.1 B is 43× too high" — evaluator dropped the 43-layer multiplier; (b) pass-2 "total 283.3 B should be 283.4 B" — 283.34 rounds to 283.3. Accepted: bandwidth ceiling now states both single-node (79 tok/s) and 2-node aggregate (157 tok/s) readings → B=1 decode 5.1×–10.2× under ceiling; active-params corrected 11.7→12.8 B (shared expert added); KV-vs-BF16 corrected 8×→3.6× (and raw-4-bit 4.0× shown alongside); MLA-vs-MHA re-expressed as the precision-independent 85×. NOT a wiki page — wiki remains a knowledge base; the ladder doc is a /tmp deliverable.

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
