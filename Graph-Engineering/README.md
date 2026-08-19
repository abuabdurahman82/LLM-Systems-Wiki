# Graph Engineering
`LAST_UPDATED: 2026-08-19` · Status: first-class section (new 2026-08-19)

## 30-Second Explanation
"Graph engineering" is the discipline of using *graph structure* — nodes + edges
with meaning — at every layer of an LLM system. It is not one technique; it is a
*family of representations* that shows up in four distinct places, and the 2024–26
research thread is that **graphs are how LLM systems organize knowledge,
reason, plan, and coordinate**:
1. **Knowledge graphs / GraphRAG** — the *data* layer: structure the corpus as
   entities+relations, retrieve over edges, not just vectors.
2. **GNNs & graph encoders** — the *model* layer: learn representations of graph
   data (and the expressivity limits of doing so).
3. **Reasoning graphs** — the *computation* layer: ToT/GoT/Think-on-Graph —
   reasoning as graph search over a partially-built solution.
4. **Agent-workflow graphs** — the *system* layer: the agent loop itself is a
   graph (AFlow, GPTSwarm, LangGraph) — and MAS topologies are graph topologies.
This section covers all four, and the shared question: **when does structure beat
flat sequence, and what does the structure cost?**

## Why graphs matter for LLMs (the structural argument)
A token sequence is a *path*; a task over knowledge is usually not a path — it's a
*web* (multi-hop: "A relates to B which relates to C"; a plan is a *tree*; a
workflow is a *DAG*; a conversation between agents is a *graph*). Three reasons
graphs win over flat context [I: synthesis]:
1. **Multi-hop retrieval.** Vector similarity retrieves *similar* chunks; a graph
   retrieves *connected* ones (HippoRAG's Personalized PageRank over the KG
   outperforms vector RAG on multi-hop — `Knowledge-Graphs-and-GraphRAG.md`).
2. **Global structure.** Summarizing a 1M-token corpus needs the *map* of the
   corpus, not a window into it — GraphRAG's "local→global" community
   summarization is the canonical instance (arXiv:2404.16130 [F]).
3. **Deliberate search.** Reasoning as *search* (ToT/GoT) needs a state space
   that is a graph, so you can branch, evaluate, and backtrack — something a
   one-shot sequence can't do (arXiv:2305.10601 [F], arXiv:2308.09687 [F]).
The cost: **graphs have build/maintenance overhead** (extract the entities, keep
the KG fresh, pay for the search) and **expressivity traps** (a GNN can't count
beyond its hop budget — `GNN-Basics.md` § expressivity).

## The pages in this section
| Page | The question it answers |
|---|---|
| `Knowledge-Graphs-and-GraphRAG.md` | How to structure a corpus as a KG, and how to retrieve/reason over it (RAG → GraphRAG → HippoRAG → LightRAG) |
| `GNN-Basics.md` | The model layer: message passing, expressivity (WL test), over-squashing, and LLM-era GNN hybrids |
| `Reasoning-Graphs.md` | The computation layer: reasoning as graph search (ToT, GoT, Think-on-Graph, and test-time compute) |
| `Agent-Workflow-Graphs.md` | The system layer: agent loops and MAS as graphs (AFlow, GPTSwarm, LangGraph; observability) |

## The four layers, one picture
```
        SYSTEM:    [A] ⇄ [B] ⇄ [C]         agent-workflow graphs
                          (AFlow / GPTSwarm / LangGraph)
        COMPUTE:   partial-solution DAG     reasoning graphs
                          (ToT / GoT / Think-on-Graph)
        MODEL:     learned node embeddings  GNNs
                          (MPNN/GAT/oversquashing limits)
        DATA:      entities + relations     knowledge graphs
                          (GraphRAG / HippoRAG / LightRAG)
```
Each layer reuses the others' questions: the *data* layer asks "what are the
edges?", the *compute* layer asks "how do I search the edge-space?", the *system*
layer asks "how do agents hand off across edges?", the *model* layer asks "what
can a neural network even *represent* about the graph?".

## The standing questions (the section's research agenda)
1. **When does structure beat flat?** (GraphRAG vs plain RAG is task-dependent —
   `Knowledge-Graphs-and-GraphRAG.md` § when-it-helps; "Do We Still Need
   GraphRAG?" arXiv:2604.09666 [F] is the 2026 counterpoint.)
2. **What is the graph's maintenance cost?** (KG freshness, entity resolution,
   edge confidence — a stale graph is worse than no graph [I].)
3. **What can neural models represent about graphs?** (the expressivity/
   over-squashing limits — `GNN-Basics.md`.)
4. **What is the right search policy for reasoning-as-graph?** (branching factor,
   evaluation function, budget — `Reasoning-Graphs.md`.)
5. **Is the workflow graph hand-designed or learned?** (AFlow's MCTS-learned
   graphs — `Agent-Workflow-Graphs.md`.)
6. **How do you observe/verify a system whose state is a graph?** (trajectory
   scoring over graph executions — `../Agents/Agent-Evaluation.md`.)

## Related
`../Context-Engineering/Agent-Memory.md` (graph memory: Zep) ·
`../Agents/Multi-Agent-Systems.md` (MAS = graph topologies) ·
`../Agents/Agent-Loops-and-Reasoning-Strategies.md` (ToT/ReAct) ·
`../RAG/README.md` (the flat-RAG baseline this section upgrades).

## Key Takeaways
Graph engineering = the discipline of giving *structure* to knowledge (KGs),
representations (GNNs), reasoning (search over states), and systems (workflow
graphs). The 2026 thread: graphs are how LLM systems organize the *multi-hop*
world that flat context can't — and the standing question is the **cost/benefit
ratio of that structure** per layer.
