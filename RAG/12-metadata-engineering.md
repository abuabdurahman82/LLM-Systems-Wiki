# Metadata Engineering — The Reason Enterprise RAG Lives or Dies Here

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
filtering semantics per vector DB follow the research bank
(`/tmp/rag-research/B-ir-embeddings-dbs.md`).

## 30-Second Explanation
Metadata is the structured data attached to each chunk that is *not* the chunk
text: where it came from, who owns it, when it was true, who may see it.
Vector search answers "what is similar?"; metadata answers "*which* similar
things am I allowed to use, from which version, in which scope". Enterprise RAG
runs on metadata: filtering, ACLs, tenancy, versioning, citation. A chunk
without provenance is a liability.

## The metadata canon
| Field | Example | Why it exists |
|---|---|---|
| **document** | `doc_id=fin-q3-report-2025` | join chunk→source; dedup; audit |
| **page / section** | `page=14, section=§4.2 Results` | citation ("p.14"), structure-aware rerank |
| **author / owner** | `author=J. Kim` | provenance; accountability |
| **date** | `published=2025-11-03` | freshness filtering ("last quarter only") |
| **department / team** | `dept=finance` | scoping + tenancy |
| **tenant** | `tenant=acme-corp` | isolation (49) — the most safety-critical field |
| **security classification** | `classification=confidential` | pre-retrieval ACL enforcement (48) |
| **language** | `lang=en` | per-language retriever/embedding routing (07) |
| **version** | `version=3, supersedes=2` | stale-answer prevention; audit |
| **source URL / path** | `url=wiki.internal/fin/q3` | citation; re-fetch; dedup |
| **chunk index / overlap id** | `chunk=17, parent=parent-3` | parent-child return (18), dedup (41) |
| **license / rights** | `license=internal-only` | export control (34 web RAG: Crawlable vs no-crawl) |

The first ten fields cover the *core* enterprise needs (the last two cover
cross-reference and export-control cases) [I]. The design rule: **record at
parse time what you will ever need to filter, sort, cite, or authorize** —
metadata added later is a backfill at best: *scalar* fields (tenant,
classification, dates, dept) can usually be backfilled in place without
re-embedding (Qdrant `set_payload`, Pinecone `update`, Weaviate PATCH-class
payload writes) [I: vendor mechanisms — see 09], but *parse-derived structural*
metadata (page/section/chunk boundaries, parent ids) forces re-parsing, and any
change to chunking forces re-embedding.

## Filtering: pre vs post, and why it matters
Three enforcement points:
1. **Pre-filtering**: filter the candidate set *before* ANN search
   (`WHERE tenant='acme' AND classification IN ('public','internal')`). In
   HNSW-class indexes the filter is applied *during* graph traversal — the
   graph was built over the whole space, so a highly selective filter can
   degrade recall (the traversal may not be able to reach the few allowed
   nodes) [I: generic HNSW behavior]. Vendors address this differently —
   e.g. Qdrant documents building a *separate HNSW over the filtered subset*
   for highly selective filters in addition to filter-aware traversal; Milvus/
   Weaviate pre-filter variants [I: vendor doc behavior; see 09]. (Running HNSW
   "within the subset" literally is a separate sub-index, not the same graph.)
2. **Post-filtering**: ANN search over everything, filter the top-k. Fast, but
   can return *fewer than k* results when most of the top-k are filtered out —
   and worse, the ANN layer *looked at* disallowed documents. Never acceptable
   as the sole ACL mechanism.
3. **Hybrid**: pre-filter for the strict fields (tenant, classification),
   post-filter for soft ones (recency) — a common production compromise [I].

The non-negotiable: **ACLs are pre-filter or separate-index, enforced by the
search engine, not by the LLM** (48). A model that "promises" not to quote a
confidential doc is not an access-control system.

## Why enterprise RAG depends on metadata
- **Scoping**: "only last two quarters, only finance, only GA releases" is a
  metadata predicate — without it, retrieval over the whole corpus pollutes
  every answer.
- **ACLs/tenancy**: `tenant` + `classification` are the two fields a security
  team will audit first (48, 49).
- **Versioning**: `version`/`supersedes` let you serve "current" answers and
  audit "what did the system know on 2025-09-01".
- **Citation**: page/section/source make "p.14 of the Q3 report" a real claim,
  not "a chunk" (45).
- **Diagnostics**: when retrieval fails, metadata tells you *where* it failed
  (wrong section? wrong version? filtered out by a stale predicate?) — 47/50.

Filter design smells [I]: filtering on free text (store categories as enum
metadata, not as string-matched prose); missing a `null` policy (a chunk with
no `classification` must default *deny*, not *allow*); and unversioned
metadata (a doc re-uploaded with changed scope but the same `doc_id`).

## Key Takeaways
1. Metadata is retrieved alongside vectors — design it at parse time or pay
   for a backfill (scalar) / re-parse (structural) / re-embed (chunking)
   later.
2. ACL enforcement is an engine-layer property — **pre-filter or separate
   index**; post-filtering and prompt-layer promises are not security
   (post-filtering may still serve as a defense-in-depth *check* on top, but
   never as the mechanism).
3. Tenant + classification are the two fields security audits; default-deny on
   missing values.
4. Version/supersede fields are what make "stale answer" a detectable, fixable
   bug instead of a mystery (47).
5. Citation quality is a metadata quality problem: no page/section fields, no
   real citations.

## Related
[48 security](48-rag-security.md) · [49 multi-tenant](49-multi-tenant-rag.md) ·
[09 vector DB filtering](09-vector-databases.md) · [47 stale-info failure](47-rag-failure-modes.md) ·
`../Safety/README.md`
