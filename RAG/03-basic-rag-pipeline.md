# The Basic RAG Pipeline — Stage by Stage

`LAST_UPDATED: 2026-08-29` · Status: core page · The baseline architecture every
variant in this section is measured against. Terminology note: "basic/naive RAG"
is not a standardized term — `2312.10997`-style surveys popularized the
Naive/Advanced/Modular split (see 05); here it simply means the single-pass,
single-retriever pipeline below.

## 30-Second Explanation
The baseline: parse documents → chunk → embed → index; at query time: embed the
query → ANN top-k → stuff chunks into a prompt → LLM. Twelve stages (the table
below), each with a defensible default and a measurable failure mode. This pipeline is the "happy
path" — every upgrade in this section (hybrid, rerank, HyDE, graphs, agents) is
a *replacement or insertion of one of these stages*, which is why knowing the
baseline is the 80/20 entry point.

## The pipeline
```
INGESTION (offline, per corpus change)
documents → parsing → cleaning → chunking → embeddings → index

QUERY (online, per request)
user query → query embedding → similarity search → top-k → prompt assembly → LLM → answer
```

## Stage by stage
| Stage | What happens | Default | Failure mode when done poorly |
|---|---|---|---|
| **Documents** | The corpus: PDFs, HTML, code, DBs, wikis | whatever the business has | unparseable content silently dropped (11) |
| **Parsing** | bytes → ordered text + structure (headings, tables, images) | plain-text extraction | structure lost → chunks cross section boundaries; tables become gibberish (11) |
| **Cleaning** | dedup, boilerplate removal, encoding/ligature fixes | light cleanup | junk tokens waste embedding budget; duplicates inflate recall of the same content |
| **Chunking** | split into retrieval units | fixed ~512 tokens, 10–15% overlap | splits destroy context; huge chunks dilute retrieval (10) |
| **Embeddings** | chunk → dense vector (optionally also sparse scores) | a general-purpose embedding model | wrong model for the language/domain (07) |
| **Index** | vectors (+ metadata) into searchable structure | HNSW ANN index, no filters | ANN recall loss; missing metadata = no filtering (08, 12) |
| **Query** | user's raw question (as-is in the naive version) | the raw string | coreference, typos, underspecification (15) |
| **Query embedding** | query → same vector space as chunks | same model as index | asymmetric retrieval gap (07) |
| **Similarity search** | find top-k by cosine/dot over the index | k=10–20, HNSW | semantic mismatch: similar-looking, wrong-for-the-question (06) |
| **Top-k** | the k chunks, in score order | raw ANN order | no ranking quality; duplicates; context pollution (14) |
| **Prompt** | chunks + question + instructions, in order | concatenation | lost-in-the-middle; instruction dilution; no citation format (40, 41) |
| **LLM** | generate the answer | any instruct model | unfaithful synthesis even when the right chunk is present |

The two halves have different cost structures: ingestion runs once per corpus
update (parse + embed + index; cost scales with corpus size), the query path runs
per request (embed + search + LLM; cost scales with k and context length).
Everything in `44-rag-economics.md` builds on this split.

## The pipeline's built-in weaknesses
The naive pipeline is *the* baseline, and its weaknesses are the map of this
section. Each names the page that fixes it:

| Weakness | Consequence | Fix (page) |
|---|---|---|
| Bad chunking | retrieval unit ≠ semantic unit | 10 |
| Weak / mismatched embeddings | wrong neighborhood | 07 |
| Semantic mismatch (dense-only) | miss exact-match queries (error codes, IDs) | 13 |
| Missing context in chunk | "the throughput rose 27%" — of what? | 40 |
| Irrelevant top-k | the LLM hallucinates or rambles | 14, 15 |
| Duplicate / near-duplicate chunks | wasted context, inflated self-similarity | 41, 46 |
| No reranking | ANN order ≠ relevance order | 14 |
| Context pollution (20 chunks, 4 useful) | 80% of tokens are noise | 14, 41 |
| Lost-in-the-middle | evidence in position 10/20 under-attended | prompt ordering; `../Context-Engineering/` |
| No reasoning over retrieval | single hop, one-shot, no follow-up | 24, 26, 27 |
| No validation | no idea whether retrieval hit; ungrounded answers ship | 45, 47 |

Two of these deserve emphasis because they define the whole quality story:
**(1) retrieval miss is unrecoverable by the generator** — the LLM can only
work with what the context contains; and **(2) recall ≠ faithfulness** — the
retrieval layer optimizes "did the right chunk make the top-k" (measurable in
advance, see 45/46), while generation quality is a separate, conditional
property ("given these chunks, is the answer faithful"). You cannot debug one
with the other's metric.

## What "top-k" actually costs
k is not free. Each chunk consumes context tokens (prefill), KV cache, and
attention. A hand model [E, machine-checked]: with 512-token chunks at
$3/$15 per 1M in/out tokens, 10 chunks = 5,120 input tokens ≈ $0.0154 input +
500-token generation ≈ $0.0075 → **≈ $0.023/request**; 50 chunks is ~5× the
input cost (~$0.077 input ≈ $0.084/request total) and ~5× the prefill/KV load. This is why "send
more chunks" is a last resort, not a first move — see `41-context-compression.md`
and `44-rag-economics.md`.

## Key Takeaways
1. Twelve stages, two cost domains (ingestion vs query) — all RAG engineering is
   choosing implementations per stage.
2. Every "advanced" technique replaces or inserts one stage; learn the baseline
   before the variants.
3. Retrieval misses are unrecoverable downstream — retrieval quality caps
   generation quality.
4. Top-k has a token price; context size is an engineering budget, not a knob
   to turn up.
5. Evaluate retrieval (recall@k, MRR) and generation (faithfulness) separately
   — they must be measured separately (45); a retrieval miss caps the
   generator, but the two failure modes are distinct, not "independent."

## Related
[04 taxonomy](04-rag-taxonomy.md) · [05 naive vs advanced vs modular](05-naive-advanced-modular-rag.md) ·
[10 chunking](10-chunking.md) · [14 reranking](14-reranking.md) ·
[45 evaluation](45-rag-evaluation.md) · `../Evaluation-Engineering/RAG-Evaluation.md`
