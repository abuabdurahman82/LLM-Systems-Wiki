# VERIFIED FACT-PACK — Triton section (2026-08-27)
Everything below was verified THIS SESSION against primary sources or measured on the
local GB10. Page authors MUST use these numbers verbatim; anything not here and not
in the house constants bank must be re-verified or tagged UNVERIFIED.

## Environment the [E] numbers come from (state on every page that quotes them)
- GPU: NVIDIA GB10 (DGX Spark), Blackwell, compute capability 12.1 (`sm_121`),
  48 SMs, 6144 CUDA cores, 24 MiB L2, ~100 KB shared mem/SM (48 KB max/block),
  65,536 regs/SM, 130.6 GB unified LPDDR5x, 273 GB/s nominal bandwidth.
- Software: Triton 3.6.0, torch 2.11.0+cu130, CUDA 13.0.
- CRITICAL CONTEXT: the measurement box is running the production GLM vLLM service
  (`--gpu-memory-utilization 0.84`), so kernel benchmarks ran under memory pressure
  from a concurrent 10-GB-serving process. Numbers are honest but NOT clean-room.
- [E] vec-add FP32 n=4M (48 MB moved): 0.558 ms → **86.0 GB/s** (vs 273 GB/s spec;
  load + unified-memory contention visible).
- [E] fused softmax 2048×2048 FP32: Triton **0.265 ms** vs torch eager **0.646 ms**
  (Triton ~2.4×); Triton 190 GB/s effective (3·bytes convention).
- [E] RMSNorm 2048×4096 FP16: Triton **0.323 ms** vs unfused torch-composed ref
  3.378 ms (**~10.5×**); 104 GB/s.
- [E] GEMM FP16 1024³: Triton 15.2 TFLOPS vs cuBLAS 16.7 (cuBLAS wins).
- [E] GEMM FP16 2048³: Triton **26.6** TFLOPS vs cuBLAS 21.7 (Triton wins at this
  shape on GB10 — worth stating as measured-on-this-box, not universal).
- [E] Skinny GEMM M=1 & M=16 (N=K=4096, FP16): Triton 69/71 GB/s vs cuBLAS 135/146 —
  cuBLAS wins here (our autotune space was trimmed; honest negative result).
- tl.dot_scaled signature (3.6.0): (lhs, lhs_scale, lhs_format, rhs, rhs_scale,
  rhs_format, acc=None, fast_math=False, lhs_k_pack=True, rhs_k_pack=True,
  out_dtype=float32).
- FP8 tl dtypes present: float8e4b15/e4b8/e4nv/e5/e5b16. target: backend=cuda arch=121.

## Version & release facts [F]
- Latest release: **Triton 3.7.1 (2026-06-18)**; 3.7.0 (2026-05-07); 3.6.0
  (2026-01-21); 3.5.1 (2025-11-12); 3.5.0 (2025-10-21); 3.4.0 (2025-07-30).
  Tag dates from GitHub releases API. Local box runs 3.6.0.
- Repo: github.com/triton-lang/triton, MIT license, ~20k stars; repo created 2014
  (project older than the OpenAI era), OpenAI donated to triton-lang org.
- Tutorial set (current main): 01-vector-add, 02-fused-softmax, 03-matrix-mult,
  04-low-memory-dropout, 05-layer-norm, 06-fused-attention, 07-extern-functions,
  08-grouped-gemm, 09-persistent-matmul, 10-block-scaled-matmul,
  11-programmatic-dependent-launch, + gluon/ subdirectory.

## History [F — primary sources]
- Pre-OpenAI: Phil Tillet began Triton as a research project (paper
  "Triton: an intermediate language and compiler for tiled neural network
  computations" — exists as a PDF; NOT on arXiv; cite the GitHub repo + paper title).
- OpenAI blog "Introducing Triton: Open-Source GPU Programming for Neural Networks"
  (2021-07-28, archived): Triton 1.0 open-sourced; "original creator now works at
  OpenAI"; FP16 matmul matching cuBLAS in ~25 lines; softmax keeps rows in SRAM;
  pipeline shown: Python → Triton-IR → LLVM-IR → PTX; comparison table: coalescing
  automatic, shared-mem mgmt automatic, scheduling within SMs automatic, scheduling
  ACROSS SMs manual.
- MLIR rewrite: commit "Merge triton-mlir branch — Complete rewrite of the backend
  from scratch (#1004)" — **2022-12-21**.
- Triton 2.0.0 tag: **2023-03-02** (first MLIR-based release line).
- Triton 3.0.0 tag: **2024-07-19** (ships with PyTorch 2.4-era Inductor; TMA/tensor
  descriptors era).
- 3.4.0 (2025-07-30): PDL (programmatic dependent launch), persistent TMA matmul
  epilogue subtiling, SwiGLU optimizations.
- 3.5.x (2025-10/11): Blackwell/FP4 era.
- 3.6.0 (2026-01-21): ragged TMA, warp-spec enabled for persistent matmul + FA,
  TMEM control-flow support, GFX1250/RDNA4 WMMA.
- 3.7.0/3.7.1 (2026-05/06): tl.squeeze/unsqueeze, scaled BMM, out-of-tree dialect
  plugins, async-read fence fix, LLVM InstCombine pin fix.
- Warp specialization ("autoWS") design post: pytorch.org blog 2026-01-08; autoWS
  upstreamed partly to OSS Triton; enabled via `warp_specialize=True` in ForOp /
  tuning configs; on B200 FA-forward TFLOPS close to Gluon/cuDNN (cuDNN still leads
  10–20%), 1.5–2× stock Triton [F: pytorch blog, vendor-adjacent].
- Gluon: low-level adjacent dialect (triton.experimental.gluon) with explicit
  TMA/mbarrier/tcgen05 control; tutorials ship in-repo; Hopper+ only for WS.

## Hardware-support matrix [F]
- TMA: NVIDIA cc ≥ 9.0 (Hopper+). tl.make_tensor_descriptor / host-side
  TensorDescriptor (triton.tools.tensor_descriptor).
- Warp specialization: cc ≥ 9.0, requires ≥ 4 warps (3.6 error message).
- tcgen05/TMEM (5th-gen Tensor Core path): cc 10.x datacenter (SM100). B200-class.
- CLC (cluster launch control) persistent matmul: cc ≥ 10.0.
- Block-scaled matmul (tl.dot_scaled): NVIDIA cc ≥ 10.0 (5th-gen Tensor Cores),
  formats mxfp4/mxfp8/nvfp4 (NVIDIA), mxfp4 on AMD CDNA4. Tutorial 10.
- SM121 (GB10/DGX Spark) vs SM100: consumer/edge Blackwell — NO TMEM, NO WGMMA
  wg-wmma path, 128 KB smem/SM (vs 228 KB), max 48 warps/SM (vs 64), each SM
  independent (no 2-SM cluster cooperation). tl.dot still maps to Tensor Cores but
  not the tcgen05 path [F: backend.ai teardown + device probe].
- AMD: ROCm/HIP backend; CDNA (MI300/MI350) + RDNA4 WMMA; FA3-class features differ.

## vLLM Triton kernel surface (verified from repo tree, 2026-08-27)
- Attention: vllm/v1/attention/backends/triton_attn.py (+_diffkv), ops/
  triton_decode_attention.py, triton_prefill_attention.py,
  triton_unified_attention.py, triton_merge_attn_states.py,
  triton_reshape_and_cache_flash.py (KV write), triton_fp8_mqa_logits.py,
  triton_turboquant_{decode,store}.py; MLA: triton_mla.py, aiter_triton_mla.py.
- Quant: kernels/linear/scaled_mm/triton.py, layers/quantization/awq_triton.py,
  compressed_tensors/triton_scaled_mm.py, kernels/triton/qkv_padded_fp8_quant.py.
- MoE: layers/fused_moe/ (fused_moe.py, moe_align_block_size.py,
  moe_permute_unpermute.py, experts/ with triton fused-expert kernels).
- Fusion passes (compilation/passes/fusion/): add_rms_fusion, rms_quant_fusion,
  qk_norm_rope_fusion, allreduce_rms_fusion — Triton-generated under torch.compile.
- LoRA: lora/ops/triton_ops/fused_moe_lora_op.py etc.

## SGLang Triton kernel surface (verified from repo tree, 2026-08-27)
- python/sglang/srt/layers: attention/decode_attention.py + prefill (Triton
  paged attention), rotary_embedding/ (rotary_triton.py), layernorm.py,
  activation.py, sampler.py, moe/ (fused_moe triton configs + tuning),
  quantization/ (triton kernels for fp8/int4/fp4).
- kernels/ops/attention: dsa/triton_sparse_mla.py, nsa_triton_decode/,
  flash_mla_sm120_triton.py, rotary_triton.py.
- Both engines: Triton = default/extensibility layer; FlashInfer/CUDA kernels used
  for the hottest attention paths [F: vLLM docs list FlashAttention, FlashInfer,
  TRTLLM-GEN, FlashMLA, Triton as optimized attention backends].

## Citation bank (all title-verified this session unless noted)
- FlashAttention 2205.14135 · FA-2 2307.08691 · FA-3 2407.08608 ·
  PagedAttention/vLLM 2309.06180 · SGLang 2312.07104 · GPTQ 2210.17323 ·
  AWQ 2306.00978 · SmoothQuant 2211.10438 · DeepSeekMoE 2401.06066 ·
  FlashInfer 2501.01005 · RoPE 2104.09864 · RMSNorm 1910.07467 ·
  Roofline-for-LLM 2402.16363 · Switch Transformers 2101.03961 ·
  Mixtral 2401.04088 · DeepSeek-V3 2412.19437.
- NOT on arXiv (cite repo/docs): Triton (the original paper is a PDF;
  repo = github.com/triton-lang/triton), CUTLASS, TensorRT-LLM, MLIR (llvm.org),
  PTX ISA (docs.nvidia.com), vLLM/SGLang docs, OpenAI blog (archived URL).

## House constants (from _STYLE.md — reuse, do not re-derive)
- H100 SXM: 989 TFLOP BF16 dense, 3.35 TB/s HBM3, 132 SMs, 228 KB smem/SM,
  64 warps/SM max. B200: ~8 TB/s HBM3e, FP8 ~4.5 PFLOP, FP4 ~9 PFLOP (vendor).
- Example model for worked arithmetic: 6.5B-class dense: d=4096, 32 layers,
  d_ff≈11008, GQA h_kv=8, d_h=128; KV/token = 128 KiB (BF16, GQA-8).
- Roofline ridge H100 BF16 ≈ 295 FLOP/byte.

## Non-duplication map (link, don't re-derive)
- GPU-Systems/{Architecture,Memory-Hierarchy,GEMM,Custom-GEMM,Fused-Kernels,
  FlashAttention,Tensor-Cores,CUDA-From-Zero,Kernel-Life,Profiling,GPU-Metrics,
  Kernel-Stack,vLLM,SGLang,TensorRT-LLM}.md — the thread-level CUDA story, the
  engines, the profiling tool catalogs.
- ../Inference/Roofline.md, ../Inference/Continuous-Batching.md,
  ../KV-Cache/README.md, ../Quantization/README.md, ../Speculative-Decoding/README.md,
  ../Distributed-Inference/README.md, ../Serving-Engines/README.md.
- GPU-Systems/Triton.md remains the single-page overview; this section deepens it.
