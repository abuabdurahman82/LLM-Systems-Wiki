# Multi-Agent RAG — When More Than One Retriever Mind Helps

`LAST_UPDATED: 2026-08-29` · Status: core page · Architecture reasoning [I];
agent-loop mechanics cross-link to `../Agents/`.

## 30-Second Explanation
Single-agent RAG (24) is one controller that plans, retrieves, and reflects.
**Multi-agent RAG** splits the retrieval/reasoning work across *several*
agents — usually one per source domain (web agent, vector agent, SQL/graph
agent) — with a coordinator that merges their evidence. The pitch is
specialization and parallelism: each agent can be tuned to its source's
failure modes and run concurrently. The counter-pitch is that each extra agent
is another LLM loop: more cost, more latency, more ways to desynchronize, and
a merge step that is itself a retrieval problem. **Multi-agent helps when the
sources are genuinely heterogeneous and the question requires parallel,
domain-tuned retrieval; it creates complexity when it doesn't.**

## The reference architecture
```
                 Research Coordinator
        (plans: which sub-questions, which agents,
         what counts as sufficient evidence)
                        │
      ┌─────────────────┼─────────────────┐
      ▼                 ▼                 ▼
  Web Agent       Vector Agent      Graph/SQL Agent
  (34: search,    (07/13/14:       (30/28: schema-aware
   extract,        hybrid+rerank   queries, graph
   trust-tier)     over internal)  traversal)
      │                 │                 │
      └─────────────────┼─────────────────┘
                        ▼
                  Evidence Merge
                  (dedup, cross-source conflict,
                   provenance + trust tiers, 36)
                        ▼
                      Evaluator
                      (per-claim coverage check:
                       is every load-bearing claim
                       supported by merged evidence?)
                        ▼
                      Answer (with per-source citations)
```

The roles, precisely [I]:
- **Coordinator**: decomposes the goal into sub-questions, assigns agents,
  decides when evidence is *sufficient* (the termination condition, 27), and
  owns the final answer. Its loop is a planning loop (`../Agents/Agent-Loops-and-Reasoning-Strategies.md`).
- **Worker agents**: each owns one source with its own retrieval stack and
  *source-specific* tooling (the web agent knows fetch/render/robots; the SQL
  agent knows the schema and read-only rules, 30; the graph agent knows
  traversal, 28). Specialization is the whole justification — a worker that
  does "generic retrieval" is just a redundant single agent.
- **Evidence merge**: the federated-rank step (36) — heterogeneous scores,
  cross-source dedup, conflict surfacing, trust tiers. This is where most of
  the *design* lives; the agents are the easy part.
- **Evaluator**: a separate pass (usually a different/cheaper model) that
  checks claim-by-claim coverage against the merged evidence before the answer
  ships (the 45 verification pass, made per-claim). Optional at low stakes;
  standard in high-stakes multi-source systems [I].

## When multiple agents help
1. **Genuinely heterogeneous sources** where per-source tuning pays: the web
   agent's anti-injection discipline (34/48), the SQL agent's read-only +
   schema discipline (30), the vector agent's hybrid+rerank (13/14) are
   different *policies*, not just different indexes. One agent holding all
   three toolsets has one prompt, one policy, and one context budget to
   juggle them; three agents each own one [I: the standard argument].
2. **Parallelizable evidence collection**: the web fetch + vector search + SQL
   query run concurrently → wall-clock latency ≈ max(agents), not sum
   [I: the latency argument — valid only when the coordinator's decomposition
   is good enough that the agents' sub-questions don't depend on each other].
3. **Context isolation**: each agent's intermediate reasoning (search
   dead-ends, retries) stays in *its* context; the coordinator sees only
   evidence, not agent noise. For long investigations this keeps the
   coordinator's context clean (the 41 argument applied to agent context).
4. **Different model tiers**: the SQL agent can be a cheap model with strong
   schema grounding; the web agent needs a strong model for source judgment
   [I: model routing, `../Platform-Economics/11-economic-model-routing.md`].

## When it is unnecessary complexity
- **One source, one retriever**: a single-agent RAG (24) — or even a non-agent
  pipeline (03+13+14) — does it cheaper and more predictably.
- **The "agents" don't differ in policy/tools**: two agents over the same
   vector index with different prompts are two chances to disagree with no
   information gain — the merge becomes noise mixing [I: the degenerate
   case].
- **Dependent sub-questions**: if agent B's query depends on agent A's answer
   (multi-hop, 26), the "parallel" architecture collapses into a serial chain
   with two sets of overhead — a single agent's loop is simpler and
   equally correct.
- **Cost/latency SLOs**: k agents ≈ k× the LLM cost of a single agent's
  retrieval steps, plus merge + evaluator. At 100 qps this is not a
  "research pattern", it is a bill (44). The 80/20 rule: **start single-agent;
  split into specialists only when one source's failure mode is measurably
  hurting the whole** (47/46 evidence).

## Failure modes specific to multi-agent
1. **Coordinator under-decomposition**: sub-questions that miss part of the
   goal → evidence is incomplete and *the agents cannot recover it* (the
   retrieval-miss problem, 47, at the planning layer). Symptom: answers that
   are confident but missing a dimension. Detection: golden-set multi-part
   questions (46) with per-part scoring.
2. **Duplicate evidence, conflicting**: two agents retrieve overlapping
   evidence with different interpretations; the merge silently picks one →
   the answer reflects the merge's bias, not the corpus. Fix: conflict
   surfacing (36), provenance labels in the packed context.
3. **Termination disagreement**: the coordinator declares "sufficient" while
   the evaluator would flag a gap (or vice versa) → oscillation or premature
   stop (27's termination conditions, now between *two* decision-makers).
4. **Context drift between agents**: agent A's sub-question, re-phrased by the
   coordinator for agent B, has drifted from the original goal (15's
   transformation-drift problem, amplified across hops). Mitigation: the
   coordinator carries the original goal verbatim in every agent prompt.
5. **Cost explosion on failure**: a web agent retrying bad queries 5× while
   the coordinator waits — the agent loop has no budget unless the coordinator
   enforces per-agent step/cost caps [I: agent-harness discipline,
   `../Harness-Engineering/`].

## Key Takeaways
1. Multi-agent RAG = coordinator + source-specialized workers + evidence merge
   + (usually) an evaluator; the merge is the design center of gravity.
2. It helps when sources are heterogeneous *in policy*, and when collection
   is parallelizable with independent sub-questions.
3. It is pure overhead when the "agents" share one retriever, when
   sub-questions are dependent, or when SLOs don't afford k× LLM cost.
4. Start single-agent; split only on measured per-source failure (46/47).
5. Watch the multi-agent-specific failures: under-decomposition, merge bias,
   termination disagreement, goal drift, unbounded agent cost.

## Related
[24 agentic RAG](24-agentic-rag.md) · [26 multi-hop](26-multi-hop-rag.md) ·
[36 federated (the merge)](36-federated-rag.md) · [30 structured](30-structured-data-rag.md) ·
[34 web](34-web-rag.md) · [44 economics](44-rag-economics.md) ·
`../Agents/Multi-Agent-Systems.md`
