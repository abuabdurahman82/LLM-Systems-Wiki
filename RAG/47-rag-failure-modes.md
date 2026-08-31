# RAG Failure Modes — A Six-Layer Taxonomy

`LAST_UPDATED: 2026-08-29` · Status: core page · Diagnosis-reasoning page; the
taxonomy is an engineering synthesis [I]; paper-grounded behavior claims (retrieval
relevance dependence [F: 2401.15884], lost-in-the-middle [F: 2307.03172],
Self-RAG self-reflection [F: 2310.11511]) verified against fetched abstracts
2026-08-29. Metrics per layer live in 45; this page tells you which layer to blame.

## 30-Second Explanation
A RAG system does not fail; **a layer of it fails**. Six layers sit between the
user's question and the answer — query, retrieval, ranking, context, reasoning,
generation — and each has its own symptoms, its own detection signal, and its own
fix. The single most expensive mistake in RAG operations is treating a
generation-layer symptom (wrong answer) with a retrieval-layer fix (add chunks,
add k), because each layer can fail *independently*: a perfect retriever can
feed a truncated context, and a perfect context can be mis-synthesized. Diagnose
top-down, fix where the evidence says the break is.

## The six layers

```
L1 QUERY ──► L2 RETRIEVAL ──► L3 RANKING ──► L4 CONTEXT ──► L5 REASONING ──► L6 GENERATION
 (asked       (found the       (ordered the   (packed the    (read the          (wrote the
  well?)       right stuff?)     right stuff?)  right stuff?)  evidence well?)    answer well?)
```

Each layer inherits the previous layer's output, so a failure at L2 makes every
downstream layer look bad. The corollary: **always localize before fixing.** The
detection column below is the localization procedure.

### L1 — Query failure
**Definition:** the request the retriever sees does not represent the user's
information need — the question is underspecified, contains jargon or IDs the
retriever cannot match, carries coreference from a chat history, or was
malformed by an upstream rewrite. The pipeline then faithfully answers the
wrong question.

- **Symptoms:** users reformulate and resubmit ("let me ask that differently");
  answers are topically adjacent but miss the point; multi-turn threads drift
  after the second turn; queries with product codes or error strings return
  nothing relevant.
- **Detect [I]:** high rewrite/disambiguation rate; query-clarification rate in
  product analytics; run the golden set (46) with rewrites ablated on/off;
  lexical (BM25) zero-hit rate on ID-shaped queries.
- **Root causes:** coreference and ambiguity in multi-turn input; vocabulary
  mismatch between user language and corpus language; missing domain/ID
  normalization; over-aggressive automatic rewrites that change the intent.
- **Fixes:** query transformation and expansion (15); multi-query variants (16)
  to cover interpretations; conversational query rewriting with history (32);
  log raw vs rewritten queries side-by-side so regressions in the rewriter are
  visible; ask-a-clarifying-question fallback below a confidence gate [I].

### L2 — Retrieval failure
**Definition:** evidence that exists in the index was not returned in the
candidate set — the classic "the answer was in the corpus and the system still
got it wrong" case. This is the layer where the generator is helpless: no
prompting trick recovers a chunk that was never fetched.

- **Symptoms:** answers cite nothing or cite the wrong document; user reports
  "this info is on our wiki, why can't it find it"; zero (or near-zero)
  retrieval scores; the same question succeeds when paraphrased by hand.
- **Detect [E-style procedure, thresholds I]:** recall@k and hit rate@k on the
  golden set (45, 46) — the headline number; index hit rate (queries whose top
  scores fall under a usable-evidence floor) from production logs (50); the
  ablation is decisive: insert the known-good chunk manually and regenerate —
  if the answer improves, the miss was L2, not L6.
- **Root causes:** ingestion gap — the document never made it into the index
  (parse failure, connector error, ACL dropped it silently); wrong or stale
  embedding model vs the query encoder (07); chunking destroyed the semantic
  unit (10); dense-only retrieval misses exact tokens — IDs, error codes (13);
  ACL/filter applied incorrectly so a visible doc is unsearchable (12, 49).
- **Fixes:** hybrid retrieval — BM25 + dense fused (13) — the single highest-
  value upgrade for keyword-shaped misses; fix the ingestion pipeline with
  dead-letter monitoring (11); re-chunk along document structure (10); expand k
  upstream of the reranker to buy candidate headroom (14); per-language or
  per-domain embedding routing (07); version-stamp the index so you can prove
  whether the doc was present at query time (12).

### L3 — Ranking failure
**Definition:** the right evidence was retrieved but buried — it is in the
candidate pool at rank 40, and the top-k cut or the ordering kept it out of the
context or positioned it where the model under-attends. Retrieval "worked";
the cut lost it.

- **Symptoms:** answers degrade in a way that flips when the same evidence is
  pasted manually; recall@50 is healthy while recall@10 is poor; users complain
  the answer "had the wrong emphasis" or blended the wrong section.
- **Detect [I]:** the recall@k curve (recall@10 vs @50 vs @100) — a large gap
  means ranking is leaving quality on the table; MRR / NDCG@k on graded golden
  sets (45); rerank-ablation: run with and without the reranker and diff the
  dropped-chunk list against expected evidence.
- **Root causes:** ANN order is a similarity order, not a relevance order (08,
  14); k cut too tight for the corpus's noise level; reranker threshold set so
  the correct chunk scores under the cut; lost-in-the-middle — evidence present
  in the context but positioned where attention underweights it [F: 2307.03172].
- **Fixes:** cross-encoder reranking before the cut (14); tune k and the rerank
  cutoff against the recall@k curve rather than by convention; prompt ordering —
  best evidence first and last (Context-Engineering: lost-in-the-middle page);
  parent-child retrieval so the cut operates on precise chunks while generation
  sees their parents (18).

### L4 — Context failure
**Definition:** the evidence reached the context assembly step and was mangled
there — truncated mid-document, deduplicated away, packed over budget, drowned
by near-duplicates, or ordered so the model under-attends. The retriever and
reranker did their job; the packer did not.

- **Symptoms:** answers stop mid-reasoning or reference "the document" without
  specifics; citations point at chunk boundaries that cut the sentence in half;
  token-usage dashboards show context packing at the model's limit; duplicated
  near-identical chunks dominate the prompt.
- **Detect [I]:** log context tokens packed per request (50) and alert on
  saturation; prompt-hash diffing on repeated queries; retrieval-side metrics
  will look *good* here (recall@k fine, rerank fine) — which is exactly the
  signature: healthy upstream, broken downstream.
- **Root causes:** fixed max-token truncation that drops the tail of evidence;
  no dedup before packing (near-duplicates inflate k); no per-chunk budgeting
  or compression (41); chunks ordered naively (relevance order ignored) so
  key evidence lands mid-context [F: 2307.03172]; template drift pushes the
  question after a huge evidence block.
- **Fixes:** explicit context budgeting (Context-Engineering: Context-Budget)
  with evidence-first packing order; context compression / extraction of the
  relevant spans (41); dedup by min-hash or embedding similarity pre-pack;
  parent-child expansion (18) so small chunks retrieve and larger, coherent
  parents get packed; lost-in-the-middle-aware ordering [F: 2307.03172].

### L5 — Reasoning failure
**Definition:** the context is complete and well-packed, but the model fails to
use it — it cannot connect evidence across chunks, integrates a distractor,
misses the contradiction between two sources, or reasons over only part of the
evidence for a multi-hop question. This is a capability/decomposition problem,
not a data problem.

- **Symptoms:** answers that are *almost* right — correct pieces, wrong
  synthesis; multi-part questions answered from a single chunk; the model
  repeats one source and ignores another; contradictory sources reconciled by
  picking the more confident-sounding one.
- **Detect [I]:** multi-hop benchmark subsets (HotpotQA, MuSiQue — 46) scored
  separately from single-hop; faithfulness/answer-relevance metrics from RAGAS
  [F: 2309.15217] on fixed inputs; contradiction-injection tests in the golden
  set (46); A/B the same prompt with evidence reordered — instability across
  orders is an L5 signature.
- **Root causes:** question needs evidence composition the model won't do in
  one pass; distractor chunks that semantically neighbor the answer [F:
  2005.11401 shows retrieval noise directly conditions answer quality];
  contradictory sources with no recency/authority signal in metadata (12);
  model under-capacity for the reasoning depth required.
- **Fixes:** multi-hop retrieval with intermediate query generation (26);
  Self-RAG-style self-reflection tokens that critique evidence support before
  answering [F: 2310.11511]; metadata-driven recency/authority ordering so
  conflicts resolve by policy (12); Adaptive-RAG routing — route hard questions
  to a decomposition pipeline [F: 2403.14403]; IRCoT-style interleaving of
  retrieval and reasoning steps for chain questions (26).

### L6 — Generation failure
**Definition:** the context contains the correct evidence, well-ranked and
well-packed, and the model still produces an answer unfaithful to it —
hallucinated synthesis, unsupported claims, refusal, or style/verbosity
failures. Everything upstream is exonerated by definition.

- **Symptoms:** confident claims with no basis in the provided chunks; citation
  markers that point at documents not actually used; the correct answer appears
  verbatim in the context while the response states something else.
- **Detect [I]:** faithfulness/groundedness metrics (RAGAS [F: 2309.15217],
  judge-based — 45); citation success rate — does each cited chunk actually
  support its claim (50); the decisive ablation: empty or evidence-free prompt —
  if the "answer" persists, it came from parametric memory, not the context.
- **Root causes:** no grounded-answer instruction or citation format in the
  prompt; context so polluted that signal drowns (see L4's cost of noise);
  prompt-injected instructions inside retrieved documents hijacking the answer
  (48); sampling temperature too high for factual tasks; answer-laundering of
  model priors over conflicting evidence.
- **Fixes:** grounded-generation prompt contract: answer only from context,
  cite chunk ids, abstain when unsupported [I]; citations as a first-class
  output (45, 50) so faithfulness is checkable; lower temperature + stricter
  system prompts for factual paths; CRAG-style retrieval evaluation triggering
  corrective actions before generation [F: 2401.15884]; document-scanning at
  ingestion for injection payloads (48).

## Incident-to-layer map
The table the on-call engineer starts from. Every incident in the wild maps to
one (or two) layers; the root cause column names the usual culprit.

| Incident (what was observed) | Layer | Usual root cause | First diagnostic move |
|---|---|---|---|
| Relevant document not indexed | **L2 Retrieval** | ingestion (11): parse/connector/ACL silent drop | search the index directly for the doc; check ingestion dead-letter queue |
| Retriever missed evidence (doc in index, not returned) | **L2 Retrieval** | embedding mismatch / chunking / dense-only miss | manual chunk injection ablation; check hybrid coverage (13) |
| Reranker removed correct chunk | **L3 Ranking** | rerank threshold too strict; cross-encoder miscalibrated on domain text | diff dropped-by-rerank list vs expected evidence (45) |
| Context truncation | **L4 Context** | fixed token budget drops tail evidence | log context tokens packed + which chunks dropped (50) |
| Contradictory documents in context | **L4/L5** | no recency/authority metadata (12); multi-source corpora | contradiction-injection tests; check metadata ordering policy |
| Stale information (answer reflects old doc version) | **L2 Retrieval / ingestion** | no versioning; old chunks still indexed (12) | version-stamp query: was the old chunk in top-k at query time? |
| Hallucinated synthesis over correct context | **L6 Generation** | no grounded-answer contract; context pollution; injection (48) | empty-context ablation; faithfulness metric on fixed inputs (45) |

Read the last column as the escalation script: each diagnostic either exonerates
the layer above or convicts the layer itself, and you walk the chain once, not
in a loop.

## Where to look — the six-layer map

```
 L1 QUERY            L2 RETRIEVAL           L3 RANKING            L4 CONTEXT
 ask the right       find the evidence      order the evidence    pack the evidence
 ┌────────────┐  q   ┌──────────────┐  ids  ┌──────────────┐ text  ┌──────────────┐
 │ rewrite,   │────►│ hybrid BM25+ │─────► │ cross-encoder│─────► │ budget, dedup│
 │ history,   │     │ dense, ANN   │       │ rerank, cut  │       │ order, pack  │
 │ intent     │     │ + filters    │       │              │       │              │
 └────────────┘     └──────────────┘       └──────────────┘       └──────────────┘
  look at:            look at:               look at:               look at:
  rewrite logs,       recall@k, hit rate,    recall@k curve,        tokens packed,
  zero-hit lex        score dist, index      MRR/NDCG, dropped-     dedup count,
  queries (15,50)     version (45,50)        by-rerank (14,45)      drop list (41,50)
     │                    │                      │                      │
     ▼                    ▼                      ▼                      ▼
 ┌─────────────────────────┐  ┌───────────────────────────┐  ┌──────────────────┐
 │ L5 REASONING            │  │ L6 GENERATION             │  │ CROSS-LAYER      │
 │ compose the evidence    │► │ write the faithful answer │  │ one incident can │
 │ ┌─────────────────────┐ │  │ ┌───────────────────────┐ │  │ implicate two    │
 │ │ decomposition,      │ │  │ │ grounded contract,    │ │  │ layers (L4/L5    │
 │ │ multi-hop, reflect  │ │  │ │ citations, abstain    │ │  │ contradictions,  │
 │ └─────────────────────┘ │  │ └───────────────────────┘ │  │ L2/ingestion     │
 │  look at: multi-hop     │  │  look at: faithfulness,   │  │ staleness) —     │
 │  splits, contradiction  │  │  citation success, empty- │  │ always localize  │
 │  tests (26,46)          │  │  context ablation (45,50) │  │ before fixing    │
 └─────────────────────────┘  └───────────────────────────┘  └──────────────────┘
```

## Operating rule: localize, then fix, then re-measure
1. **Classify** the incident with the table above — one layer, or a named pair.
2. **Convict with an ablation** (manual chunk injection, empty-context, rerank
   drop-diff) — never from the symptom alone, because L2 symptoms and L6
   symptoms are identical to the user: "wrong answer".
3. **Fix at the layer**, pull the corresponding page, and change *one* thing.
4. **Re-measure on the golden set (46) before and after** — a fix that improves
   the incident class while degrading recall elsewhere is a regression.
5. **Feed the incident into the golden set** — every L2 miss and every L6
   hallucination becomes a labeled case so the same failure cannot silently
   return (46, 50).

The taxonomy also explains why "just add more chunks" is an anti-pattern (56):
it is a blanket L4 change deployed against an unlocalized failure — it sometimes
masks an L2 miss at 5x the token cost (44) while making L5's job harder [I].

## Key Takeaways
1. Six layers — query, retrieval, ranking, context, reasoning, generation —
   each with its own metrics, signatures, and fixes; diagnose by layer, not by
   symptom.
2. Retrieval misses (L2) are unrecoverable downstream; generation failures (L6)
   are invisible to retrieval metrics — evaluate both separately (45).
3. The incident table is the on-call entry point: symptom → layer → usual root
   cause → first diagnostic move.
4. Ablations convict layers where dashboards cannot: manual chunk injection,
   empty-context, rerank drop-diff.
5. Complexity is earned per layer: fix the failing layer with the targeted page
   (13, 14, 41, 26, prompt contract) — never blanket k increases (56).

## Related
[45 evaluation — metrics per layer](45-rag-evaluation.md) ·
[56 anti-patterns — fixes that look right but aren't](56-rag-antipatterns.md) ·
[46 golden datasets](46-rag-golden-datasets.md) · [50 observability](50-rag-observability.md) ·
`../Evaluation-Engineering/RAG-Evaluation.md` · `../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md`
