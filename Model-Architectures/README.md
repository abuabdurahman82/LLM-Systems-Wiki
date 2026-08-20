# Model Architectures — The Evolution
`LAST_UPDATED: 2026-08-20` · Status: section index

> **Note (2026-08-20):** for the *how-it-trains* side of these
> architectures (parameter counts, FLOPs/param, KV-cache math, MoE
> activation accounting, why MoE flips the binding constraint from
> FLOPs to HBM) see
> [`Training-Engineering/Model-Anatomy`](../Training-Engineering/Model-Anatomy.md).
> This page keeps the architecture taxonomy (families, head designs,
> positional encodings, non-transformer alternatives).

## Three families
1. **Encoder-only** (BERT 2018, arXiv:1810.04805 [F]) — masked LM; great for understanding
   tasks; can't generate.
2. **Decoder-only** (GPT line, 2018+) — causal LM; the dominant LLM family; generation
   is the native task.
3. **Encoder-decoder** (T5, BART) — seq2seq; NMT-style; used in some 2024+ multimodal
   bridges.

## Dense vs Mixture-of-Experts
- **Dense:** every token activates every parameter. Compute ∝ params. GPT-3 (175B) was
  dense and famous for its cost.
- **MoE:** FFN replaced by N experts + router; each token activates top-k experts
  (typically 2 of 64–256). Total params ↑, *activated* params flat.
  [F: Shazeer et al. 2017 "Outrageously Large Neural Networks" arXiv:1701.06538;
  Switch Transformer arXiv:2101.03961 (2021); GShard arXiv:2006.16668]
- Consequences: training needs expert-parallel AllToAll (`Distributed-Inference/`);
  serving needs expert placement; memory ≫ compute (hence MoE's bandwidth problems at
  decode). See `Mixture-of-Experts.md`.

## Attention head designs
MHA → MQA → GQA → MLA: `Attention-Head-Designs.md`.

## Positional encodings
Sinusoidal (2017) → learned → RoPE (2021) → ALiBi → YaRN/Paged-style context extensions:
`Positional-Encodings.md`.

## Layer-level conventions (modern default, LLaMA-class [F: arXiv:2302.13971])
Pre-norm RMSNorm [F: arXiv:1910.07467] → GQA attention + RoPE → SwiGLU FFN
[arXiv:2002.05202] → residual. No biases.

## Non-transformer alternatives (2024–2026)
- **State-space models** (Mamba/Mamba-2 [F: arXiv:2312.00752, arXiv:2405.21855]) — O(1)
  state recurrence; strong at fixed cost; long-context recall still contested [I].
- **Hybrids** — Jamba (Mamba+attention [F: arXiv:2403.19646]), Griffin [F: arXiv:2402.19444],
  Falcon-Mamba, NVIDIA Nemotron-H [I: family name per HF blog 2026].
- **Linear attention** — Performer [F: arXiv:2009.14784] line; mostly research.

## Related
`Transformer/README.md` · `Attention/README.md` · `Research-Lineage/README.md`.

## Key Takeaways
The architecture has been *stable since 2022*: pre-norm GQA-RoPE-SwiGLU + optional MoE.
Innovation moved to (a) sparsity (MoE/MLA), (b) post-training, (c) systems.
