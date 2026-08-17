# Transformer Fundamentals — First Principles
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
A Transformer reads a sequence of tokens and predicts the next token. It does this with
fully-parallel **self-attention** (every position looks at every earlier position) stacked
in identical layers, plus feed-forward networks per position. Pretraining = next-token
prediction at massive scale; that single objective, scaled, produces the abilities we see
in LLMs.

## Why This Exists
RNNs process sequences left-to-right: O(S) sequential steps, gradients vanish across long
spans, no way to parallelize over the sequence. The Transformer (Vaswani et al. 2017 [F:
arXiv:1706.03762]) replaced recurrence with attention: O(1) sequential depth per position,
O(S²) pairwise interactions, fully parallel across positions on GPUs.

## Problem It Solves
Long-range dependencies + parallel training. Attention directly connects any two positions
in one step; attention weights are data-dependent (vs. fixed convolutions).

## First-Principles Explanation
A model is a function P(next token | previous tokens). We need:
1. a way to **represent** a token (embedding vector),
2. a way to let tokens **talk to each other** (attention),
3. a way to **transform representations non-linearly** per position (FFN),
4. a way to stack these **without blowing up gradients** (residuals + normalization),
5. a way to turn the final representation into a **distribution over the vocabulary**
   (logits + softmax).

## How It Works
Per layer (pre-norm, the modern default [F: LLaMA, GPT-NeoX]):

```
x' = x + SelfAttention( RMSNorm(x) )
y  = x' + FFN( RMSNorm(x') )
```

Self-attention (per head):
```
Q = X·Wq      K = X·Wk      V = X·Wv          Wq,Wk,Wv ∈ R^(d × h·d_h)
A   = softmax( Q·Kᵀ / √d_h )                  A ∈ R^(S×S) (per head, causal mask)
out = A·V     out reshaped → linear → R^(S×d)
```
FFN (SwiGLU, the LLaMA/Qwen/GPT-3.5+ style [F]): `H1=X·W1; H2=X·W2; FFN = (silu(H1)·H2)·W3`,
with d_ff ≈ 2.7·d.

## Mathematics — every variable
- `X ∈ R^(S×d)`: input matrix; S = sequence length, d = hidden size (e.g. 4096).
- `Wq,Wk,Wv ∈ R^(d × h·d_h)`: projections; h = #heads, d_h = head dim; h·d_h is often = d.
- `Q,K,V ∈ R^(S×h·d_h)`: after reshape, `R^(S×h×d_h)` (batch B prepended in practice).
- `Q·Kᵀ ∈ R^(S×S)`: raw relevance scores; `√d_h` keeps their variance ≈1 (q,k ~ N(0,1)
  gives Var(q·k)≈d_h; unscaled scores would drive softmax to one-hot as d_h grows)
  [F: Vaswani 2017].
- `softmax` row-wise, with a **causal mask** (A[i,j]=0 for j>i): each position only sees
  itself and earlier positions → autoregression.
- `A·V ∈ R^(S×h·d_h)`: value mixture.
- Logits: `Z = h_last · W_embᵀ ∈ R^(1×V)` (serving computes the LAST position only;
  V = vocabulary size, e.g. 150k).
- Sampling: temperature T scales logits (Z/T), optional top-k / top-p / min-p filters,
  then sample from softmax. T=0 → argmax (greedy).

## Visual Mental Model
```
 ids → X[S,d] → [Norm → QKV → causal attention → out-proj] → +res → [Norm → SwiGLU FFN] → +res → ×L → Norm → W_embᵀ → [V] logits
```

## Example (hand-calculable, [E] verified in Python)
Toy: L=2 layers, d=6, h=2, d_h=3, S=4, V=10, d_ff=12, BF16.
- `ids [4] → X [4,6] → Q,K,V [4,6]→[4,2,3] → scores [4,4]` (causal: 6 of 16 entries live)
- FLOPs per layer: QKV 3×(2·4·6·6)=864; attention 2 heads ×(QKᵀ 2·4·4·3 + ×V 2·4·4·3)=384;
  out-proj 288; SwiGLU 3×(2·4·12·6)=1728 → **3,264/layer**; 2 layers = 6,528; logits
  2·1·6·10=120 → **≈6,648 FLOPs** for the whole 4-token prefill.
- Scale-up (27B, S=8192): prefill ≈ 2·N·S ≈ **442 TFLOP**; decode per token 2·N ≈ 54 GFLOP.

## Impact on Training
Attention is O(S²·d + S·d²) per layer (S²·d for the score + value mixes across heads,
S·d² for the QKV/out projections) → long sequences cost quadratically in the
score matrix (solved at the *kernel* level by FlashAttention, not by changing the math).

## Impact on Inference
- **Prefill** = all S tokens in one parallel pass: dense GEMMs, compute-bound.
- **Decode** = 1 token/step: GEMMs degenerate to GEMVs; every step streams all weights +
  all prior K,V → memory-bandwidth-bound. The KV cache exists precisely to avoid
  recomputing K,V. See `Inference/The-Life-of-a-Token.md`.

## Performance Implications
The prefill/decode dichotomy (compute-bound vs bandwidth-bound) explains ~80% of inference
engineering: batching, GQA, quantization, FlashAttention, PagedAttention, chunked prefill,
prefix caching all target one side of it. See `Inference/Roofline.md`.

## Advantages
Parallelism; long-range; hardware efficiency; composability (MoE, GQA, RoPE all bolt on).

## Limitations
O(S²) attention (mitigated, not eliminated: FlashAttention is IO; linear/SSM are
architecture changes); positional generalization beyond trained length; no native
symbolic reasoning (addressed post-hoc: `Reasoning/`).

## Important Research
- Vaswani et al. 2017, "Attention Is All You Need" [F: arXiv:1706.03762]
- Sennrich et al. 2016, "Neural Machine Translation of Rare Words with Subword Units" (BPE) [F: arXiv:1508.07909]
- Su et al. 2021, RoPE [F: arXiv:2104.09864]; Press et al. 2022, ALiBi [F: arXiv:2108.12409]
- Shazeer 2020, GLU variants / SwiGLU [F: arXiv:2002.05202]
- Ba et al. 2016, LayerNorm (the pre-norm alternative to RMSNorm) [F: arXiv:1607.06450]
- Dao et al. 2022, FlashAttention [F: arXiv:2205.14135]
- Zhang et al. 2019, RMSNorm [F: arXiv:1910.07467]
- Touvron et al. 2023, LLaMA [F: arXiv:2302.13971]

## Major Implementations
PyTorch (`nn.MultiheadAttention`, `torch.nn.functional.scaled_dot_product_attention`),
JAX, and every serving engine's attention backend (see `Serving-Engines/`).

## Related Topics
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` ·
`Model-Architectures/Attention-Head-Designs.md` · `Model-Architectures/Positional-Encodings.md` ·
`KV-Cache/README.md` · `Attention/README.md`

## Key Takeaways
1. One objective (next-token) + one building block (attention+FFN stacked L times).
2. Causal mask = what makes generation autoregressive.
3. Prefill vs decode = compute-bound vs bandwidth-bound; everything else follows.
4. Keep the toy shapes in your head: [S,d], [S,h,d_h], S×S scores, last-position logits.

## References
See "Important Research" above; see also `Research-Papers/README.md` for full records.
