# Recursive RAG — Retrieve, Reason, Retrieve Again

`LAST_UPDATED: 2026-08-29` · Status: core page · Loop mechanics [I];
paper-anchored variants cross-link to 21/22.

## 30-Second Explanation
One-shot RAG retrieves *once*: the answer must be reconstructable from one
top-k. **Recursive RAG** makes retrieval a *loop*: retrieve → reason over what
came back → the reasoning produces a *new* query (a follow-up, a gap, a
derived entity) → retrieve again → repeat until the answer is grounded. It is
the control-flow answer to the one-shot limitation: sometimes the evidence for
step 2 of the answer is only *findable* after you have read step 1's evidence.
Multi-hop RAG (26) is the canonical task class; recursive RAG is the general
loop that serves it (and more).

## The loop
```
question
   ↓
[1] retrieve(query_0)  → evidence_0
   ↓
[2] reason: is the answer grounded in evidence_0?
   ├── YES → answer (citations from evidence_0)
   └── NO:  what is missing?
         ↓
   [3] derive query_1 (the gap, re-phrased as a retrievable question)
         ↓
[4] retrieve(query_1) → evidence_1
   ↓
[5] reason over evidence_0 ∪ evidence_1  →  grounded? / new gap?
   ↓  (repeat: query_i+1 from the current gap)
[termination] → answer OR "insufficient evidence"
```

The reasoning step is the difference from "just call the retriever N times":
the *next query is derived from the current evidence*, not pre-computed.
"What else has the lead author published?" first retrieved by evidence_0
(a paper's abstract, which *names* the lead author "J. Smith (MIT)") — the
*next* query is "J. Smith MIT other publications", which no single pre-written
query would have expressed: the entity string is a retrieval handle that only
exists after reading the evidence.

## The derived-query problem (where recursive RAG lives or dies)
The loop's quality is bounded by the **gap→query translation**: from
"evidence says X, answer needs Y, Y is not in evidence", produce a query that
actually retrieves Y. Failure modes [I, each observed in practice]:
1. **Drift**: each derived query is re-phrased from the *previous* evidence,
   and small meaning shifts compound — query_3 is no longer about the original
   question (15's transformation drift, iterated). Mitigation: carry the
   original question verbatim into every loop iteration's reasoning prompt.
2. **Re-retrieval loops**: the derived query re-phrases the *same* gap →
   the same top-k → the same "not grounded" → infinite loop. Detection:
   query-similarity and evidence-overlap monitors between iterations (50);
   the loop must have a seen-query/evidence set.
3. **Query too narrow/too wide**: the derived query matches one chunk (too
   narrow) or the whole topic (too wide) — the retriever's granularity
   problem re-appears every iteration (10). Mitigation: derive *several*
   candidate queries per gap and retrieve all (a one-step multi-query, 16).
4. **Evidence that cannot be queried**: the gap is "I need the *number* in
   figure 3" — the retrieval language is text; the answer needs a structured
   read (30) or a vision read (31). The loop must be able to *switch
   retrieval type* (federated routing, 36) or it stalls.

## Termination conditions (the engineering that makes it safe)
A recursive loop needs *all* of these [I: standard loop discipline]:
1. **Max iterations** (typically 3–5): a hard cap; benchmark multi-hop sets
   are largely 2-hop by construction (HotpotQA), so 3–5 covers the long tail
   and is generous for general traffic [I: the conventional cap — tune on your
   multi-hop set, 46].
2. **Progress check**: if a *large* fraction of evidence_i (say ~80%+) is
   already present in evidence_0 ∪ … ∪ evidence_{i−1}, the loop is not
   learning → stop (the re-retrieval detector, above). The denominator is the
   prior union, not the current evidence.
3. **Groundedness check**: the reasoning step outputs *per-claim* support
   ("claim A: supported by evidence_0 chunk 2; claim B: unsupported") —
   termination is "all load-bearing claims supported", not "I feel done"
   (the 45 per-claim check, made the loop's exit condition).
4. **Cost/latency budget**: each iteration is an LLM reasoning pass +
   retrieval + rerank; the loop is *capped by the SLO*, not just by
   iterations (44: iteration i costs ~a full retrieval+reasoning round).
5. **Honest failure exit**: if the cap is hit with unsupported claims, the
   system says "evidence insufficient for: [claims]" — *not* an answer
   assembled from partial grounding (the 47 hallucinated-synthesis failure,
   prevented at the loop level).

## Recursive vs related patterns (not the same thing)
| Pattern | Loop shape | Difference |
|---|---|---|
| **One-shot RAG** (03) | retrieve once | no loop; the answer is bounded by one top-k |
| **Multi-query** (16) | N parallel retrievals, one reason pass | the queries are *independent* (no evidence informs them); no iteration |
| **Multi-hop** (26) | the *task* of needing chained evidence | recursive RAG is the *mechanism* that serves multi-hop; "multi-hop" names the problem, "recursive" names the loop |
| **IRCoT-style** | interleaved retrieval with chain-of-thought generation | retrieval happens *during* generation (each CoT step may trigger a retrieval); more tightly coupled to the generator [F: arXiv:2212.10509 verified in research bank] |
| **Agentic RAG** (24) | the agent loop *is* the loop, retrieval is one tool | recursive RAG is the retrieval-specific skeleton; agentic adds source choice, tool use, and general planning (24/25) |
| **Self-RAG / CRAG** (21/22) | learned/corrective signals *inside* one iteration | they improve *each* retrieve-reason step; recursive stacks the steps — the two compose (a Self-RAG-style gate on each iteration) [I] |

## Cost profile [I, from the 44 bank]
Each iteration ≈ (1 retrieval pass: ms-scale, 08/13) + (1 rerank: 0.2–1 s) +
(1 reasoning LLM pass: the generation-side cost, order of a short generation).
Both the retrieval-side *and* the generation-side cost scale ~linearly with
iterations (a 3-iteration loop ≈ 3 reasoning passes + 3 reranks vs one-shot's
1); the only iteration-independent term is the final answer's token count.
The break-even question is the same as agentic's: does the
multi-hop task class actually exist in your traffic (measure it, 46), because
you are paying the loop for every query in it.

## Key Takeaways
1. Recursive RAG = retrieve → reason → derive next query → retrieve; the
   derived query is informed by evidence, which one-shot and multi-query
   cannot do.
2. The loop's quality is bounded by gap→query translation; drift and
   re-retrieval are the two *loop-dynamics* failure modes (of four named).
3. Termination is a bundle: max iterations + progress check + per-claim
   groundedness + cost cap + honest "insufficient evidence" exit.
4. It is the mechanism behind multi-hop (26); agentic RAG (24) generalizes it
   with source choice and tool use.
5. Cost is ~linear in iterations on *both* sides (retrieval and generation);
   the real cost question is whether your task mix justifies the loop (44/46).

## Related
[26 multi-hop](26-multi-hop-rag.md) · [24 agentic](24-agentic-rag.md) ·
[16 multi-query](16-multi-query-rag.md) · [21 Self-RAG](21-self-rag.md) ·
[44 economics](44-rag-economics.md) · [46 golden datasets](46-rag-golden-datasets.md)
