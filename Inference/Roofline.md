# The Roofline Model Applied to LLM Inference
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
`Achievable FLOPS = min(Peak FLOPS, HBM bandwidth × arithmetic intensity)` where
arithmetic intensity (AI) = FLOPs per byte moved. GEMM-heavy prefill has huge AI
(compute-bound); 1-token decode GEMVs have AI ≈ 1–4 (bandwidth-bound). This single model
explains why prefill and decode have different bottlenecks, why quantization mostly helps
decode, and why we batch.

## Why This Exists
Williams, Waterman & Patterson 2009 [F: ACM CACM] gave a model separating "how fast can the
machine add?" (peak FLOPS) from "how fast can it feed data?" (HBM bandwidth). LLM
inference sits on different sides of the ridge for prefill vs decode, so one kernel
library must serve both.

## First-Principles Explanation
For each workload measure: F (FLOPs) and B (bytes from HBM). AI = F/B.
- If AI ≥ ridge = peak/BW → compute-bound: speed ∝ peak FLOPS (tensor cores, big GEMMs).
- If AI < ridge → bandwidth-bound: speed = BW × AI; FLOPS are wasted waiting on data.

Ridge examples [F: vendor specs]:
- H100 SXM: 989 TFLOPS BF16 dense / 3.35 TB/s ≈ **295 FLOP/byte**
- RTX 5090 (GDDR7): ~3351 TFLOPS NVFP4 / 1.79 TB/s ≈ **223 FLOP/byte** [F spec]
- GB10 (DGX Spark-class): ~273 GB/s [A: spec-sheet]

## How It Works — LLM cases
**Prefill GEMM [S,d]×[d,d]:** F = 2·S·d·d; bytes ≈ S·d·b_act + d·d·b_w + S·d·b_act
(the 2·d factor in FLOPs offsets the activation read+write) → **AI ≈ d/b_w**.
For d=4096, b_w=2: AI ≈ 2048 ≫ ridge → **compute roof** [E: verified in Python].

**Decode GEMV (batch B=1):** F = 2·d per matrix; bytes ≈ d·b_w (activations negligible)
→ **AI = 2/b_w**: BF16 → 1.0; NVFP4 (~4.5 bit/param incl. block scale ≈ 0.5625 B) → ≈3.56.
Both ≪ ridge → **memory roof**: tokens/s ≈ BW / bytes-per-token [E].

**Decode batch B:** bytes(B) ≈ B·b_act·2d + d·b_w → AI(B) = 2B·d / (2B·b_act + b_w·d).
The "knee" batch B* where AI hits the ridge: B* ≈ ridge·b_w/2 (large-d limit):
**BF16 on 5090-class ≈ 250; NVFP4 ≈ 70; BF16 on H100 ≈ 345** [E: computed].
Below B* decode is bandwidth-bound; batching to B* amortizes the weight stream. Above it,
you approach the compute roof.

## Visual Mental Model
```
 FLOPS
  │        ______________________________   ← compute roof (peak FLOPS)
  │       /
  │      /
  │     /        ● prefill (AI ≈ d/b)
  │    /         (compute-bound)
  │   /
  │  /  ● decode B=1 (AI ≈ 1)
  │ /   (bandwidth-bound)
  └──────────────────────────────────── bytes/instr →
            ridge ≈ 295 (H100 BF16)
```

## Example [E]
27B model, 1 GPU, GDDR7 ~1.79 TB/s: decode bytes/token ≈ 50.3 GiB (BF16 weights) +
KV read (≈1 GiB @8192 ctx, GQA h_kv=8, FP16 — verified via the KV-cache script) ≈
51.3 GiB → **≈33 tok/s** ceiling; NVFP4 weights (≈14.1 GiB) + 1 GiB KV ≈ 15.1 GiB →
**≈118 tok/s** ceiling. (Kernel overhead and the attention KV-read pull real numbers
below this.)

## Impact on Training
Training is GEMM-dominated (huge S and batch) → nearly always compute-bound; the roofline
predicts ~70–80% of peak with good pipelining (MFU), not memory limits. [I]

## Impact on Inference
- Quantize **weights** → decode bytes↓ → decode speed up (until the ridge); prefill mostly
  unaffected (unless low-precision tensor-core FLOPS rise too).
- Batch → amortize weights (until B*).
- GQA/MQA → shrink KV bytes per token.
- FlashAttention → remove S² HBM traffic (helps prefill at large S; decode is dominated by
  KV *reads*, which it does not reduce).
- Co-scheduling (chunked prefill) → keep tensor cores busy during decode steps.

## Performance Implications
See `Inference/Continuous-Batching.md`, `Model-Architectures/Attention-Head-Designs.md`
(GQA as a bandwidth lever), `Quantization/README.md`, `Speculative-Decoding/README.md`.

## Advantages / Limitations
A model, not a measurement: it predicts the *ceiling* and the *regime*, not kernel
quality. Real kernels sit below the roof (measured MFU matters). [I]

## Important Research
Williams, Waterman, Patterson 2009 "Roofline: an insightful visual performance model for
multicore architectures" [ACM CACM] · Pope et al. 2020 "Efficiently Scaling Inference
Infrastructure" [F: arXiv:2111.02534, MLSys] · Dao et al. 2022 (FlashAttention) ·
Kwon et al. 2023 (vLLM/PagedAttention, SOSP'23).

## Related Topics
`The-Life-of-a-Token.md` · `Inference/Inference-Metrics.md` · `Inference/Inference-Optimization.md` · `Distributed-Inference/README.md`

## Key Takeaways
1. Prefill = compute roof; decode = memory roof; the ridge is where batching lives.
2. Decode speed ≈ BW / bytes-per-token — every KV/weight byte you save is speed.
3. B* (the knee batch) ≈ ridge·b_w/2 — quantizing weights lowers the bytes, raising the
   achievable tok/s, and shifts the knee.
