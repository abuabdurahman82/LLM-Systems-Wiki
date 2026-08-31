# Code RAG — Retrieval Over Repositories, Not Text

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
structure-aware chunking patterns are [I] unless a tool is cited.

## 30-Second Explanation
Code is the clearest example of a document type where *structure is the
meaning* (HTML/JSON/tables are also structure-as-meaning, but code's structure
— symbol, body, signature, docstring — is also its *semantics*):
a unit of behavior, a class is a unit of responsibility, an import declares
what a file needs. Chunking a repository into 512-token windows slices
*large* functions in half and orphans docstrings at window boundaries (the
median ~20–50-line function, ~150–400 tokens, usually survives a window
whole). Code RAG (the retrieval layer
under coding agents — `../Agents/Coding-Agents.md`) replaces text chunking with
*code-aware retrieval*: AST/symbol boundaries, call graphs, and repo
structure. It is also where RAG meets the highest-stakes consumer of evidence:
an agent that writes and runs code.

## What a repository actually contains
| Unit | Retrieval unit | Why |
|---|---|---|
| **Symbols** (functions, methods, classes, interfaces) | the unit | behavior lives here; docstring + signature + body belong together |
| **Files** | context unit (a locator, not the pack) | a file is the natural "parent" (18): retrieve symbol, reference the file region for context — the *pack* is symbol + docstring + imports (not a raw file fragment, 18) |
| **Modules / packages** | scoping unit | "where is auth handled?" is a module question |
| **Imports / dependencies** | edges | what this file needs — the cheapest multi-hop signal |
| **Call graph** | edges | "who calls this?" / "what does this call?" — retrieval as graph traversal |
| **Git history** | provenance | who changed this and why (blame + commit messages) |
| **Docs / README / CHANGELOG** | intent | the *why* that code does not say |
| **Tests** | specification | what behavior is *expected* — often the best spec available |
| **Build / config** | environment | what this repo actually is (framework, versions) |

## Text chunking vs code-aware retrieval
| Dimension | Text chunking (512 tok) | Code-aware |
|---|---|---|
| Unit | arbitrary window | symbol (function/class), complete |
| Boundaries | mid-function, mid-docstring | AST: signature→body, docstring attached |
| "Where is X?" | similarity over fragments | symbol index (fuzzy symbol match + structure) |
| "Who calls X?" | misses (the call sites are text, not similar) | call-graph traversal |
| "What changed here?" | misses | git history join |
| Precision | low (a 512-tok window of a 2000-line file ≈ noise) | high (symbol ± neighborhood) |
| Cost | one embedding per window | embeddings + symbol index + optional graph build |

The empirical pattern behind the gap [I]: code questions are mostly
*symbol-anchored* ("the `RetryPolicy` class", "the /v1/chat completions
handler"). A symbol index (fuzzy match on names + path) answers the *anchor*
part with high precision (fuzzy name matching is strong but not near-perfect:
same-name symbols across packages in a monorepo, test mocks, generated code);
embeddings answer the *semantic* part ("the
thing that does exponential backoff"); call/import graphs answer the
*relational* part ("who uses it"). Production code retrieval stacks all three
—that is why coding agents are simultaneously "vector RAG + symbol search +
graph traversal + agentic iteration" (24).

## The code-aware pipeline
```
Repository
   ↓ Parser (tree-sitter / language server) — AST per file
   ↓ Symbol extraction (name, signature, docstring, location, imports)
   ↓ Embedding (per symbol + per file, NOT per arbitrary window)
   ↓ Optional graph build (calls, imports, inheritance)
   ↓ Query:
   │    symbol-anchored?  → symbol index (fuzzy) → symbol + file region
   │    semantic?         → ANN over symbol embeddings → top symbols
   │    relational?       → graph traversal (callers/callees, dependents)
   ↓ Context pack: symbol + docstring + imports + (test if exists) + git note
   ↓ LLM / coding agent (with the repo's own docs as secondary evidence)
```

## Domain-specific details (code is a domain, 37)
- **Embedding model**: general text embedders under-weigh identifiers;
  code-tuned embedders (code-trained, e.g. the code-embedding model families)
  improve semantic code search measurably [I: standard practice in coding
  tools; verify per model with your golden set (46)].
- **Chunk size**: symbols, not tokens — a 30-line function with its docstring
  is one chunk even at only ~250–300 tokens (code tokenizes at roughly 8–12
  subword tokens/line — a 30-line function + docstring); a 400-line class is
  retrieved by member,
  with the class as parent (18).
- **Repo scale**: monorepos need module-level routing first (which package?)
  before symbol search — a two-stage retrieval that mirrors 19's hierarchy.
- **Git as evidence**: "why does this exist?" is answered by commit messages +
  PR descriptions — index them as documents linked to symbols (provenance the
  LLM can cite).
- **Security**: repositories are high-value targets; the same ACL/tenancy
  discipline applies (48/49), and code execution by the consuming agent is a
  harness concern with its own threat model (`../Agents/Coding-Agents.md`,
  `../Safety/README.md`).

## Key Takeaways
1. In code, structure *is* meaning: symbol/AST boundaries beat text windows.
2. Three retrieval signals, stacked: symbol index (anchor), embeddings
   (semantics), call/import graph (relations).
3. The context pack is symbol + docstring + imports + test + git note — not a
   file fragment.
4. Code-tuned embedding models and per-repo golden sets are the domain
   specializations that matter (37, 46).
5. Code RAG is the retrieval layer under coding agents — its failure modes are
   agentic failure modes (24, 47).

## Related
[37 domain-specific](37-domain-specific-rag.md) · [24 agentic](24-agentic-rag.md) ·
[18 parent-child](18-parent-child-rag.md) · [36 federated (code as one source)](36-federated-rag.md) ·
`../Agents/Coding-Agents.md` · `../Safety/README.md`
