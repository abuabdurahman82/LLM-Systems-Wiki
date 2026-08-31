# RAG Anti-Patterns — What Fails and How to Fix It

`LAST_UPDATED: 2026-08-29` · Status: core page · Practice page; each entry is
engineering judgment [I] unless tagged; paper-grounded claims verified in the
research bank 2026-08-29 (lost-in-the-middle [F: 2307.03172]; CRAG's retrieval-
quality dependence [F: 2401.15884]; RAPTOR's chunk-limit motivation [F:
2401.18059]; GraphRAG's graph-build economics [F: 2404.16130]). Companion to
47 (failure taxonomy) — 47 localizes an incident; this page names the design
mistakes that manufacture incidents.

## 30-Second Explanation
Most RAG systems fail in one of seventeen ways that were decided *before* the
first query was served — at design time. Each subsection below is compact on
purpose: why it fails, the symptoms, the detection signal, and the fix. The
meta-pattern across all seventeen: the anti-pattern is usually a shortcut that
is *locally* rational (buy a DB, ship ANN order, crank k, trust the cache) and
*globally* expensive.

## The failure map
Where the seventeen live in the pipeline — most sit at design time, not in
model behavior [I]:

```
 DESIGN TIME                      RUN TIME (per query)
 ┌───────────────────────────┐    ┌────────────────────────────────────────┐
 │ 1  DB-only pipeline       │    │ 2  blind top-k                         │
 │ 3  huge chunks            │    │ 5  no reranking (ANN order shipped)    │
 │ 4  too much overlap       │    │ 8  50 chunks to the LLM                │
 │ 6  one embedder for all   │    │ 13 agents where retrieval suffices(24) │
 │ 7  metadata ignored (12)  │──► │ 15 1M context instead of retrieval(39) │
 │ 9/10 no/flat evaluation   │    │ 16 stale cache hits (42)               │
 │ 11 no doc versioning (12) │    │                                        │
 │ 12 no ACL enforcement(48) │    │ 4/6 symptoms surface at query time,    │
 │ 14 GraphRAG unearned (28) │    │    but are designed in at build time   │
 │ 17 no citations (45)      │    │                                        │
 └───────────────────────────┘    └────────────────────────────────────────┘
        design-time mistakes are the cheapest to fix and the most common
```

## The seventeen

### 1. "Vector database = RAG"
- **Why it fails:** buying the DB is one of nine stages (03); parsing,
  chunking, embedding choice, ranking, context packing, evaluation, and tenancy
  are unbought. The result is a toy pipeline with production expectations (56's
  most common origin story).
- **Symptoms:** demos work on the sample folder, corpus-wide quality is
  unusable; nobody can answer "what's our recall@10?"; a single retriever call
  is the whole "architecture".
- **How to detect:** stage inventory against 03's ten-stage table — count which
  stages have owners, metrics, and configs; missing evaluation (item 9) is the
  tell.
- **How to fix:** adopt the full pipeline (03) with the default stack: hybrid +
  rerank + metadata (13+14+12); stand up evaluation before scaling (45/46);
  wire observability (50) so the remaining gaps are measurable, not vibes.

### 2. Blind top-k
- **Why it fails:** a fixed k for all queries ignores that questions differ in
  evidence needs and corpora differ in noise; k that satisfies one slice
  starves another — and k directly prices the request (44).
- **Symptoms:** thin answers on broad questions, polluted contexts on narrow
  ones; recall@k gaps between query classes; cost surprises at p95.
- **How to detect:** recall@k curves *per query class* (45); ablate k on the
  golden set and watch which slice moves.
- **How to fix:** adaptive k by query type or retrieval-score feedback [I];
  rerank-then-cut so the cut operates on relevance, not ANN order (14);
  budget-based packing (Context-Engineering: Context-Budget) so k emerges from
  the token budget, not a constant.

### 3. Huge chunks (5k-token chunks)
- **Why it fails:** the retrieval unit becomes the size of a small document;
  one vector must summarize too many distinct ideas, so similarity scores
  flatten and every chunk half-matches everything — retrieval dilution [I];
  the RAPTOR authors built their whole method on the observation that short
  contiguous chunks miss document-level context [F: 2401.18059] — the fix is
  structure, not size.
- **Symptoms:** top-10 results all "kind of relevant"; reranker can't
  discriminate (all scores cluster); packed contexts waste tokens on paragraphs
  that never answer anything.
- **How to detect:** score-distribution histogram (50) — compressed spread is
  the signature; per-chunk token size distribution vs the ~512-token default
  (10).
- **How to fix:** structural chunking near 256–512 tokens (10); parent-child
  retrieval — retrieve small, generate with parents (18); RAPTOR-style summary
  trees when holistic document questions matter (20).

### 4. Too much overlap
- **Why it fails:** 50% overlap means half of every packed context is
  duplicated; you pay tokens for repetition, dedup fights the retriever, and
  near-duplicate chunks inflate apparent similarity (41).
- **Symptoms:** the same sentence appears 2–3 times per prompt; context-token
  spend higher than content warrants.
- **How to detect:** n-gram overlap audit between packed chunks (50); tokens
  packed vs unique-content ratio (44).
- **How to fix:** 10–15% overlap as the default (10); dedup at pack time (41);
  structural boundaries (headings, sections) instead of fixed windows with
  large strides.

### 5. No reranking
- **Why it fails:** ANN returns *similarity* order, not *relevance* order; the
  LLM receives evidence sorted by embedding closeness, with distractors
  interleaved with answers (14) — and position in the prompt changes how the
  model uses evidence [F: 2307.03172].
- **Symptoms:** answers that cite the 4th-ranked chunk when the 1st was noise;
  quality flips with paraphrase.
- **How to detect:** recall@10 vs recall@50 gap on the golden set (45); MRR
  with and without rerank (14).
- **How to fix:** cross-encoder rerank of the top-50/100, then cut to the
  budget (14); tune the rerank cutoff against the recall@k curve, not by
  convention; keep the dropped-by-rerank list logged (50).

### 6. One embedding model for every language/domain
- **Why it fails:** a single encoder is a compromise everywhere it operates
  outside its training distribution — code, legal text, non-English languages,
  and jargon each degrade (07); queries and chunks can even drift into
  different vocabularies entirely.
- **Symptoms:** one language or domain has visibly worse recall@k; zero-hit
  rate spikes for ID/code queries; cross-lingual queries return monolingual
  noise.
- **How to detect:** golden-set recall sliced by language/domain (45, 46);
  BEIR-style zero-shot checks when swapping models [F: 2112.09118 — contrastive
  dense retrievers' transfer limits motivate this caution].
- **How to fix:** language/domain-routed retrieval (07) with per-slice models
  where volume justifies; hybrid lexical backup for ID-shaped queries (13);
  re-embed and version the index on model changes — never mix vectors from two
  models in one index (07, 49).

### 7. Ignoring metadata
- **Why it fails:** no filters, no tenancy, no versioning means every hard
  requirement — access, freshness, scoping — is unsatisfiable at search time;
  the corpus becomes an undifferentiated soup (12).
- **Symptoms:** stale answers (item 11), cross-tenant fear (item 12), "can you
  restrict it to 2025 docs?" is unanswerable; citations lack locators.
- **How to detect:** fraction of chunks missing required fields (12's canon:
  doc_id, date, tenant, classification, lang); audit queries that *should* have
  been filtered but weren't.
- **How to fix:** enforce the metadata canon at ingestion (12); mandatory
  server-side tenant/ACL predicates (49, 48); version fields as first-class
  (item 11); metadata-filtered evaluation slices (45).

### 8. Sending 50 chunks to the LLM
- **Why it fails:** context pollution — the signal-to-noise ratio collapses,
  attention dilutes across near-misses, and the cost is linear in chunks:
  50 chunks ≈ $0.084/request vs ≈ $0.023 at 10 [E: constants bank; 512-token
  chunks, $3/$15 pricing] — plus ~5× the KV/prefill load [E: ~3200 MiB vs
  ~640 MiB KV at 70B-class]. Position matters too: evidence buried mid-stack
  is under-attended [F: 2307.03172].
- **Symptoms:** hallucination rate rises with k; answers blend multiple
  half-relevant chunks; per-request cost dominates the P&L (44).
- **How to detect:** context tokens packed distribution (50); tokens packed vs
  tokens *used* by the answer (citation coverage — 45); cost per resolved query.
- **How to fix:** rerank hard, pack few (14); compress/extract relevant spans
  instead of whole chunks (41); budget-based packing (Context-Engineering:
  Context-Budget); treat "raise k" as a last resort after retrieval fixes (47).

### 9. No retrieval evaluation
- **Why it fails:** only end-to-end "vibes" means retrieval bugs are invisible
  and unprioritized; the team tunes prompts while recall quietly rots (45's
  core argument, mirrored in 47's two-directional mislead).
- **Symptoms:** quality debates settled by anecdote; regressions discovered by
  users; every fix is a prompt tweak.
- **How to detect:** absence itself — no golden set, no recall@k, no per-layer
  metrics in dashboards (50).
- **How to fix:** build the golden set (46); gate deploys on recall@k/MRR
  thresholds (45); evaluate retrieval and generation separately (45); feed
  production misses back into the set (50).

### 10. Only evaluating final answers
- **Why it fails:** end-to-end scores average away the layer that failed; a
  system can score "fine" while retrieval is carried by parametric memory, or
  generation wastes an excellent retrieval (47's L2/L6 independence).
- **Symptoms:** "answer quality is 0.8" explains nothing; fixes that help one
  benchmark slice hurt another with no explanation.
- **How to detect:** can your eval attribute a failure to a layer? If not, the
  eval is end-to-end only (45).
- **How to fix:** per-layer metrics wired to the 47 taxonomy; ablation tests
  (manual chunk injection; empty-context) as standing fixtures (45).

### 11. No document versioning
- **Why it fails:** without versions, re-indexing is a coin flip — stale
  chunks answer beside fresh ones, contradictions ship as facts, and no one
  can prove what the system knew when it answered (12; audit demands it too,
  48).
- **Symptoms:** contradictory answers across days; "which version answered
  this?" is unanswerable; full re-embeds are terrifying because nothing is
  diffable.
- **How to detect:** duplicate content with different dates in the index (12);
  traces without index-version fields (50); stale-answer incident rate (47's
  staleness row).
- **How to fix:** version-stamp every chunk and index build (12); effective-dating
  and supersession logic at ingestion; reindex as a versioned, replayable
  operation (50); cache keys that include index version (42).

### 12. No ACL enforcement
- **Why it fails:** retrieval is an authorization decision — whatever reaches
  the context is readable by the model and quotable to the user; a shared
  index without engine-enforced tenant/ACL predicates leaks across tenants
  (48's central invariant; 49's whole page).
- **Symptoms:** tenant B sees tenant A's snippets; audit finds chunks without
  classification; "access control" exists only as prompt text.
- **How to detect:** negative authz tests through every entry point (48);
  unfiltered-query attempts in logs; chunks missing tenant_id/ACL fields (12).
- **How to fix:** identity resolved server-side before search; engine-layer
  mandatory predicates with fail-closed defaults (49); post-retrieval re-check
  as defense in depth; per-tenant partitioning for large/compliant tenants (49).

### 13. Using agents when simple retrieval suffices
- **Why it fails:** an agent loop multiplies LLM calls, latency, cost, and
  nondeterminism for questions a single hybrid+rerank pass answers; the loop
  also *adds* failure modes (bad plans, infinite tool loops) on top of
  retrieval's own (24's honest cost accounting; 54's cost ladder).
- **Symptoms:** p95 latency in the tens of seconds; per-query cost 5–20×
  baseline; nondeterministic answers to identical questions; agent logs show
  one retrieval followed by pointless reflection.
- **How to detect:** measure the single-pass baseline on the same traffic first
  (45); count LLM calls per query (50); the 54 test — can you name the measured
  failure that needs a loop?
- **How to fix:** default to the rung-0 stack (13+14+12); add Adaptive-RAG-style
  routing so loops are only entered for complex queries [F: 2403.14403]; cap
  iterations and budget per query (24); revisit 26 for multi-hop *without* full
  agency.

### 14. Using GraphRAG when relationships do not matter
- **Why it fails:** the graph index is built with LLM calls over the whole
  corpus — entity and relation extraction at ingestion is the most expensive
  indexing operation in this section [F: 2404.16130 motivates the build; 28
  quantifies it] — and if questions are local/factual, a vector+rerank pipeline
  matches it at a fraction of the cost.
- **Symptoms:** ingestion invoices spike; graph answers are no better than the
  old pipeline on the golden set; the graph goes stale after the first corpus
  update because nobody wants to pay to rebuild it.
- **How to detect:** question-type audit — what fraction of traffic asks
  multi-entity or global-theme questions? [F: 2404.16130 defines the class
  GraphRAG targets]; A/B graph vs hybrid on the golden set (45).
- **How to fix:** earn the graph (54's ladder): build it for entity-relation
  and global questions (28/29), skip it otherwise; if partial, build the graph
  only over the sub-corpus where those questions live [I].

### 15. Using 1M context instead of designing retrieval
- **Why it fails:** long context does not repeal attention: relevant material
  mid-context degrades [F: 2307.03172 — the position effect holds even for
  long-context models]; meanwhile every query pays prefill over the whole
  dump — the cost grows per request instead of amortizing at ingestion (44;
  39's full analysis).
- **Symptoms:** "just paste everything" pipelines; TTFT in seconds before the
  first token; answers miss facts that are verifiably in the prompt (the
  classic lost-in-the-middle complaint); cost per query dominated by input
  tokens.
- **How to detect:** input-token share of cost (44); position-of-evidence vs
  answer-correctness correlation on sampled traces (50); token spend vs
  retrieval-equivalent baseline.
- **How to fix:** retrieve for breadth, then stuff the *selected* evidence (39's
  hybrid answer); budget-based packing with best-evidence-first ordering
  [F: 2307.03172]; long context reserved for bounded, known-up-front evidence
  sets (39).

### 16. Caching stale answers
- **Why it fails:** a semantic cache keyed on query similarity — without the
  index version, embedding model, and document versions in the key — serves
  yesterday's evidence after a reindex or model swap (42's central hazard);
  staleness then hides behind the cache's latency win.
- **Symptoms:** users report answers that "used to be right"; contradiction
  between cached and fresh answers; incidents cluster right after reindexing.
- **How to detect:** cache-hit audit after every reindex (50's replay checks);
  key-composition review — if the key lacks index version (item 11), it is
  broken by construction.
- **How to fix:** composite cache keys: query embedding *and* index version
  *and* retriever/reranker params (42); invalidate on ingestion events;
  TTL-bounded semantic caches for time-sensitive corpora; traceable cache hits
  so staleness is measurable (50).

### 17. No citations
- **Why it fails:** without cited chunks there is no audit trail, no
  faithfulness check, no user trust signal — and no way to detect that the
  model answered from parametric memory instead of the evidence (45's
  faithfulness metrics need citations to attach to; 47's L6 detection collapses
  without them).
- **Symptoms:** unsupported claims ship; "where did that come from?" has no
  answer; evaluation judges refuse or guess (45).
- **How to detect:** responses without chunk-id citations in sampled traces
  (50); abstention rate — a system that never abstains is not grounded, it is
  unmonitored [I].
- **How to fix:** grounded-generation contract: answer only from context, cite
  chunk ids, abstain when unsupported (47's L6 fixes); citation success rate as
  a production metric (50); judge-scored citation support on samples (45) —
  RAGAS-style reference-free metrics assume citable evidence [F: 2309.15217].

## The meta-fix
Seventeen anti-patterns, three root habits [I]: **measure the layers**
(9, 10 → 45/47), **spend complexity only when earned** (2, 8, 13, 14, 15 →
54's ladder), and **make provenance structural** (7, 11, 12, 16, 17 → 12/48/49).
The pipeline stage that each anti-pattern corrupts is cataloged in 03; the
incident they produce is diagnosed in 47.

## Key Takeaways
1. Most RAG failures are designed in, not run into — the fix list above is
   mostly design-time work: chunking, metadata, evaluation, citations.
2. Retrieval discipline dominates: hybrid, rerank, sane chunks, adaptive k —
   items 2–6 are the cheapest quality multipliers in the whole section.
3. Provenance failures (7, 11, 12, 16, 17) are also *safety* failures — tenancy,
   staleness, and auditability share one fix: metadata as a first-class system.
4. The expensive anti-patterns (13, 14, 15) are the seductive ones — agents,
   graphs, and million-token contexts must be justified by measured failures,
   never by demo envy.
5. Evaluation absence (9, 10) is the enabling anti-pattern: without per-layer
   metrics, the other sixteen are invisible until users report them (45/47).

## Related
[47 failure modes — the incident-side view](47-rag-failure-modes.md) ·
[45 evaluation — the measurement discipline](45-rag-evaluation.md) ·
[54 which RAG — the cost ladder](54-which-rag-should-i-use.md) ·
[48 security](48-rag-security.md) · [49 multi-tenant RAG](49-multi-tenant-rag.md) ·
[42 caching](42-rag-caching.md) · `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`
