# RAG Hands-On Labs + Experiment Matrix

`LAST_UPDATED: 2026-08-30` · Status: synthesis page · Every number in the
matrix is a *prediction to verify*, not a result: the labs exist so you can
reproduce the failure modes this section describes on your own corpus.
Arithmetic below is machine-checked; retrieval quality claims are lab
outcomes, tagged [A] where they are assumptions.

## Lab 0 — Environment
- A corpus: ~50 documents of one domain (the wiki's LLM-inference section
  works: ~15 pages, ~40KB of text).
- Tools: Python 3.10+, `faiss-cpu`, an embedding model (sentence-transformers
  `all-MiniLM-L6-v2` as default; see 07), a small LLM for generation and
  evaluation (45).
- **Rule**: hold out 20 questions with known-correct answers *before* any
  pipeline run; they are the eval set (45: golden QA set).

## Lab 1 — The baseline and its failure modes
Chunk the corpus 512-token (20% overlap) chunks, embed with all-MiniLM-L6-v2,
FAISS `IndexFlatIP` (exact, small N), retrieve top-20, concatenate into a
prompt, generate. Score against the golden set.
- **Expected failure modes to observe** [A]: (i) questions whose answer spans
  two chunks; (ii) a question using terms absent from any chunk ("speculative
  decoding" when the text says "draft-model acceptance"); (iii) the
  long-document attention bias — for a question about a late section, the
  *relevant chunk* exists but ranks below top-10 (35, Lost in the Middle).
- Record: per-question retrieved rank of the golden chunk. This one number
  explains most of what the next three labs are for.

## Lab 2 — Hybrid retrieval delta
Add BM25 (06) over the same chunks, fuse with RRF (13) at k=60.
- **Hypothesis** [A]: lexical-only questions (exact term match) improve;
  paraphrased questions (different wording than the chunk) stay flat or drop
  — that is the exact failure mode hybrid is *not* for (13: failure-mode
  taxonomy).
- Measure per failure mode separately; the aggregate number will look
  better even when half the modes got worse. This is the 45/46
  "aggregate masks regime" lesson made concrete.

## Lab 3 — Reranker delta
Take the top-100 from Lab 2, rerank with a cross-encoder
(Cross-Encoder/ms-marco-MiniLM-L-6 [I: available HF model; swap freely]),
take top-5 for the prompt.
- **Hypothesis** [A]: rank of the golden chunk in the *final* prompt improves
  most on the "right chunk, wrong position" cases (Lab 1 (iii)); little effect
  on "chunk missing" cases — the reranker cannot recover what the retriever
  never fetched (14).

## Lab 4 — Chunking sensitivity
Re-run Lab 1 at chunk sizes 256 / 512 / 1024 tokens (same overlap rule).
- **Expected** [A]: small chunks → more precision, more multi-chunk answers
  broken; large chunks → more context per hit, more attention dilution
  (33/35: context-length dilution is real and measurable). The optimum is
  corpus-dependent — that is the whole point of 32/33.

## Lab 5 — Evaluation without a golden set
Replace the golden QA set with RAGAS-style metrics (45: faithfulness, answer
relevance, context relevance) computed by an LLM judge.
- **Known limits** [I: 45's "no free lunch"]: LLM-judge scores track
  human judgment imperfectly; a pipeline can be *better on every judge
  metric* while answering more actual questions wrong (46's
  "eval-overfitting" mechanism). Keep the golden set as the anchor.

## Experiment matrix
Columns: R = retrieval stage variable, G = generation prompt variable.
Each cell = one pipeline config; "Δ rank" = golden-chunk rank vs Lab 1.

| Lab | Chunking | Retrieval | Rerank | Prompt | Δ rank (expect) |
|---|---|---|---|---|---|
| 1 | 512/20% | dense top-20 | none | concat | baseline |
| 2 | 512/20% | RRF(dense,BM25) top-20 | none | concat | lexical↑, paraphrase± |
| 3 | 512/20% | RRF top-100 | CE top-5 | concat | pos-errors↓, miss± |
| 4a | 256/15% | dense top-20 | none | concat | multi-chunk↓ |
| 4b | 1024/20% | dense top-20 | none | concat | dilution↑ |
| 5 | 512/20% | RRF top-100 | CE top-5 | + self-critique (17/21 pattern) | judge-metric↑, golden± |

## What "pass" means
A lab is not "done" when it runs; it is done when you have (a) the per-mode
numbers, (b) one sentence on which hypothesis was falsified, and (c) the
failure cases archived with their retrieved ranks. Those archived failures
are the golden dataset for the next iteration (46).

## Cost notes
Embedding the corpus: one pass per model version [E: ~N×(40KB/512) calls,
trivially small at this scale; use 08's table to extrapolate to real N].
The expensive step is Lab 4 re-embedding ×3 — cache embeddings keyed by
(chunk_hash, model_version) so the matrix is cheap to re-run after a model
swap (44: caching as a first-class design object).
