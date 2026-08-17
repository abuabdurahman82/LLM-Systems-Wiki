# Foundations — From Shannon to Self-Attention
`LAST_UPDATED: 2026-08-16` · Status: history page (all entries well-established [F])

## 30-Second Explanation
LLMs are not a sudden invention. They are the end of a ~80-year chain: information
theory (what to optimize), trainable neurons (how to learn), backpropagation (how to
train deep), distributed word representations (what to represent), recurrent sequence
models (how to handle order), and attention (how to skip the bottleneck). Each step
removed one blocker to the next.

## The chain

### 1948 — Information theory (Shannon) [F: "A Mathematical Theory of Communication", Bell Syst. Tech. J.]
Cross-entropy (nats/bits) becomes the objective for probabilistic models. **Why it
matters:** a language model's loss — cross-entropy of next-token prediction — is literally
Shannon's definition of information. "Bits" are the unit of both communication and
learning.

### 1957–58 — Perceptron (Rosenblatt) [F]
Weighted sum + activation + delta rule: the first trainable "neuron". **Limitation:**
linear separability (Minsky & Papert 1969 showed perceptrons can't do XOR) — resolved
two decades later by backprop through *layers*.

### 1986 — Backpropagation (Rumelhart, Hinton & Williams) [F: Nature 323, 1986]
Gradients through layered networks via the chain rule. **Why it matters:** without
backprop there are no deep neural nets; everything since is backprop + architecture
choices.

### 2003–2013 — Word embeddings [F: Mikolov et al. 2003 "Computing (logistic)
probability..."; word2Vec arXiv:1301.3781; GloVe 2014]
Distributed representations: "king − man + woman ≈ queen". **Why it matters:** proved
that meaning is a *vector geometry* problem — the direct ancestor of LLM embeddings and
the embedding table in every transformer today.

### 1990s–2014 — RNN/LSTM/GRU sequence models [F: Hochreiter 1997 (vanishing
gradients); Hochreiter & Schmidhuber 1997 LSTM arXiv:9707.0248; GRU 2014]
Gates keep/forget state over time. **Limitation:** O(S) sequential steps (no parallelism),
hard long-range memory. **Why it matters:** they defined the "sequence transduction"
problem statement that seq2seq then attacked.

### 2014 — Seq2Seq + attention (Cho et al. 2014; Bahdanau et al. 2014, arXiv:1409.0473) [F]
Encoder compresses the source into a fixed vector; decoder generates the target.
Bahdanau's **attention** lets the decoder *look at* relevant source positions instead of
the bottleneck vector. **Why it matters:** attention was born here — as an alignment
mechanism for machine translation. The "attention is all you need" idea is this mechanism
applied to the sequence itself.

### 2015 — "Effective Approaches to Attention" (Luong et al. arXiv:1508.04025) [F]
Systematizes attention types (additive vs multiplicative). Sets up the 2017 breakthrough.

### 2017 — The Transformer (Vaswani et al., "Attention Is All You Need", arXiv:1706.03762) [F]
Kills the recurrence: **self-attention** (Q/K/V) + FFN + residuals + positional encodings,
fully parallel over the sequence. **Why it mattered:** O(1) sequential depth per position
→ the sequence dimension becomes a *parallel* dimension on GPUs. Every LLM after is this
architecture with incremental upgrades (RoPE, GQA, RMSNorm, SwiGLU, MoE, MLA — see
`Model-Architectures/`).

## What changed and why (one line each)
- Information theory → the objective (cross-entropy).
- Perceptron → learning rules.
- Backprop → depth.
- Word vectors → geometric meaning.
- RNN/LSTM → sequence order (and its limits).
- Seq2Seq+attention → long-range lookups.
- Transformer → parallelism. The rest is engineering at scale.

## Related
`Transformer/README.md` · `Milestones.md` · `Research-Papers/README.md`.

## Key Takeaways
Every LLM capability traces to one of these seven steps; know the chain and most
"new" papers slot into a known slot.
