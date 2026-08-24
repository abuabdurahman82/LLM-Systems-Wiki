# The AI Compute Workload
`LAST_UPDATED: 2026-08-23` · Status: core page · Claims tagged `[F]/[E]/[I]/[A]/UNVERIFIED`.

## 30-Second Explanation
A transformer layer is a sequence of matrix multiplies (Q, K, V projections, attention
scores × values, output projection, and the FFN) interleaved with cheap elementwise work
(normalization, activation, residual add). **The matmuls carry >90% of the FLOPs**, so any
chip that wants to be fast at LLMs must be fast at matrix multiplication. The catch: the
*shape* of those matmuls changes with the workload — training and prefill are fat GEMMs
(many tokens against one weight matrix), decode is a skinny GEMV (one token against all the
weights). That single shape difference is the root of almost every architectural argument in
this section: compute-bound vs bandwidth-bound, FLOPS vs bytes/second, batch size as a
first-class tuning knob.

## The transformer as a sequence of operations
One decoder layer (dense model, GQA), in execution order:

| Step | Operation | Math | Shape (M=batch·seq) | Type |
|---|---|---|---|---|
| 1 | Input RMSNorm | elementwise, per-position | (M, d) | elementwise |
| 2 | Q projection | X @ W_q | (M,d)×(d,d) | GEMM |
| 3 | K projection | X @ W_k | (M,d)×(d, d·h_kv/h) | GEMM |
| 4 | V projection | X @ W_v | (M,d)×(d, d·h_kv/h) | GEMM |
| 5 | RoPE on Q,K | elementwise (per head) | (M, h, d_h) | elementwise |
| 6 | Attention scores | Q @ K^T | (M,h,d_h)×(d_h, M) | GEMM |
| 7 | Softmax + mask | elementwise | (M,h,M) | elementwise |
| 8 | Attention out | S @ V | (M,h,M)×(M,d_h) | GEMM |
| 9 | Output projection | A @ W_o | (M,d)×(d,d) | GEMM |
| 10 | Residual add | X + A | (M,d) | elementwise |
| 11 | FFN gate/up | X @ W_gate, X @ W_up | (M,d)×(d, d_ff) ×2 | GEMM |
| 12 | SiLU activation | elementwise | (M, d_ff) | elementwise |
| 13 | FFN down | (gate·up) @ W_down | (M,d_ff)×(d_ff,d) | GEMM |
| 14 | Residual add | X + F | (M,d) | elementwise |

For the wiki's standard example model (d=4096, 32 layers, d_ff≈11008, GQA h_kv=8, d_h=128 —
see `../GPU-Systems/_STYLE.md`), the per-layer weight bytes in BF16: QKV+O = 4·d² = 67.1M
params, MLP = 3·d·d_ff = 135.3M params (SwiGLU has three matrices) → ≈ 404.8 MB/layer,
≈ **12.95 GB total for 6.5B-class** [E: python-verified this session; note this slightly
exceeds 6.5B×2B = 13.0 GB only because d_ff was rounded]. The point is not the exact model —
the point is that **projections + FFN dominate the weight budget**, and attention's own QK^T/SV
matmuls carry no weights.

### What / Why / How / When
- **What:** "Most FLOPs are matrix operations" is a statement about the *weight* operations:
  each of the 8 GEMM-class steps above does 2·M·(output_dim)·(in_dim) FLOPs, while each
  elementwise step does O(1) FLOPs per element.
- **Why it matters:** a chip's matrix engine (Tensor Core, MXU, Matrix Core, FMAC mesh) is
  sized to saturate on GEMMs; the elementwise steps are so cheap that any decent machine
  finishes them while the engine drains.
- **How to verify:** for d=4096: one Q projection at M=1024 tokens is 2·1024·4096·4096 ≈
  34.4 GFLOP; the RMSNorm on the same 4M elements is ≈ 5–10 FLOPs/element ≈ 20–40 MFLOP.
  The matmul is ~1000× the arithmetic [E].
- **When the ratio flips:** attention at *very long* context (step 6/8 are O(M²) and
  weight-free) and MoE dispatch/routing (scatter/gather, no matmul) are the two places where
  non-matmul work becomes architecturally interesting — the TPU SparseCore and Trainium
  GPSIMD/CC-Cores exist partly for exactly these (see `10-google-tpu-architecture.md`,
  `13-aws-trainium-architecture.md`).

## GEMM, GEMV, MAC, tiles
```
GEMM (general matrix-matrix multiply):   C[M,N] = A[M,K] @ B[K,N] + C
GEMV (general matrix-vector multiply):   y[N]   = A[M=N,K] @ x[K]     (M = 1)
MAC  (multiply-accumulate, the atom):    acc += a * b
```
- **MAC:** the indivisible FLOP pair (a multiply and an add); "FLOPs" on a matmul = 2·M·N·K
  because each output element is K MACs = 2K FLOPs.
- **GEMV:** M=1. The matrix A still must be *read in full* for every output element, but each
  element of A is used exactly once. Bytes moved ≈ M·K + K·N + N (in/out), FLOPs = 2·M·N·K →
  arithmetic intensity ≈ 2·M / (bytes per operand) → for M=1, **AI ≈ 1–2 FLOPs/byte** no
  matter how big N and K are [E: python-verified, `03` covers the full curve].
- **Tiles / M×N×K:** a real GEMM kernel computes C in blocks: a tile of size Tm×Tn is loaded
  from HBM into on-chip memory, the K loop streams K in chunks, and the tile is accumulated.
  Tile size is the central knob of every matmul engine (see `../GPU-Systems/GEMM.md` and
  `06-nvidia-sm-and-tensor-cores.md`). The hardware's on-chip storage sets the maximum useful
  tile; the compiler/kernel chooses the actual one.
- **Arithmetic intensity of GEMM:** AI = 2·M·N·K / ((M·K + K·N + M·N)·b) FLOP/byte, with b the
  operand bytes. As M, N, K all grow, AI ≈ 2·(MNK)/(MN·b) = 2K/b → **GEMM AI is proportional
  to K** and can exceed 1000 FLOP/byte; GEMV AI is capped near 1. This is the entire
  prefill-vs-decode story in one formula.

## The three regimes: TRAINING / PREFILL / DECODE

### Training
```
many tokens (micro-batch 32–1024) x many steps, forward + backward + update
- forward:  large GEMMs (high AI, compute-bound)
- backward: ~2x the forward GEMMs (dL/dA and dL/dW paths)
- weights updated every step -> weights must be READ and the gradient must be aggregated
  across the data-parallel group (all-reduce) -> communication-heavy
- activations are large (checkpointing trades memory for recompute)
```
Training stress: sustained compute + big HBM capacity for activations + fast collectives.
Arithmetic intensity at micro-batch 128 for the example model: projection GEMMs run at
M=128·seq, AI in the hundreds → compute-bound on any modern accelerator [E: AI(M=128,K=N=4096)
= 120.5 FLOP/byte on H100's 295 ridge → still below ridge; M=512+ is safely compute-bound].
(See `../Training-Engineering/Parallelism.md` for the 5-axis parallelism that makes training
fit on many chips at all.)

### Prefill
```
the prompt (512–200k tokens) is processed in one pass, all tokens in parallel
- all projection GEMMs run at M = prompt_length -> large GEMMs, high AI, compute-bound
- attention is O(L^2) over the prompt -> FlashAttention tiling matters
  (`../GPU-Systems/FlashAttention.md`)
- KV cache is WRITTEN for the whole prompt -> bandwidth on the write side
- this phase sets TTFT (time-to-first-token)
```
Prefill is "training-shaped" inference: fat GEMMs, compute-bound, low latency target per
prompt. A machine that is compute-bound at prefill can use its FLOPs efficiently; a machine
starved of FLOPs pays TTFT.

### Decode
```
one token at a time (or B tokens if batched), each step conditions on all previous tokens
- every weight of the model is READ every step (the GEMV property)
- KV cache is READ (all previous K,V per layer) and appended
- M = 1 (or small B) -> AI ~ 1-2 -> MEMORY-BANDWIDTH-BOUNDED on every major accelerator
- latency target: ITL / TPOT, usually 20-50 ms/token for chat
```
The decode bandwidth floor: a 7B model at FP16 is 14.0 GB of weights [E: 7e9 × 2 B]. At
H100's 3.35 TB/s HBM, the batch-1 decode ceiling is 3.35e12 / 14e9 ≈ **23.9 tokens/s**
[E: python-verified] before any overhead — a useful rule of thumb: `batch-1 decode tok/s
≈ HBM bandwidth / weight bytes`. This single equation is why:
- FP8/FP4 quantization halves/quarters the weight bytes and doubles/quadruples decode speed
  (`../Quantization/README.md`),
- HBM3e/HBM4 capacity and bandwidth are first-class architectural resources
  (`../Hardware/README.md`),
- Groq/Cerebras, which trade chip count for SRAM bandwidth, win batch-1 decode and lose
  throughput-per-dollar (`12`, `14`).

Batching is the escape hatch: at batch B, the weight bytes are shared across B tokens, so
AI scales ~linearly with B until you hit the roofline ridge. For H100 BF16 (ridge ≈ 295
FLOP/byte), the decode batch knee is B* ≈ 295 × 2B_operand / 2 ≈ ~295 concurrent decode
streams [E: derivation in `23-roofline-across-ai-architectures.md`] — far beyond any real
decode batch, which is why decode stays memory-bound at practical batch sizes.

## How this connects to the rest of the wiki
| Regime | Dominant cost | Wiki section |
|---|---|---|
| training | FLOPs + collectives | `../Training-Engineering/Parallelism.md`, `../Training-Engineering/Scaling-Laws.md` |
| prefill | large GEMMs, attention O(L²) | `../Inference/The-Life-of-a-Token.md`, `../GPU-Systems/FlashAttention.md` |
| decode | weight + KV bandwidth | `../Inference/Continuous-Batching.md`, `../KV-Cache/README.md` |
| the roofline tying them together | AI vs bandwidth/compute | `../Inference/Roofline.md`, `../Inference/Prefill-Decode-Disaggregation.md` |
| speculative decoding | verify-step GEMMs at M=k | `../Speculative-Decoding/README.md` |
| MTP / multi-token prediction | k small GEMMs per step | `../Speculative-Decoding/README.md` |
| P/D disaggregation | separating the two regimes' hardware | `../Inference/Prefill-Decode-Disaggregation.md` |

The deeper structural point (developed in `../Inference/Prefill-Decode-Disaggregation.md`
and `22-workload-to-chip-mapping.md`): **prefill and decode want different machines** —
compute-rich for prefill, bandwidth-rich for decode — which is why modern serving stacks
run them on different hardware pools and why "one chip for everything" is a 2022 assumption.

## Worked example: one layer of the example model at M=8192 (prefill) vs M=1 (decode)
```
QKV+O+MLP weights/layer: 404.8 MB (BF16)                     [E]
Projection FLOPs/layer (M tokens): 2*M*(4*d^2 + 3*d*d_ff)
  M=8192: 2*8192*(67.1e6 + 135.3e6) = 3.34e12 FLOP/layer      [E]
  M=1:    2*1*(2.02e8)           = 4.04e8 FLOP/layer         [E]
AI (BF16, 2B/operand):  M=8192 -> ~ 808 FLOP/byte  (compute-bound)  [E]
                        M=1    ->   ~ 2 FLOP/byte    (bandwidth-bound) [E]
Time on H100 (989 TFLOP BF16 dense, 3.35 TB/s):
  M=8192: 3.34e12/9.89e14 = 3.4 ms/layer (FLOPs-bound)        [E]
  M=1:    min(FLOPs time 0.4us, bytes time 404.8e6/3.35e12=121 us)
          -> 121 us/layer, i.e. the WHINE is in HBM, not FLOPs  [E]
```
The 350× spread between "3.4 ms" and "121 µs" is not a bug — it is the arithmetic-intensity
change. Every architecture in this section is a different strategy for what to do when the
machine is in the M=1 regime (which is most of a chatbot's serving time).

## Key Takeaways
1. A transformer is ~95% matmuls by FLOPs; the non-matmul steps are the tax you pay to
   keep the matmul engines fed.
2. GEMM arithmetic intensity grows with the tile sizes (≈ 2K/b); GEMV is pinned near AI≈1.
   That difference, not "FLOPS", explains prefill-vs-decode behavior.
3. Batch-1 decode speed ≈ HBM bandwidth / weight bytes. Quantization and HBM upgrades act
   on exactly this ratio; FLOPS upgrades do almost nothing for it.
4. Training ≈ 3× the FLOPs of inference per token (forward + 2×backward) plus all-reduce
   traffic; prefill ≈ inference-shaped compute; decode ≈ inference-shaped bandwidth.
5. The M dimension (1 for decode, hundreds–thousands for prefill/training) is the single
   most important workload parameter a chip architect must know.

## Related
- `03-memory-wall-and-data-movement.md` — what the bandwidth numbers actually mean
- `../Inference/The-Life-of-a-Token.md` — prefill/decode lifecycle
- `../GPU-Systems/GEMM.md` — how a GEMM actually runs on an SM
- `../KV-Cache/README.md` — the second big read in decode
- `22-workload-to-chip-mapping.md` — the full regime→hardware matrix

## References
- "Attention Is All You Need" (arXiv:1706.03762) — the layer structure
- "FlashAttention: Fast and Memory-Efficient Exact Attention" (arXiv:2205.14135) [F: bank]
- Yuan et al. "LLM Inference Unveiled: Survey and Roofline Model Insights" (arXiv:2402.16363) [F: bank]
- Llama-2 technical report (arXiv:2307.09288) — 70B actual parameter count 67.8B [F]
