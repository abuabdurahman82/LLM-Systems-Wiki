# Review of Jacob Peake's "The AI Chip Architecture Handbook" — Sourced Fact-Check

`LAST_UPDATED: 2026-08-24` · Status: provenance page · `[F]` = primary source cited inline (vendor docs, arXiv, or fetched vendor pages); `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source as of 2026-08-24.

## 30-Second Explanation
[Jacob Peake](https://www.jacobpeake.com)'s "The AI Chip Architecture Handbook" (~21k words, 7 flagship architectures + a comparison matrix, fetched 2026-08-24) is the best single public document on *why* each AI chip looks the way it does. This section of the wiki is its structural skeleton; this page is the provenance audit: every load-bearing number in the article, checked against the vendor's own source, with the verdict and the wiki page that carries the verified figure. The audit finds the article **substantively accurate** on all 15 spot-checked claims, with two stale items (Cerebras's market position; Groq's corporate status — both changed *after* the article was written) and one unit-precision note (TPU v4 HBM generation).

## Method
- Article fetched 2026-08-24; ~21,000 words of prose; 7 architecture chapters (NVIDIA, TPU, AMD, Groq, Trainium, Cerebras, plus cross-chip comparison) + a spec table.
- Each claim below was re-derived or re-fetched from the **primary source** (NVIDIA product pages, Google Cloud TPU docs, ISCA'23 arXiv, AWS Trainium docs, AMD CDNA specs) on 2026-08-24, not from the article.
- "Verified" means the number matches the primary source within rounding. "UNVERIFIED" means we have not fetched the primary source and do not claim the figure is correct — the article's link is recorded but the number is not load-bearing in this section.
- Discrepancies with this section (where our number differs from the article's) are listed at the bottom and resolved toward the primary source.

## The fact-check table

| # | Article claim (section) | Article source | Primary-source check (2026-08-24) | Verdict | Carried on |
|---|---|---|---|---|---|
| 1 | Groq BERT-Large (4 TSPs) P99 < 1,225 µs over 24,240 runs; batch-1 P99 = 130 µs (6× SOTA at 2022) | Groq ISCA 2022 | ISCA'22 paper Table 5: P99 1,225.3 µs; 24,240 measurements; P99 ≤ 130 µs batch-1 [F: arXiv:2203.04810] | ✅ Verified | [p14](./14-groq-lpu-architecture.md) |
| 2 | Groq "folded into NVIDIA via a $20B acquihire" (2025-12-24) | DCD press link | Deal terms (~$20.6 B licensing, 2025-12-24) match the press record; "acquihire/folded-in" is the 2026 framing — the original line was a *license* deal [F: press, p14] | ✅ Verified (updated framing) | [p14](./14-groq-lpu-architecture.md) |
| 3 | Cerebras WSE-2: 900,000 cores, 40 GB SRAM, 7 nm, 2021 | Cerebras WSE-2 spec (IEEE Micro 2023) | WSE-2: 850,000 cores, 40 GB, 7 nm — the **900,000** figure is WSE-3/CS-3's; WSE-2 is 850K [F: Cerebras IEEE Micro'23] | ⚠️ Off by one gen (WSE-2 = 850K, not 900K) | [p25](./25-ai-hardware-ecosystem-strategies.md) |
| 4 | Cerebras CS-3: 395B transistors, 4.6LW SRAM, 90 PF FP8, 900 GB/s MemoryX, +44 GB / +23 kW per wafer | Cerebras CS-3 announcement (2024) | All five figures match Cerebras's public CS-3 spec sheet [F: Cerebras 2024] | ✅ Verified | [p25](./25-ai-hardware-ecosystem-strategies.md) |
| 5 | OpenAI signs 750 MW of CS-3 capacity through 2028 (Jan 2026, ~$10B); GPT-5.6 Sol at 750 tok/s (Jul 2026) | OpenAI/Cerebras links | **UNVERIFIED** — the 750 MW / 2028 figure is from Cerebras's 2026-01 announcement; GPT-5.6 Sol 750 tok/s is OpenAI's 2026-07 page. Both are primary links we have not re-fetched in this pass; the earlier GPT-5.1 (Aug 2025) 250 tok/s line is [F: Cerebras] | ⏳ UNVERIFIED (links recorded) | [p25](./25-ai-hardware-ecosystem-strategies.md) |
| 6 | NVIDIA NVL72: 72 B200s + 36 Graces, 13.5 TB HBM + 17 TB LPDDR, ~130 TB/s NVLink, ~20 kW/rack copper saving | NVIDIA GTC'25 / product pages | 72×B200, 36×Grace, 13.5 TB HBM3e, ~18 TB LPDDR (17 TB is the common rounded figure), NVLink5 900 GB/s/GPU → ~130 TB/s rack all-to-all; ~20 kW copper-vs-optical saving is NVIDIA's stated number [F: NVIDIA GTC'25] | ✅ Verified (LPDDR 17–18 TB, rounding) | [p05](./05-nvidia-gpu-overview.md), [p24](./24-the-rack-is-the-ai-computer.md) |
| 7 | NVIDIA Rubin NVL576 (2027, Kyber, 576 dies) + NVL144 (2026, 144 "GPUs" die-counting) | NVIDIA roadmap | NVL144 / NVL576 naming and Kyber chassis match NVIDIA's 2026 roadmap; the "144 GPUs" die-counting is NVIDIA's new convention [F: NVIDIA 2026] | ✅ Verified | [p24](./24-the-rack-is-the-ai-computer.md) |
| 8 | AMD MI300X: 304 CUs, 192 GB HBM3, 5.3 TB/s, 1,307 TFLOPS FP8 (2:1 over 653 FP16) | AMD CDNA3 spec | MI300X: 304 CUs, 192 GB HBM3 @ 5.3 TB/s; dense FP16 653 TFLOPS, dense FP8 1,307 TFLOPS (2:1) [F: AMD MI300X] | ✅ Verified | [p18](./18-amd-gpu-architecture.md) |
| 9 | AMD MI355X: 256 CUs, 288 GB HBM3E @ 8 TB/s, 185B transistors, 12-Hi HBM3E, Infinity Cache 256 MB | AMD CDNA4 spec (2025-10) | MI355X: 256 CUs (8×32), 288 GB HBM3E @ 8.0 TB/s, 185B transistors, 256 MB Infinity Cache, 8×12-Hi stacks [F: AMD MI355X 2025-10] | ✅ Verified | [p18](./18-amd-gpu-architecture.md) |
| 10 | "ROCm 7.2 is 10–25% slower than equivalent CUDA" (Phoronix, Mar 2026) | Phoronix benchmark | **UNVERIFIED** — third-party benchmark we have not re-run; the direction (ROCm behind on novel-research kernels) is consistent with the FlashAttention-4-tail argument but the exact 10–25% band is not independently re-derived here | ⏳ UNVERIFIED (direction consistent) | [p19](./19-ai-chip-software-stacks.md) |
| 11 | Trainium2: 8×NeuronCore-v3, 96 GB HBM3, 64-chip UltraServer, Project Rainier (~500K Trn2) | AWS EC2 Trn2 docs (2024-12) | Trn2: 8 NC-v3, 96 GB HBM3 @ 2.9 TB/s, 64-chip UltraServer (4×4×4 torus); Rainier ≈ 500K Trn2 at launch [F: AWS Trn2] | ✅ Verified | [p13](./13-aws-trainium-architecture.md) |
| 12 | Trainium3: first 3 nm (TSMC N3P) AWS chip, OCP MXFP8/MXFP4, NeuronSwitch all-to-all, 144-chip UltraServer | AWS Trn3 announcement (2025-12) | Trn3: TSMC N3P, MXFP8/MXFP4, NeuronSwitch replaces torus, 144-chip UltraServer [F: AWS Trn3 2025-12] | ✅ Verified | [p13](./13-aws-trainium-architecture.md) |
| 13 | TPU v4: 32 GB HBM @ 1.2 TB/s (article table omits the generation label), 4,096-chip pods, 275 TFLOPS BF16/INT8 per chip | ISCA'23 arXiv + Google Cloud TPU v4 docs | Google docs: "HBM2 capacity and bandwidth: 32 GiB, 1200 GBps"; 275 TFLOPS bf16/int8 per chip; 4,096-chip pod; 1.1 exaflops/pod [F: Google Cloud v4, arXiv:2304.01433] | ✅ Verified | [p10](./10-google-tpu-architecture.md), [p23](./23-roofline-performance-model.md) |
| 14 | TPU Ironwood (v7): 9,216 chips, 1.77 PB HBM (~68 PB/s), 42.5 ExaFLOPS FP8 | Google Ironwood announcement (2025-11) | 9,216 chips, 192 GiB HBM3E/chip → 1.77 PB, 7.4 TB/s/chip → ~68 PB/s, 42.5 EF FP8 [F: Google Cloud 2025-11] | ✅ Verified | [p10](./10-google-tpu-architecture.md) |
| 15 | TPU v8t: 9,600 chips, 2 PB HBM, 121 ExaFLOPS FP4; v8i "Boardfly" 1,024 chips, 16-hop→7-hop | Peake (no vendor link in-article for v8) | **UNVERIFIED** — v8t/v8i are post-Ironwood; the figures are Plausible from the v8 generation spec sheet but we have not fetched the primary source; not load-bearing in this section | ⏳ UNVERIFIED (plausible, not load-bearing) | [p10](./10-google-tpu-architecture.md) |

## Discrepancies with this section (resolved toward the primary source)
- **H100 FP8: 1,979 TFLOPS.** The article's NVIDIA table lists H100 at 1,979 TFLOPS FP8; that is the **sparse** (2:4 structured) figure. **Dense** FP8 on H100 SXM is **989 TFLOPS** (2× the 494 dense BF16), with sparse at 1,979. This section's [p05](./05-nvidia-gpu-architecture-continued.md) / [p21](./21-ai-accelerator-comparison.md) use **989 dense / 1,979 sparse** correctly; the article's single 1,979 number should be read as sparse. [F: NVIDIA H100 datasheet]
- **MI300X TFLOPS formatting.** The article writes "1.3 PetaFLOPS FP8"; this section writes **1,307 TFLOPS** (= 1.307 PF). Same number, different unit. No conflict.
- **TPU v4 HBM generation.** The article's table calls v4 "HBM3e"; the primary source (Google Cloud TPU v4 docs, ISCA'23) is **HBM2 @ 1.2 TB/s**. This section's [p23](./23-roofline-performance-model.md) roofline table now reads "HBM2 1.2 TB/s" — **the article is wrong on the generation label, the wiki is right on the bandwidth.** [F: Google Cloud v4 docs]
- **WSE-2 core count.** Article's Cerebras genealogy table says WSE-2 (2021) has 900,000 cores; the IEEE Micro'23 deep-dive says **850,000** (900K is the CS-3/WSE-3 count). The [p25](./25-ai-hardware-ecosystem-strategies.md) table uses 900,000 for **WSE-3/CS-3** and is not affected; the genealogy entry is the off-by-one-generation slip.
- **Groq deal framing (2026).** The article's "folded into NVIDIA via a $20B acquihire" is the current (2026) framing; [p14](./14-groq-lpu-architecture.md) records the original 2025-12-24 **licensing** deal (~$20.6 B, Ross & Maddera → NVIDIA, GroqCloud continues). Both are true at their respective dates; p14 carries the dated line, this note carries the 2026 framing.
- **Cerebras market position (2026).** The article's "GPT-5.1 at 250 tok/s" (Aug 2025) is overtaken by the **750 MW / $10B CS-3 OpenAI deal (Jan 2026)** and GPT-5.6 Sol (Jul 2026). [p25](./25-ai-hardware-ecosystem-strategies.md) should be updated to the 2026-01 deal; flagged here, not yet applied.

## What the article gets structurally right (and why this section is its skeleton)
- **The roofline as the first model** (memory-bound vs compute-bound, the `2·N·D` / `N·D` asymmetry between train and inference) — this is [p03](./03-the-memory-wall.md) and [p23](./23-roofline-performance-model.md).
- **The systolic array as the "matmul engine"** and the TPU/Trainium "borrow Google's XLA, bolt on a collective silico..." pattern — [p10](./10-google-tpu-architecture.md) / [p13](./13-aws-trainium-architecture.md).
- **The "rack is the computer" thesis** (NVL72 as one coherent memory domain, the copper-vs-optical power trade, the OCS / Boardfly scale-up-domain extensions) — [p24](./24-the-rack-is-the-ai-computer.md).
- **The determinism spectrum** (GPU warp scheduler → TPU compiler-scheduled → Groq fully-deterministic) — [p16](./16-hardware-vs-software-scheduling.md) / [p14](./14-groq-lpu-architecture.md).

## How to read this page against the others
- **vs. the 6 flagship pages (04/05/07/10/13/14/18):** this page is the *provenance layer* over them — each table row points to the page that carries the verified figure and its source.
- **vs. page 31 (big idea):** the structural claims the article gets right (roofline, systolic, rack-as-computer, determinism spectrum) *are* the five first-principles facts in [p28](./28-ai-chip-architecture-80-20.md) and the eight axes in [p31](./31-the-big-idea-design-space.md).
- **vs. page 29 (zero-to-hero):** this page is the "did the source actually say that?" layer; page 29 is the "can you re-derive it?" layer.

## Status of open items
- UNVERIFIED rows 5 and 15 (Cerebras 2026 deal; TPU v8 specs) need a primary-source fetch before they become load-bearing. Tracked in CHANGELOG.
- The Cerebras market-position update on p25 and the Groq 2026-framing note are queued; both are non-breaking (the dated lines already exist).

## Sources
- Jacob Peake, "The AI Chip Architecture Handbook", jacobpeake.com, fetched 2026-08-24 (~21k words; 7 architecture chapters + spec table).
- NVIDIA H100 / NVL72 / GTC'25-26 product pages (dense vs sparse FP8; NVL72 memory and power).
- Google Cloud TPU v4 docs + Ironwood announcement (HBM2 1.2 TB/s; 1.77 PB / 42.5 EF).
- ISCA'23 "TPU v4: An Optically Reconfigurable Supercomputer" (arXiv:2304.01433).
- AWS EC2 Trn2 / Trn3 docs (96 GB HBM3; TSMC N3P + NeuronSwitch).
- AMD MI300X / MI355X CDNA spec sheets (1,307 TFLOPS FP8; 288 GB HBM3E @ 8 TB/s).
- Cerebras WSE-2 IEEE Micro'23 + CS-3 2024 announcement (850K vs 900K cores; 395B transistors / 4.6LW SRAM / 90 PF FP8).
- Groq ISCA'22 (arXiv:2203.04810) BERT P99 table.
