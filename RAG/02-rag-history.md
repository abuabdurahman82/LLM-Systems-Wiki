# RAG History & Lineage — From Inverted Indexes to Self-Reflecting Retrieval

`LAST_UPDATED: 2026-08-30` · Status: core page · Every citation below was
fetched and title-verified against the arXiv API / primary sources on
2026-08-29/30; venues marked UNVERIFIED where the record does not settle it.

## 30-Second Explanation
RAG is not one idea — it is the **confluence of two 30-year-old research lines**:
classical information retrieval (BM25, TF-IDF, the inverted index) and
neural sequence models. The modern stack is what you get when dense
embeddings learned to replace term matching *at the retrieval layer*, while
the LLM took over *the generation layer* — and both lines kept contributing
ideas (hybrid fusion, rerankers, self-reflection, graphs). Knowing which layer
each idea came from tells you what it will break when you change the other layer.

## The two parent lines

**Line A — classical IR (1970s–2019).** Term matching scaled because of the
inverted index, not because it was smart.
- **TF-IDF** — the canonical reference is Salton & Buckley, "Term-weighting
  approaches in automatic text retrieval", *Information Processing &
  Management* 24(5):513–523, 1988 [F: Crossref + live DOI, verified 2026-08-29].
- **BM25** — Robertson & Walker, "Some Simple Effective Approximations to the
  2-Poisson Model for Probabilistic Weighted Retrieval" (SIGIR 1994; the 1995
  label reflects the printed proceedings). The conventional defaults
  k1=1.2, b=0.75 are the Lucene/Elasticsearch/OpenSearch settings
  [F: Lucene 9.12 Javadoc + ES docs].
- **Dense retrieval** arrived from this line too: **DPR** (Karpukhin et al.,
  arXiv:2004.04906, EMNLP 2020 [F]) trained a bi-encoder to replace the bag of
  words on open-domain QA; **ColBERT** (Khattab & Zaharia, arXiv:2004.12832,
  SIGIR 2020 [F]) kept interaction cheap with token-level late interaction.

**Line B — neural language models (2013–2020).** Word2Vec → BERT → GPT:
embeddings that capture *meaning*, generators that capture *context*. RAG is
where line A's retriever is bolted under line B's generator.

## The founding paper

**RAG** — Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive
NLP Tasks", arXiv:2005.11401, NeurIPS 2020 [F: venue per arXiv comment field].
Parametric memory = a pre-trained seq2seq; non-parametric memory = a dense
Wikipedia index read by a neural retriever. The paper compares two
*formulations* — **RAG-Sequence** (conditions on the same retrieved
passages across the whole sequence) and **RAG-Token** (can use a different
retrieval per generated token). The result still stands as the taxonomy's
"Naive RAG" stage (05).
Note: the ID 2005.11409 is *not* this paper — it resolves to an unrelated
functional-analysis paper. The correct ID is 2005.11401 [F: arXiv API].

## The pre-trained retriever wave (2020–2022)

Retrievers became their own research object, trained with retrieval objectives:
- **REALM** (Guu et al., arXiv:2002.08909, ICML 2020 [F: PMLR v119]) —
  retrieval-augmented *pre-training* of a BERT-class bidirectional encoder,
  using masked language modeling back-propagated through a retrieval step;
  retrieval became part of training, not just inference.
- **Contriever** (Izacard et al., arXiv:2112.09118, **TMLR 2022** [F: dblp +
  OpenReview; not ICML 2022]) — unsupervised dense retrieval via contrastive
  pre-training; no relevance labels needed.
- **RETRO** (Borgeaud et al., arXiv:2112.04426, **ICML 2022** [F: PMLR v162
  borgeaud22a] — real title "Improving language models by retrieving from
  trillions of tokens") — retrieve from 1.2T tokens at inference for a
  7.5B-param LM; the "retrieval as a layer under the LM" pattern at scale.
- **HyDE** (Gao et al., arXiv:2212.10496, ACL 2023 [F: Anthology
  2023.acl-long.99]) — query-side fix: embed a *hypothetical* answer, not the
  question. Deep dive: 17.

## The learned-control wave (2023–2024)

Retrieval stopped being a fixed pre-step and became something the model
*decides*:
- **Self-RAG** (Asai et al., arXiv:2310.11511, **ICLR 2024 oral** [F: OpenReview
  forum hSyW5go0v8, published 2024-02-01]) — reflection tokens let one LM
  retrieve on demand and critique its own evidence. Deep dive: 21.
- **CRAG** (Yan et al., arXiv:2401.15884 [F: paper verified; venue UNVERIFIED —
  no proceedings entry found]) — a cheap evaluator grades the retrieval, and
  the verdict structurally changes the evidence. Deep dive: 22.
- **Adaptive-RAG** (Jeong et al., arXiv:2403.14403, NAACL 2024 [F: arXiv
  comment field]) — route by predicted question complexity. Deep dive: 23.
- **RAPTOR** (Sarthi et al., arXiv:2401.18059, ICLR 2024 [F]) — recursive
  cluster-and-summarize into a retrieval tree. Deep dive: 20.
- **GraphRAG** (Edge et al., arXiv:2404.16130 [F: paper verified; "ECAI 2025"
  UNVERIFIED — cited as ECAI 2025 (Bologna) by multiple secondary sources,
  but no ECAI proceedings entry was findable as of 2026-08-30]) —
  LLM-built entity graph + community summaries for
  corpus-global questions. Deep dive: 28.
- **IRCoT** (Trivedi et al., arXiv:2212.10509, ACL 2023 [F: Anthology
  2023.acl-long.557]) — interleaves retrieval *inside* chain-of-thought.

## The production wave (2023–2026)

While the research line added self-control, the production line made retrieval
*engineerable*:
- **Frameworks** (LlamaIndex, LangChain, Haystack, DSPy) — 52.
- **Hybrid search + rerankers** became the default retrieval stack (13, 14);
  RRF (Cormack, Clarke & Büttcher, SIGIR 2009, k=60 [F]) as the fusion.
- **Contextual retrieval** (Anthropic, "Introducing Contextual Retrieval",
  Sep 19, 2024 [F: post fetched]) — index-time LLM descriptions: −35% / −49% /
  −67% top-20 retrieval failure for embeddings / +BM25 / +rerank
  (5.7%→3.7%→2.9%→1.9%, each step vs the 5.7% baseline). Deep dive: 40.
- **Evaluation discipline** — RAGAS (arXiv:2309.15217, EACL 2024 demo [F]),
  ARES (arXiv:2311.09476, NAACL 2024 [F]), golden datasets (46).

## The lineage map

```
TF-IDF (1988) ── BM25 (1994/95) ──────────────┐
                                              │  lexical half
word2vec → BERT → GPT ───────────┐            │
                                 │           (hybrid, 13)
DPR (2020) → Contriever (2022) → ColBERT (2020, late interaction)
REALM (2020) → RETRO (2022)          retrieval as a layer under the LM
                                 │
Lewis et al. RAG (2020, NeurIPS) ─┤  parametric generation + retrieved evidence
   "Naive RAG" (05)               │
HyDE (2023) ← query-side fix      │
Self-RAG (2024) / CRAG (2024) / Adaptive-RAG (2024)   ← learned control
RAPTOR (2024) / GraphRAG (2024)                 ← structure-based
IRCoT (2023)                                   ← interleaved reasoning
Frameworks (2023–) / Hybrid+rerank default / Contextual retrieval (2024)
                                              ← production stack
Gao et al. survey (2023, arXiv:2312.10997) names the three paradigms:
Naive / Advanced / Modular RAG [F]
```

## What the lineage predicts [I: the pattern, not a law]

1. **Every query-side trick (HyDE, multi-query, 15/16) composes with
   every index-side trick (chunking 10, contextual 40)** — the two lines
   never fought over the same knob.
2. **Learned control (Self-RAG/CRAG/Adaptive) is the most expensive
   improvement** — a second (or learned) call in the critical path — and the
   most easily earned back by a cheap router (54).
3. **Hybrid survived every dense-retriever generation** — the lexical half
   still wins on exact tokens (IDs, codes, names). That is a property of the
   *task*, not of the model generation (13).

## Key Takeaways
1. RAG = IR line (BM25 → DPR → ColBERT) × LM line (BERT → GPT), fused in
   2020 by Lewis et al. (arXiv:2005.11401, NeurIPS 2020).
2. Two post-2023 waves: learned retrieval control (Self-RAG, CRAG,
   Adaptive-RAG) and production stack (hybrid + rerank, frameworks,
   contextual retrieval).
3. The Naive/Advanced/Modular taxonomy is the Gao et al. 2312.10997 survey's,
   not a universal standard — 05 says what each stage actually means.
4. Every ID above was title-verified this pass; the commonly-wrong ones
   (2005.11409, 2009.0466, 2002.07992, 2403.10119, 2212.04064) are NOT RAG /
   DPR / REALM / Adaptive-RAG / RETRO.

## Related
[03 basic pipeline](03-basic-rag-pipeline.md) · [05 naive/advanced/modular]
(05-naive-advanced-modular-rag.md) · [06 IR foundations](06-information-retrieval-foundations.md) ·
[17 HyDE](17-hyde.md) · [20 RAPTOR](20-raptor.md) · [21 Self-RAG](21-self-rag.md) ·
[22 CRAG](22-corrective-rag.md) · [28 GraphRAG](28-graph-rag.md) ·
[40 contextual retrieval](40-contextual-retrieval.md) · [59 open questions](59-open-rag-research-questions.md)
