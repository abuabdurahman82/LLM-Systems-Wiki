# Query Transformation — Fixing the Query Before Retrieval

`LAST_UPDATED: 2026-08-29` · Status: core page · All pattern claims [I] unless
a paper is verified in the research bank (HyDE → 17; the rest are standard
practice).

## 30-Second Explanation
Retrieval is only as good as the query it receives — and the raw user query is
often not the best query: it contains typos, coreference ("the second one"),
underspecified scope ("the pricing"), mixed intents, and sometimes a phrasing
that has no lexical/semantic overlap with the corpus at all. **Query
transformation** is the pre-retrieval step that turns the raw query into one or
more *retrieval-optimized* queries. Each pattern below answers four questions:
what, why, when, and its failure mode.

## The pattern catalog
| Pattern | What | Why | When | Failure mode |
|---|---|---|---|---|
| **Query rewriting** | One LLM pass: "rewrite this question for a search engine" | normalize: fix typos, resolve coreference (32), drop conversational filler | always, cheap (small model) | over-rewriting: the rewriter *changes the question's meaning* — a silent drift no metric catches without golden-set canaries (45) |
| **Query expansion** | Add synonyms/related terms to the query | widen the lexical net for BM25 | lexical-heavy corpora (37) | term explosion dilutes BM25's IDF signal; expansion of rare-token queries can actively hurt |
| **Multi-query retrieval** | generate N different queries, retrieve each, merge | one phrasing rarely covers all evidence phrasings (16) | ambiguous/broad questions | cost ×N; duplicate context (41); needs a merge policy |
| **Query decomposition** | split a compound question into sub-questions, retrieve per sub-question | "A and B" as one query matches each part only weakly (predominantly single-part documents) | multi-part questions (26) | decomposition error: wrong sub-questions, or lost cross-part constraints |
| **Step-back prompting** | generate the *general* question behind the specific one ("What are the failure modes of X?" behind "why did X fail at 3am?") | the specific query may match zero docs; the general one matches the explanatory section | long-tail specific queries | the general query retrieves *too much* — the specific evidence is now in position 40, not 1 |
| **HyDE** | generate a *hypothetical answer*, embed that instead of the question | questions and answers embed in different regions; a hypothetical answer sits where the real answers are (17) | semantic gap between question phrasing and doc phrasing | the hypothetical answer can be *wrong*, and you retrieve near the wrong answer; the error is silent |
| **Keyword extraction** | extract the load-bearing terms (entities, codes, dates) | force exact-token matching for the parts that are exact (13) | ID/code-heavy queries (37) | over-extraction: treating "system" as a load-bearing keyword |
| **Entity extraction** | pull named entities, link them to known entities | entity-anchored retrieval *can be* the most precise for entity-centric queries, when linking is reliable (36/38) | entity-rich corpora (legal, medical, code) | entity-linking errors (the "Apple" problem); new entities not in the link table |
| **Intent classification** | classify: factual / procedural / comparative / unanswerable / out-of-scope | route per intent (retrieve / structured / web / refuse — 54) | multi-source systems (36) | misclassification routes to the wrong source; "unanswerable" misfires kill legitimate questions |

## Design rules [I]
1. **One transformation, one job.** Stacking rewrite + multi-query + HyDE +
   step-back on one query is not "more power", it is four chances to drift
   from the user's actual question. Start with *conversational rewrite* (coref
   + typos) only; add patterns when the golden set (46) shows a specific
   failure class they fix.
2. **Transform with a cheap model, verify on the expensive one.** The
   transformer is a pre-LLM stage: rule-based transforms add tens of ms, but a
   small-LLM rewrite call typically adds ~0.1–1 s (prefill + short decode)
   [I: the cost/latency budget rule, 44 — budget the LLM-call latency, not the
   rule latency].
3. **The transformed query is logged** (50): the trace must show raw query →
   transformed query → per-query results, or you cannot debug which
   transformation broke retrieval (47).
4. **Unanswerable is a first-class intent** [I: the standing best practice]. A
   system that must retrieve for every query will retrieve *something* and
   hallucinate over it; routing "unanswerable/out-of-scope" to a refusal is
   cheaper and more honest (54's "when NOT to retrieve").
5. **Measure per transformation** (45/46): ablation = the golden set with and
   without the transformation. A *retrieval-affecting* transformation that
   doesn't move recall@k or MRR on your set is pure cost. (Intent/refusal
   routing is scoped out: it moves *routing accuracy*, not recall@k — a perfect
   router can leave recall@k unchanged and still be essential.)

## Where query transformation sits in the pipeline
```
raw query
   ↓ conversational rewrite (32: coref + typos + scope)
   ↓ intent classification (route: retrieve / structured / refuse / web)
   ↓ [if retrieve] per-pattern transforms (multi-query 16, HyDE 17, step-back…)
   ↓ retrieval (hybrid, 13)
   ↓ rerank (14)
```
The transforms that produce *multiple* queries feed the merge (16); transforms
that produce *one* better query just replace the input. Note that query
transformation and *context* transformation (40) are different sides of the
same gap — 40 enriches the *document side* (index-time), query transformation
enriches the *query side* (query-time); both attack the semantic mismatch
between "how the question is phrased" and "how the evidence is phrased".

## Key Takeaways
1. The raw user query is usually not the best retrieval query; transformation
   is the pre-retrieval quality lever.
2. One transformation, one job — stacking is drift risk, not power.
3. Each pattern has a named failure mode (meaning drift, wrong hypothetical
   answer, decomposition loss); the golden set detects them (45/46).
4. Log raw→transformed→results; unanswerable is a first-class intent.
5. Cheapest-first ordering: conversational rewrite → intent routing → the
   expensive patterns (HyDE, multi-query) only when measured failures demand
   them.

## Related
[16 multi-query](16-multi-query-rag.md) · [17 HyDE](17-hyde.md) ·
[32 conversational](32-conversational-rag.md) · [13 hybrid](13-hybrid-rag.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · [45 evaluation](45-rag-evaluation.md)
