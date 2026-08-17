# Attention Head Designs — MHA / MQA / GQA / MLA
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
How many Key/Value heads does each query head share with? MHA = one-to-one; MQA = one
shared; GQA = groups share (e.g. 8 KV heads for 64 Q heads); MLA = K,V compressed into a
shared low-rank latent. Fewer KV heads = smaller KV cache = more concurrency at long
context.

## The family
| Design | h_kv | KV bytes factor | Quality | Used by |
|---|---|---|---|---|
| MHA [F: Vaswani 2017] | = h_q | 1.0× | reference | original Transformer, GPT-2 |
| **MQA** [F: Shazeer 2019, arXiv:1911.06145] | 1 | 1/h_q | small drop | T5-v1.1, GPT-NeoX |
| **GQA** [F: Ainslie et al. 2023, arXiv:2305.13245] | g (e.g. 8) | g/h_q | near-MHA | Llama 2/3, Qwen, GPT-4-class, most 2023+ models |
| **MLA** [F: DeepSeek-V2 arXiv:2405.04434, V3 arXiv:2412.19437] | latent ~ 576-dim + 64-dim RoPE part | ~0.03–0.15× of MHA | frontier | DeepSeek-V2/V3/R1 family |

## Mathematics (what changes)
- Standard: K = X·Wk with Wk ∈ R^(d × h_kv·d_h). GQA just sets h_kv < h_q; query heads in
  group i use KV head ⌊i/g⌋. **No retraining needed** for the MHA→GQA *conversion*
  (average Q/K heads within groups — "GQA-from-MHA" trick [I: common practice]).
- MLA: compress K,V jointly: c_t = W_DK·h (low-dim latent), K = W_UK·c_t, V = W_UV·c_t;
  cache **c_t instead of full K,V** → ~97% smaller cache; RoPE applied to a separate
  small part to preserve position info. **Why it works:** K,V matrices are low-rank in
  practice, so the compression is near-lossless [F: DeepSeek-V2 report; I: rank claim].

## Compute / memory / inference impact
- Decode bandwidth ∝ h_kv·d_h·L·S → GQA cuts it g/h_q times; MLA cuts it ~10–30×.
- Prefill: KV projection FLOPs also drop (smaller Wk/Wv) — a modest prefill win.
- MQA/GQA slightly reduce attention quality at extreme scale (expressivity of the
  key space) — GQA was the compromise that became the default [I].

## Training impact
GQA/MQA need training from scratch (or fine-tuning); MLA is architecture-level.
MHA→GQA post-hoc conversion works for inference but is not optimal [I].

## Related
`Transformer/README.md` · `Attention/README.md` · `KV-Cache/README.md` · `Labs/Lab-3`.

## Key Takeaways
h_kv is a *dial* on the KV budget: 1 (MQA) ↔ h_q (MHA), with GQA the default and MLA the
2024+ frontier move that also changes what is cached.
