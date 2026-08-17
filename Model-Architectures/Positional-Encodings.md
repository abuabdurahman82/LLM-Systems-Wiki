# Positional Encodings
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
Self-attention is permutation-equivariant — it doesn't know token order. Positional
encodings inject order. The design choice determines how far the model can reliably
attend and whether context can be extended post-hoc.

## The family
| Method | Mechanism | Properties |
|---|---|---|
| Sinusoidal (2017 [F: arXiv:1706.03762]) | fixed sin/cos per position | no learned params; no extrapolation guarantee |
| Learned embeddings (2018) | positional vector added to token embedding | learned; hard to extend beyond trained length |
| **RoPE** (Su et al. 2021, arXiv:2104.09864 [F]) | rotate q,k by position-dependent angles; attention sees *relative* position via (i−j) | dominant in LLaMA/Qwen/DeepSeek/GPT-class; enables YaRN/Ntk context extension |
| **ALiBi** (Press et al. 2022, arXiv:2108.12409, EMNLP [F]) | additive linear bias per head (slope × distance) | no extra params; strong length extrapolation |
| **YaRN / NTK-aware / Paged** (2023–24 [I: recipe literature]) | interpolate RoPE base frequency (stretch) | 8K→32K/128K extensions; standard for context expansion |
| NoPE / position-free (2024–25) | rely on learned attention patterns (SSM hybrids) | research |

## Why RoPE won
Relative-position encoding *inside the dot product*: <q_i, k_j> depends on (i−j) →
the model learns "distance" without a position table; frequencies give a multi-scale
clock (low freq = long range). Extension: scale the base → same learned distances cover
more tokens [F: mechanism; I: empirical success of YaRN-class recipes].

## Limits
Beyond trained length, quality degrades (attention patterns trained on shorter spans);
fixes = RoPE scaling + fine-tuning, or architectures without positions (SSM hybrids) [I].

## Related
`Transformer/README.md` · `Model-Architectures/README.md`.

## Key Takeaways
RoPE is the default; context extension is mostly RoPE interpolation + light fine-tuning;
the failure mode of long context is positional, not attentional.
