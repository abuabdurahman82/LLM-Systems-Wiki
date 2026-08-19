# Lost in the Middle & Long-Context Reality
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
The advertised context window (128k, 1M, 10M) is a *memory capacity* number, not a
*usable-attention* number. The model's **effective context** — the length at which
it reliably uses information placed at *any* position — is typically a fraction of
the nominal one, and attention is *position-biased*: information at the start and
end of the context is used better than information in the middle
("**lost in the middle**"). This page covers (a) what the evidence says,
(b) why position bias happens, and (c) the 2024–26 extension methods and their
honest limits.

## What the evidence says
- **Lost in the Middle** (Liu et al. 2023, arXiv:2307.03172 [F]): on multi-document
  QA, accuracy follows a **U-shaped curve** — highest when the relevant document is
  first or last, lowest in the middle, even in models with long nominal windows.
  The effect is *structural*, not just a matter of length. [F]
- **RULER** (Hsieh et al. 2024, arXiv:2404.06654 [F]): synthetic, controllable
  long-context tasks (retrieval, multi-needle, tracking, QA) that separate *retrieval
  capacity* from *reasoning at length*. Headline: many models whose marketing says
  "128k" perform reliably only up to **a few × 10k** tokens on RULER-style tasks
  [I: consistent with the paper's finding that effective length ≪ nominal; exact
  per-model numbers vary and are model/version-specific].
- **BABILong** (arXiv:2406.10149 [F]): long-context *reasoning-in-a-haystack* —
  shows that stuffing a long context degrades even simple reasoning, not just
  retrieval.
- **LongBench** (arXiv:2308.14508 [F]): earlier multi-task long-context benchmark
  (bilingual).
- **Thus Spake Long-Context** (Liu et al. 2025, arXiv:2502.17129 [F]): the
  2025 long-context *survey* (architecture / infrastructure / training /
  evaluation, + 10 open questions) — the reference map of the field; its
  framing: LLMs push toward ever-longer context while context remains
  fundamentally finite.
- **Frontier claim vs reality [A/vendor-claim]:** "1M-token" models (e.g.
  Gemini-class, 2024–26) are *retrieval-capable* near 1M for needle-finding, but
  *multi-step reasoning over the whole window* degrades well before 1M
  [I: consistent across the eval literature]. Distinguish: **needle in a haystack
  (find one item)** ≠ **reason across the haystack (use many items together)**.
  The first scales nearly to the nominal window; the second does not.

## Why position bias happens (first principles)
1. **Attention is local-ish + recency-weighted.** Even with global attention,
   the model's learned behavior (from mostly short training examples) weights
   recent tokens heavily; middle tokens get less aggregate attention mass
   [I: consistent with attention-sink / recency findings].
2. **Training-data length distribution.** Most pretraining sequences are short
   (few k); the model sees *very few* truly-long examples, so its long-range
   attention is under-trained even when the *architecture* supports it [I].
3. **KV-cache pressure at length.** At long S, the attention kernel must read a
   large KV per step; approximate/skipping patterns (or the model's own learned
   "ignore the middle" shortcut) emerge. The *compute* of long attention is real
   (`../Inference/Roofline.md`), so "infinite attention" is never free
   [I].
4. **Softmax saturation.** With very long sequences, the softmax over attention
   weights can dilute any single important token's weight across thousands of
   distractors — retrieval becomes a "1-of-many" problem that gets harder with
   many [I].

## The extension methods (2023–26) and honest limits
| Method | Paper | What it does | Limit |
|---|---|---|---|
| **Positional interpolation** | Chen et al. 2023, arXiv:2306.15595 [F] | rescale RoPE base to fit more positions | smooths, doesn't add capability; needs light retraining |
| **YaRN** | Peng et al. 2023, arXiv:2309.00071 [F] | "attention compensation" + PI + no-rope zone; 4× Llama-2 context | per-model tuning; degrades beyond ~4× |
| **LongRoPE** | Ding et al. 2024, arXiv:2402.13753 [F] | identifies non-uniformities in positional interpolation via an *efficient (non-RL) search* over rescaling factors + progressive extension; 2M on Llama-3 class [F: abstract] | expensive to derive; per-architecture |
| **Streaming / attention sinks** | Xiao et al. 2023, arXiv:2309.17453 [F] | keep a few "sink" tokens + rolling window for *streaming* | unbounded *stream*, not unbounded *reasoning* |
| **Ring / context-parallel attention** | arXiv:2310.01889 [F]; Ulysses arXiv:2309.14509 [F] | split KV across devices to *serve* long S | solves the memory/parallelism, not the position bias |
| **Long-context RL / post-training** | (2024–26) [I] | train on long-horizon tasks to *use* the window | the real fix for "reasons across it", but expensive |

**The pattern [I: synthesis]:** interpolation/PI/YaRN/LongRoPE extend *retrieval
capacity* (needle-finding) far past the trained window, cheaply. But they do **not**
automatically extend *reasoning quality across the window* — that requires either
post-training on long tasks or an external retrieval/summarization layer
(`RAG/`, `Context-Compaction.md`). A model can *store* 1M tokens and *find* a
needle at 900k while still failing a task that needs to *integrate* 50 facts
scattered across 500k. **Effective context for reasoning ≪ effective context for
retrieval** — that's the 2026 working distinction. [I]

## Implications for context engineering (the design rules)
1. **Don't rely on the middle.** Put critical info at the *front* (system/goal)
   or the *back* (most recent + the immediate instruction). If you must place
   important content mid-context, restate it near the end.
2. **Retriever > long-window for multi-document.** When the task is "find the
   relevant 5 of 500 docs", a retrieval step (`RAG/`) beats shoving 500 docs into
   the window — cheaper, and avoids the U-shaped degradation.
3. **Chunk + map-reduce for very long reasoning.** Split a long document into
   chunks, summarize/extract per chunk, then reason over the summaries
   (`Context-Compaction.md` § map-reduce).
4. **Benchmark the *task*, not the window.** A "128k model" is only as good as its
   performance *on your task* at *your* length — measure, don't assume
   (`../Agents/Agent-Evaluation.md`).
5. **Mind the batch.** Long S multiplies KV by B (`Context-Budget.md`); a config
   that works at B=1 fails at B=8.

## Related
`Context-Budget.md` · `Context-Compaction.md` · `../RAG/README.md` ·
`../KV-Cache/README.md` · `../Inference/Roofline.md` · `../Attention/README.md`.

## Key Takeaways
Nominal ≠ effective. Attention is U-shaped (ends beat the middle), retrieval
scales farther than reasoning, and extension methods buy *capacity* cheaply but
*reasoning quality* only via post-training or external summarization. Design
against the U: keep the critical stuff at the ends, retrieve rather than stuff,
and map-reduce when the task spans more than the model can integrate.
