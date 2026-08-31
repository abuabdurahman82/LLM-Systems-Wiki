# Retrieval-Based and Self-Speculative Decoding
`LAST_UPDATED: 2026-08-27` · Status: core page
Sources: REST arXiv:2311.08252, Lookahead arXiv:2402.02057, LayerSkip arXiv:2404.16710, Draft & Verify arXiv:2309.08168, SpecInfer arXiv:2305.09781, OSD arXiv:2310.07177 — all title-verified; vLLM/SGLang docs for production n-gram [F: docs].

## 30-Second Explanation
Two ways to draft without training a dedicated model: **look it up** (retrieval from a
corpus or the prompt itself) or **look inside** (the target drafts with a subset of its
own computation). Both are deployable in minutes, both ride the same verify machinery
as classical speculation, and both shine on predictable workloads — code, templates,
summarization, editing.

## REST: retrieval-based speculation (He et al., 2311.08252)
```text
Corpus ──▶ offline index (suffix array / n-gram store)
                │
Current suffix ─┤  longest-match lookup
                ▼
   candidate continuations (merged into a tree)
                ▼
   target verifies the tree in one pass
```
- **Mechanism:** keys = short text spans; values = continuations from the corpus; the
  matched candidates form a token tree verified in parallel. Greedy/exact-match style
  acceptance rather than residual sampling [F: paper].
- **Reported:** 1.62-2.36× on code/text generation with 7B/13B models, single-batch
  (A100-class hardware for the main results) [F: abstract].
- **Why code/structured text wins:** licenses, imports, API calls, and boilerplate
  repeat; near-duplicate contexts are common, so retrieval hits often and long prefixes
  survive. Open-ended prose rarely repeats ⇒ acceptance collapses.
- **Costs:** datastore memory; zero help on novel text; quality ceiling = corpus.
- **Production cousins:** vLLM `ngram` (prompt + generated text as the "corpus"),
  SGLang `NGRAM` with trie depth/capacity knobs, vLLM `suffix` decoding (dynamic depth)
  [F: docs]. These draft from the *live* prompt — the special case where the "corpus"
  is the request itself (extraction, rewriting, multi-turn echo). Connects to
  [../KV-Cache/Prompt-and-Prefix-Caching.md](../KV-Cache/Prompt-and-Prefix-Caching.md):
  both exploit "this text already appeared", but prefix caching reuses KV, retrieval
  speculation reuses *text*.

## Lookahead decoding (Fu et al., 2402.02057)
- **Mechanism:** Jacobi/fixed-point iteration on the token sequence — a window of
  positions updates in parallel each step; an n-gram pool harvested from the model's
  own recent output feeds candidate branches; verification folds into the iteration.
- **No draft model, no datastore, no training**; exact (lossless) decoding [F: paper].
- **Reported:** up to 1.8× on MT-bench; up to 4× with multi-GPU strong scaling on code
  [F: abstract].
- **Trade:** each step spends extra FLOPs on the window — nearly free while
  bandwidth-bound, painful when compute-bound (large batch). Implementation is more
  invasive than draft-model speculation.

## Self-speculative family
```text
Target Model
│
├─ shallow computation (skip layers / early exit) → draft
│
└─ full computation → verify (same model, same weights)
```

### Draft & Verify (Zhou et al., 2309.08168)
- Skip a chosen set of middle layers to draft; full model verifies. FLOPs-aware layer
  selection (rank layers by cost saved vs accuracy impact); **no retraining, no extra
  memory** [F: paper]. Reported up to 1.99× on Llama-2-class models, single A100 [F].

### LayerSkip (Elhoushi et al., 2404.16710)
- Training recipe (layer dropout + deep supervision at every layer) so that *any*
  layer can serve as an exit; draft = early exit at layer k, verify = remaining layers
  in one pass; draft/verify share activations and KV [F: paper].
- Reported: 2.16× on CNN/DM summarization, 1.82× coding, 2.0× on TOPv2 semantic
  parsing (Llama-2 7B/13B/70B variants) [F: abstract].
- Compared to Draft & Verify: better draft quality per FLOP, but requires the modified
  training run (not retrofit-able to arbitrary checkpoints).

### Hybrid-model self-speculation (2605.01106, 2026)
- For architectures mixing attention with linear/SSM layers, the *cheap subgraph*
  itself can be the drafter. The same paper shows the acceptance gap is enormous and
  architecture-dependent: parallel hybrids reached α=0.68 at k=2 while sequential
  hybrids collapsed to α=0.038 — an 18× gap [F: abstract]. Lesson: self-speculation
  viability is a property of the architecture, testable without running speculation
  (perplexity-degradation ratio).

## Why these methods matter
- **Zero-training deployability:** n-gram/lookahead/self-spec run on unmodified
  checkpoints; useful when you own neither training compute nor model weights.
- **No second model:** memory, loading, and tokenizer-alignment problems vanish.
- **Workload-shaped:** retrieval methods are essentially free where output echoes
  input; self-speculation is essentially free where the architecture is redundant.
- The cost is acceptance: training-free drafters sit below trained ones (EAGLE-class)
  on the same targets — which is why production stacks often offer both and let the
  operator choose per model ([17 Framework Implementations](17-framework-implementations.md)).

## Worked example (hand-calculable)
JSON extraction with a 70B target: the answer quotes the prompt. vLLM ngram with
`prompt_lookup_min=5` matches a 40-token span from the prompt and proposes it as a
chain; verification is one pass; acceptance for quoted spans approaches the block
length. Effective cost ≈ 1 target pass for ~20 emitted tokens instead of ~20 passes
[E: arithmetic per the [03](03-acceptance-and-verification.md) model] — the
"retrieval acceptance" regime where these methods look unfair.

## Failure modes
- Retrieval: novel content ⇒ no hits (pure overhead); datastore bloat; stale caches.
- Lookahead: window FLOPs hurt at compute-bound batch; scheduler integration is
  nontrivial.
- Self-speculation: layer-choice (or exit-point) tuning per model; weak redundancy ⇒
  low α; LayerSkip-style recipes need a training pass.

## How to measure it
Retrieval hit rate, mean drafted length per hit, α per position; for self-speculation
the layer/exit sweep; then the standard latency/throughput battery
([18 Performance Benchmarking](18-performance-benchmarking.md)).

## Key Takeaways
1. Retrieval speculation replaces the drafter with corpus/prompt statistics — unbeatable
   on repetitive workloads, useless off-distribution.
2. Self-speculation turns the target's redundancy into the drafter; architecture-
   dependent (hybrid models vary wildly).
3. Lookahead/Jacobi removes even the draft model, trading per-step FLOPs for fewer
   steps; exact and training-free.
4. All ride standard verification: they are drop-in proposer replacements in the
   taxonomy, not new acceptance machinery.
5. Production stacks pair these with trained drafters — n-gram as the zero-cost
   fallback, EAGLE/MTP as the acceptance workhorse.

## Related
[02 Draft and Verify](02-draft-and-verify.md) · [04 Taxonomy](04-speculative-decoding-taxonomy.md) ·
[07 SpecInfer](07-specinfer-tree-decoding.md) ·
[../KV-Cache/Prompt-and-Prefix-Caching.md](../KV-Cache/Prompt-and-Prefix-Caching.md) ·
[17 Framework Implementations](17-framework-implementations.md)

## References
- REST, arXiv:2311.08252 [F] · Lookahead, arXiv:2402.02057 [F] · LayerSkip, arXiv:2404.16710 [F]
- Draft & Verify, arXiv:2309.08168 [F] · OSD, arXiv:2310.07177 [F]
- Component-Aware Self-Speculative Decoding in Hybrid LMs, arXiv:2605.01106 [F]
- vLLM/SGLang docs [F: docs]
