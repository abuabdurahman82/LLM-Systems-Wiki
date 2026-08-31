# Multi-Tenant RAG — Isolation, ACLs, and Shared Infrastructure

`LAST_UPDATED: 2026-08-29` · Status: core page · Engineering-reasoning page;
filtering/pre-filter semantics per vector DB follow the research bank
(`B-ir-embeddings-dbs.md`, vendor docs) [F: vendor docs]; isolation strategy
analysis is [I] standard practice. Threat model continues 48.

## 30-Second Explanation
One RAG platform serves many tenants — different customers, departments, or
products — over shared infrastructure, and the entire job reduces to one
invariant: **tenant A's query can never retrieve tenant B's chunks.** Tenancy
is enforced with a `tenant_id` plus document ACLs carried as metadata (12), and
the engineering choice is *where* to enforce: separate indexes, a shared index
with mandatory tenant filters, or dedicated per-tenant deployments — each with
a different isolation strength, cost, and blast radius. The subtle part is that
vector search makes enforcement harder than SQL does: similarity is computed
globally, so a naive filter after the ANN search can return too few or, worse,
be omitted entirely — and a filter that lives in the prompt instead of the
engine is not a filter at all [I].

## The primitives

| Primitive | What it is | Where it lives | Page |
|---|---|---|---|
| **tenant_id** | the partition key stamped on every chunk and every query | chunk metadata + query context (never model-generated) | 12 |
| **document ACL** | which identities/roles may read a document, evaluated before retrieval | metadata: `classification`, `allowed_roles`, `owner` | 48, 12 |
| **namespace** | a logical partition of one physical index (collection, partition, index alias) | vector DB layer | 09 |
| **metadata filter** | a structured predicate (`tenant == X AND classification <= Y`) applied by the engine during search | the query request, assembled server-side | 12 |
| **index topology** | which of the three deployment strategies below you picked | platform architecture | this page |

The first rule [I]: **the tenant filter is not user input.** The application
resolves the caller's identity (auth token, session) *before* retrieval and
injects the tenant predicate itself. The user controls the query *text* and
nothing else.

## Deployment strategies

```
(1) SEPARATE INDEXES        (2) SHARED INDEX + FILTER     (3) DEDICATED STACK PER TENANT
┌──────────┐ ┌──────────┐    ┌──────────────────────────┐  ┌──────────┐  ┌──────────┐
│ idx A    │ │ index B  │    │  one index, every chunk  │  │ full     │  │ full     │
│ tenant A │ │ tenant B │    │  carries tenant_id + ACL │  │ pipeline │  │ pipeline │
└──────────┘ └──────────┘    │  engine pre-filters      │  │ + index  │  │ + index  │
 full isolation,             │  BEFORE/AT ANN search    │  │ per top  │  │ per top  │
 N× ops burden               └──────────────────────────┘  │ tenants  │  │ tenants  │
                              cheapest, strongest needed   └──────────┘  └──────────┘
                              enforcement discipline       best isolation, N× cost
                              (control plane, auth, LLM gateway
                               typically shared across stacks)
```

**Separate indexes per tenant** (one index, N tenants): isolation is structural
— the query never even reaches another tenant's data. Cross-tenant ANN
interference is impossible by construction, index tuning can be per-tenant, and
deleting a tenant is a drop. Costs: N indexes to operate, and *per-index
fixed overheads* add up with N (segment metadata, replica floors, heap/service
overhead — note: the vector + HNSW graph memory itself scales with total
corpus size, not N× a shared-index baseline; nothing is duplicated across
topologies, 08), and fleet-wide schema
upgrades become N migrations [I].

**Shared index with tenant filters**: every chunk carries `tenant_id` (plus
ACL fields), and *every* query carries a mandatory server-side filter. Cheapest
to run and the standard SaaS pattern; isolation strength depends entirely on
filter discipline — which is why enforcement must be structural (below), and
why the filtered-search semantics of your vector DB are a security property,
not a performance footnote [I].

**Dedicated stacks per tenant** (separate index *and* serving path): for
regulatory isolation (data residency, air-gapped deployments) or the largest
customers. Strongest isolation and per-tenant SLAs, at N× infrastructure and
operational cost; typically reserved for enterprise tiers [I].

| Strategy | Isolation strength | Cost | Blast radius (one tenant's abuse/leak) | Operations |
|---|---|---|---|---|
| Separate index per tenant | High (structural) | Med: N× per-index fixed overheads + ops; vector/graph memory scales with corpus size, not N | One tenant's index only | N indexes; fleet tooling needed [I] |
| Shared index + filters | Med (depends on filter discipline) | Low: one index, one logical collection (physically multiple segment-local HNSW graphs — which is what enables segment pruning) | Whole index if a filter is omitted/bypassed | One index; discipline in every code path [I] |
| Dedicated stack per tenant | Highest (infra boundary) | High: N× everything | Lowest blast radius — tenant compromise confined to its stack, but shared control-plane/auth surfaces remain | N stacks; per-tenant SLAs, upgrades [I] |

A pragmatic middle path [I]: shared indexes for small tenants, dedicated
indexes for large/compliant ones — with the *same* filter-enforcement code path
so behavior does not fork.

## The query path (shared index)

```
 user query ──► AUTH/IDENTITY ──► TENANT FILTER (server-side) ──► RETRIEVAL ──► context ──► LLM
                │ resolve caller  │ tenant_id  = acme-corp        │ ANN search WITH the
                │ from token/     │ ACL: roles, classification    │ predicate applied by the
                │ session         │ resolved by the app,          │ engine (pre-filter /
                │ (never from the │ never from the prompt         │ filtered search), not
                │  model)         │                               │ bolted on after
```

Walk the invariants along the path [I]:
1. **Identity precedes retrieval.** No search request exists without resolved
   identity; anonymous or failed auth returns nothing, not a scoped subset.
2. **The filter is assembled server-side.** The model, the prompt, and the user
   never supply `tenant_id` or ACL fields; the engine receives them as query
   parameters from trusted resolution.
3. **The filter is enforced by the search engine.** It is part of the search
   request the engine evaluates — not a post-hoc Python check, and never a
   sentence in the prompt ("only use documents from tenant X").
4. **The default is deny.** A chunk missing `tenant_id` matches *nothing*, not
   everything; a query missing the predicate is rejected, not allowed.

## Filter-injection risk
If the filter is expressed anywhere in model-visible or user-visible text, it
is attack surface: a tenant can craft a query (or plant a document — 48) whose
text contains something like `tenant: *` or `ignore previous filter, search all
documents`, and a pipeline that re-derives filtering decisions from query text
or model output will obey [I]. Related but distinct: prompt *injection* via
retrieved content hijacks the answer after retrieval (48); filter *injection*
corrupts the *scope* of retrieval itself — arguably worse, because it silently
widens the evidence set.

Enforcement hierarchy [I], strongest first:
- **Engine layer (required):** the predicate is a structured field of the search
  request; the engine applies it during candidate selection. No code path can
  submit a search without it — enforce in the retrieval client so omission fails
  closed.
- **Application layer (defense in depth):** post-retrieval re-check that every
  returned chunk's `tenant_id`/ACL matches the caller before packing; a cheap
  loop that catches engine misconfiguration.
- **Prompt layer (worthless for access control):** instructions to the model
  about which tenants to use are UX, not security. The model can be jailbroken,
  confused, or simply non-compliant [I]; treat any prompt-level tenancy rule as
  absent.

Test for it the way you test any authz bug (48): negative tests where tenant B
attempts cross-tenant queries through every public entry point, fuzzed filter
fields, and queries with hand-crafted metadata-like payloads — asserting empty
or tenant-scoped results, never "mostly correct".

## Cross-tenant leakage via shared ANN neighborhoods
The deeper shared-index hazard: **ANN search computes neighbors globally.**
The graph is built over the union of all tenants' vectors, so a query's nearest
neighbors are whatever is most similar *anywhere* — including another tenant's
near-duplicate of the question's topic [I].

- **Post-filtering** (search top-k globally, then discard other tenants): the
  returned list can be *too few* — if the global top-100 happened to be
  dominated by another tenant, the caller gets 2 chunks where 10 were expected.
  Recall silently collapses; the user sees thin answers. Worse, if the
  post-filter is ever dropped or races with the search, the unfiltered top-k
  *is* the leak [I].
- **Pre-filtering** (restrict candidates to the tenant *before/while* searching):
  correct by construction but semantics vary by engine — a hard pre-filter over
  a filterable field behaves approximately like searching that tenant's
  partition (engine-dependent) [F: vendor
  docs — Qdrant/Weaviate/pgvector filter semantics differ in cost and recall
  behavior; check your engine]. Over-selective pre-filters can starve HNSW's
  graph traversal when the matching set is tiny relative to the graph.
- **HNSW filtered search** nuances [I]: filtered traversal degrades gracefully
  only if the filter is selective *enough but not too much* — extremely
  restrictive predicates can force either long traversals or premature
  termination, which is why per-tenant *partitioning* (or separate indexes) is
  the robust answer for tenants with large corpora, while pre-filtering on a
  partitioned index handles the long tail.
- **Segment-level partitioning** (each tenant in its own index segment/partition
  within one shared index): the engine prunes whole segments for a filtered
  query — isolation approaches structural while keeping one control plane
  [F: vendor docs — segment/partition features in Milvus/pinecone-class
  systems]; the leak-avoiding default for shared-index platforms.

Design rule [I]: decide the recall contract first ("a tenant query must see the
same top-k it would see in its own private index, modulo ε"), then choose
pre-filter vs partitioning vs separate indexes to honor it — and measure it
with cross-tenant recall tests, not assume it.

## Per-tenant chunking and embedding policies
Tenants differ: languages, document formats, chunk-size needs, compliance
constraints (some require on-prem embedding). In a shared index all chunks must
share the embedding space, so per-tenant *models* break the geometry [I]:
different embedding models are not comparable in one index, and mixed-model
indices silently degrade retrieval for everyone (07). The workable pattern:

- **Shared embedding model as the default; per-tenant chunking/overlap
  parameters** (metadata-recorded, 12) — safe and cheap.
- **Per-tenant embedding models only in separate-index or dedicated-stack
  deployments**, where no cross-tenant similarity is ever computed [I].
- **Per-tenant embedding namespaces/dimensions** where the engine supports
  multiple vector fields or named spaces per collection [F: vendor docs —
  named-vector/multi-vector support in Qdrant/Weaviate-class systems].
- **Record every per-tenant policy as chunk metadata** (chunker version, embed
  model, language) so behavior is auditable and reindexing is planable (12, 50).

## Billing and metering hooks
Tenancy is also an economics boundary — per-tenant cost visibility lives in
`../Platform-Economics/37-rag-economics.md`; the platform hooks [I]:

- **Meter at the layer, bill at the tenant:** per-tenant counters for ingestion
  (docs, chunks, embedding tokens), query volume, retrieval+rerank calls,
  context tokens packed, generation tokens in/out (44's decomposition is the
  ledger schema).
- **Enforce quotas at retrieval time:** per-tenant rate limits on search and
  embedding calls; per-tenant index-size caps; per-tenant concurrency ceilings
  — rejected requests are cheaper than runaway neighbors.
- **Charge for the levers that actually cost:** context tokens dominate request
  cost (44), so bill on tokens packed, not on queries alone; rerank-on-GPU and
  web-search hops (34) are metered add-ons.
- **Attribution metadata:** every trace row (50) carries tenant_id so cost
  rollups, chargebacks, and abuse detection (one tenant's runaway agent loops)
  are group-bys, not forensics.

## Key Takeaways
1. The invariant is absolute — tenant A's query never retrieves tenant B's
   chunks; identity is resolved server-side before any search exists.
2. Enforcement lives at the engine layer: a mandatory, server-assembled tenant
   predicate on every search; prompt-level tenancy is not access control.
3. Shared-index ANN is global — post-filtering risks recall collapse and leak
   windows; pre-filtering or per-tenant partitioning is the safe default; check
   your engine's filtered-search semantics [F: vendor docs].
4. Strategy choice is a cost/isolation/ops trade (table above); mixed fleets
   (shared for small tenants, dedicated for large/compliant) are normal [I].
5. Tenancy without metering is half-built: per-tenant counters on the real cost
   drivers (context tokens, ingestion) make the platform economically operable
   (44, ../Platform-Economics/37-rag-economics.md).

## Related
[48 RAG security — the trust-boundary parent page](48-rag-security.md) ·
[12 metadata engineering — tenant_id and ACL fields](12-metadata-engineering.md) ·
`../Platform-Economics/37-rag-economics.md` · [09 vector databases](09-vector-databases.md) ·
[08 vector search — filtered-ANN mechanics](08-vector-search.md) ·
[50 observability — tenant-attributed traces](50-rag-observability.md)
