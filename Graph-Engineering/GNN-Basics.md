# GNN Basics (message passing, expressivity, over-squashing, LLM hybrids)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
A **graph neural network (GNN)** learns node/graph representations by *message
passing*: each node aggregates information from its neighbors, iteratively, so
after k layers a node "knows" about its k-hop neighborhood. The model layer of
graph engineering answers the question the data layer can't: **what can a neural
network actually *represent* about a graph, and where does it hit a wall?**
The walls are well-understood — the **Weisfeiler-Leman (WL) expressivity limit**
and **over-squashing** — and the 2024–26 thread is *LLM-era hybrids* that use
language models to read/write graphs (GraphGPT, GraphText, Think-on-Graph).

## Message passing (the core mechanism)
Two-phase per layer, repeated:
```
1. MESSAGE   m(v→u) = MSG(h_v, h_u, e_uv)      for each edge u–v
2. AGGREGATE h'_u = AGG( { h_u } ∪ { m(v→u) : v ∈ N(u) } )   # e.g. mean/sum/attention
3. UPDATE    h_u = UPDATE(h'_u)
```
After L layers, `h_u` encodes the u's L-hop neighborhood. [I: this is the
canonical form; the variants (MSG/AGG/UPDATE choices) are the specific
architectures below.]

## The architecture family (the reference points)
| Arch | Paper / arXiv | The idea | Limit it hits |
|---|---|---|---|
| **GCN** | Kipf & Welling 2016, arXiv:1609.02907 [F] | spectral GC: `h' = D^{-1/2} A D^{-1/2} h W` — fixed (non-learned) propagation + linear | fixed spectrum; can't model edge types well |
| **GraphSAGE** | Hamilton et al. 2017, arXiv:1706.02216 [F] | *inductive*: sample a neighbor set, aggregate → generalize to unseen nodes | fixed aggregation; no edge features |
| **GAT** | Veličković et al. 2017, arXiv:1710.10903 [F] | *learned attention* over neighbors (per-edge weights) | attention is 1-hop; still WL-bounded |
| **GATv2** | Brody et al. 2021, arXiv:2105.14491 [F] | fixes GAT's static-attention bug (dynamic per-query attention) | (expressivity still WL) |
| **GIN** | Xu et al. 2019, arXiv:1810.00826 [F] | "How Powerful are GNNs?" — sum-agg + MLP is *as powerful as the 1-WL test* | **exactly** the WL ceiling |
| **MPNN** | Gilmer et al. 2017, arXiv:1704.01212 [F] | the neural-network form of message passing (quantum-chemistry origin) | — |
| **Graph Transformer** | Shi et al. 2019 "Do Transformers Really Perform Badly for Graph Representation?" (arXiv id UNVERIFIED 2026-08-19 — arXiv API/S2 both throttled this session, excluded rather than mis-cited) and the verified spectral line: **Kreuzer et al. 2021, arXiv:2106.03893** "Rethinking Graph Transformers with Spectral Attention" [F] | attention over *all* nodes (not just neighbors) → global receptive field in 1 layer | O(N²) attention; scales poorly |
| **HGT / heterogeneous** | arXiv:2003.01332 [F] | type-aware attention for heterogeneous graphs | — |
| **MixHop** | Abu-El-Haija et al. 2019, arXiv:1905.00067 [F] | mix multi-hop adjacency powers to escape shallow over-smoothing | — |
| Surveys | Wu et al. arXiv:1901.00596 [F]; Zhang & Yang arXiv:1812.08434 [F] | the field map | — |

## The two fundamental limits (the "walls")
### 1. The WL expressivity ceiling
**The Weisfeiler-Lehman (1-WL) test** is a *color-refinement* algorithm: it
repeatedly re-colors each node by the multiset of its neighbors' colors, until
stable. **GIN's theorem [F: arXiv:1810.00826]:** a GNN with **sum aggregation +
an MLP update** is *as expressive as* 1-WL (the two compute the same graph
invariants); **mean and max pooling are strictly less powerful** than sum (they
lose the multiset cardinality). So the practical ceiling for "vanilla" GNNs is
the 1-WL colors, and the specific aggregator matters. [I: the "ceiling" framing]
**The classic counterexample [E: the standard WL-non-distinct pair]:** two
*non-isomorphic 2-regular graphs* — the 6-cycle C₆ vs two disjoint triangles
K₃∪K₃ — are indistinguishable to 1-WL (every vertex has degree 2 in both; the
color refinement stabilizes on a single color) yet one is connected and the
other is not. More generally, GNNs **cannot count** reliably beyond the
neighborhood, cannot reliably distinguish non-isomorphic regular graphs with
the same degree sequence, and cannot distinguish graphs with the same
degree/multiset structure. (Note: a cycle Cₙ *vs* a path Pₙ of the same length
is *not* a counterexample — the path's two degree-1 endpoints break the
symmetry, so 1-WL separates them [E: degree-sequence argument].)
**Why it matters for LLMs:** if your task is "count the triangles" or "is this
subgraph a cycle?", a plain GNN *will fail* — you need higher-order structure
(equivalence tests, k-WL, or explicit counting). The 2024–26 workaround: use the
*LLM* as the reasoner over the graph (it can count), not the GNN.
[I: this is exactly why Think-on-Graph/GraphText offload the "hard structural"
part to the LM — see `Reasoning-Graphs.md`]

### 2. Over-squashing (and over-smoothing)
**Over-squashing:** as you aggregate a *large* neighborhood into a *fixed-size*
vector, information is lost — the bottleneck. Long-range dependencies get
"squashed" through narrow edges; gradients vanish for far nodes. The
"Are More Layers Better?" line (2020; arXiv id UNVERIFIED 2026-08-19) showed
empirically that *more layers does not always help* — over-squashing +
over-smoothing make deep GNNs *worse* on long-range tasks. [I: direction well-
supported; the specific paper's arXiv id is unverified this session, so it's cited
by result, not id]
**Over-smoothing:** repeated message passing makes all node embeddings converge
to the same vector (the graph "forgets" which node is which) — deep GNNs
degenerate. MixHop (arXiv:1905.00067 [F]) and depth-separation tricks mitigate.
**The design consequence [I]:** don't just stack layers; *control the receptive
field per task*. A short-horizon task wants few layers; a long-range task wants
*global* attention (Graph Transformer) or *explicit* long edges (skip connections,
MixHop), not more of the same aggregation.

## The LLM-era hybrids (the 2024–26 thread)
The question GNNs can't answer ("count", "explain", "plan over this structure")
is exactly the question LLMs can — so the 2024–26 hybrids *offload* the
structural reasoning to the LM:
| Hybrid | Paper / arXiv | What it does |
|---|---|---|
| **GraphGPT** | 2023, arXiv:2401.00529 [F] | a pre-trained *Eulerian-path* transformer that reads/writes graphs as a linearized token sequence (graph-as-text) |
| **GraphText** | 2023, arXiv:2310.01089 [F] | does the *reasoning* in **text space** (an LLM walks the graph as text), not in embedding space — sidesteps the WL limit by using the LM's symbolic capacity |
| **Think-on-Graph** | 2.0: arXiv:2407.10805 [F]; 3.0: arXiv:2509.21710 [F] | an LLM agent *reasons over a KG*: it queries the graph, gets back subgraphs, and reasons in context — the "agent reads the graph" pattern; 3.0 makes it adaptive/efficient |
| **GNN + LLM (hybrid encoders)** | [I] | GNN produces node embeddings; LM does the task; or LM produces graph tokens, GNN refines — the split is the research question |

**The principle [I: synthesis]:** *let the GNN do what GNNs are good at
(local, learned, fast propagation) and let the LLM do what LLMs are good at
(counting, explaining, planning, multi-hop symbolic reasoning).* The hybrid's
value is that neither hits its own expressivity wall.

## Expressivity for LLM tasks (what to check before you pick a GNN)
A decision checklist [I]:
1. **Does the task need >1-hop?** If yes, a 1-WL GNN may not suffice — use
   Graph Transformer (global) or the LLM-hybrid.
2. **Does it need counting / subgraph-isomorphism / cycles?** If yes, *avoid*
   a plain GNN (WL ceiling) — use the LLM or k-WL / higher-order features.
3. **Is the graph large / sparse?** If yes, *inductive* sampling (GraphSAGE) or
   Graph Transformer with *local* attention (avoid O(N²)).
4. **Is the graph heterogeneous?** If yes, GATv2/HGT (type-aware).
5. **Is it long-range?** If yes, watch for over-squashing/over-smoothing — add
   global attention or explicit long edges, don't just add layers.

## Related
`Knowledge-Graphs-and-GraphRAG.md` (the *data* these models run on) ·
`Reasoning-Graphs.md` (the LLM-hybrids in depth) · `Agent-Workflow-Graphs.md`
(systems as graphs) · `../Model-Architectures/` (the non-graph model layer).

## Key Takeaways
GNNs = message passing with two hard walls: the **WL expressivity ceiling**
(can't count / can't distinguish same-degree structures) and **over-squashing/
over-smoothing** (deep ≠ better). The 2024–26 resolution is *hybrid*: GNN for
local/fast propagation, **LLM for the symbolic reasoning the GNN can't do**
(GraphGPT, GraphText, Think-on-Graph). Pick the model by checking whether your
task needs >1-hop, counting, or long-range — that determines whether a GNN alone
suffices.
