# Paged KV Cache (PagedAttention)
`LAST_UPDATED: 2026-08-26` · Status: deep-dive page · Foundational paper: [F: Kwon et al.,
"Efficient Memory Management for Large Language Model Serving with PagedAttention", SOSP 2023,
arXiv:2309.06180]

## 30-Second Explanation
Continuous (non-paged) KV allocation wastes 60–80% of HBM: a request's KV grows
dynamically and is preallocated at the max possible length, so most reserved space sits
empty and fragmentation grows with concurrency. **Paging** fixes it with the OS
virtual-memory trick: KV is cut into fixed-size **blocks** living in a shared **block
pool**; each request gets a **block table** mapping logical → physical blocks that are
allocated *on demand* as the request grows. Result: near-zero fragmentation (waste only
the tail of the last block) and, crucially, **shared physical blocks for shared prefixes**.

## Why it exists (the OOM / waste numbers)
- Pre-configured KV: vLLM v0.1 measured 60–80% waste without paging across their baseline
  workloads [F: paper]. The dominant driver: worst-case-length reservation and
  fragmentation across many concurrent variable-length requests.
- Paging reduces waste to ~4% (only the partial tail block per request) [F: paper / [E]
  geometry below].

## The mechanism
```
block pool (global):  [b0][b1][b2][b3] ... fixed-size KV blocks, each BLOCK_SIZE tokens
request A block table: logical 0→phys 7, logical 1→phys 2, ...
request B block table: logical 0→phys 7   ← SHARED if A and B share that prefix
```
- **Block** = `BLOCK_SIZE` tokens × all layers × KV heads of K and V. Storage grows
  only in whole blocks.
- **[E] size of one block (8B-class, BLOCK_SIZE=16, all 32 layers, BF16):**
  `2·32·8·128·2·16 = 2.0 MiB`. A block is the allocatable/addressable/movable unit.
- **Block table** = the per-request page table. **[E]** For a 128k request (8192 blocks,
  8 B/entry): ~64 KiB of table vs 16 GiB of KV — negligible.
- **Refcounts:** shared blocks (shared prefix) hold a reference count; freed only when
  the last request leaves.

## Fragmentation — the three kinds
1. **Internal:** partial tail block (≤ BLOCK_SIZE−1 tokens). BLOCK_SIZE=16 → ≤ ~1.5% of
   a fully-packed cache; the accepted price.
2. **External:** eliminated by the shared pool + on-demand allocation (blocks are
   allocated wherever free, not contiguously per request).
3. **Beam / cache-topology waste:** a request tree (beam search, branching agents) can
   share the trunk and fork per branch [F: paper — beam-search case]. Paging nails the
   trunk, but each branch still needs its own suffix blocks.

## Block size trade-off [I: synthesis, workload-dependent; measure]
- **Small blocks (16)**: fine granularity → less internal waste, better high-concurrency
  packing, cheaper eviction (evict a little). Cost: more table entries, more per-block
  metadata, and tables/kernels must chase more rows.
- **Large blocks (64+)**: fewer, coarser → cheaper bookkeeping, better attention-kernel
  efficiency (FlashAttention over longer contiguous spans). Cost: more internal waste,
  coarser sharing/eviction.
- Engines pick differently (vLLM 16, SGLang 64 [F: docs]) — a real design dimension, not
  an accident. SGLang pairs 64-wide blocks with its radix prefix tree (→
  `Prompt-and-Prefix-Caching.md`).

## Paged-aware attention kernels
The block table is consumed by the attention kernel itself, not the host: FlashInfer,
TRT-LLM-GEN and FlashMLA (DeepSeek) all support paged KV [F: vLLM docs]. The kernel walks
the block table and may skip blocks that are *not present* (i.e. the tail is partial and
past positions may be missing under eviction). This "block-level sparsity" is how
prefix-cache and eviction integrate with correct attention.

## Relationship to the rest of the stack
- **Shared blocks** are the physical substrate of *prefix caching* →
  `Prompt-and-Prefix-Caching.md`.
- **Blocks** are the unit of *placement* — a prefix hit means the same block IDs exist
  on the target replica → `Distributed-KV-Cache.md`, `Hierarchical-Offloading.md`.
- **Block-level eviction** (drop whole cold blocks) is the memory-manager's lever →
  `Eviction.md`.
- **MLA / MQA** shrink the KV per token, so fewer blocks per request →
  `Model-Architectures/Attention-Head-Designs.md`.

## Quantization interacts with paging
b∈{2,1} (BF16/FP8) changes bytes per block (2.0 MiB→1.0 MiB at 8B/16-token [E]) → 2×
blocks in the same HBM (→ this section README §KV Quantization). KV-dtype is an orthogonal
axis to block *count*.

## Open questions [I]
1. Optimal block size is workload-dependent — is it worth auto-tuning per workload?
2. Block-level sparsity under eviction: how much correctness loss does skipping absent
   blocks cost vs. full recompute of a trimmed region?
3. Variable-block sizing per layer (early layers pack tighter) — related to PyramidKV,
   see `Eviction.md`.

## Related
`Architecture-Overview.md` · `Prompt-and-Prefix-Caching.md` · `Eviction.md` ·
`README.md` (memory equation) · `GPU-Systems/vLLM.md` · `Serving-Engines/SGLang.md` ·
`GPU-Systems/FlashAttention.md` (kernel IO-awareness) ·
`Distributed-KV-Cache.md` (what we do with the blocks once paged).

## Key Takeaways
1. Paging cut KV waste from ~60–80% to ~4% and is the substrate for everything else.
2. The block is the unit of allocation, sharing, movement, and eviction — model it as such.
3. Block size (16 vs 64) is a real knob trading packing efficiency against kernel/table cost.
