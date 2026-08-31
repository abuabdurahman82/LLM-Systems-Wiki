# Context Compression — Less Context, Same Evidence
`LAST_UPDATED: 2026-08-29` · Status: core page · Cost numbers derived in-session from the
constants bank [E]; compression-technique trade-offs are engineering inference [I]; the
lost-critical-evidence risk is a mechanism argument, not a benchmarked statistic.

## 30-Second Explanation
Retrieval is tuned for *recall*, so it over-fetches: top-k returns chunks the generator
never needed. Context compression sits between retrieval and generation — retrieve 20
chunks, keep the evidence, drop the padding — and pays for itself twice: lower prefill cost
and less attention dilution. The discipline is in the subtitle: compression must preserve
*evidence*, not merely reduce tokens. The failure that makes this page matter is silent:
compression removes a span that was sparse, low-salience, and load-bearing — the one exact
number the answer needed — and everything downstream still runs green. Compress with a
paper trail; measure what you drop (45).

## The pipeline
```
            CONTEXT COMPRESSION IN THE RETRIEVAL PIPELINE

 [ Retriever ]          [ COMPRESSOR ]                       [ LLM ]
 top-k = 20 chunks  ->  rerank -> prune -> extract/condense  ->  packed context
 20 x 512 tok           keep evidence spans,                 e.g. 10 chunks or
 = 10,240 tok [E]       drop redundancy                      ~5,000 tok [E]
                            │
                            ├── kept spans (with chunk ids) -> prompt
                            └── dropped spans -> logged for ablation (45)

  cost @ $3/1M input [E]:  10,240 tok = $0.0307  ->  ~5,000 tok ≈ $0.015
                           save ≈ $0.015 per request (about 50%)
```
Note the ordering: compression runs *after* reranking when a reranker is present — the
reranker's relevance scores are the cheapest good pruning signal you already have (14).

## The four compression families
They compose; a common production shape is reranker pruning + one of the first
three [I: engineering-consensus inference, not a measured adoption statistic].

| Technique | Mechanism | Keeps | Drops | Failure mode |
|---|---|---|---|---|
| **Extractive compression** | select whole spans/sentences that bear on the query (small ranker or heuristic scorer over sentences) | original wording, citable verbatim | everything unselected, including connective tissue the generator may need for coherence | the selected spans read as fragments; context breaks |
| **LLM compression** | a (small, cheap) LLM summarizes each chunk or the whole candidate set into a condensed brief | gist, coherent narrative | exact wording, edge details, the "boring" sentence holding the one precise number | fluent summary that quietly omits critical evidence — hardest failure to notice |
| **Sentence filtering** | score each sentence against the query; drop below a threshold | high-salience sentences | anything below threshold — including low-salience-but-essential facts (dates, thresholds, footnotes) | threshold tuned on topical questions destroys numeric-evidence questions |
| **Reranker-based pruning** | use cross-encoder relevance scores from reranking; drop whole chunks below a relevance cutoff *before packing* | the top-scoring chunks intact | low-relevance chunks — no sentence surgery | inherits reranker biases (14); a chunk that is globally low-scored but holds the one needed number gets dropped whole |

Selection guidance [I]: extractive when citations must be verbatim; LLM compression when
coherence matters more than verbatim fidelity (and the domain tolerates paraphrase);
sentence filtering when chunks are long and mostly boilerplate; reranker pruning as the
always-on baseline because the scores are already paid for.

## What it saves [E]
Before the arithmetic, the bill for doing nothing — each item is a compression argument on
its own [E, bank constants; derivations re-run in-session]:

| Quantity (512-tok chunks, $3/1M in, $15/1M out) | Value |
|---|---|
| 20 chunks of input per request (20 x 512 tok) | 10,240 tok |
| Input cost of those 20 chunks | $0.0307 |
| Input cost at 10 chunks (bank's standard request) | $0.0154 (= $0.01536; the bank's 0.0153 is truncated) |
| **Saving from halving 20 -> 10** | **$0.0154 per request** |
| Saving from a lighter prune (20 -> 15) | $0.0077 per request |
| KV memory at 10,240 tok (128 KiB/tok, 7B-class convention) | ~1,280 MiB |
| KV memory at 5,120 tok | ~640 MiB (half) |

Derivations from the constants bank (chunks of 512 tok; $3/$15 per 1M in/out;
rounded to 4 dp; the bank's $0.0153 for 10x512 input is the truncated form of
the same $0.01536):

- 20 chunks x 512 tok = **10,240 tok** ≈ **$0.0307** input per request.
- Halving to the 10 useful chunks = 5,120 tok ≈ $0.0154 input.
- **Saving ≈ $0.0154 per request** (20→10); a lighter prune (20→15) saves
  2,560 tok ≈ $0.0077 — so call the saving **≈ $0.008–$0.015 depending on how
  hard you prune** (rounded; exact anchors $0.0077 / $0.0154).
- Per 10k requests/day that is roughly $77–$154/day on input alone
  (≈ $80–$150; $0.0077–$0.0154 × 10k) [I: linear scaling of the per-request
  delta; this is the *gross* saving — LLM-based compression adds its own
  per-request cost (44), which erodes part of it].
- Secondary savings: prefill latency and KV memory drop proportionally — at the
  bank's 128 KiB/token convention (≈ 7B-class GQA in fp16, e.g. Mistral-7B:
  32 layers × 8 KV heads × 128 × 2B; a 70B-class model like Llama-3-70B is
  ~320 KiB/token in fp16, so the *ratio* is what matters here), 10,240 tok ≈
  1,280 MiB of KV vs 5,120 tok ≈ 640 MiB [E: bank ratio applied to bank
  constants] — which matters under continuous
  batching (43, ../Inference/Continuous-Batching.md).

None of this counts the generation-side win: shorter, denser contexts can
reduce attention dilution and lost-in-the-middle effects (../Context-Engineering/
Lost-in-the-Middle-and-Long-Context-Reality.md), so compression often buys
accuracy *and* cost at once [I: the direction is consistent with the
long-context eval literature; per-model, measure on your set (46)].

## The core risk: compression removes critical evidence
Retrieval and compression both score *salience*, and some evidence is structurally
low-salience: the fact that answers the question sits in one clause inside a chunk that is
otherwise off-topic. The classic shape [I]:

> The answer needs the exact number on **line 7 of chunk 3** — "the pilot cohort was
> **412 patients**, not 421" — a single clause inside a chunk that is mostly about
> recruitment logistics. Every sentence-level scorer ranks that clause low: low query-term
> overlap, no headings, no emphasis. Extractive selection keeps the logistics prose;
> sentence filtering drops the clause; LLM summarization writes "recruitment proceeded
> without issues." The generator then answers *plausibly and wrong*, with citations —
> the worst failure class in this handbook (47).

Three properties make this dangerous: it is **silent** (pipeline metrics stay green), it is
**question-dependent** (the same compressor is safe on topical queries and unsafe on
numeric ones), and it is **eval-invisible** if your eval set under-represents
sparse-evidence questions (45, 46).

## Detection: measure what you drop
- **Ablation protocol** [I]: for a sample of eval questions, run generation twice — full
  context vs compressed context. Score both (faithfulness, answer correctness, citation
  correctness; 45). Divergence = the compressor is deleting load-bearing evidence. Automate
  as a recurring job, not a one-off.
- **Drop-log audit**: persist every dropped span with its scores and sample them for human
  review. Questions the ablation fails should be traced to specific dropped spans.
- **Sparse-evidence eval slice**: add golden questions whose evidence is a single number or
  name buried in a long chunk (46). This is the eval set that catches the line-7 failure
  class before users do.
- **Change-correlated ablation**: re-run the ablation whenever the compressor, its
  thresholds, or the upstream retriever changes — compression quality is a function of all
  three [I].
- **Canary entities**: thread rare tokens (ids, codes, figures) through the corpus and
  check the compressed context still contains them for the corresponding questions [I].

## Mitigations
- **Keep-entity rule**: never drop a span containing an entity that appears in the query
  (or its rewritten form): ids, codes, names, numbers, dates. Cheap, mechanical, catches
  the worst class [I].
- **Compress-not-delete for high-stakes domains**: legal, medical, financial, compliance —
  prefer *relocating* low-salience spans to a condensed "detail appendix" section of the
  context over deleting them. Costs tokens; the domain forbids silent loss.
- **Keep originals addressable for citations**: the compressor works on chunk ids; the
  citation layer resolves answers back to the *original* chunk (position, doc, version),
  not to the compressed text. Even if display shows the compressed brief, the audit trail
  and re-expansion path stay intact (12).
- **Question-aware thresholds**: numeric/id-style queries get looser pruning (or none);
  topical queries prune aggressively [I].
- **Small-k fallback**: when the evidence set is small and knowable (one contract, one
  incident), do not compress at all — long-context reading is the right tool (39).

## Key Takeaways
1. Compression sits between retrieval (tuned for recall) and generation (needs precision):
   20 chunks in, evidence retained, padding gone — with a drop-log.
2. Four composable techniques: extractive, LLM summarization, sentence filtering, reranker
   pruning; reranker pruning is the cheapest baseline because the scores already exist (14).
3. The savings are real [E]: pruning 20x512-tok chunks to 10 saves ~5,120 tok ≈ $0.0154
   per request at $3/1M input, plus proportional prefill/KV relief.
4. The core risk is silent deletion of low-salience-but-essential evidence — the exact
   number on line 7 of chunk 3 — which topical eval sets never catch.
5. Detect with ablation (same question, compressed vs full) and sparse-evidence golden
   questions; mitigate with keep-entity rules, compress-not-delete in high-stakes domains,
   and originals that stay addressable for citations.

## Related
[14 reranking (the pruning signal)](14-reranking.md) ·
[45 evaluation (measure what you drop)](45-rag-evaluation.md) ·
[46 golden datasets](46-rag-golden-datasets.md) · [03 basic pipeline](03-basic-rag-pipeline.md) ·
[42 caching](42-rag-caching.md) · `../Context-Engineering/Context-Budget.md` ·
`../Context-Engineering/Lost-in-the-Middle-and-Long-Context-Reality.md` ·
`../KV-Cache/Paged-KV-Cache.md`
