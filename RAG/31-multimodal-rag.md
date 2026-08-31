# Multimodal RAG — Retrieval Over Text, Images, Tables, and More

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
model capabilities are [I] unless a system is cited.

## 30-Second Explanation
A real document is not text: it has figures, tables, diagrams, photos, and
often audio/video. **Multimodal RAG** retrieves across *all* of it — a
"retrieval" that finds "the architecture diagram in section 4" or "the table
with Q3 margins" needs the non-text content indexed, addressable, and
retrievable. The pattern is the same as text RAG (the 03 pipeline extended to
non-text modalities): parse → represent → index → retrieve → pack (in a
modality the generator can read) → answer. The new problems: how to
*represent* each modality for retrieval, and how to *pack* it so the
generator actually uses it.

## The modalities and their retrieval representations
| Modality | Ingestion/representation | Retrieval mechanism | Packing into context |
|---|---|---|---|
| **Text** | plain/structured text (11) | text + embeddings (07/13) | native |
| **Images (photos/diagrams)** | caption (vision model), OCR text, metadata | multimodal embedding (image↔text) OR caption/text retrieval; region-level for dense docs | the image itself (vision LLM) or caption+OCR text |
| **Tables** | structured extraction (markdown/JSON, 11) | row-as-chunk with headers attached; column-aware queries (30 when tabular) | markdown table in context (models read these well) or summary + key rows |
| **Figures with labels** | label extraction + caption | text retrieval over labels/captions; multimodal embedding over the rendered figure | image + labels |
| **Audio** | transcription (ASR) | text retrieval over the transcript; timestamps as metadata | transcript excerpt + timestamp |
| **Video** | keyframes (captions) + transcript (ASR) + segments | text retrieval over segment transcripts; multimodal over keyframes | transcript + keyframe image(s) |
| **Charts** | OCR of data labels + caption; optionally structured data extraction | text (labels/caption) or the underlying data via 30 | image + extracted data points |

The unifying design: **every non-text item gets a text projection** (caption,
transcript, OCR, structured extraction) *plus* optionally a **multimodal
embedding** that places images and text in a shared space. Text projection
alone (captions + transcripts) covers most of the value cheaply [I];
multimodal embeddings add "find the image that *looks like* this" capability
at the cost of a second index and a second retrieval path.

## The multimodal embedding question
Text-only RAG embeds text. Multimodal RAG needs one of:
1. **Cross-modal via projection**: embed the image's *text projection* (caption
   + OCR) with a text model — cheap, strong when captions are good (which
   requires a good captioner at ingestion), weak for visual-only content.
2. **Joint-space models**: paired (dual-tower) encoders — a text encoder and
   an image encoder, trained (contrastively) so their outputs land in one
   shared vector space (CLIP-class; the vision-embedding model families) —
   "similar image" and "image matching text" both work; the index is one more
   vector store (09) with mixed-type vectors.
3. **Dual-path retrieval**: text retrieval over projections + multimodal
   retrieval over the joint space, fused (RRF-style, 13) — the production
   default for document corpora with real figures [I].
Which to use is a corpus decision: a diagram-heavy engineering corpus wants
(2)/(3); a report corpus with decent captions is well served by (1) + table
extraction.

## The packing problem: what does the generator see?
The generator's modality determines the packing:
- **Vision LLM**: pack the actual image(s) + surrounding text; the model reads
  the figure natively. Cost: image tokens (an image is hundreds–thousands of
  tokens depending on resolution/tile strategy [I]) — image-heavy answers get
  expensive fast (44).
- **Text-only LLM**: pack the text projection (caption + OCR + labels) +
  "figure reference" (source, page, figure id). The model cannot *see* the
  figure — the projection must carry the information (or the answer says "see
  figure 4.2, p. 21" and the UI renders the image).
The hybrid: text projection in context for reasoning, image rendered in the
UI for verification [I: the common pattern — the citation is clickable to the
actual figure].

## Tables: the quietly hard modality
Tables fail text RAG in two distinct ways [I]: (1) *extraction* — a table read
as interleaved text is garbage (11: the parser must output structured form);
(2) *retrieval granularity* — a 40-row table as one 3K-token chunk retrieves
for everything and dilutes for nothing. The pattern: index **row-as-chunk with
headers attached** (each row chunk carries the column headers, so a value "42"
becomes "Region=EU, Quarter=Q3, Revenue=42"), retrieve row-chunks, and
**re-assemble the table**
at pack time from the parent table id (the parent-child pattern, 18, applied to
tables). When the table *is the data* (a financial statement), the structured
path (30) beats the similarity path.

## Audio/video: the timestamp is the retrieval key
For ASR transcripts, the chunk carries `timestamp` metadata; retrieval is text
retrieval over transcript chunks; the answer cites a timestamp ("04:12–04:30 of
the meeting"), and the UI can deep-link. Video adds keyframes: a keyframe is a
*visual chunk* with a timestamp and caption — retrieved like an image, packed
like an image. The failure mode is *segmentation*: a 2-hour video chunked by
time, not by topic, produces chunks that cross subject boundaries —
transcript-aware segmentation (topic change detection) is the multimodal analog
of 10's structure-aware chunking [I].

## Failure modes specific to multimodal
1. **Silent drop**: the parser skips figures (11's loss class) → "the diagram"
   questions are unretrievable; ingest-audit (11) must include figure
   coverage.
2. **Caption gap**: the caption says "Figure 5: Results" and the information
   is in the plot → caption-only retrieval misses; OCR + chart extraction or
   a vision model is required.
3. **Wrong-modality packing**: text-only LLM + "see figure 4.2" but the figure
   is not rendered in the UI → the user cannot verify the claim.
4. **Cost explosion**: image-token pricing makes naive "send all figures"
   unaffordable — select 1–3 figures per answer, budget them (44).
5. **Table re-assembly drift**: row-chunks retrieved from two different tables
   get mixed in context — the packer must group by `table_id` (parent-child
   discipline, 18).

## Key Takeaways
1. Multimodal RAG = text RAG + a text projection for every non-text item +
   (optionally) a joint-space index; the projection covers most of the value
   cheaply [I].
2. Dual-path retrieval (text over projections + multimodal over joint space,
   fused) is commonly the production default for figure-heavy corpora [I].
3. Pack by the generator's modality: vision LLM gets images, text LLM gets
   projections + a rendered reference in the UI.
4. Tables: extract structured, index row-with-headers, re-assemble by parent —
   or go structured-data RAG (30) when the table is the data.
5. Audio/video retrieve over transcripts with timestamps as the citation key.

## Related
[11 ingestion](11-document-ingestion.md) · [18 parent-child](18-parent-child-rag.md) ·
[30 structured](30-structured-data-rag.md) · [38 code](38-code-rag.md) ·
[44 economics](44-rag-economics.md) · `../Multimodal/README.md`
