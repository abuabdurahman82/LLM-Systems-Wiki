# Multi-Hop RAG — Answers That Require Chained Evidence

`LAST_UPDATED: 2026-08-29` · Status: core page · Benchmark facts [F] from the
research bank; mechanism claims [I].

## 30-Second Explanation
One-shot retrieval (03) assumes the answer to the question is recoverable
from a *single* top-k. **Multi-hop questions** do not have that property: the
answer requires Fact A from one place, Fact B from another, and the
*relationship* between them (a join, a comparison, a chain). The retrieval
must therefore *iterate*: retrieve A, derive the query for B from what A
told you, retrieve B, reason over the pair. This page defines the task class;
the loop mechanism is 27 (recursive RAG) and the agentic generalization is 24.

## The canonical example
> **Question:** "Which company's founder previously co-founded the startup
> that this framework was originally part of?"

The answer requires: (A) identify the framework's originating startup
[evidence: a doc about the framework]; (B) identify that startup's founder
[evidence: a different doc, or the web]; (C) identify the company *that*
person went on to found / co-founded *other than S* [evidence: a third
source]. No single document contains the full chain; each hop's query is only
*derivable* from the previous hop's evidence.

```
Question
  ↓ hop 1: retrieve("framework origin")          → evidence A
  ↓ reason: A names the startup "S"; the question now needs S's founder
  ↓ hop 2: retrieve("S founder")                  → evidence B
  ↓ reason: B names the person "P"; the question now needs P's company
  ↓ hop 3: retrieve("P founded")                 → evidence C (the answer company X; excludes S)
  ↓ reason over A ∪ B ∪ C                          → answer + citations (3 sources)
```

The defining property: **hop i+1's query is a function of hop i's evidence**.
Pre-computing all the queries (multi-query, 16) cannot do this — the queries
do not exist before the intermediate facts are known.

## The task class, precisely
Multi-hop questions fall into a small number of *shapes* [I: the taxonomy
that benchmark tasks use — see the verified datasets below]:
1. **Bridge** (the example above): entity in A → relation → entity in B →
   relation → answer. The chain of entities.
2. **Comparison**: "Is X newer than Y?" where X and Y are each retrieved
   separately and their attributes compared — the retrieval is two hops, the
   reasoning is the join.
3. **Aggregation**: "How many papers by authors who also work at university
   U?" — retrieve the papers, retrieve the affiliations, count. The answer is
   a *function* of the retrieved set.
4. **Cross-verification**: "Do the incident report and the postmortem agree on
   the root cause?" — two retrievals, one comparison; the *conflict* is the
   answer (36's conflict handling, made the task).
What all four share: a single pre-formed top-k cannot be *reliably targeted*
at all hops — hop i+1's query does not exist before hop i's evidence (a
single top-k can *incidentally* contain multi-hop facts, e.g. two co-mentioned
entities in one doc; that is luck, not a mechanism). The failure
signature of one-shot RAG on these questions is specific and useful: the
answer is *plausible but incomplete*, or *confidently wrong on exactly one
hop* (47's retrieval failure, multi-hop flavor).

## The benchmark evidence (verified)
The multi-hop task class has standard benchmarks [F: all confirmed in the
research bank — `C-eval-benchmarks.md`]:
- **HotpotQA** (arXiv:1809.09600, EMNLP 2018): 113K questions over Wikipedia
  requiring 2-hop reasoning (bridge + comparison types); the reference
  "fullwiki" setting is the multi-hop retrieval benchmark.
- **MuSiQue** (arXiv:2108.00573, TACL 2022): 2–4-hop questions; the key
  finding [F: as verified]: many existing multi-hop systems score well
  *only because they can brute-force over all Wikipedia paragraphs* — the
  paper introduced a *no-brute-force* split, showing substantial drops when
  the system must actually retrieve the hops. The methodological lesson:
  multi-hop evals must forbid full-corpus access or they measure "can read
  Wikipedia", not "can retrieve hops".
- **2WikiMultihopQA** (COLING 2020, arXiv:2011.01060): multi-hop QA combining Wikipedia and
  Wikidata, with weakly-supervised construction.
- **MS MARCO / Natural Questions / BEIR** (the single-hop families, same bank):
  the control set — systems should *not* regress on single-hop when they add
  multi-hop capability.
The evaluation consequence [I: the methodological point these benchmarks
force]: measure multi-hop *and* single-hop, with a retrieval-budget that
mimics production (top-k per hop, not full-corpus), or the numbers are not
transferable.

## Mechanism: what serves multi-hop well
1. **Recursive RAG (27)**: the generic loop — retrieve, reason, derive,
   retrieve; the termination bundle (27) is the safety.
2. **Agentic RAG (24)**: the same loop with source choice (the hops may live
   in different sources — hop 1 in the internal corpus, hop 2 on the web,
   36) and per-claim verification.
3. **IRCoT-style interleaving** [F: arXiv:2212.10509 — verified in the
   research bank]: retrieval interleaved with chain-of-thought *generation*
   — the CoT step names the gap, the retrieval fills it; tighter coupling
   than the explicit loop.
4. **Graph/KG traversal (28/29)**: when the hops are *known relationships* in
   a built graph, traversal replaces retrieval-hops — the chain is a graph
   walk, not a search loop [I: the regime where graph RAG has its cleanest
   multi-hop win].
5. **Multi-agent (25)**: when the hops are heterogeneous sources, one agent
   per source with a coordinator.

The shared requirement across all five: **the intermediate facts must survive
between hops** (the running context carries hop i's evidence into hop i+1's
query-derivation) — dropping intermediate evidence is the multi-hop version of
context truncation (47).

## Failure modes specific to the multi-hop case
1. **Hop-2 query drift**: the hop-1 evidence is paraphrased into the hop-2
   query and the meaning shifts (27's failure #1, iterated) — the hop-2
   retrieval is for the *wrong* entity. Mitigation: carry hop-1's exact
   evidence (entity strings, not summaries) into the hop-2 derivation.
2. **Entity ambiguity at the join**: hop 1 yields "J. Smith (MIT)"; the
   corpus has three J. Smiths — the hop-2 query resolves to the wrong one and
   the whole chain is confidently wrong (15's entity-extraction failure,
   made load-bearing). Mitigation: entity disambiguation before the hop
   (entity linking, 15/38).
3. **Evidence not retrievable at hop 2**: the needed fact is in a table
   (31) or a structured system (30) that the text retrieval cannot reach —
   the loop must switch retrieval type (36) or it stalls (27's failure #4).
4. **Premature join**: the system reasons over hops 1–2 before hop 3's
   evidence — the answer reflects a partial chain. Mitigation: the
   per-claim grounding check (27's termination) must mark *which* claims are
   hop-incomplete.
5. **Cost blowup**: each hop is a full retrieval+reasoning round; a 4-hop
   question at high QPS is the 44 cost problem in its purest form — multi-hop
   traffic needs its own cost class (44, 54's cost-ladder argument).

## Key Takeaways
1. Multi-hop = the answer needs chained facts whose *queries are only
   derivable from intermediate evidence*; one pre-formed top-k cannot be
   reliably targeted at all hops.
2. The task shapes: bridge, comparison, aggregation, cross-verification —
   they share one signature under one-shot RAG (plausible-but-incomplete, or
   confidently wrong on exactly one hop), and the page's per-shape failures
   are join-level (failure modes below).
3. The benchmarks are real and methodologically strict (MuSiQue's
   no-brute-force split): measure under a production retrieval budget, and on
   single-hop controls (MS MARCO / NQ / BEIR — 46).
4. Mechanisms: recursive loop (27), agentic (24), IRCoT-style interleaving,
   graph traversal (28), multi-agent (25) — chosen by source heterogeneity.
5. Multi-hop failures are join failures: entity ambiguity, hop drift,
   unretrievable hops, premature joins — each has a named mitigation.

## Related
[27 recursive (the loop)](27-recursive-rag.md) · [24 agentic](24-agentic-rag.md) ·
[28 graph RAG (the graph-walk regime)](28-graph-rag.md) ·
[25 multi-agent](25-multi-agent-rag.md) · [46 golden datasets](46-rag-golden-datasets.md) ·
[47 failure taxonomy](47-rag-failure-modes.md)
