# Research Lineage — GPU Systems & LLM Inference
`LAST_UPDATED: 2026-08-21 · Status: core page` · An idea-influence map, not a paper list.
Each lineage shows the **chain of ideas** that led to the current technology, with the
key papers (verified arXiv ids), what each contributed, and where the line stands now.
Companion to `../Research-Lineage/README.md` (broader) — this is the GPU-systems track.

## 30-Second Explanation
"Lineage" = follow the *idea*, not the paper. Most of today's inference stack is the
endpoint of a few long threads: **IO-aware attention**, **memory-as-the-bottleneck**
(prefill/decode asymmetry → disaggregation), **custom-kernel ecosystems** (GEMM →
Triton/CUTLASS), and **KV-memory management** (PagedAttention → vLLM → P/D routing).
Reading a lineage lets you predict the *next* move instead of just memorizing the last one.

## Lineage 1 — IO-aware attention
```
Attention is All You Need (Transformer)  [F: Vaswani et al. 2017]
   │  "O(S²) memory + O(S²) HBM traffic for the S×S matrix"
   ▼
memory-efficient attention (tiling / streaming ideas, 2019–2020)
   ▼
FlashAttention  [F: arXiv:2205.14135, Dao 2022]   — IO-aware tiling + online softmax
   ▼
FlashAttention-2  [F: arXiv:2307.08691, Dao 2023] — better parallelism over heads
   ▼
FlashAttention-3  [F: arXiv:2407.08608, 2024]     — Hopper async + TMA, more Tensor-Core
   ▼
paged/ragged attention kernels (FlashInfer)  [F: arXiv:2501.01005] — the inference-era engine
```
- **Problem:** the naive attention materializes the S×S matrix in HBM → O(S²) memory + IO.
- **Key idea:** the **math is unchanged** (exact softmax), but the **order of operations**
  is re-tiled so the S×S matrix never hits HBM; online-softmax runs in SRAM. The win is
  IO, not FLOPs. → `FlashAttention.md`
- **Limitation:** still O(S) memory for KV; long context is still KV-bound, not compute-bound.
- **Now:** FlashAttention is the reference; the frontier moved to *paged/ragged* decode
  attention (FlashInfer) and to attention alternatives (see Lineage 6 + Research-Radar).

## Lineage 2 — Memory is the bottleneck (prefill/decode → P/D)
```
roofline for LLM inference (P/BW ridge)  [F: Williams CACM 2009; Yuan et al. arXiv:2402.16363]
   │  "decode is memory-bound (AI≈1), prefill is compute-bound (AI≫ridge)"
   ▼
Orca — iteration-level (continuous) batching  [F: arXiv:2211.05102]
   ▼
Sarathi / Sarathi-Serve — chunked prefill  [F: arXiv:2308.16369, 2403.02310]
   ▼
DistServe / Splitwise / Mooncake — prefill/decode DISAGGREGATION  [F: arXiv:2401.09670, 2311.18677, 2407.00079]
   ▼
KV-aware routing + multi-node P/D  [current]
```
- **Problem:** prefill (big GEMMs, compute-bound) and decode (tiny GEMMs, bandwidth-bound)
  want **different GPUs and different SLOs**; co-locating them steals KV from each other.
- **Key idea:** separate the two pools and **move the KV** between them; route by cache
  state, not by connections. → `Prefill-Decode-Disaggregation.md`
- **Limitation:** the KV-transfer network becomes the new bottleneck; long-context KV
  transfer is expensive. → `Multi-Node.md`
- **Now:** P/D disaggregation is production (vLLM/SGLang/TRT-LLM all expose it); the
  frontier is **KV-aware routing** and **disaggregated multi-node** serving.

## Lineage 3 — Custom-kernel ecosystem (GEMM → Triton/CUTLASS)
```
naive GEMM → tiled → shared-memory → Tensor-Core GEMM  (CUDA textbooks, cuBLAS)
   ▼
cuBLAS / cuBLASLt (the autotuned default)  [F: NVIDIA]
   ▼
CUTLASS — build your own Tensor-Core GEMM  [F: github.com/NVIDIA/cutlass]
   ▼
Triton — a Python kernel language + compiler  [F: github.com/triton-lang/triton]
   │  torch.compile → Inductor → emits Triton kernels  [F: PyTorch docs]
   ▼
LLM-specialized kernels: grouped/skinny/quantized GEMMs, MoE GEMMs  [current]
```
- **Problem:** the generic library is not optimal on the *LLM-specific* shapes (M=1..32
  decode, grouped MoE, quantized). → `Custom-GEMM.md`
- **Key idea:** an **ecosystem, not one library** — cuBLASLt picks an algo, CUTLASS builds
  a kernel, Triton generates a kernel, custom CUDA is the fallback; an engine picks among
  them per (shape, dtype, arch). → `Triton.md`
- **Limitation:** the hottest kernels (Tensor-Core GEMM, attention) still beat Triton's
  ceiling → hand-written CUTLASS/CUDA wins there.
- **Now:** Triton is the "research kernel" layer; the frontier is **quantized and MoE
  kernels** and **GPU compilers** (see Research-Radar).

## Lineage 4 — KV-memory management (PagedAttention → vLLM)
```
KV cache (the decode-era HBM consumer)
   ▼
PagedAttention — block-based KV + block tables (OS virtual-memory idea)  [F: arXiv:2309.06180]
   ▼
vLLM — PagedAttention + continuous batching  [F: arXiv:2309.06180]
   ▼
prefix caching (APC) / RadixAttention (radix-tree prefixes)  [F: arXiv:2312.07104 SGLang]
   ▼
KV-aware routing + eviction (SnapKV/H2O)  [F: arXiv:2404.14469]
   ▼
disaggregated KV (KV as first-class transferable state)  [current]
```
- **Problem:** KV waste (fragmentation, fragmentation) + wasted prefill on shared prefixes.
- **Key idea:** treat KV like **paged virtual memory** (blocks + tables) so it's compact,
  shareable, and movable; then **reuse** it (prefix cache) and **route** to where it is.
  → `vLLM.md`, `SGLang.md`
- **Now:** prefix caching is default in vLLM/SGLang; the frontier is **KV-aware
  routing/scheduling** and **disaggregated KV** (P/D). → `../KV-Cache/README.md`

## Lineage 5 — Quantization
```
FP16/BF16 mixed precision  →  INT8/FP8 (SmoothQuant)  [F: arXiv:2211.10438]
   ▼
weight-only quant: GPTQ  [F: arXiv:2210.17323], AWQ  [F: arXiv:2306.00978]
   ▼
KV quantization (KIVI)  [F: arXiv:2402.02750]
   ▼
sub-4-bit: INT4 / FP4 / NVFP4 (Tensor-Core native)  [current]
```
- **Problem:** weights dominate HBM; decode is bandwidth-bound → fewer bytes/token.
- **Key idea:** quantize the **weights** (and optionally KV/activations) to move less;
  the Tensor-Core path then does the dequant in-kernel. → `Tensor-Cores.md`,
  `../Quantization/README.md`
- **Limitation:** speedup ≠ bit-width ratio (the dequant + low-AI regime cap it); quality
  degrades at the low end.
- **Now:** INT8/FP8 is production; FP4/NVFP4 is on Hopper/Blackwell Tensor Cores; the
  frontier is **FP4 + KV-quant** and **quantized GEMM kernels**.

## Lineage 6 — Speculative decoding
```
draft-verify: Leviathan et al. "Speculative Decoding" (2022) + Chen et al.
"Speculative Sampling" (2023) — two independent origin papers
   ▼
EAGLE / EAGLE-2 — an AR-draft head over hidden states  [F: arXiv:2401.15077]
   ▼
MTP (Multi-Token Prediction, DeepSeek) — native draft heads  [F: arXiv:2412.19437]
   ▼
spec-decode in engines (vLLM/SGLang/TRT-LLM)  [current]
```
- **Problem:** decode is bandwidth-bound; a small draft model is "free-ish" relative to
  the verify step → more accepted tokens per pass of the big model.
- **Key idea:** generate k draft tokens, verify them **in parallel** with one big-model
  pass; accept the prefix. → `../Speculative-Decoding/README.md`
- **Now:** spec-decode is production; the frontier is **native MTP** and **agentic
  spec-decode** (draft from the agent's own loop).

## Lineage 7 — Parallelism & MoE
```
Megatron-LM — TP (col/row-parallel GEMM, 2 AllReduce/layer)  [F: arXiv:1909.08053]
   ▼
GPipe / PipeDream / 1F1B — pipeline parallelism  [F: arXiv:1811.06965, 1806.03377]
   ▼
Sequence/context parallelism: Ring Attention  [F: arXiv:2310.01889], Ulysses  [F: arXiv:2309.14509]
   ▼
MoE: Switch  [F: arXiv:2101.03961] → Mixtral  [F: arXiv:2401.04088] → DeepSeekMoE  [F: arXiv:2401.06066] → DeepSeek-V3  [F: arXiv:2412.19437]
   ▼
Expert parallelism + AllToAll + NVL72  [current]
```
- **Problem:** one GPU can't hold / serve a frontier model; MoE adds experts to shard.
- **Key idea:** compose TP (intra-node, NVLink) + PP (inter-node) + EP (MoE, AllToAll) +
  DP (router); put each on the fabric that fits. → `Distributed-Architectures.md`
- **Now:** NVL72 makes wide TP/EP feasible; the frontier is **MoE on the network** and
  **KV-aware expert placement**.

## How to read a new paper against these lineages
1. **Which lineage does it extend?** (attention-IO? memory/P-D? kernel-eco? KV? quant? spec? MoE?)
2. **What does it move the bottleneck to?** (every advance pushes the limit one layer down
   — see `Cross-Layer-Optimization.md`.)
3. **Production or research-stage?** (check `Research-Radar.md`.)
4. **What does it make the *next* step cheaper?** (that's the forward signal.)

## Related
`Research-Radar.md` (what's current, by maturity) · `../Research-Lineage/README.md` ·
`../Latest-Research/2026-08.md` · `Cross-Layer-Optimization.md` · per-lineage deep dives
(`FlashAttention.md`, `vLLM.md`, `Custom-GEMM.md`, `Tensor-Parallelism.md`, `MoE-Expert-Parallelism.md`).
