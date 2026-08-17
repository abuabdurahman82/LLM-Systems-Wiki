# Attention — Taxonomy
`LAST_UPDATED: 2026-08-16` · Status: core page

The single most important distinction in attention research: **is the change an
architecture change (different math/params), a kernel change (same math, better IO), or a
memory-management strategy (same math+kernel, different KV storage)?** Most confusion in
the literature comes from mixing these three.

## Three Classes

### A. Architecture changes (different model)
| Technique | What changes | Effect |
|---|---|---|
| **MHA** (Vaswani 2017) [F] | h_kv = h_q heads | baseline; max expressivity; KV ∝ h |
| **MQA** (Shazeer 2019, arXiv:1911.06145) [F] | h_kv = 1 | KV ÷ h; decode bandwidth ↑; small quality cost |
| **GQA** (Ainslie 2023, arXiv:2305.13245) [F] | 1 < h_kv < h_q (e.g. 8) | near-MHA quality at fraction of KV; now default in Llama3/Qwen/DeepSeek |
| **MLA / latent attention** (DeepSeek-V2/V3, 2024) [F: tech report] | K,V projected to a shared low-rank latent + small RoPE part cached | KV cache ~97% smaller than MHA at same quality class; decoding becomes more compute-leaning |
| **Local / sliding-window** (Longformer, Swin-style, Mistral SWA 32K, arXiv:2310.06825) [F] | attention restricted to window W (+ optional global) | O(S·W); KV constant; long-range via global tokens/chunks |
| **Sparse attention** (BigBird, Longformer) [F] | block-diagonal + random patterns | sub-quadratic; mainly a training-era technique |
| **Linear attention** (Performer, Linear Transformer) [F] | QKᵀ via associative (feature-map) form | O(S); approximates softmax attention; quality gaps at scale [I] |
| **State-space models** (Mamba/S4, arXiv:2312.00752; Mamba-2, arXiv:2405.21855) [F] | no attention; selective scan recurrence, O(1) state | O(S) time, O(1) memory; strong at fixed cost, but less proven for long-context recall [I]; hybrid SSM+attention emerging (Jamba arXiv:2403.19646 [F]; Griffin arXiv:2402.19444 [F]) |

### B. Kernel changes (same math, better IO)
| Technique | What it does | Class |
|---|---|---|
| **FlashAttention** (Dao 2022, arXiv:2205.14135) [F] | exact softmax attention tiled in SRAM; never materializes S×S in HBM; O(S) memory | kernel |
| **FlashAttention-2** (2023, arXiv:2307.08691) [F] | better work partitioning/parallelism; ~2× FA1 | kernel |
| **FlashAttention-3** (2024, arXiv:2403.04951) [F] | Hopper: warp-specialized pingpong, FP8 support; ~1.5–2× over FA2 | kernel |
| **FlashInfer** (2025, arXiv:2501.15907, ICLR'25) [F] | prefill+decode kernels for *paged* KV, ragged batching; SGLang's primary backend; vLLM backend too | kernel |
| **PagedAttention** (Kwon 2023, SOSP'23, arXiv:2309.00032) [F] | KV stored in blocks + block tables; kernel indexes by table | **kernel + memory strategy** |
| **FlashMLA** (DeepSeek 2025) [F: repo] | MLA-optimized exact attention; used by vLLM for DeepSeek-family models | kernel |
| **TRT-LLM attention kernels** | custom compiled attention incl. fused paged paths | kernel |
| **Ring / context-parallel attention** (arXiv:2211.12876 "Ring Attention"; DeepSpeed Ulysses arXiv:2309.14509) [F] | split sequence across devices, rotate KV | distributed-kernel |

### C. Memory-management strategies (same math+kernel)
- **Paging** (block allocation), **prefix sharing** (APC / RadixAttention),
  **KV quantization** (FP8/INT8), **eviction/pruning** (`KV-Cache/Eviction.md`),
  **offloading** (CPU/SSD), **disaggregated KV transfer** (`Inference/Prefill-Decode-Disaggregation.md`).

## Why the Distinction Matters
1. "Linear attention beats Transformer" is an *architecture* claim — it says nothing
   about FlashAttention, which makes *standard* attention memory-efficient.
2. "PagedAttention is 2× faster" is usually a *memory strategy* claim (fewer
   pre-allocations, less fragmentation, better batching) — the math is unchanged.
3. Serving-engine benchmark fairness hinges on pinning the kernel class: FlashInfer vs
   FA3 vs TRT-LLM kernels are not interchangeable, even for the same model.

## Which Changes What (quick matrix)
| Goal | Change class |
|---|---|
| Cut KV bytes at the model level | architecture (GQA/MQA/MLA) |
| Cut KV bytes at runtime | strategy (quantize, evict, offload) |
| Cut prefill HBM traffic | kernel (FlashAttention) |
| Cut fragmentation / enable sharing | strategy (paging, radix) |
| Go beyond HBM capacity | strategy (offload, disaggregation) |
| Sub-quadratic sequences | architecture (SSM/linear/sparse) |

## Related
`Transformer/README.md` · `Model-Architectures/Attention-Head-Designs.md` ·
`KV-Cache/README.md` · `Serving-Engines/` (per-engine kernel choices) · `Labs/Lab-3`.

## Key Takeaways
Always ask: *architecture, kernel, or memory strategy?* The question prevents most
benchmark misreadings.
