# GPU-Systems Authoring Guide (house style)
`LAST_UPDATED: 2026-08-21` · Meta file (not a content page). Durable reference for anyone
authoring or editing a page in this section. Supersedes the ephemeral `/tmp` style guide
if the two ever conflict — this lives in the repo.

## File shape
- Line 1: `# <Title>` — the ONLY h1 in the file.
- Line 2: `LAST_UPDATED: YYYY-MM-DD · Status: core page` (+ a one-line source note where
  useful).
- Open with `## 30-Second Explanation` (the 20% that carries the 80%).
- Close with `## Key Takeaways` (5 numbered points), `## Related`, `## References`
  (References optional for pure-prose pages). No disclaimer footer.
- Length: core pages 180–420 lines; deep-dive pages up to ~600.

## Claim tags (mandatory on technical claims)
- `[F]` — verified primary source (paper/docs/spec); give the link or arXiv id inline.
- `[A]` — engineering assumption (state it as an assumption).
- `[I]` — author inference ("inference"/"synthesis").
- `[E]` — verified by computation/measurement this session; show the arithmetic inline
  where it's the crux.
- `UNVERIFIED` — could not verify; state explicitly, never rely on it.
- Vendor numbers: `[F: vendor spec]` / `[F: vendor claim]` — never presented as independent.
- NEVER invent benchmark numbers, GPU specs, paper titles, or arXiv ids.
- Prefer **at least one BARE `[T]`** per tag class in the body even when you also use
  sourced forms (`[E: ...]`), so plain grep-style checks find the tag.

## Citation bank (verified 2026-08-21 — reuse, don't re-guess)
FlashAttention 2205.14135 · FA-2 2307.08691 · FA-3 2407.08608 · PagedAttention/vLLM
2309.06180 · SGLang 2312.07104 · ZeRO 1910.02054 · DistServe 2401.09670 · Mooncake
2407.00079 · GPTQ 2210.17323 · AWQ 2306.00978 · KIVI 2402.02750 · SmoothQuant
2211.10438 · Megatron-LM 1909.08053 · Ring Attention 2310.01889 (Liu et al.) ·
DeepSpeed-Ulysses 2309.14509 · GPipe 1811.06965 · PipeDream 1806.03377 · DeepSeekMoE
2401.06066 · Mixtral 2401.04088 · FlashInfer 2501.01005 · EAGLE 2401.15077 · Orca
2211.05102 · Mamba 2312.00752 · RoPE 2104.09864 · RMSNorm 1910.07467 · GPT-3 2005.14165 ·
LLaMA 2302.13971 · Llama-2 2307.09288 · Llama-3 2407.21783 · Mistral-7B 2310.06825 ·
DeepSeek-V3 2412.19437 · DeepSeek-V2 2405.04434 · SnapKV 2404.14469 · FlexGen 2303.06865 ·
Splitwise 2311.18677 · Llumnix 2406.03243 · Sarathi 2308.16369 · Sarathi-Serve 2403.02310 ·
Qwen2.5 2412.15115 · Kimi-K2 2507.20534 · Switch Transformers 2101.03961 · Megatron-LM
activation-recompute/SP 2205.05198 · Yuan et al. "LLM Inference Unveiled" 2402.16363.
NOT on arXiv (cite repo/docs, not a fake id): CUTLASS, Triton, TensorRT-LLM, NVIDIA
Dynamo, llm-d. Verify any title you write against the arXiv abs page before it ships.

## The 9-field concept template (for EVERY major concept)
`### What / Why / How / When / Hardware impact / Inference impact / Example / Failure
modes / How to measure it` (omit a field only if truly N/A). "Example" must be
concrete and hand-calculable (tensor shapes, byte counts, short code).

## Cross-linking (≥4 other pages per page)
- Siblings in this section: bare `Name.md` or `./Name.md`.
- Other sections (repo-root-relative): `../Inference/Roofline.md`, `../Hardware/README.md`,
  `../KV-Cache/README.md`, `../Quantization/README.md`, `../Networking/README.md`,
  `../Distributed-Inference/README.md`, `../Speculative-Decoding/README.md`,
  `../Inference/Continuous-Batching.md`, `../Inference/Inference-Metrics.md`,
  `../Serving-Engines/README.md`.
- Keep links to siblings that don't exist yet — they get authored.

## Visuals
Fenced ``` ASCII blocks for architecture/hierarchy/data-flow; ```mermaid where a graph
is clearer; tables for comparisons. ≥1 diagram in most pages.

## Depth rules
1. Start with the 30-Second Explanation.
2. Fundamentals → mechanism → numbers → optimization → failure modes → measurement.
3. NEVER assume "naming a technology = explaining it."
4. Always connect back to LLM inference: TTFT, ITL/TPOT, throughput, KV cache, memory.

## Hardware constants (cross-check ../Hardware/README.md + NVIDIA specs)
- H100 SXM: 989 TFLOP BF16 dense; 3.35 TB/s HBM3; ~900 GB/s NVLink aggregate; 132 SMs;
  65,536 32-bit registers/SM (256 KB); max 64 warps / 2048 threads resident/SM; 4 warp
  schedulers/SM. H100 BF16 roofline ridge ≈ 295 FLOP/byte.
- H200: 141 GB HBM3e. B200: ~8 TB/s HBM3e; FP8 dense ~4.5 PFLOP; FP4 ~9 PFLOP.
- NVL72: 72-GPU NVLink domain. DGX/HGX: 8×H100 NVSwitch node.
- RTX 5090: GDDR7 1.79 TB/s. GB10/DGX Spark: ~273 GB/s.
- PCIe 5.0 x16: ~64 GB/s. IB NDR 400G: ~50 GB/s/link.
- State GB vs GiB and Gb/s vs GB/s (×8) explicitly.

## Prohibitions
- No universal engine/GPU winner; frame rankings as hypotheses.
- No vendor benchmark presented as an independent [E].
- No fabrication. No restating the task prompt. No disclaimer footer.
- Only the target file may be written; everything else is read-only.

## Example model convention (for worked arithmetic)
Unless a page says otherwise, the "example model" is a **6.5B-class dense model**:
d=4096, 32 layers, d_ff≈11008, GQA h_kv=8, d_h=128. Per-layer QKV+O weights ≈ 128 MB;
MLP ≈ 269 MB. KV/token (GQA-8, BF16) = 2·32·8·128·2 = 128 KiB. Use this for hand
arithmetic; label it `[E, example model]`. For MoE examples use the real cited model
(DeepSeek-V3 d=7168, top-k=8, 256 experts; Mixtral 8×top-2).
