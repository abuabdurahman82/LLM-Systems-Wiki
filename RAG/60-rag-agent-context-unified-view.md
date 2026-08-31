# RAG, Agents, Memory, and Context Engineering — One Unified View

`LAST_UPDATED: 2026-08-29` · Status: core page · Synthesis page connecting the RAG,
Context-Engineering, and Agents sections; role definitions and failure modes are
engineering framing [I], grounded in the referenced pages.

## 30-Second Explanation
An agent that answers well is running one operation four times over: *select the
right information and put it in the window*. RAG selects it from external
knowledge, memory selects it from history, tools select it from live systems, and
context engineering decides what actually fits, in what order, at what budget. The
same orchestrator logic — select, rank, pack, budget — applies to all three
sources, which is why this wiki treats RAG, memory, and tool use as one discipline
seen from three sides. The failure modes start when the roles blur.

## The architecture

```
                         AGENT
                           |
                 Context Orchestrator
                           |
          +----------------+----------------+
          v                v                v
         RAG             Memory            Tools
          |                |                |
    Knowledge Base     Past State       APIs/Web
          +----------------+----------------+
                           v
                          LLM
```

One orchestrator, three feeders, one consumer. The orchestrator's job is not to
answer — it is to assemble the best possible window under a token budget, then let
the LLM reason over it.

## The four roles, crisply

| Role | Retrieves | Nature of the content | Canonical failure if misused |
|---|---|---|---|
| **RAG** | EXTERNAL knowledge | corpus-backed, versioned, shareable, citable (01) | treating a retrieved doc as current truth when the index is stale |
| **Memory** | HISTORICAL agent/user state | episodic (what happened), semantic (what was learned), user (who they are) | treating user-asserted memory as verified fact |
| **Tools** | LIVE systems or actions | point-in-time reads of DBs, APIs, web; writes with side effects | treating tool output as corpus knowledge |
| **Context engineering** | — (it is the packing discipline) | decides what reaches the model, in what order, at what budget | unbounded context growth; cost and attention dilution |

**RAG** grounds the model in a *corpus*: an artifact you own, can version, can
re-index, and can share across users and agents. Its evidence is addressable — a
citation can point at it, and a deletion can remove it (01).

**Memory** grounds the model in *history*. Episodic memory recalls past
interactions ("last week you said the rollout failed"), semantic memory holds
distilled conclusions, user memory holds stable preferences. None of it is
corpus knowledge: it is asserted or observed, not verified
(33; ../Context-Engineering/Agent-Memory.md; 32).

**Tools** ground the model in *the present*. A database query, an API call, a web
fetch returns the state of the world *right now* — something no index snapshot can
promise (34; 35). Tools also act: writes, sends, deployments are state changes,
which is why they carry authorization duties retrieval does not
(../Agents/Tool-Use.md).

**Context engineering** is the discipline governing all three: budget (how many
tokens each source gets), ordering (instruction → evidence → question; most
relevant placement), and compression (dropping, summarizing, restructuring under
pressure). See ../Context-Engineering/Context-Budget.md and
../Context-Engineering/Context-Compaction.md.

## Why one orchestrator logic covers all three sources

Every feeder is subject to the same four operations [I]:

```
SELECT   which candidates from this source are relevant to the current turn?
RANK     which of those earn scarce window space (freshness, authority, score)?
PACK     in what order and form do they enter the prompt (citations, formats)?
BUDGET   how many tokens does this source get this turn — and who loses them?
```

A RAG retriever does select→rank (13, 14); so does a memory manager deciding which
past episodes matter, and so does a tool router deciding which API to call (24).
The budget line is shared and finite: memory tokens compete with evidence tokens
compete with tool output, every turn. That competition is exactly the context
budget problem, and treating the three sources as one budgeted pool — instead of
three independently stuffed lists — is the core insight of this page [I]
(41; ../Context-Engineering/Context-Budget.md).

## One turn through the orchestrator [I]

A user asks the agent: *"Why did the EU rollout slow down last week — and what
did we decide about it in March?"* One turn, all three feeders:

```
turn budget: 6,000 tokens of context for the answering LLM
 |
 +-- TOOLS   (live): query incidents DB for EU deploys, last 7 days
 |             -> select: 2 incident rows   rank: newest first
 +-- RAG     (corpus): retrieve rollout runbook + March decision memo
 |             -> select: 4 chunks         rank: rerank, dedupe
 +-- MEMORY  (history): recall this user's March thread on the rollout
 |             -> select: 1 episodic summary  confidence: user-asserted
 |
 +-- PACK: system prompt (fixed) -> tool table -> corpus evidence (cited)
 |         -> memory lane (labeled "recalled, not verified") -> question
 +-- BUDGET: 6,000 tokens split ~15% tools / 45% evidence / 15% memory
             / rest for instructions and headroom; compress or drop by rank
```

Note what the orchestrator did *not* do: it did not pour each source's full output
into the window, and it did not let the March memory pose as the March memo — the
memo (corpus, citable) and the thread (memory, asserted) both appear, labeled.

## Failure modes when the roles blur

**Memory treated as fact.** User-asserted memory ("we use Postgres everywhere")
is a claim from a conversation, not a verified corpus statement. An agent that
answers from memory with corpus confidence produces confident errors with no
citation — and nobody can audit which sentence came from where [I]. Rule: memory
needs a confidence lane and, where stakes are high, corpus verification (33; 45).

**Tool output treated as corpus knowledge.** A tool result is a *point-in-time
reading* of a live system, valid until the next transaction. Persisting it into
the index without versioning turns a snapshot into false provenance: citations
point at "the document" but the live source has moved (35; 30). Rule: tool reads
are ephemeral evidence with a timestamp; only curated, versioned material belongs
in the knowledge base.

**Unbounded context growth.** The easiest way to "improve" an agent is to stuff
more in — more retrieved chunks, more memory, full tool dumps. The bill arrives as
prefill cost, KV pressure, and attention dilution; utilization falls precisely
when the prompt is largest [I] (57-P7; 43;
../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md). Rule:
every turn's context is packed under an explicit budget, with compression and
eviction as first-class operations, not emergency measures (41).

## Where this page sits in the wiki

- 32-conversational-rag.md — RAG blended with dialogue state (the RAG+memory seam).
- 33-memory-rag.md — memory as a retrieval source for RAG pipelines (the deep dive
  on the Memory feeder).
- 24-agentic-rag.md — retrieval as a tool the agent decides to call (the RAG+tools
  seam; the agent loop lives in ../Agents/Agent-Loops-and-Reasoning-Strategies.md).
- ../Agents/Tool-Use.md — the tool-calling contract: schemas, side effects,
  authorization (the deep dive on the Tools feeder).
- ../Context-Engineering/Context-Budget.md — the budget discipline the
  orchestrator enforces across all feeders.

## Key Takeaways
1. RAG, memory, and tools are three evidence sources with different epistemic status: corpus-verified, historically-asserted, live-but-ephemeral.
2. One orchestrator logic — select, rank, pack, budget — governs all three, because they share one finite context window.
3. Label provenance: memory is not fact, tool output is not corpus, and citations must distinguish the three.
4. Context engineering is the fourth role: budget, ordering, and compression decide quality as much as any retriever (../Context-Engineering/Context-Budget.md).
5. The three classic blunders — memory-as-fact, tool-output-as-knowledge, unbounded growth — are all budget-and-provenance failures, not model failures.

## Related
- The agent side: 24-agentic-rag.md · ../Agents/Tool-Use.md · ../Agents/Agent-Loops-and-Reasoning-Strategies.md · ../Agents/Multi-Agent-Systems.md
- The context side: ../Context-Engineering/Context-Budget.md · ../Context-Engineering/Context-Compaction.md · ../Context-Engineering/Agent-Memory.md
- The memory seam: 32-conversational-rag.md · 33-memory-rag.md · 60's era view in 61-rag-big-picture.md
- The live-data seam: 34-web-rag.md · 35-realtime-rag.md · 30-structured-data-rag.md
