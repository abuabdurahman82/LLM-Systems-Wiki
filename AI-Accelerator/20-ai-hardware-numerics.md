# AI Hardware Numerics — FP32 → BF16/FP16 → FP8 → FP4, Microscaling, and Accumulation
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
Every FLOP claim in this section is *incomplete* without a *precision*: "989 TFLOPS" means nothing until you know it is *BF16 dense, per H100 chip*. This page is the *numerics* frame: the *precision ladder* (FP32 → TF32/BF16/FP16 → FP8 → FP4), the *two* formats that *matter* for LLMs (*BF16* for *training*, *FP8* for *inference*), the *microscaling* idea that makes *4-bit* *usable* (per-*block* scaling, not *per-tensor*), and the *accumulation* question (you *compute* in low precision but *accumulate* in high precision, or you *lose*). The *payoff* is a *rule of thumb*: *halving the bytes-per-param halves the memory-wall cost and doubles the compute ceiling, at the price of accuracy that microscaling mostly recovers.*

## The precision ladder
| Format | Bits | Range | Mantissa | Typical use in this section |
|---|---|---|---|---|
| FP32 | 32 | wide (8 exp bits) | 23 | *training* reference; *rarely* the *work* precision |
| TF32 | 19 | wide (8 exp) | 10 | NVIDIA's *TF32 Tensor Core* (H100/A100); *automatic* in cuDNN [F: NVIDIA] |
| BF16 (bfloat16) | 16 | *same as FP32* (8 exp) | 7 | *training* work precision (TPU, MI300, H100) [F: vendors] |
| FP16 | 16 | narrow (5 exp) | 10 | *training* work precision (older); *overflow* risk → *BF16* preferred |
| FP8 (E4M3) | 8 | narrow | 3 | *inference* + *forward* (H100, MI300, TPU v5p, Trainium2) [F: vendors] |
| FP8 (E5M2) | 8 | wider range | 2 | *backwards* (gradients need *range*) [F: NVIDIA] |
| FP6 (OCP) | 6 | — | — | OCP MX standard; *between* FP8 and FP4 [F: OCP] |
| FP4 (E2M1) | 4 | very narrow | 1 | *inference* (B200, NVFP4) [F: NVIDIA] |
| INT8 | 8 | fixed | — | *inference* (Groq TSP, TPU INT8) [F: vendors] |

*The first-principles read:* the *ladder* is a *bytes-vs-accuracy* trade. *FP16* has *more mantissa* than *BF16* (10 vs. 7) but a *narrower range* (5 vs. 8 exp bits); *BF16* is *the* training format *because* *gradients* need *range* (the *backwards* pass *underflows/overflows* at *FP16* range). *FP8* is *the* inference format *because* *4× the compute of FP16* at *half the bytes of FP16*, and *microscaling* recovers most of the *accuracy* [I]. (The *Blackwell* *B200* extends the ladder to *FP4*: ~9,000 TFLOPS FP4 dense per GPU, ~4,500 TFLOPS FP8 dense per GPU — consistent with the DGX B200's 72 PFLOPS FP8 dense / 144 PFLOPS FP4 sparse system figures ÷ 8 GPUs [E/F: secondary sources, cross-consistent].)

## Why "FLOPs" are meaningless without a precision
A *TFLOP* is *not* a *unit* — it is a *rate* of *operations*, and the *operation* is *precision-dependent*. The *H100* does:
- *989 TFLOPS* at *BF16* (dense) [F: NVIDIA, page 05]
- *1,979 TFLOPS* at *FP8* (dense) [F: NVIDIA]
- *3,958 TFLOPS* at *FP8* (2:4 *sparse*, the "*SPRS*") [F: NVIDIA]

The *ratio* (*1,979 / 989 = 2×*) is *the precision effect*: *FP8* doubles the *BF16* rate *because* the *Tensor Core* does *two FP8 MACs* in the *time* of *one BF16 MAC* (the *FP8* *data path* is *half the width*). The *sparse* number (*3,958 / 1,979 = 2×*) is *a different* effect: the *2:4 structured sparsity* skips *half the MACs* [F: NVIDIA]. **You cannot compare "989 TFLOPS" to "1,979 TFLOPS" without stating which precision** — they are *different operations*. This is the *first* *rule* of the *comparison matrix* (page 21).

## Microscaling — why 4-bit is usable
The *naive* objection to *FP4*: *4 bits* (1 *exp* + 1 *mantissa* + 1 *sign* for *E2M1*) has *no* *range* and *no* *precision* — the *dynamic range* of a *tensor* (a *70B* model's *weights* span *~6 orders of magnitude*) *cannot fit* in *4 bits*. The *answer* is *microscaling* (the *OCP MX* standard, and *NVIDIA's NVFP4*): you *scale per-block*, not *per-tensor* [F: OCP, NVIDIA].

*The mechanism:* a *FP4 tensor* is divided into *blocks* (e.g., *32 elements*), and *each block* gets *its own FP8* *scale factor*. The *effective precision* of *element i* is *FP4 mantissa + FP8 scale range* — the *block* *recovers* the *range* that the *4-bit* *value* lost. The *cost* is *~2 bits per 32 elements* of *scale overhead* ([E] 8/32 = *25%* *overhead* at *32-element* blocks; *~12.5%* at *64-element* blocks) [E].

*The first-principles read:* *microscaling* is *the* *enabler* of *4-bit inference*: it *turns* the *global-range problem* into a *local-range problem* (the *block* is *scaled* to its *own range*), and the *accuracy loss* is *mostly recovered*. The *Groq TSP* does *not* use *FP4* (it is *INT8/FP16*, page 14) — *microscaling* is *a* *NVIDIA/AMD/TPU* *feature* (the *Blackwell*, *MI300/350*, and *TPU v5p* *Tensor Cores* *support* *MX* formats) [F: vendors]. *INT8* is *the* *Groq* *equivalent*: *fixed-point* with *per-channel* *quantization* (the *Groq* *compiler* *places* the *scales*), not *per-block* *floating-point* [I].

## Accumulation — compute low, accumulate high
The *second* *rule* of *low-precision*: you *compute* in *low precision* (FP8, FP4, INT8) but *accumulate* in *high precision* (FP32, FP16, INT32). The *reason* is *the* *matmul*: a *320×320* *tile* *accumulates* *320 partial products* — the *partial products* are *~6 digits* of *magnitude* *wider* than the *inputs* (the *sum of 320 FP8 products* *spans* *~FP16 range*). If you *accumulated* in *FP8*, the *sum would overflow/underflow* and the *result would be garbage*. The *MXU/MXM/Tensor Core* *accumulates in a wide register* (the *INT32* *accumulator* on *Groq*, the *FP32* *accumulator* on *NVIDIA/TPU/AMD*), and *only the final result* is *written back in the low precision* [F: ISCA 2022, NVIDIA, Google].

*The first-principles read:* *accumulation precision* is *the* *hidden* *cost* of *low-precision compute*: it *determines* the *maximum* *K* (the *reduction* dimension) that *you can accumulate before rounding*. A *320-wide* *MXM* *tile* *accumulates* *320 products in INT32* (the *INT32* *range* *covers* the *sum of 320 INT8 products* with *headroom*) [F: ISCA 2022]. A *Tensor Core* *tile* *accumulates* in *FP32* (the *FP32* *range* *covers* the *sum of 16/32 FP8 products* with *headroom*) [F: NVIDIA]. *The accumulator is the "free" high-precision register that makes low-precision compute safe.*

## The bytes-per-param knob
The *single* *most important* *number* for *inference* *cost* is *the bytes-per-param* (bpp):
| Precision | bpp (weights) | 70B model footprint [E] |
|---|---|---|
| FP16 / BF16 | 2 | 135.6 GB |
| FP8 / INT8 | 1 | 67.8 GB |
| FP6 | 0.75 | 50.9 GB |
| FP4 | 0.5 | 33.9 GB |
| FP4 + microscaling (~25% overhead) | 0.625 [E] | 42.4 GB |

*The rule of thumb:* *halving* the *bpp* *halves* the *memory-wall cost* (page 03) *and doubles* the *compute ceiling* (the *Tensor Core* *does 2× the MACs at half the width). The *accuracy* *cost* is *mostly recovered* by *microscaling* (FP8) or *per-channel quantization* (INT8) [I]. This is *why* the *Groq 576-TSP* system runs *Llama-2 70B at INT8* (page 14): the *FP16* *footprint* (135.6 GB) *exceeds* the *aggregate SRAM* (132.5 GB), but the *INT8* *footprint* (67.8 GB) *fits with 64.7 GB headroom* [E].

## The precision bet per chip
| Chip | Optimized precision | Accumulation | Microscaling? |
|---|---|---|---|
| NVIDIA H100 | FP8 (E4M3 fwd, E5M2 bwd) | FP32 | no (FP8 is *per-tensor*; MX is *Blackwell+) [F: NVIDIA] |
| NVIDIA B200 | FP4 (NVFP4) | FP32 | **yes** (NVFP4 is *per-block* [F: NVIDIA]) |
| Google TPU v4 | BF16 / INT8 | FP32 / INT32 | no [F: ISCA 2023] |
| Google TPU v5p | FP8 | FP32 | partial (FP8 *per-tensor*; *MX* on *later* [I]) |
| AMD MI300X | FP8 | FP32 | partial [F: AMD] |
| Groq TSP (2022) | INT8 / FP16 | INT32 / FP32 | no (*INT8* is *per-channel*, *placed by the compiler* [I]) |
| AWS Trainium2 | cFP8 | FP32 | **yes** (*cFP8* is *AWS's microscaling* [F: AWS]) |

*The first-principles read:* *the* *precision bet* *is* *the* *chip's* *statement* about *where* the *accuracy/quality* *tradeoff* *lives* *for* the *target workload*. *NVIDIA's* *NVFP4* (the *per-block* *4-bit* format) *is* *the* *most aggressive* *bet* (the *lowest* *bpp*, the *highest* *compute ceiling*, the *reliant-on-microscaling* *accuracy). *Groq's* *INT8* *is* *the* *most conservative* *bet* (the *fixed-point*, the *per-channel*, the *no-microscaling* format) — *but* it *fits* *the Groq* *philosophy* (the *determinism* *over* the *generality).

## How to read this page against the others
- **vs. page 03 (memory wall):** this page is the *bytes-per-param knob* that *page 03's memory wall* *is measured in*.
- **vs. page 06 (Tensor Cores):** page 06 is the *NVIDIA* *Tensor Core* in depth; this page is the *cross-chip precision comparison*.
- **vs. page 14 (Groq):** page 14's *INT8/FP16* *MXM* is *the* *Groq* *precision* *in depth*; this page is the *comparison*.
- **vs. page 21 (comparison matrix):** this page *provides* the *precision column* of the *matrix*.
- **vs. page 23 (roofline):** the *roofline* *is* *precision-dependent* (the *FLOP* *ceiling* and the *byte* *floor* *both* *change with precision); this page is the *precision* *axis* of that *roofline*.
