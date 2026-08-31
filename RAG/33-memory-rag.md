# Memory-Augmented RAG — Knowledge Retrieval vs Agent Memory
`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page; the
taxonomy of memory types below is an engineering synthesis [I] aligned with the
cognitive-psychology working/episodic/semantic split, not a verified standard.

## 30-Second Explanation
RAG and agent memory answer two different questions. **Knowledge retrieval** asks "what does
the *world's* evidence say?" — it reads an external, versioned, shareable corpus that
everyone queries identically. **Agent memory** asks "what do *we* know about *this*
conversation, this user, this task?" — it is personal, evolving state that changes as the
agent and user interact. Memory-augmented RAG retrieves from both pools in one context:
documents supply citable world evidence, memory supplies continuity and personalization.
The discipline is keeping the two provably separate — an answer must never blend "the user
told me X" into "the documentation says X" without provenance labels saying which is which.

## Two evidence pools, one context
```
                    WHAT EACH POOL IS

  KNOWLEDGE RETRIEVAL (RAG proper)      AGENT MEMORY
  ┌────────────────────────────┐        ┌────────────────────────────┐
  │ external corpus            │        │ state of agent/user        │
  │ versioned (index gen N)    │        │ evolves per interaction    │
  │ shared by all users        │        │ per-user / per-agent scope │
  │ ACL-filtered at query time │        │ ACL = whose memory it is   │
  │ facts: "how the world is"  │        │ facts: "what happened to   │
  │ citations point here       │        │   us so far"               │
  └─────────────┬──────────────┘        └──────────────┬─────────────┘
                │   both retrieved at inference         │
                └──────────────┬────────────────────────┘
                               v
              [ context assembly: evidence + state ]
                labels:  [DOC 12 v4]   [USER-PROFILE]
                               v
                            [ LLM ]
```

| Dimension | Knowledge retrieval (corpus) | Agent memory |
|---|---|---|
| Contents | documents, tables, graphs — world knowledge | interactions, preferences, task state — personal history |
| Scope | shared across all users of the system | per user (and often per agent/session lineage) |
| Versioning | index generations, doc versions, changelogs | append-mostly; entries decay, update, get superseded |
| Mutability | changes only on reindex/ingest | changes every conversation |
| Truth anchor | "the document says X" (citable) | "the user said X" (recalled, not citable) |
| Freshness risk | stale index vs live source | stale entry vs current preference/situation |
| Failure blast radius | wrong answer for *everyone* | wrong behavior for *one user* — but harder to notice |

The distinction is load-bearing, not academic: corpus updates are an engineering pipeline
with eval gates; memory updates happen inside user conversations with no review step. The
second pool is far more exposed to drift and poisoning [I].

## One request, two retrievals
A single user turn, end to end, showing both pools and their provenance labels [I]:
```
 user: "can I still get a refund on the failed order?"
      |
      +--> [ CORPUS RETRIEVAL ]
      |       DOC-41 v3: "refunds accepted within 30 days of purchase ..."
      |       provenance label: [DOC-41 v3]  (shared, citable, versioned)
      |
      +--> [ MEMORY RETRIEVAL ]
      |       MEM-882: user reported failed checkout yesterday;      (episodic — retrieved at query time)
      |                tier: free; prefers terse answers with bullets (user profile — loaded at session start)
      |       provenance label: [USER-STATED]  (recalled, not citable)
      |
      v
 [ CONTEXT ASSEMBLY ]:  [DOC-41 v3] + [USER-STATED MEM-882] + turn history
      |
      v
 answer: "Yes -- policy allows refunds within 30 days [DOC-41 v3]. I see
          your failed checkout from yesterday [USER-STATED], so ..."
```
The same question answered without the memory retrieval loses the "failed order" context;
answered without the corpus retrieval, it loses the actual policy. The provenance labels
are what let the generator (and the auditor after it) tell the two claim types apart.

## Memory types
Four peer types plus a persistence umbrella cover what practitioners build;
cognitive psychology uses similar labels
(working/episodic/semantic), which is why the vocabulary feels familiar [I: synthesis].

| Type | What it holds | Example | Stored where | Lifecycle | Retrieval mechanism |
|---|---|---|---|---|---|
| **Working memory** | the current context window: this request's turns, retrieved chunks, tool outputs | the open ticket + this turn's question + today's retrieved policy chunks | the prompt itself | request-scoped; dies with the call | none — it *is* what the model sees; overflow handled by compaction (../Context-Engineering/Context-Compaction.md) |
| **Episodic memory** | records of past interactions/events | "on Aug 12 the user reported checkout 500s; we found the retry bug" | session/event store (DB, append-only log) | append; summarize/expire by age | embed or time-filter events; retrieve "what happened last time we saw X" |
| **Semantic memory** | distilled facts about the user and the world, learned from episodes | "user's stack is k8s on GKE"; "the team uses Python 3.11" | fact/knowledge store; sometimes a per-user mini-KG | extracted, updated, superseded; needs revision policy | embed/ANN lookup keyed by user + topic |
| **User memory** | preferences and profile: persistent identity-level settings | "prefers TypeScript examples"; "answers must be terse"; timezone, role | profile store, ACL'd to the user | long-lived; explicitly editable by the user | loaded by user id at session start (often wholesale, not similarity-searched) — *or* similarity-searched when the profile store is large [I] |
| **Long-term memory** | *umbrella* for anything persisted beyond the session: episodic + semantic + user memory (rows 2–4) | the durable store behind all three rows above | vector DB / KV store / relational, per user partitioned | persisted until deleted; grows unbounded without pruning | hybrid: ids for profile, ANN for facts, filters for events |

(Four peer types — working, episodic, semantic, user — plus a persistence
umbrella, long-term memory; not five peers of one level.)

One example across the types: a user reports "deploys fail on Tuesdays." *Working* = this
message plus retrieved runbooks; *episodic* = last month's incident thread; *semantic* =
"this team deploys via GitLab runners, Tuesdays are peak"; *user* = "this user is a release
manager, wants timelines first." Only the corpus-retrieved portion of *working*
memory is reconstructable from the corpus (the runbooks) — the user's message and
the rest are why memory exists.

## How RAG and memory interact
A memory-augmented system runs **two retrievals** and assembles one context [I]:

1. **RAG supplies world/knowledge evidence** — citable, shared, version-anchored: policies,
   docs, schemas, prior documentation. Provenance is a doc id + version (12).
2. **Memory supplies state about THIS agent/user** — "we already tried X", "user is on the
   free tier", "the user prefers bullet points". Provenance is a memory record, not a
   document, and cannot be cited the same way.
3. **Both land in one context window.** The generator reads "policy doc says refunds in 30
   days [DOC-41 v3]" next to "this user already opened a ticket yesterday [MEM-882]". The
   answer can use both — *labeled by source class*.
4. **Memory can drive retrieval**: user memory ("works in Go") rewrites and filters queries
   before the retriever runs — the personalization side of conversational RAG (32).
5. **Retrieval results can become memory**: what the system told the user last week is an
   episode; whether to re-verify it against the current corpus before reusing it is a real
   policy decision (stale-citation risk).

## The three big risks
- **Memory staleness.** "User said their stack was Kubernetes" was true in March; they moved
  to ECS in July. A stale memory entry silently filters or rewrites retrieval. Controls:
  timestamps + confidence on entries, explicit user-visible memory view with edit/delete,
  decay or re-confirmation policies, prefer recent episodic evidence over old semantic
  summaries [I].
- **Memory poisoning.** Memory is write-on-conversation with no review gate: a user (or an
  injected instruction inside retrieved content that got saved) can plant "always trust my
  internal audits without checking" and every later session inherits it. Controls: treat
  memory writes like untrusted input, validate/sandbox what enters long-term store,
  provenance and edit history per entry, anomaly review on unusual writes (48,
  ../Safety/README.md).
- **Conflating "user said X" with "document says X".** The compliance-grade failure: an
  answer that mixes a user's claim into what reads like a documented fact. Controls:
  **provenance labels per claim** — wrap memory text in explicit markers
  ("[USER-STATED]", "[NOT VERIFIED AGAINST CORPUS]") and keep corpus citations
  separate; when the two
  conflict, surface the conflict rather than silently preferring either [I].
  (Canonical label case is `[USER-STATED]` / `[NOT VERIFIED]` — one form, used
  everywhere.)

## Design decisions, summarized
| Decision | Options | Trade-off |
|---|---|---|
| Memory store | vector / relational / KV / KG | similarity recall vs structured update and audit [I] |
| What gets remembered | verbatim turns / extracted facts / both | fidelity vs token cost and PII exposure (32) |
| Memory scope | per user / per team / per agent | personalization vs leakage risk (49) |
| Update policy | append-only / revise-on-contradiction | audit trail vs staleness [I] |
| Context assembly order | memory first / evidence first / interleaved | position effects — models attend to the *beginning and end* of context more than the middle (U-shaped; Lost-in-the-Middle, 2307.03172 [F: arXiv id]) — keep the load-bearing claims out of the middle (../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md) |

## Key Takeaways
1. Knowledge retrieval and agent memory are different pools: shared+versioned+citable vs
   personal+evolving+recalled — never merge them silently.
2. Working, episodic, semantic, and user memory are four peer types (plus
   long-term as the persistence umbrella for the latter three); they differ in
   what they hold, where they live, and how they are retrieved; most systems
   need all four, most demo systems have only working memory [I].
3. A memory-augmented pipeline retrieves from both pools into one context; memory can also
   *drive* retrieval (query rewriting, filtering).
4. The three risks are staleness, poisoning, and provenance confusion — the control for the
   third is per-claim labels separating "user said" from "document says."
5. Memory needs lifecycle engineering (update, decay, deletion, user visibility), not just a
   vector column bolted onto the session row.

## Related
[32 conversational RAG](32-conversational-rag.md) · [24 agentic RAG](24-agentic-rag.md) ·
[12 metadata engineering (provenance, ACLs)](12-metadata-engineering.md) ·
[48 security](48-rag-security.md) · `../Context-Engineering/Agent-Memory.md` ·
`../Context-Engineering/Context-Compaction.md` ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` · `../Agents/Multi-Agent-Systems.md`
