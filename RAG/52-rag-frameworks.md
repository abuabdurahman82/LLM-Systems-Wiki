# RAG Frameworks — LlamaIndex, LangChain, DSPy and the SDK Land

`LAST_UPDATED: 2026-08-30` · Status: core page · All repos/licenses/venues
below verified against GitHub API + paper sources on 2026-08-29/30.

## LlamaIndex
- **Repo** github.com/run-llama/llama_index · **license MIT** · one of the
  most-starred data-framework repos in Python [F: GitHub API 2026-08-29].
- Core abstraction stack: `Document` → `Node`/`TextNode` (the unit of
  retrieval) → **index** (`VectorStoreIndex`, `KeywordTableIndex`,
  `KnowledgeGraphIndex`) → `Retriever` → `QueryEngine`/`AgentWorkflow`
  [F: package structure].
- Ingestion pipeline (loaders → node parsers → embedders → index) is the
  part that encodes chunking choices — see 46: the framework's default
  chunker settings are exactly the kind of "default you must inspect"
  this section keeps flagging.

## LangChain / LangGraph
- **Repo** github.com/langchain-ai/langchain · **MIT** [F]. The 2024–25
  restructure split the monolith into `langchain-core` (abstractions),
  `langchain-community` (third-party integrations), and vendor packages
  (`langchain-openai`, `langchain-anthropic`, …) [I: structure per repo
  layout; package names verified].
- RAG-relevant abstractions: `Document` loaders, `Embeddings`, vector-store
  wrappers, `Retriever`, `ChatModel`, and the retrieval-qa chain pattern.
- **LangGraph** (github.com/langchain-ai/langgraph) reframes workflows as an
  explicit **graph of nodes** with typed state + checkpointer (persistence
  across steps, human-in-the-loop) [F: repo; MIT]. Where plain LLM-calling
  frameworks treat retrieval as one tool call, LangGraph makes *when* to
  retrieve a control-flow decision — the same question 23 (Adaptive-RAG)
  answers with a learned router.
- LangSmith is the paid observability platform in the same ecosystem [I:
  product positioning, not audited here].

## DSPy
- **Paper**: arXiv:2310.03714 "DSPy: Compiling Declarative Language Model
  Calls into Self-Improving Pipelines" — Khattab, Singhvi, et al. (13
  authors) [F: arXiv API + OpenReview record, venue ICLR 2024].
- **Repo** github.com/stanfordnlp/dspy · **MIT** · ~37k★ [F: GitHub API].
  (The "stanford-templates" org 404s — use stanfordnlp.)
- Abstraction model: **Signatures** (typed LM calls), **Modules**
  (composable units), **Optimizers** (compile the pipeline against a metric).
  `MIPROv2` (multi-prompt inference) is the flagship optimizer and lives in
  `dspy/teleprompt/mipro_optimizer_v2.py` [F: file path verified in repo].
- RAG relevance: DSPy's optimizer can tune *both* the prompt templates and
  (via retrieval modules) the retrieval pipeline against an eval metric —
  the closest open-source analogue to "compile your RAG" [I: interpretation
  of the abstractions].

## Haystack (deepset)
- **Repo** github.com/deepset-ai/haystack · **Apache-2.0** [F].
- Abstraction: components (PreProcessor, DocumentSplitter, Embedder,
  Retriever, Ranker) wired into a **Pipeline**; index backends include
  Elasticsearch/OpenSearch, Weaviate, Qdrant, in-memory [F: repo docs].
- Historically the cleanest open source expression of the
  "load → split → embed → index → retrieve → rerank" pipeline, which is why
  its component list reads like this section's 31/32/33/34 [I: reading of
  the lineage].

## Microsoft Semantic Kernel
- **Repo** github.com/microsoft/semantic-kernel · **MIT** [F].
- Positioning: SDK for integrating LLMs into *applications* (agents,
  plugins, planners), with RAG building blocks (vector-data-store
  abstractions over Azure AI Search / other backends) [I: positioning per
  repo docs; not audited for retrieval quality].
- Distinct from the academic frameworks: it targets production app
  integration with Azure services rather than research pipelines [I].

## How to pick (the engineering answer)
- You want **research-adjacent control** over every stage → LlamaIndex or
  Haystack (explicit pipeline objects, index/retriever separable) [I].
- You want **agentic control flow** around retrieval (loops, tools,
  human-in-loop) → LangGraph [I].
- You want the pipeline **optimized against a metric** rather than hand-tuned
  → DSPy [I].
- You are building an **enterprise app on Azure** → Semantic Kernel [I].
- The retrieval-quality levers that actually matter (chunking, retrieval
  model, reranking, evaluation) are framework-agnostic — see 31/38/14/45.
  Frameworks change the plumbing, not the physics [A].
