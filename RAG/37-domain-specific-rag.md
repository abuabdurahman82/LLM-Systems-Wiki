# Domain-Specific RAG — When "General" Stops Being Good Enough

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
all domain claims are [I] (standard practice) unless a system/paper is cited.

## 30-Second Explanation
A RAG pipeline built on defaults (general embedder, fixed chunks, one index,
generic evaluation) works *surprisingly well* until the domain bites: legal
cites, medical entities, code symbols, error codes, citations-with-precedent,
numbers-that-must-be-exact. Domain-specific RAG is the practice of
**specializing each pipeline stage to the domain's failure modes** — usually
the embedder, the chunking, the metadata, and *above all* the evaluation —
before touching the exotic architecture. The order matters: domain adaptation
of the boring stages almost always beats architecture exotica (54).

## The domains, and what they actually need
| Domain | What breaks with defaults | Domain specialization |
|---|---|---|
| **Legal** | citation precision (a case cite is an exact string, not a meaning), jurisdiction/version sensitivity, long argumentative structure | exact-match hybrid (13) over citations; version + jurisdiction metadata (12); chunk = argument unit (issue→holding→rationale), not paragraph; golden set = real case queries with expected citations |
| **Healthcare** | entity precision (drug/gene/protein names, dosages), terminology variants (SNOMED vs lay terms), high-stakes wrong answers | domain embedder or medical term normalization; structured entity retrieval (30) for clinical data; strict faithfulness + citation policy (45); evaluation with domain experts (46) |
| **Finance** | numbers must be exact (a "≈" is a liability), recency (markets move), regulatory language | structured RAG for the data (30); document RAG for reports/MD&A with as-of stamps (35); golden set dominated by numerical-accuracy cases; high-verification default (51) |
| **Engineering/infra** | part numbers, error codes, config keys (exact tokens); multi-hop "component A drives failure in B" | hybrid + rerank (13/14); symbol/code-aware retrieval when code-adjacent (38); multi-hop patterns (26) for failure chains; graph for topology-heavy questions (28) |
| **Code** | structure is meaning (see 38 in full) | the whole 38: AST chunking, symbol index, call graph, code embedder |
| **Cybersecurity** | fast-changing IoCs/advisories, exact CVE identifiers, alert correlation | streaming ingestion for advisories (35); exact-token hybrid for CVEs; event correlation is structured (30); source-trust tiers heavy (48) |
| **Research/academic** | citation graphs, methodology precision, long-form synthesis | citation-aware retrieval (cite + cited co-retrieved, [I: the standard trick]); section-aware chunking; GraphRAG for corpus-sensemaking questions (28); evaluation with known-answer sets (46) |
| **Customer support** | high volume, product/version mismatch (answers for v2 must not serve v3), tone policy | version + product metadata with hard filters (12); small-k + fast rerank (latency SLO); answer-policy enforcement (51); evaluation = resolution rate, not just retrieval recall (45) |

## The five specialization levers (in the order that pays)
1. **Evaluation first** (46): the domain's golden set is what tells you which
   stage to specialize. A legal set will show retrieval-miss on exact
   citations; a medical set will show faithfulness failures; a support set will
   show version-mismatch. Specialize what the set exposes.
2. **Embedding model** (07): a domain-tuned embedder (legal, medical, code,
   multilingual) routinely beats a general one *on that domain's set* [I: the
   consistent finding across the domain-embedding literature — measure on your
   set, don't assume]. The change is cheap (re-embed the corpus once) and the
   win is at the most upstream stage.
3. **Chunking** (10): the domain's semantic unit. Legal: argument units.
   Medical: paragraph + entity context. Code: symbols. Support: article + FAQ
   pair. The general 512-token window is the one thing the domain set will
   almost certainly argue against.
4. **Metadata** (12): the domain's filters. Jurisdiction/version/tenant/
   classification/term-taxonomy. Domain RAG without domain metadata is
   general RAG with a costume.
5. **Retrieval architecture** (13/14/18/26/28): hybrid + rerank is the base
   layer; the domain adds multi-hop (failure chains, cross-references),
   graphs (precedent/topology/citation networks), parent-child (section
   context). This is where the 54 decision tree applies — *after* 1–4, not
   instead of them.

## The anti-pattern: domain cosplay
Applying a domain's *architecture* without its *evaluation* is the recurring
failure [I]: "we are in healthcare, therefore GraphRAG + agentic + 20 chunks"
— with no domain golden set, no version metadata, no faithfulness policy.
The architecture inherits nothing of the domain's actual failure modes, and
the cost/latency/complexity is paid in full. The discipline: every domain
specialization is a hypothesis ("legal citation queries fail retrieval
because…") tested on the domain set (45/46), and paid for only when it
measures.

## Key Takeaways
1. Domains break defaults at *specific* stages — the domain's golden set
   (46) tells you which; specialize that stage.
2. The order that pays: evaluation → embedder → chunking → metadata →
   architecture. Cheap levers first.
3. Domain embedders win upstream; version/term metadata is where support and
   finance stop serving wrong-version answers.
4. Exact-token domains (legal cites, CVEs, part numbers) need the lexical
   half of hybrid (13) — dense-only fails there.
5. Domain cosplay (exotic architecture, no domain evaluation) is the
   anti-pattern; every specialization must measure on the set.

## Related
[07 embeddings](07-embedding-engineering.md) · [10 chunking](10-chunking.md) ·
[38 code RAG](38-code-rag.md) · [46 golden datasets](46-rag-golden-datasets.md) ·
[54 decision tree](54-which-rag-should-i-use.md) · [45 evaluation](45-rag-evaluation.md)
