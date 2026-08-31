# The Big Picture — RAG 1.0, RAG 2.0, and RAG + Agents

`LAST_UPDATED: 2026-08-29` · Status: core page · Section-concluding synthesis; era
boundaries are editorial framing [I]; the pattern claims are defended page-by-page
elsewhere in this section.

## 30-Second Explanation
RAG has passed through three eras: **RAG 1.0** (2020–2023) made retrieval-augmented
generation *exist*; **RAG 2.0** (2023–2025) made it a *system* — routing, hybrid
retrieval, reranking, evaluation, security, economics; **RAG + Agents** (2025–)
makes retrieval *a decision* the model makes under a policy. Each era absorbed the
previous one as a component; none replaced it. The through-line is a single
principle, and it is worth stating before the history:

> **RAG is not a vector database feature. It is an information retrieval +
> context engineering system.**

## Era 1 — RAG 1.0 (2020–2023): "stuff and hope"

```
Query ──► Vector Search ──► Top-K ──► LLM ──► Answer
              (one retriever, flat chunks, score order, no verification)
```

- A single dense retriever over flat chunks; the question string is embedded as-is.
- Top-k chunks are concatenated into the prompt in score order — selection and
  packing are accidents of k (03).
- "Stuff and hope": correctness depends entirely on whether the right chunk
  happened to rank high [I].
- Successes were real but brittle: it worked on clean corpora and failed loudly on
  identifiers, multi-part questions, and enterprise structure (06; 47).

## Era 2 — RAG 2.0 (2023–2025): the system era

```
Query ──► Query Understanding ──► Routing ──► Multi-source Retrieval
      ──► Hybrid Search ──► Reranking ──► Context Selection ──► Reasoning
      ──► Validation ──► Citations
                                        (evaluation ↺ feedback ↺ reindexing)
```

- The pipeline grew *stages*: query transformation (15), routing across sources
  (36), hybrid lexical+dense retrieval (13), cross-encoder reranking (14),
  deliberate context selection and packing (41).
- Metadata became first-class — freshness, tenancy, ACLs — because enterprise
  retrieval is "the right chunk *for this user*" (12; 49).
- The discipline became measurable: two-layer evaluation (45), failure taxonomies
  (47), per-request economics where every packed chunk is prefill cost — the
  10→50 chunk jump is ~5× input cost, ≈ $0.023 → ≈ $0.084 per request [E]
  (44; 43), and security moved to retrieval time (48).
- This is the era this section mostly documents: a *system*, engineered and
  audited, not a demo (51).

## Era 3 — RAG + Agents (2025–): retrieval as a decision

```
Goal ──► Plan ──► Retrieve ──► Evaluate ──► Reformulate ──► Retrieve Again
     ──► Reason ──► Verify ──► Answer
              (the agent decides when, where, and whether to retrieve)
```

- Retrieval becomes a tool in the agent's hands: it plans, queries, reads results,
  and decides to search again — or to stop (24; 60).
- The loop adds judgment stages the fixed pipeline lacked: evaluate retrieved
  evidence, reformulate failed queries, verify before answering (21; 22; 23;
  ../Agents/Agent-Loops-and-Reasoning-Strategies.md).
- The price is real: more steps, more tokens, harder determinism and evaluation —
  agency must be earned by measured failure of the static pipeline, exactly like
  graphs [I] (54; 57-P15).
- The orchestrator view (60) is the era's architecture: one context budget shared
  by RAG, memory, and tools.

## What changed between eras

Same goal — grounded answers — but the locus of intelligence moved [I]:

| Dimension | RAG 1.0 | RAG 2.0 | RAG + Agents |
|---|---|---|---|
| Who decides what to retrieve | the developer, at design time | the router, per query | the agent, per step |
| Retrieval passes | one | one, but staged (hybrid + rerank) | as many as the loop justifies |
| Context packing | concatenation | selection + ordering under budget | orchestrator over RAG+memory+tools (60) |
| Failure handling | none (silently wrong) | validation + evaluation loops | evaluate/reformulate/verify in-loop |
| Unit of engineering | the model call | the pipeline | the policy |
| Cost driver | generation tokens | packed-context prefill (44) | retrieval decisions × steps (43) |

The pattern across rows: each era pushes a decision that was once hard-coded
closer to runtime, and each push makes evaluation and budgeting harder, not
easier — which is why the invariants below matter more, not less, in the agentic
era [I].

## What survives every era (the invariants)

The stacks above will be rebuilt again; these six will not change [I]:

1. **Evidence must be discrete and addressable** — citation, deletion, and audit
   require retrievable units, not baked-in knowledge (01).
2. **Retrieval quality caps generation quality** — no prompt recovers evidence the
   retriever never surfaced (57-P1).
3. **Evaluate both layers separately** — retrieval and generation fail
   independently, and only separate metrics tell you which to fix (45).
4. **Context is a budget** — which chunks, in what order, at what token cost is an
   engineering decision with a price tag (41; 44;
   ../Context-Engineering/Context-Budget.md).
5. **Security is pre-generation** — authorization happens as retrieval-time
   filters; evidence that should not exist in the prompt must never reach it
   (48; 49).
6. **Complexity must be earned** — every stage (rerank, graph, agent) exists
   because a measured failure justified it (54; 56).

Era 3 does not retire these — it *implements* them: an agentic retrieve→evaluate
loop is principle 1, 3, and 6 running dynamically instead of at design time.

## Reading the eras against this section

Every page in this section documents one layer of one of these eras:

- **Era 1 baseline** — 03-basic-rag-pipeline.md (the pipeline everyone starts with
  and outgrows), 07-embedding-engineering.md, 08-vector-search.md.
- **Era 2 machinery** — 15-query-transformation.md, 13-hybrid-rag.md,
  14-reranking.md, 41-context-compression.md, 12-metadata-engineering.md on the
  pipeline; 45/46/47 on evaluation; 44/43 on economics; 48/49 on security;
  51-production-rag-reference-architecture.md ties the era into one blueprint.
- **Era 3 machinery** — 21-self-rag.md, 22-corrective-rag.md, 23-adaptive-rag.md
  (retrieval judgment), 24-agentic-rag.md and 25-multi-agent-rag.md (retrieval as
  a tool), 60-rag-agent-context-unified-view.md (the orchestrator), 59 for the
  questions era 3 has not answered yet.

If you arrived here first, the fastest path backward is 57 (the principles) →
03 (the baseline) → whichever era your problem actually lives in (54 helps decide).

## Where the frontier is open

The era-3 stack rests on unsolved questions: when should the agent retrieve at
all, how should it weigh contradictory sources, when should it refuse for lack of
evidence? Those are catalogued with their state of knowledge in
59-open-rag-research-questions.md — the honest companion to this page. For
adjacent sections of the wiki: the context-engineering side of the unified view
lives in ../Context-Engineering/Context-Budget.md and
../Context-Engineering/Agent-Memory.md, the agent side in ../Agents/Tool-Use.md
and ../Agents/Multi-Agent-Systems.md, the serving side in
../Inference/The-Life-of-a-Token.md, and the graph side in
../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md.

## Key Takeaways
1. RAG 1.0 proved the pattern; RAG 2.0 made it a measurable system; RAG + Agents makes retrieval a runtime decision.
2. Each era absorbed the previous one — agents still run retrieval, reranking, and packing; they did not replace them.
3. The single principle: RAG is an information retrieval + context engineering system, not a vector database feature.
4. Six invariants survive all eras: addressable evidence, retrieval-capped quality, two-layer evaluation, context budgets, pre-generation security, earned complexity.
5. The honest next chapter is 59's open questions, tested on 46's golden sets and 53's experiment matrix.

## Related
- The 80/20 that drives all three eras: 57-rag-80-20.md
- Era 2 in depth: 13-hybrid-rag.md · 14-reranking.md · 44-rag-economics.md · 45-rag-evaluation.md · 48-rag-security.md · 51-production-rag-reference-architecture.md
- Era 3 in depth: 24-agentic-rag.md · 60-rag-agent-context-unified-view.md · ../Agents/Tool-Use.md
- The frontier: 59-open-rag-research-questions.md · 53-rag-labs.md · 46-rag-golden-datasets.md
- Cross-sections: ../Context-Engineering/Context-Budget.md · ../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md · ../Evaluation-Engineering/RAG-Evaluation.md · ../Learning-Path/80-20-LLM-Guide.md
