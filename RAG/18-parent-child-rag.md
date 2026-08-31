# Parent-Child Retrieval — Small for Precision, Big for Context

`LAST_UPDATED: 2026-08-29` · Status: core page · Pattern claims [I]; the
two-tier structure generalizes to tables (31) and code (38).

## 30-Second Explanation
There is a standing tension in chunking (10): *small* chunks retrieve with
precision (a focused topic embeds sharply) but return too little context;
*large* chunks return context but embed as blurry topic averages.
**Parent-child retrieval** splits the two jobs: **embed the children** (small,
focused chunks — the retrieval unit), **return the parent** (the larger section
that contains the matched child — the context unit). Search is precise; the
context the LLM receives is complete.

## The structure
```
Document
  ├── Parent A (e.g. a section, ~1–2K tokens)
  │    ├── child 1 (~256 tok)  ← embedded
  │    ├── child 2 (~256 tok)  ← embedded
  │    └── … (illustrated with 3; a 1–2K parent typically holds ~4–8 of them)
  │
  └── Parent B
       ├── child 4
       └── child 5
```
```
query → embed → ANN over CHILDREN → top child(ren)
      → map child → parent id (metadata)
      → return the PARENT(S) (dedup: one copy per parent even if 2 children hit)
      → pack parent text → LLM
```
The mapping is a metadata field on every child: `parent_id` (and, for deeper
hierarchies, `grandparent_id` — 19). The retrieval is over children; the
*return* is over parents.

## Why it works (the two failure modes it fixes)
1. **Context starvation**: the right *fact* is in child 3, but the child alone
   lacks the surrounding explanation ("it" has no antecedent, the definition is
   in the section intro, the caveat is in the next paragraph). Returning the
   parent restores the span [I: the 10 "answer-span fit" property, enforced
   structurally].
2. **Retrieval dilution**: a 2K-token section as the embedding unit averages
   its topics; the embedding sits between its sub-topics and matches weakly to
   all of them. Embedding the 256-token children keeps each embedding
   sharp — the *retrieval* granularity is fine, the *delivery* granularity is
   coarse [I: the separation is the whole trick].

The same pattern appears in three guises:
- **Tables** (31): rows are the children, the table (with headers) is the
  parent.
- **Code** (38): symbols are the children, the file/module region is the
  parent.
- **Sectioned docs** (the default): paragraphs/sentences embed, sections
  return.

## Design parameters
| Parameter | Default [I] | Rationale |
|---|---|---|
| Child size | 128–512 tok | small enough to embed sharply; ≥1 sentence of head coverage (10) |
| Parent size | 1–4K tok | big enough for answer-span; cap *below* 4K when packing top-10 parents — 10 × 4K = 40K tok exceeds a tight retrieval/packing budget (see Failure mode 1, 44) |
| Return policy | top-1 child → its parent; top-N children → up to M *distinct* parents (M < N) | dedup keeps the context from being 3× the same section |
| Overlapping parents | a child belongs to exactly one parent (no overlap at the parent boundary) | overlap is a *child-level* concern (10); parent dedup is by id |
| Parent metadata | carries the parent's section heading + doc/page metadata | the packed context keeps structure ("§4.2 Results: …"), improving both retrieval attribution and citation (45) |

## Failure modes
1. **Parent too big**: top-10 parents at 4K tok = 40K tok of context — that
   fits a 128K–200K model window, but it *can* blow a tight retrieval/packing
   budget (the few-K-token passage allocation a serious system keeps reserved
   for the LLM's own reasoning and other context; 44), and it is back to
   context pollution either way. Fix: cap M, compress parents (41), or size
   parents to the median answer span (measure on 46).
2. **Wrong-parent mapping**: the child is at a section *boundary* and was
   assigned to the wrong parent (the fact's context is in the *other*
   section) → you return the wrong context. Fix: boundary-aware splitting
   (10), or a small context-prefix on the child itself (the 40 trick at child
   granularity).
3. **Parent duplication across queries**: the same parent returned by two
   different queries in a multi-query loop (16) — the merge must dedup by
   parent id, not child id.
4. **Retrieval precision lost**: if the children are *too* small (<1 sentence
   of head coverage), the sharp embedding is of a fragment, not a topic —
   precision degrades back toward the small-chunk failure (10).
5. **Index doubling**: you embed children *and* store parents — the index is
   the children, the *store* is the parents; make sure the retrieval path
   never accidentally searches parent embeddings (a common miswiring: two
   indexes, one query).

## When parent-child is the right move
- Corpus with clear section structure and answers that span more than one
  paragraph (docs, wikis, reports, contracts) [I: the default case for
  enterprise text].
- Table/code-heavy corpora (31/38) — the structural analog is stronger.
- When your golden set (46) shows *context-starvation* failures: the right
  chunk is retrieved but the answer needs its surroundings.
It is *less* valuable when: chunks are already self-sufficient (FAQ-style
corpora, 37's support case), or you are using contextual retrieval (40) to fix
the head-coverage problem at the embedding level — the two patterns overlap,
and a corpus often needs neither, both, or one (measure, don't assume).

## Key Takeaways
1. Two granularities, two jobs: children embed (precision), parents return
   (context). The `parent_id` metadata field is the whole mechanism.
2. It fixes context starvation without paying the dilution cost of big
   embedding units.
3. Cap the *distinct* parents packed (M < N) — parent dedup is by id, not by
   child hit.
4. Size parents to the median answer span; 4K × 10 parents *can* blow a tight
   packing budget even on large-window models.
5. The pattern generalizes: rows/tables (31), symbols/files (38); and it
   composes with contextual embedding (40) — use what your set (46) shows.

## Related
[10 chunking](10-chunking.md) · [19 hierarchical](19-hierarchical-rag.md) ·
[31 multimodal (tables)](31-multimodal-rag.md) · [38 code](38-code-rag.md) ·
[40 contextual retrieval](40-contextual-retrieval.md) · [41 compression](41-context-compression.md)
