# Long Context vs RAG — When to Stuff and When to Retrieve

`LAST_UPDATED: 2026-08-29` · Status: core page · Analysis page; model behavior
claims are [I] or [F] from verified literature (see 02 for the
lost-in-the-middle paper).

## 30-Second Explanation
Since long-context models (hundreds of K to M tokens) became the default, the
standing question is: **if I can put the whole corpus in context, do I still
need retrieval?** The honest answer: for a *bounded* evidence set that is
*known up front*, yes — stuffing wins on simplicity and doesn't have the
retrieval-miss failure mode. For a *large, changing, heterogeneous* corpus
served at volume, no — cost, latency, and attention dilution all scale
against you. The production answer is **hybrid**: retrieve for breadth, then
put the *selected* evidence in a long context for depth.

## The two strategies, precisely
| | Stuff-it (long context) | Retrieve-it (RAG) |
|---|---|---|
| Evidence selection | none — everything is in | top-k by similarity (+ filters) |
| Failure to include evidence | impossible (it's all there) | possible — the retrieval miss (47) |
| Cost per query | prefill over the whole corpus | prefill over k chunks |
| Latency (TTFT) | grows with corpus | grows with k (flat in corpus size) |
| Freshness | re-prompt = refresh | reindex (or stream, 35) |
| Attention behavior at scale | dilutes; lost-in-the-middle [F: arXiv:2307.03172 — U-shaped performance vs position] | the model sees only the selected slice |
| Citation quality | "page X of 500" is hard to localize | chunk/page citations are natural |
| Security | the whole corpus is in context (any of it can be quoted) | ACL-filtered subset only |
| Breaks when | corpus > window, or corpus × cost too high | retrieval misses; multi-hop needs |

## The cost side, quantified
[E: from the constants bank + canonical 128 KiB/token KV constant]:
- A "small" enterprise corpus: 100K chunks × 512 tok = 51.2M tokens ≈
  ~200 MB of text. Stuffed per query: 51.2M input tokens → at $3/1M that is
  ~$154 *per request* — the strategy that is "obviously cheaper" is not.
- Even a "manageable" 1M-token context: ~3.8 MiB of text ≈ 750K words [E];
  prefill of 1M tokens is O(N²) attention work on standard attention models
  [I: quadratic in the prompt], and ~122 GiB of KV at 70B-class [E: 1e6 × 128
  KiB = 128,000,000 KiB ≈ 122.1 GiB binary] — a full GPU, for one request,
  before decode.
- RAG at 10×512-tok chunks: 5,120 tokens ≈ $0.015 input + ~640 MiB KV [E].
The ratio is ~4 orders of magnitude (10⁴) in this worked example — it grows
further with corpus size, but the example shows exactly 10⁴. *Even when the
window fits, the window is not the constraint — the bill is.*

## Quality at scale: why stuffing degrades
1. **Lost-in-the-middle**: performance dips for evidence placed mid-context,
   even in models that "support" the length [F: arXiv:2307.03172]. The
   *effective* context is less than the *nominal* context.
2. **Attention dilution**: with more irrelevant tokens, the attention the model
   gives the critical token drops; retrieval + a focused context inverts the
   ratio in the model's favor [I: consistent with the long-context eval
   literature — verify per model on your golden set (46)].
3. **Contradiction load**: a large context contains *inconsistent* versions of
   the same fact (old + new); the model must resolve contradictions it would
   otherwise never see [I: model-behavior claim per the page's tagging
   convention]. Retrieval + version metadata (12) removes the old
   version instead of forcing the model to out-argue it.
4. **Security surface**: everything in context can be cited; the ACL-filtered
   retrieval path (48/49) is strictly smaller.

## The hybrid answer (the 2025–26 norm)
```
large corpus
   ↓ retrieve (hybrid + rerank, 13/14) → top-k candidates
   ↓ pack into a long context WITH ORDERING:
        instructions → most-relevant-first (mitigates lost-in-the-middle)
        → as-of stamps → per-chunk provenance labels
   ↓ generate
```
- Retrieve for **breadth** (corpus → k); long context for **depth** (k →
  thorough reading). This is just 41's compression argument with the
  budget raised.
- For **multi-hop/agentic** flows (24/26), each hop's evidence enters a
  running context — the context is the agent's working memory, and retrieval
  is how it grows (60).
- **KV/prefix caching** makes the hybrid cheap: repeated system blocks +
  frequently-retrieved chunks hit the prefix cache when they appear in a
  *stable prefix position* across requests (cache keys match exact token
  prefixes; dynamic re-ranking that moves a chunk's position breaks the hit)
  (43, `../KV-Cache/`).

## Decision guide
- **Stuff**: the corpus is ≤ ~100K tokens, stable per task, all of it is
  relevant-or-harmless to include, and cost per query is acceptable (a
  single-contract analysis, a bounded document review). [I: the 100K-tok
  threshold is cost-dependent, not a law — recompute the bill for your
  model/pricing.]
- **Retrieve**: the corpus is larger, changing, private (ACLs), or served at
  volume — i.e. *all of production RAG in this section*.
- **Both** (the default): retrieve, then read deeply in a long context;
  measure both on the golden set (45/46) because the interaction (retrieval
  recall × attention dilution) is the only thing your measurements will tell
  you.
- **Neither**: exact/structured data — go to 30.

## Key Takeaways
1. Window size and affordability are different constraints; at scale the bill
   kills stuffing long before the window does (exactly 10⁴ in this page's
   worked example; grows with corpus size [E]).
2. Nominal context ≠ effective context: lost-in-the-middle and dilution make
   "it fits" worse than it looks [F: 2307.03172; I: per-model].
3. Stuffing has no retrieval miss; RAG has no ~122-GiB single-request KV [E].
   Each wins in its regime.
4. The production answer is hybrid: retrieve for breadth, read deeply in a
   long context, ordered for the attention model.
5. The threshold is a cost calculation per model/pricing, not a fixed number
   — recompute it (44).

## Related
[44 economics](44-rag-economics.md) · [43 inference](43-rag-inference-engineering.md) ·
[41 compression](41-context-compression.md) · [24 agentic](24-agentic-rag.md) ·
`../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md` ·
`../Context-Engineering/Context-Budget.md` · `../KV-Cache/README.md`
