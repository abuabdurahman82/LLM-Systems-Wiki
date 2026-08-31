# Chunking Engineering — The Retrieval Unit Is a Design Decision

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
splits are [I] unless marked.

## 30-Second Explanation
A chunk is the *atomic unit of retrieval*: what gets embedded, what gets
scored, what gets deduplicated, what gets cited. If the chunk boundaries are
wrong, no retriever or reranker downstream can fully recover — the embedding
model *embeds* the content of the chunk, and a chunk that mixes two topics embeds in
between them. Chunking is therefore a retrieval design decision with a measurable
cost, not a text-processing detail.

## The chunk family
| Strategy | Rule | Good for | Danger |
|---|---|---|---|
| **Fixed-token** | every N tokens (e.g. 512) | simple corpora, baselines | cuts mid-sentence/mid-table; uniform size ≠ uniform semantic load |
| **Fixed-character** | every N chars (e.g. 1000–2000) | legacy pipelines | same problem, coarser control |
| **Sentence** | 1–3 sentences | fine-grained retrieval, QA over facts | too little context; coreference ("it", "they") breaks |
| **Paragraph** | blank-line blocks | prose where paragraphs are topical | paragraph length is wildly uneven; some are pages |
| **Recursive** | split by hierarchy: section → paragraph → sentence → word, taking the *largest* unit that fits the size | the practical default (e.g. LangChain's `RecursiveCharacterTextSplitter`) | still blind to *semantic* boundaries |
| **Sliding-window** | fixed window + overlap (10–25% typical) | smooth coverage across boundaries | duplicates inflate the index; overlapping content retrieved twice (dedup at ingestion (11) or retrieval time) |
| **Semantic** | embed sentences, cut where embedding similarity drops (clustering of consecutive embeddings) | topic-coherent chunks | cost: embed everything twice; boundary sensitivity to the embedding model |
| **Document-structure** | follow headings/sections (Markdown `#`, PDF TOC, HTML sections) | structured corpora (docs, wikis, code) | structure quality varies; deep hierarchies → tiny leaves |
| **Parent-child** | embed small children, return the parent on hit | precision + context (see 18) | two-tier complexity; parent size must fit the budget |
| **Hierarchical** | index every level (chunk, section, chapter, doc summary) | coarse-to-fine routing (see 19, 20) | index construction cost × levels |

## Chunk size: the standing question
"What is the optimal chunk?" has **no universal answer** — it is a function of
query type, corpus structure, embedding model, and the reranker downstream
[I]. What *is* measurable, per corpus, with your golden set (46):

- **Too small** (<256 tok): context starvation — "the system" is in chunk 4,
  what it is in chunk 3; retrieval granularity exceeds the answer's span.
- **Too large** (≥2048 tok): dilution — the chunk's embedding is an average over
  multiple topics; the top-k fills up with partially-relevant material; the
  prompt budget blows up [E: 512-tok chunks ≈ 2 KB text ≈ 380–400 words; a
  2048-tok chunk is ≈ 4× that (≈1,500–1,600 words); 10 of the large ones is
  20,480 tokens of prefill].
- **The 80/20 range**: 256–1024 tokens for general text (a chunk *at* the
  bottom of that band is workable; below ~256 starts to starve), *structure-
  aware boundaries preferred over fixed sizes* [I: common practitioner default;
  see 53 Lab 4 for the ablation protocol].

Overlap: 10–25% is the conventional band [I]; more buys boundary safety at the
cost of index bloat and duplicate context (56: "too much overlap"). If you use
structure-aware splitting, overlap can often be *zero* — the structure is the
safety.

## Semantic coherence: what actually matters
The property that makes a chunk retrievable is **topical self-sufficiency**: can
a reader (or an embedding model) tell what this chunk is *about*, and is the
answer to plausible questions about that topic *inside* it? Three checks:
1. **Head coverage**: does the chunk state its own subject? ("In §4.2 we show
   that PagedAttention reduces KV waste…" — yes. "…reduces KV waste…" — no.)
2. **Coreference closure**: does "it" have an antecedent *in the chunk*?
3. **Answer span fit**: does a typical answer to a question about this chunk fit
   in one chunk without crossing a boundary?

Chunks that fail head-coverage are the raw material of **contextual retrieval**
(40) — prefix them with generated context. Chunks that fail answer-span-fit are
the argument for parent-child (18).

## Context redundancy
A document's information is not uniformly distributed: the bulk of retrieval
value often sits in headers, first paragraphs, and tables [I: the *in-document
value-density* observation — distinct from lost-in-the-middle, which is a
*positional-attention* effect inside long LLM contexts (39, 47 cover the
latter); they motivate the same mitigation but are not the same phenomenon].
Chunking that treats page 1 and page
40 identically wastes the index. Two cheap mitigations: keep section headings
attached to their chunks (structure-aware splitting), and index *summaries* of
large units alongside their chunks (19/20).

## The chunking decision, summarized
```
corpus structure?
├── well-structured (docs/wiki/code)  → structure-aware, 256–1024 tok, no overlap
├── flat prose (chat logs, tickets)   → recursive/sentence, 256–512 tok, 10–25% overlap
├── fact-dense (specs, catalogs)      → fine chunks + parent-child return (18)
└── long-form (reports, books)        → hierarchical: index leaves AND summaries (19/20)
```
Then *measure*: golden set (46) → retrieval recall@k per chunking config →
pick by your task, not by vibes. Lab 4 in 53 is exactly this
ablation.

## Key Takeaways
1. The chunk is the retrieval unit — its boundaries are a design decision with
   measurable cost, not a formatting choice.
2. No universal optimal size; 256–1024 tokens with structure-aware boundaries is
   the 80/20 default [I].
3. Overlap is a boundary-safety tax; structure-aware splitting often removes the
   need for it.
4. Self-sufficiency (head coverage, coreference closure, answer-span fit) is the
   property that makes chunks retrievable.
5. Chunking ablations on a golden set are cheap and decisive — run them (53).

## Related
[18 parent-child](18-parent-child-rag.md) · [19 hierarchical](19-hierarchical-rag.md) ·
[40 contextual retrieval](40-contextual-retrieval.md) · [46 golden datasets](46-rag-golden-datasets.md) ·
[11 ingestion](11-document-ingestion.md) · [56 anti-patterns: huge chunks / too much overlap](56-rag-antipatterns.md)
