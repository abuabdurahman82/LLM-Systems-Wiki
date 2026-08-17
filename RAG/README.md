# RAG (Retrieval-Augmented Generation)
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
Give the model external knowledge at inference time: retrieve relevant documents, inject
them into context, generate. RAG = the model's external memory + its grounding in your
data (vs. hallucination or stale training data).

## The canonical pipeline
```
documents → chunking → embedding → vector DB → retrieval → reranking → context → LLM
```
| Stage | Choices | Failure mode |
|---|---|---|
| **Chunking** | fixed-size / semantic / hierarchical | splits destroy context; too big wastes window |
| **Embedding** | sentence-transformer-class, ColBERT-style, LLM-based embedders | semantic drift; domain mismatch |
| **Vector DB** | HNSW/pgvector/Milvus/Qdrant/FAISS-class | ANN recall loss; scale |
| **Retrieval** | dense / sparse(BM25) / **hybrid** | single-modality blind spots |
| **Reranking** | cross-encoder (ColBERTv2, RankLLaMA) | cost; top-k only |
| **Context assembly** | order + budget (`Context-Engineering/`) | lost-in-the-middle |
| **Generation** | grounded answer + citations | citation hallucination |

## Advanced RAG (the 2023–2026 research wave)
- **Hybrid retrieval** (dense + BM25, reciprocal rank fusion) — still the workhorse [I].
- **Query rewriting / multi-query** — decompose, retrieve per subquery, merge [I].
- **Graph RAG** (Microsoft, arXiv:2404.16135 [F]) — knowledge-graph + community
  summaries; strong for "corpus-wide" questions; costlier to build.
- **Agentic RAC/RAG** — the agent *decides* when/what to retrieve, iteratively
  (search-as-tool); the 2025+ default in coding agents [I].
- **Corrective RAG (CRAG)** (arXiv:2401.15884 [F]) — retrieval confidence + web fallback.
- **Self-RAG** (Asai et al. 2023, arXiv:2310.11511, ICLR'24 [F]) — model emits critique
  tokens (Retrieve/IsRel/IsSup) and learns to retrieve when needed.
- **Late interaction** (ColBERT-class) — token-level matching for precision [F: arXiv:2004.12832].
- **Long-context vs RAG** — the standing debate: at 1M+ contexts, "stuff the context"
  competes with retrieval. Evidence: long-context is *worse per-token cost* and has
  lost-in-the-middle issues; RAG stays cheaper and refreshable. The practical answer is
  **hybrid**: RAG for breadth, long context for depth [I: 2025–26 consensus].

## Evaluation
- Faithfulness/groundedness (answer supported by context), relevance, retrieval quality
  (recall@k, MRR). RAGAS-class toolkits (2024 [F: repo]).
- **What it does NOT test:** whether the *right* document existed in the corpus
  (coverage), chunking adequacy, or whether the model would have known it anyway.

## Related
`Context-Engineering/README.md` · `Evaluation/README.md` · `Safety/README.md`
(prompt injection via RAG).

## Key Takeaways
RAG = external memory with a hard recall problem. The pipeline is 80% solved; the hard
parts are chunking quality, hybrid retrieval, and grounding faithfulness.
