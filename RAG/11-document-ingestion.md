# Document Ingestion — Parsing, Structure, and Why Bad Parsing Kills Good Retrieval

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
format-specific guidance is [I] unless a tool's behavior is cited from docs.

## 30-Second Explanation
Retrieval can only find what ingestion preserved. The pipeline is:
document → parser → structural extraction → cleaning → chunking → metadata →
index. Every format carries structure (headings, tables, figures, code
blocks) that a *structure-aware* parser keeps and a *text-dump* parser
destroys. The central claim of this page: **bad parsing makes even excellent
retrieval fail** — if the table's cells are interleaved, the chunk's embedding
is garbage, and a dense-only ANN index can fail to surface "the Q3 revenue
figure" from a chunk that contains it in scrambled order.

## The pipeline
```
Document (any format)
   ↓ Parser (format-specific)
Raw text + structure (headings, tables, figures, code, order)
   ↓ Structural extraction (what is a section? a table? a figure?)
   ↓ Cleaning (dedup, boilerplate, encoding, ligatures, whitespace)
   ↓ Chunking (10 — structure-aware where possible)
   ↓ Metadata (12 — source, page, section, tenant, classification, version)
   ↓ Index
```

## Format by format
| Format | What's easy | What's easy to break | Parser strategy [I] |
|---|---|---|---|
| **PDF** | text layers on born-digital PDFs | scanned pages (no text layer → OCR), two-column layout interleaving, tables as positioned text, headers/footers repeated on every page, figure text | layout-aware parsers (e.g. PDF→markdown tools that reconstruct reading order); OCR only for scanned content; strip running heads |
| **HTML/web** | semantic tags (`<h1>`, `<table>`, `<article>`) | boilerplate (nav, footer, cookie walls), JS-rendered content invisible to static fetch, CSS-hidden text, infinite scroll | read semantic tags, drop nav/aside; headless render for JS-heavy sites (34) |
| **Markdown** | explicit structure (headings, fences, tables) | very long files, nested structure that defeats flat chunkers | the best source format for RAG — chunk by heading hierarchy |
| **Word (.docx)** | headings via styles, tables | embedded objects, headers/footers, section breaks, text boxes (floating text is unordered) | extract in document order; keep heading style→chunk boundary mapping |
| **PowerPoint** | slide boundaries | notes vs slide text, speaker notes with the real context, dense bullet slides where one bullet is a whole topic | treat a slide as a chunk candidate; index notes with the slide |
| **Spreadsheets** | cells have addresses | merged cells, multiple sheets, formula *results* vs *formulas*, very wide tables that are better as rows | decide the unit: row-as-chunk (one record) vs sheet-section; carry column headers into every chunk (a row without its header is "42") |
| **Email** | sender/date/subject | threads (replies repeat previous content), signatures, CC lists, PII | thread-aware ingestion (dedupe quoted text); subject + thread id as metadata; PII screening (48) |
| **OCR / scanned** | — | everything: layout, tables, handwriting, low resolution | modern document-OCR (layout + table detection), then treat as PDF; quality gate: sample pages for OCR error rate [I] |
| **Tables (any format)** | — | reading order (row-major vs column-major interleaving), multi-row headers, merged cells | extract tables as *structured units* (markdown table or JSON), never as interleaved text; index row-wise with headers attached |
| **Figures/diagrams** | — | the *information* is in the image; the caption may be the only text | render/OCR the figure OR caption-index it; multimodal embeddings where available (31); never silently drop |
| **Code** | syntax structure | long files, minified files, generated code (vendored libs) | AST/structure-aware chunking (38): function/class as unit, not line windows |
| **JSON/structured** | schema | nested payloads, huge documents, naive whole-document indexing of nested JSON | usually not chunked at all — go to structured RAG (30) instead of similarity search |

## Why parsing quality dominates what people think
Three failure patterns, in increasing order of subtlety:
1. **Content loss**: figure text, table cells, scanned pages never enter the
   index → the answer is *not in the corpus*. No retrieval fix exists; the
   failure shows up as "relevant document not indexed" (47).
2. **Order loss**: two-column PDF → column 2 of page N interleaved with column
   1 → sentences from two topics in one chunk → embeddings average the two
   topics → retrieval miss or context confusion.
3. **Metadata loss**: the parser doesn't record page/section/URL → chunks are
   un-citable and un-filterable → no ACLs, no "which page", no versioning
   (12). A retriever without provenance is a liability, not an asset.

Detection is cheap: **ingest-audit sampling** — take 20 known-good documents,
run the pipeline, and eyeball the extracted text + table fidelity; track a
parse-error rate per format [I: the standard pre-flight check; run it on every
parser/model upgrade, because these parsers change silently].

## Layout-aware parsing: what it buys
Modern document-OCR and layout models (e.g. the PDF→markdown tooling family)
*attempt to* recover reading order, table grid, and figure regions — with
varying fidelity; table-grid recovery in particular remains error-prone and
tool-dependent [I: tool behavior, not cited from a specific vendor doc — the
page's header rule would make this a tool claim, so it is tagged]. The payoff is
exactly the two failure classes above: correct order + intact tables. Cost:
latency and
per-document GPU/OCR spend at ingestion time — which is fine, because ingestion
is the *offline* half of the pipeline (03): you pay it once per corpus update,
not per query. Rule [I]: spend on parsing where content is lossy (scans,
tables, figures); stay with fast plain-text extraction where it is proven lossless
(plain text, clean Markdown).

## Key Takeaways
1. Ingestion is offline engineering with online consequences: garbage in,
   garbage retrieved, forever (until reindex).
2. Tables, figures, and scanned content are the loss points; structure-aware
   parsing + multimodal coverage (31) is the fix.
3. Keep provenance (page, section, source, version) at parse time or lose
   citations, ACLs, and versioning (12, 48).
4. Run an ingest-audit on 20 sample docs after every parser change.
5. PDFs are the hard case; Markdown is the easy case — when you control the
   source, make it Markdown.

## Related
[03 pipeline](03-basic-rag-pipeline.md) · [10 chunking](10-chunking.md) ·
[12 metadata](12-metadata-engineering.md) · [30 structured RAG](30-structured-data-rag.md) ·
[31 multimodal](31-multimodal-rag.md) · [34 headless/JS rendering](34-web-rag.md) ·
[38 code](38-code-rag.md) · [47 failure: not indexed](47-rag-failure-modes.md) ·
[48 PII/security](48-rag-security.md)
