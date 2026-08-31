# Agentic RAG — The Loop That Decides Its Own Retrieval

`LAST_UPDATED: 2026-08-29` · Status: core page · The major page for the
agentic pattern. Loop mechanics cross-link to `../Agents/`; cost model in 44.

## 30-Second Explanation
Traditional RAG is a *fixed pipeline*: query → retrieve → answer. **Agentic
RAG** replaces the pipeline with a *loop with decision points*: the model (the
agent) decides *whether* to retrieve, *what* to retrieve, *from where*,
*evaluates* what came back, *reformulates* if it is not enough, and *verifies*
before answering. Retrieval stops being a stage and becomes a *tool the agent
chooses to use* — the same architectural move that made LLMs into agents in
general (`../Agents/Agent-Loops-and-Reasoning-Strategies.md`). The payoff:
adaptive behavior on a per-query basis (skip retrieval when unneeded, iterate
when evidence is missing). The price: every loop iteration is an LLM call —
latency, cost, and failure surface all grow with the loop.

## The loop
```
traditional:   query → retrieve → answer                       (03)

agentic:
goal
  ↓ plan (what is the question? what evidence would settle it?)
  ↓ choose retrieval source (vector / SQL / graph / web / memory / none, 36)
  ↓ search (the retrieval call, as a tool)
  ↓ inspect result (is this evidence? relevant? sufficient? trustworthy?)
  ├── insufficient → reformulate (new query / different source / new sub-question)
  │                  → search again        (the recursive loop, 27)
  └── sufficient   → reason over evidence
                    ↓ verify (per-claim support? contradictions? citations?)
                    ↓ answer (+ citations)   or  honest "insufficient evidence"
```

The four decision points, each a place where the agent *differs* from a fixed
pipeline:
1. **Whether to retrieve** — "what is 2+2" or "who are you" needs no corpus;
   retrieving there is pure cost and context pollution (54's "when NOT to
   retrieve", made per-query instead of per-system).
2. **What and where** — source routing (36/54): structured data → SQL (30);
   public/current → web (34); internal docs → vector (13); entities → graph
   (28). The fixed pipeline has one source; the agent has a portfolio.
3. **Inspect + reformulate** — the recursive step (27): the agent reads the
   evidence, names the gap, and writes the next query. This is the capability
   one-shot RAG structurally lacks.
4. **Verify** — per-claim grounding check before the answer ships (45's
   verification, made the loop's exit condition).

## The component inventory (what "agentic" actually adds)
| Component | Role | Failure mode if missing/poor |
|---|---|---|
| **Tool selection** | the retrieval calls are tools (`search(query, filters)`, `sql(query)`, `web_search(query)`, `graph_traverse(entity)`) | the agent picks the wrong tool for the data type (vector search over structured data — 30's argument, in reverse) |
| **Search planning** | decompose the goal into sub-questions, assign sources (25 when split across agents) | under-decomposition → incomplete evidence; the loop cannot recover what it never queried |
| **Reflection** | after each result: "did this answer the sub-question? what is still missing?" | no reflection → re-retrieval loops (27's failure #2) or premature stop |
| **Query iteration** | derive the next query from current evidence (27) | drift (27's failure #1): iteration compounds re-phrasing error |
| **Source validation** | trust tiers, freshness checks, contradiction surfacing (36/48) | the agent cites an untrusted/stale source with confidence |
| **Multi-hop retrieval** | chained queries across hops (26) | the chain breaks at hop 2 (evidence too narrow to query the next hop) |
| **Termination** | sufficiency + caps (27's termination bundle) | infinite loops; cost runaway; the harness must enforce step/cost budgets (`../Harness-Engineering/`) |

## Tool selection: the concrete patterns
- **Vector search tool** `search(query, filters, k)`: the 13/14 pipeline behind
  a function signature; the agent supplies the query and *filters* (the
  metadata predicates, 12 — the agent is what makes filters adaptive).
- **SQL tool** (30): the agent writes the query; the engine enforces
  read-only + scoping. The agent's skill is schema-grounding (30's
  semantic-layer argument).
- **Web search tool** (34): the highest-exposure tool — untrusted content,
  injection surface; the agent must be egress-limited and the retrieved pages
  must be quarantined as data (48).
- **Graph tool** (28): `neighbors(entity, depth)` / `path(A, B)` — the
  relational questions vector search cannot express.
- **Memory tool** (33): "what did the user tell me last time?" — retrieval
  over episodic/user memory.
The pattern [I: the harness discipline that makes this safe]: every tool has
an *explicit contract* (inputs, allowed scopes, cost class), the agent cannot
arbitrarily combine tools into code execution, and high-impact actions
(ejecting to web, writing SQL that touches PII scopes) are tiered
(`../Harness-Engineering/`, `../Safety/README.md`).

## Cost and latency (the honest accounting) [I, bank-based]
Each loop iteration ≈ one reasoning LLM pass (order of a short generation,
44) + one retrieval pass (ms) + optional rerank (0.2–1 s, 14). A 3-iteration
agentic query is ~3× the LLM calls of one-shot, ~3–6× the wall-clock, and the
*variance* is the real cost: the loop length is data-dependent, so capacity
planning needs the p95 loop length, not the mean. The 80/20 rule [I: the
standing recommendation this section keeps landing on]: **the agentic loop is
for the query classes where one-shot measurably fails** (multi-hop,
ambiguous-source, high-stakes verification) — and for everything else the
fixed hybrid+rerank pipeline (13/14) is cheaper and more predictable. An
agentic system that routes 100% of traffic through the loop is paying the
agent tax on queries that did not need it; a router that sends "simple factual
internal" queries to the fast path is the production shape (54).

## When agentic RAG is right (and when it is theater)
**Right** [I]: multi-hop questions (26); heterogeneous sources (36);
high-stakes answers where verification is worth the loop (45/51); coding
agents over large repos (38 — the agentic pattern is the *default* there);
conversational investigations (32 + the loop).
**Theater** [I]: single-corpus, single-hop, low-stakes — "we added an agent"
because the demo was impressive; the measured result is higher cost, higher
latency, and *less* deterministic behavior (the loop's non-determinism is a
reliability tax on the SLOs, `../Production-Operations/`). The test is always
the same: ablate the loop (53's experiment matrix, 45/46) — if one-shot
hybrid+rerank is within noise on your golden set, the loop is unearned.

## Connection to the agent stack
Agentic RAG is the *retrieval specialization* of the general agent loop:
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` (the loop,
reflection, termination), `../Agents/Tool-Use.md` (the tool contracts),
`../Agents/Coding-Agents.md` (the strongest production exemplar — code
retrieval as an agentic tool portfolio, 38), `../Agents/Multi-Agent-Systems.md`
(the split into specialist agents, 25), `../Harness-Engineering/Harness-Anatomy.md`
(the budgets and guardrails that keep the loop safe). And context
engineering: every retrieved result is a context-allocation decision —
`../Context-Engineering/Context-Budget.md` (60 unifies the view).

## Key Takeaways
1. Agentic RAG = a decision loop where retrieval is a tool; the four decision
   points (whether/what/inspect/verify) are where it differs from 03.
2. The component inventory is concrete: tool selection, search planning,
   reflection, query iteration, source validation, termination — each with a
   named failure mode.
3. Cost scales with loop length, which is data-dependent — plan on p95, not
   mean; the agent tax is paid on *every* query in the loop.
4. It is earned by the query classes one-shot measurably fails (26/36/45);
   ablate against hybrid+rerank or call it theater.
5. It is the retrieval specialization of the general agent stack — the
   harness, not the model, is what keeps the loop safe and budgeted.

## Related
[27 recursive](27-recursive-rag.md) · [26 multi-hop](26-multi-hop-rag.md) ·
[25 multi-agent](25-multi-agent-rag.md) · [36 federated](36-federated-rag.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · [44 economics](44-rag-economics.md) ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` · `../Agents/Tool-Use.md` ·
`../Context-Engineering/Context-Budget.md`
