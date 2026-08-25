# AI-Accelerator — External Evaluator Pass & Adjudication Record

`LAST_UPDATED: 2026-08-24` · Status: evaluation record

## What was run

Four independent evaluator audits of the AI-Accelerator section (all 31 pages),
via the configured reviewer endpoint (deepseek-v4-flash-0731 @ 10.1.1.51:8888):

| Chunk | Pages | Mode | Finished |
|---|---|---|---|
| 1 | 22–23 | adversarial audit (audit landed in `reasoning` field) | yes |
| 2 | 24–26 | adversarial audit | yes |
| 3 | 27–29 | adversarial audit (pass-2: verdict-to-content attempt) | yes |
| 4 | 30–31 | adversarial audit (pass-2) | yes |

Every evaluator flag was independently re-verified against primary sources or
first-principles recomputation before being applied. Refuted flags are recorded
below with the evidence, and were NOT applied.

## Confirmed findings — applied (12)

1. **Llama-2-70B total params = 68.98B, not 67.8B.**
   Evidence: official checkpoint index (`model.safetensors.index.json`,
   `metadata.total_size = 137,953,316,864` bytes FP16 → 68,976,658,432 params).
   The old 67.8B propagated a GQA attention-miscount from an earlier session.
   Cascaded correction across pages 02/12/14/15/17/18/20/22/23/24/27/28/29/30:
   `67.8e9 → 68.98e9` everywhere; derived values recomputed (135.6 → 137.95 GB
   FP16, 67.8 → 68.98 GB INT8, 2-param 135.6 → 137.95 GFLOP/token, prefill
   555 → 565 TFLOP, ⅛-shard 16.95 → 17.24 GB, decode 198 → 194 tok/s,
   5.06 → 5.15 ms/token, Groq headroom 64.7 → 63.5 GB, H100 headroom
   504.4 → 502.1 GB, KV @4096 1.28 GB → 1.25 GiB (1.34 GB), KV @1024
   4 MiB → 320 MiB, INT8 TSP estimate ~294 → ~300).
   The exact 7-GEMM count (~137 GFLOP/token) was already correct; the 2-param
   shortcut now agrees within ~1% with it.

2. **Trainium2: "158/316 cFP8 TFLOPS" is per-NeuronCore, not per-chip.**
   Evidence: AWS docs / Trn2 announcement — 8 NeuronCores per chip, chip peak
   = 1.3 PF dense FP8 (= 8 × 158). Pages 15/21/23/30/31 fixed; p23 ridge
   54 → 448 (1,300 / 2.9), range "54–591" → "230–591".

3. **DGX H100 rack density.** Evidence: NVIDIA SuperPOD design guide + design
   guide compendium — recommended 4 systems/rack (32 H100, ~40.8 kW), not
   12–16 systems / 96–128 H100 / 120–165 kW. Pages 03/24/27/28 fixed; GB200
   NVL72 (~120 kW-class) noted as the denser newer class.

4. **Roofline attribution** — Williams, Waterman & Patterson, CACM 2009,
   originally for multicore CPUs (now standard for GPUs/accelerators), not
   "for the GPU". (p23)

5. **Decode compute utilization** — the chip runs at ~0.3–0.6% of its compute
   in batch-1 decode (3.35 TFLOPS / 989 TFLOPS = 0.34%), not "3–5%". (p23)

6. **Groq node SRAM = 1.72 GiB** (8 × 220 MiB = 1,760 MiB), not 1.75 GiB. (p14, p21, p27)

7. **p28 internal-consistency fixes** — the no-off-chip axis applies to WSE-2
   *and* TSP (not WSE-only); H100 and TPU v4 are both HBM flagships; "four
   precision formats" corrected to five (INT8/FP16/BF16/FP8/FP4).

8. **Lightmatter Passage** — primary source (Lightmatter, Mar 2025): Passage
   M1000 announced, EVK stage (114 Tbps, 3D photonic superchip), **not**
   "deployed in production"; NVIDIA/AMD design wins UNVERIFIED. p26 also had a
   heading-formatting corruption (photon cell text fused into `# H1`), repaired.

9. **p26** — a 7B 4-bit distilled LLM fits the phone's DRAM (~3.5 GB), not its
   SRAM; Gaudi 3 raises HBM to 128 GB HBM2E (Gaudi 2 already had 96 GB); MTIA
   is an in-house chip, not a service-quadrant chip.

10. **400B-FP8 model fits one 8×H100 server** (640 GB HBM − 400 GB = ~240 GB
    headroom for KV+acts), so it does *not* need a pod on capacity alone.
    (p24/27/28)

11. **p25 "cannot run on-premises" was too absolute** — TPU has an on-premises
    path (GDC/TPOD) though its toolchain is GCP-native; Trainium has none.

12. **p23 precision note** — FP16→FP8 doubles the *peak* roof; the *bandwidth*
    roof does not move (ridge doubles in lockstep). (Also p26 photonic cell
    made internally consistent after 8.)

## Refuted flags — NOT applied (with evidence)

- **AWS Neuron "open"** — refuted: AWS docs + GitHub confirm Neuron compiler /
  SDK / NKI are Apache-2.0 open source.
- **TPU v4 275 TFLOPS & "ISCA 2023" venue** — refuted: arXiv:2304.01433
  fetched live; title/date confirm the ISCA 2023 TPU v4 paper with 275 TFLOPS
  BF16-or-INT8 peak.
- **"Boardfly" interconnect** — refuted: verified on p10, [F: Google v8 blog
  2026]; it is the v8 partially-switched topology.
- **BERT-Large 75 µs → "must be wrong"** — this is a *documented* anchor-vs-
  primary discrepancy (already surfaced on p14/p30 and taught on p04 with ISCA
  2022 §5.4 values: P99 < 1,225 µs / P100 = 1,300 µs), not a page error.
- **WSE-2 21 PB/s** — half-refuted / corrected: public Cerebras spec puts
  WSE-2 at 20 PB/s (21 PB/s is WSE-3); pages updated to the correct per-generation
  numbers (this is a confirmed *factual correction*, listed in both places).

## Status

- All four chunks adjudicated; corrections applied and cross-page consistent
  (residual-grep clean).
- Commit: see `git log -1` — branch `42de585`-history extended by this pass.
