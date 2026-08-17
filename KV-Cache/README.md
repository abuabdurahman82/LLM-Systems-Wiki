# KV-Cache
`LAST_UPDATED: 2026-08-16` · Status: core section

## 30-Second Explanation
The KV cache stores, for every processed position, the Key and Value vectors of every
layer. It turns decode from O(S²) recompute into O(1) append + O(S) read — and becomes the
dominant HBM consumer at long context / high concurrency.

## The Memory Equation (the one to remember)
```
KV bytes = 2 · L · B · h_kv · d_h · S · b
```
- L = layers · B = batch · h_kv = KV heads (GQA/MQA reduce this) · d_h = head dim ·
  S = context · b = bytes per KV element (2 BF16 / 1 FP8-INT8).
- [E] L=32, h_kv=8, d_h=128, S=8192, b=2, B=1 → **1.0 GiB**; S=128k → **16 GiB**;
  B=32 @8192 → **32 GiB**.

## Why It Exists
Without it, each decode step would recompute K,V for all prior tokens: O(S²) total.
The cache makes step t cost O(S) reads only. Trade: HBM capacity and bandwidth.

## Tensor Shapes
Per layer per request: `K [h_kv, S, d_h]`, `V [h_kv, S, d_h]`. Served paged:
a pool of fixed-size blocks (vLLM default 16 tokens; SGLang 64 [F: docs]) + per-request
block tables; block pool + radix/hashing index for prefix sharing
(`Attention/README.md` for the taxonomy).

## Paged KV Management
Virtual-memory analogy [F: Kwon et al. 2023, SOSP, arXiv:2309.00032]. Near-zero
fragmentation; dynamic block reallocation; shared blocks for shared prefixes; block
tables consumed by attention kernels (FlashInfer/TRT-LLM-GEN/FlashMLA all support paged
KV [F: vLLM docs]).

## Prefix Caching / Reuse
- **Hash-based APC** (vLLM): prefix hash → block list; physically shares paged blocks via
  refcounts [F: vLLM docs].
- **RadixAttention** (SGLang): radix tree over prefixes; sharing defined structurally by
  the program; 5×-class speedups on shared-prefix workloads (vendor-reported [F: SGLang blog]).
- **RadixCache/prefix caching** in serving generally: TTFT drops for repeated
  system prompts / agent history. Effect depends on hit rate — benchmark must pin
  overlap (`Inference/Prefill-Decode-Disaggregation.md`, `Labs/Lab-6`).

## KV Quantization
b=1 (FP8/INT8) halves KV bytes → 2× decode bandwidth headroom and 2× capacity for
concurrency. Trained/quantized variants exist (FP8 KV in Hopper/Blackwell stacks [F:
vLLM `--kv-cache-dtype`]); quality at FP8 is near-lossless in most evals [I: common
finding, workload-dependent].

## KV Offloading
Moving stale KV to CPU/SSD and prefetching on demand (OasisKV-style lookahead prefetch
[preprint 2026-08], FlexGen-class [F: arXiv:2303.06864], SGLang hierarchical KV [F: docs]).
Useful when KV ≫ HBM; cost is PCIe/NVLink bandwidth + latency spikes. [I]

## KV Compression / Pruning
Per-token importance scores → keep K% of tokens. See next section.

## Distributed / Disaggregated KV
Prefill/decode split ⇒ KV must **move** from prefill GPUs to decode GPUs: shared memory
(same host) → NVLink → RDMA (InfiniBand/RoCE) → NVL72 fabrics. Network becomes the
bottleneck; see `Inference/Prefill-Decode-Disaggregation.md` and `Networking/README.md`.

## Related
`Inference/The-Life-of-a-Token.md` · `Inference/Roofline.md` ·
`Model-Architectures/Attention-Head-Designs.md` (GQA/MQA shrink h_kv) ·
`Quantization/README.md` · `Labs/Lab-2` (observe KV growth).

## Key Takeaways
1. `2·L·B·h_kv·d_h·S·b` is the serving budget equation.
2. Paging made it usable; prefix caching made it shared; quantization made it cheap.
3. At ≥32k context or high concurrency, KV — not weights — is often the HBM constraint.
