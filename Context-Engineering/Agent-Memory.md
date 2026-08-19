# Agent Memory (short-term → long-term architectures)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Context (`Context-Budget.md`) is *working* memory — it dies when the window
compacts or the session ends. **Agent memory** is the layer that *persists*
across steps, sessions, and even tasks: what the agent learned, decided, and saw
last time. The 2023–2026 arc went from "the context window *is* the memory"
(MemGPT's paging idea) to dedicated **memory stores** (vector, key-value,
temporal knowledge graph, file-based) with retrieval-by-relevance + recency.
This page covers the architecture families and the hard question: **what to
store, when to consolidate, and how to retrieve without poisoning the context.**

## The two axes
1. **Short-term vs long-term.**
   - *Short-term* = the in-context working set (goal, plan, recent steps,
     scratchpad) — managed by `Context-Compaction.md`.
   - *Long-term* = persistent, out-of-context store; retrieved on demand.
2. **Episodic vs semantic.**
   - *Episodic* = "what happened" (trajectory facts, user interactions).
   - *Semantic* = "what is true" (preferences, facts, skills, rules).
   A production memory is usually *both*, with consolidation that distills
   episodic traces into semantic knowledge. [I: mirrors the cognitive-science
   split; HippoRAG's hippocampus/Cortex framing, arXiv:2405.14831 [F], does the
   same in retrieval-space.]

## The architecture families
| Family | Representative | Mechanism | Strength / limit |
|---|---|---|---|
| **Paged context (main memory)** | **MemGPT** (Packer et al. 2023, arXiv:2310.08560 [F]) | OS-inspired: LLM pages between in-context "main memory" and external "archive"; the model *decides* what to swap [F: abstract] | the founding idea; works when the *model* does the paging; archival memory *can* persist across sessions [F: paper] but that's a deployment choice, not forced by the architecture |
| **Vector store + recency** | Mem0 (arXiv:2504.19413 [F]), A-MEM (arXiv:2502.12110 [F]) | embed facts → vector DB; retrieve by relevance; A-MEM adds *agentic* linking/evolution of memories | cheap, flexible; retrieval quality = embedding quality; drift if never pruned |
| **Temporal knowledge graph** | **Zep / Graphiti** (arXiv:2501.13956 [F]) | facts as a *temporal* KG (edges carry valid-time); resolves contradictions over time, answers "as-of" queries | strong for evolving/contradictory facts; heavier infra | see `../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` |
| **Memory-as-retrieval (hippocampal)** | **HippoRAG** (arXiv:2405.14831 [F]), **HippoRAG 2** (arXiv:2502.14802 [F]) | a KG + a fast retrieval "hippocampal index" (Personalized PageRank over the graph) for single-step, high-recall retrieval; H2 makes it *continual* (non-parametric learning) | outperforms vanilla RAG on single-step multi-hop; graph build cost |
| **Episodic trace store** | Generative Agents (Park et al. 2023, arXiv:2304.03442 [F]); MemoryBank (arXiv:2305.10250 [F]) | an append-only *memory stream*; each memory is retrieved by a **weighted sum of recency + importance + relevance** (paper §4.2: score = αᵣ·recency + αᵢ·importance + αₗ·relevance, min-max normalized; αs=1 in the reference implementation) [F]; periodically *reflected* into higher-level insights | the retrieve-reflect-plan loop; reflection = auto-consolidation |
| **File / skill-based** | production coding agents [I] | skills/notes as *files* in the repo; the agent reads/writes its own "notes" and reusable skills | transparent, versionable, greppable; no embeddings needed; retrieval = search |

## The three sub-questions (every memory system must answer them)
### 1. What to store (the write policy)
- **Store** high-signal, reusable content: preferences, decisions + rationale,
  verified facts, reusable procedures/skills, user-specific state.
- **Don't store** raw transcripts (too big, too noisy) — store the *distilled*
  result. The write policy is the first quality gate; a memory that stores
  everything is just an expensive log. [I]
- **Provenance:** tag each memory with when/why it was recorded and its source,
  so later retrieval can weight recency/trust.

### 2. When to consolidate (the forgetting policy)
- **Reflect on a schedule** (Generative-Agents-style): periodically read the recent
  episodic traces and write higher-level insights ("the user prefers X"; "this
  API quirk keeps biting us"). This is *semantic distillation*.
- **Decay / prune:** low-importance, never-retrieved memories decay; a memory
  that's never useful should be evicted to keep retrieval precision up
  (`../KV-Cache/Eviction.md` is the serving-side analogue).
- **Resolve contradictions:** a new fact that conflicts with an old one must
  either *supersede* it (temporal KG, Zep) or be *flagged* for the model. Silent
  coexistence of `A is true` and `A is false` is a retrieval-poisoning bug.

### 3. How to retrieve (the read policy)
- **Relevance** (embedding similarity) + **recency** (recent matters more) +
  **importance** (load-bearing > trivia). Generative Agents' score [F:
  arXiv:2304.03442 §4.2] is a **weighted sum** of the three (min-max
  normalized; the paper's αs are all 1), not a product:
  `score = αᵣ·recency + αᵢ·importance + αₗ·relevance`. A product form
  (all three near-1 to rank high) is a stricter, *more fragile* variant
  [I: engineering generalization, not the paper's formula].
- **Retrieval is a context-engineering act:** what you pull *into* the window is
  governed by `Context-Budget.md` — over-retrieving bloats; under-retrieving
  forgets. The retrieval step is where memory and context meet.
- **Graph-structured retrieval** (HippoRAG, GraphRAG) beats flat vector search on
  *multi-hop* questions because it follows *edges*, not just similarity
  (`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md`).

## Poisoning & safety (the failure modes)
1. **Retrieval poisoning** — a stored fact is wrong or adversarial; it's retrieved
   and now shapes every future answer. Mitigate: provenance + a *write* verifier
   (an independent check before a fact is persisted), and *never* trust
   tool/external content as memory without sanitization (`../Safety/`).
2. **Stale-ness** — a memory that was true, now isn't (a config changed, a dep
   upgraded). Mitigate: `as-of` temporal edges (Zep) or re-validation on use.
3. **Confirmation entrenchment** — the agent retrieves its own prior conclusion
   and never revises it. Mitigate: store *evidence*, not just conclusions;
   allow the retrieval to surface contradicting traces.
4. **Privacy / leakage** — long-term memory that spans users/tasks can leak one
   context into another. Mitigate: strict scoping (per-user, per-project memory
   namespaces).

## Production shape (2026, [I])
```
 session → [working set (context)]  ← compacts each step
              │  (durable goal + constraints NEVER summarized)
              ▼
   [episodic log]  (append-only traces)
              │  periodic reflection/consolidation
              ▼
   [semantic store]  (vector + temporal-KG hybrid)
              │  retrieve (weighted sum: recency + importance + relevance)
              ▼
   back into the working set  (budget-limited)
```
The 2026 default is a **hybrid**: a vector store for flexible recall + a temporal
KG for evolving/contradictory facts + a file layer for skills/notes that the
agent can grep and edit directly. `../Harness-Engineering/` wires this into the
loop; `../Graph-Engineering/` covers the KG/graph side in depth.

## Related
`Context-Budget.md` · `Context-Compaction.md` ·
`../Graph-Engineering/Knowledge-Graphs-and-GraphRAG.md` ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` (§ context carried between steps) ·
`../Safety/README.md` (poisoning/privacy).

## Key Takeaways
Memory = persistent context with a **write policy** (store high-signal, tag
provenance), a **forgetting policy** (reflect, decay, resolve contradictions), and
a **read policy** (weighted sum of recency + importance + relevance [F: GA
2304.03442], budget-limited). The 2026
default is a hybrid vector + temporal-KG + files. And the #1 risk is *poisoning*
— a memory is only as safe as the verifier that let it in.
