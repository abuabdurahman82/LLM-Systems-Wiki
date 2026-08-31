# RAG Engineering — Retrieval-Augmented Generation, From Search to Knowledge Systems

`LAST_UPDATED: 2026-08-29` · Status: core section · Primary sources (papers, vendor docs, framework
repos) verified live 2026-08-29; see `EVALUATION.md` for the independent audit record.

## 30-Second Explanation
A standalone LLM answers from parametric memory: frozen at training time, un-citable,
blind to your private data, and expensive to retrain. **RAG (Retrieval-Augmented
Generation)** injects external evidence *at inference time*: retrieve relevant
documents, pack the best of them into the prompt, and generate with citations.
The naive mental model ("put docs in a vector DB, retrieve top-k") works for a toy;
production RAG is an **information-retrieval + context-engineering system**:

```
RAG = Retrieval + Ranking + Context Engineering + Generation
    + Evaluation + Memory + Policy + Observability
```

The canonical pipeline:

```
USER QUESTION → Query Understanding → Query Transformation
   → Lexical Search ∥ Vector Search → Retrieval → Reranking
   → Context Selection → Context Packing → LLM → Response
   → Evaluation / Feedback ──↺
```

## The 80/20 in one paragraph
Retrieval quality limits generation quality: a generator cannot answer what the
retriever failed to surface. Dense search finds *semantically similar* text;
keyword (BM25) search finds *exact* tokens — hybrid search + a cross-encoder
reranker is the workhorse for most corpora [I: engineering consensus 2024–26].
Top-k is not context engineering: which chunks, in what order, at what total
token budget, is a design decision with measurable cost. Chunking is a retrieval
design decision, not a text-processing step. Metadata is where enterprise RAG
lives (filtering, ACLs, tenancy). RAG must be evaluated at the retrieval layer
*and* the generation layer separately, because each can fail independently.
Security is enforced **before** evidence reaches the model — retrieval
authorization happens at the search layer, not after.

## Contents
- **Foundations** — [01 why RAG exists](01-why-rag-exists.md) ·
  [02 history & lineage](02-rag-history.md) ·
  [03 the basic pipeline](03-basic-rag-pipeline.md) ·
  [04 taxonomy of RAG types](04-rag-taxonomy.md) ·
  [05 naive vs advanced vs modular](05-naive-advanced-modular-rag.md) ·
  [06 IR foundations: TF-IDF, BM25, dense, cosine](06-information-retrieval-foundations.md)
- **Core retrieval** — [07 embedding engineering](07-embedding-engineering.md) ·
  [08 vector search & ANN algorithms](08-vector-search.md) ·
  [09 vector databases](09-vector-databases.md) ·
  [10 chunking](10-chunking.md) ·
  [11 document ingestion & parsing](11-document-ingestion.md) ·
  [12 metadata engineering](12-metadata-engineering.md)
- **Retrieval upgrades** — [13 hybrid retrieval](13-hybrid-rag.md) ·
  [14 reranking](14-reranking.md) ·
  [15 query transformation](15-query-transformation.md) ·
  [16 multi-query RAG](16-multi-query-rag.md) ·
  [17 HyDE](17-hyde.md) ·
  [18 parent-child retrieval](18-parent-child-rag.md) ·
  [19 hierarchical RAG](19-hierarchical-rag.md) ·
  [20 RAPTOR](20-raptor.md) ·
  [21 Self-RAG](21-self-rag.md) ·
  [22 Corrective RAG](22-corrective-rag.md) ·
  [23 Adaptive RAG](23-adaptive-rag.md)
- **Agents & graphs** — [24 Agentic RAG](24-agentic-rag.md) ·
  [25 multi-agent RAG](25-multi-agent-rag.md) ·
  [26 multi-hop RAG](26-multi-hop-rag.md) ·
  [27 recursive RAG](27-recursive-rag.md) ·
  [28 Graph RAG (the category)](28-graph-rag.md) ·
  [29 knowledge-graph RAG](29-knowledge-graph-rag.md)
- **Knowledge source types** — [30 structured-data RAG](30-structured-data-rag.md) ·
  [31 multimodal RAG](31-multimodal-rag.md) ·
  [32 conversational RAG](32-conversational-rag.md) ·
  [33 memory-augmented RAG](33-memory-rag.md) ·
  [34 web RAG](34-web-rag.md) ·
  [35 real-time / streaming RAG](35-realtime-rag.md) ·
  [36 federated RAG](36-federated-rag.md) ·
  [37 domain-specific RAG](37-domain-specific-rag.md) ·
  [38 code RAG](38-code-rag.md) ·
  [39 long context vs RAG](39-long-context-vs-rag.md) ·
  [40 contextual retrieval](40-contextual-retrieval.md) ·
  [41 context compression](41-context-compression.md)
- **Systems** — [42 RAG + caching](42-rag-caching.md) ·
  [43 RAG + inference engineering](43-rag-inference-engineering.md) ·
  [44 RAG economics](44-rag-economics.md) ·
  [45 RAG evaluation](45-rag-evaluation.md) ·
  [46 golden datasets](46-rag-golden-datasets.md) ·
  [47 failure modes](47-rag-failure-modes.md) ·
  [48 RAG security](48-rag-security.md) ·
  [49 multi-tenant RAG](49-multi-tenant-rag.md) ·
  [50 RAG observability](50-rag-observability.md) ·
  [51 production reference architecture](51-production-rag-reference-architecture.md)
- **Synthesis** — [52 RAG frameworks](52-rag-frameworks.md) ·
  [53 hands-on labs + experiment matrix](53-rag-labs.md) ·
  [54 which RAG should I use (decision tree)](54-which-rag-should-i-use.md) ·
  [55 RAG types comparison matrix](55-rag-types-comparison.md) ·
  [56 RAG anti-patterns](56-rag-antipatterns.md) ·
  [57 the 20% that explains 80%](57-rag-80-20.md) ·
  [58 zero-to-hero](58-rag-zero-to-hero.md) ·
  [59 open research questions](59-open-rag-research-questions.md) ·
  [60 RAG + agents: unified view](60-rag-agent-context-unified-view.md) ·
  [61 the big picture](61-rag-big-picture.md)

## Reading paths
- **Zero-to-hero:** `58-rag-zero-to-hero.md` (10 levels, mapped to these pages).
- **Enterprise builder:** 01 → 03 → 10 → 12 → 13 → 14 → 44 → 48 → 49 → 51.
- **Researcher:** 02 (lineage) → 21–23 (learned retrieval control) → 20/28
  (structure-based) → 59 (open questions).
- **Search engineer:** 06 → 08 → 09 → 13 → 14.
- **Systems engineer:** 43 → 42 → 44 → 50 → 51.

## Cross-links (no duplication, just pointers)
| Topic | Home section |
|---|---|
| Long-context limits, lost-in-the-middle | `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md` |
| Context budgeting & compaction | `../Context-Engineering/Context-Budget.md`, `../Context-Engineering/Context-Compaction.md` |
| Agent memory | `../Context-Engineering/Agent-Memory.md`, `../Agents/Multi-Agent-Systems.md` |
| Knowledge graphs & GraphRAG deep dive | `../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` |
| Prefill/decode, TTFT, continuous batching | `../Inference/The-Life-of-a-Token.md`, `../Inference/Continuous-Batching.md` |
| KV cache & prefix caching | `../KV-Cache/Prompt-and-Prefix-Caching.md` |
| Serving engines (vLLM/SGLang/TRT-LLM) | `../Serving-Engines/Engine-Landscape.md` |
| RAG evaluation measurement (metrics, judges) | `../Evaluation-Engineering/RAG-Evaluation.md` |
| RAG platform economics (tenant-level cost) | `../Platform-Economics/37-rag-economics.md` |
| Prompt injection & safety taxonomy | `../Safety/README.md` |
| Agentic loops & tool use | `../Agents/Agent-Loops-and-Reasoning-Strategies.md`, `../Agents/Tool-Use.md` |

## Key Takeaways
1. RAG is not a vector-database feature; it is an information-retrieval and
   context-engineering system with measurable failure layers (47).
2. The pipeline is a *design space*: every stage (chunk, embed, retrieve, rank,
   pack, generate, verify) has alternatives and a measurable cost.
3. Production quality comes from evaluating retrieval and generation separately,
   then iterating on the worse one (45).
4. Complexity should be *earned*: hybrid + reranker first; agents and graphs only
   when one-shot retrieval demonstrably fails (54).
5. Security and tenancy are retrieval-time concerns, not generation-time afterthoughts (48, 49).
