# The CUDA Software Stack (NVIDIA's Moat)
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = NVIDIA docs/repos.

## 30-Second Explanation
Hardware without a mature software ecosystem is not enough. NVIDIA's moat is a
*vertically integrated, proprietary* stack that runs from raw SASS to PyTorch:
`Hardware → SASS → PTX → CUDA → CUTLASS/cuBLAS/cuDNN → Triton → PyTorch →
TensorRT-LLM / vLLM / SGLang`. Every layer is maintained, optimized, and extended by
NVIDIA (or the CUDA community it funds), and the whole thing compounds: a new Tensor Core
feature lands in PTX, then in cuBLAS, then in the serving engines, within quarters. The
counter-thesis (AMD's, Tenstorrent's, Cerebras's) is that open stacks can close the gap —
the evidence so far is "yes on commodity workloads, no on the frontier kernel tail"
(quantified in `11` and `15`).

## The stack, layer by layer
```
PyTorch / JAX / ONNX            <- model-level; the user writes a model, not a kernel
   |
TensorRT-LLM / vLLM / SGLang    <- serving engines: scheduler + KV cache + paged attention
   |                               + fused kernels; pick the right kernel per shape
   |
Triton (Python DSL)             <- "kernel as a Python function"; the modern escape hatch;
   |                               cross-vendor (CUDA + ROCm backends) - see ../GPU-Systems/Triton.md
   |
cuBLAS / cuDNN / CUTLASS        <- the optimized library tier: GEMM, conv, attention
   |                               (CUTLASS is the open-source template library behind much
   |                                of cuBLASLt; the "write a GEMM" toolkit)
   |
CUDA (C++/Python runtime)       <- the programming model: grids, blocks, warps, streams,
   |                               events, cooperative groups, NCCL collectives
   |
PTX (virtual ISA)               <- stable, forward-compatible virtual assembly; the compiler
   |                               target that survives across GPU generations
   |
SASS (native ISA)               <- real machine code; per-architecture; the actual
   |                                instructions the SM executes
   |
GPU hardware                     <- SMs, Tensor Cores, HBM, NVLink
```
- **SASS vs PTX:** PTX is the *stable* layer — code compiled to PTX runs on any GPU at or
  above the PTX ISA version, and the driver JITs it to SASS. SASS is the *native* layer —
  fastest, but per-architecture. The two-layer design is what lets a single CUDA binary or
  PTX blob forward-compare across generations. [F]
- **The escape hatch is the point.** When a serving engine's library kernel is not optimal
  for your shape, you drop to CUDA (raw), or to Triton (Python, faster to iterate), or to
  CUTLASS (templated GEMM). This "kernel escape hatch" is an *architectural* property — it
  is why NVIDIA users can absorb a new model/architecture in weeks while a closed-compiler
  machine (Cerebras, Groq) waits for a vendor engineer (`04` Q7; deep: `19`).

## Why "hardware alone is not enough"
1. **The long tail of kernels.** A new attention variant, a new MoE dispatch, a fused
   quantization op — each needs a *hand-tuned* kernel to hit peak. CUDA + Triton + CUTLASS
   + the community make that cheap; the alternative is vendor-dependency.
2. **Compiler + runtime maturity.** PyTorch's `torch.compile` lowers to Triton; NCCL gives
   tuned collectives; the engines (vLLM/SGLang/TRT-LLM) encode a decade of serving
   scheduling (continuous batching, PagedAttention, chunked prefill). A chip that ships
   without this layer ships a slow chip, regardless of FLOPs.
3. **Ecosystem gravity.** CUDA has the most engineers, the most StackOverflow answers, the
   most third-party kernels, the most profiling tools (Nsight). Porting cost is a function
   of this gravity — AMD's HIP ports bulk HPC code at 80–95% but modern AI kernels with
   Blackwell primitives port much worse (`11`).

## Cross-links (this stack vs the others)
| Layer | NVIDIA | TPU | AMD | Trainium | Cerebras | Groq |
|---|---|---|---|---|---|---|
| model | PyTorch | JAX/PyTorch | PyTorch | PyTorch/JAX | PyTorch | PyTorch/Tf/ONNX |
| compiler/IR | (CUDA) | XLA + StableHLO | HIP/Triton | XLA + Neuron | Cerebras compiler | Groq compiler |
| escape hatch | CUDA/Triton/CUTLASS | Pallas | HIP/Triton/CK | NKI | CSL | none |
| serving | TRT-LLM/vLLM/SGLang | (in-house) | vLLM/ROCm | (in-cloud) | Cerebras API | GroqCloud |
Deep dive: `19-ai-chip-software-stacks.md`.

## The honest assessment
- CUDA's moat is **real but not impregnable** (Hennessy-Patterson "golden age" logic says
  the *architectures* are open; the *software* is where the lock is). AMD's open-standards
  bet (PyTorch, Triton, vLLM, OCP MX) and Tenstorrent's fully-open RISC-V stack are the
  two counter-experiments.
- The gap is most visible on the **frontier kernel tail** (FA4, Blackwell-optimized ops,
  novel research kernels): months of lag for third-party ports. On commodity workloads
  (Llama inference, dense training) the stacks converge.
- The *strategic* question is whether Triton's Python DSL becomes the cross-vendor
  lingua franca that collapses the escape-hatch gap — an open question as of 2026 [I].

## Connection to LLM inference
- A serving engine's performance is *mostly* its kernel selection and scheduling, not the
  chip: the same model runs faster on the same GPU under a better engine. The stack is the
  multiplier on the hardware.
- Portability: a model that runs on NVIDIA via vLLM should in principle run on AMD via
  vLLM+ROCm; in practice the *fastest* path is vendor-specific kernels. This asymmetry is
  the whole "software moat" in one sentence.

## Key Takeaways
1. The stack is an architectural feature: SASS/PTX two-layer design + escape hatches +
   library tier + serving engines = compound advantage.
2. PTX is the stable virtual layer (forward-compatible); SASS is the native per-arch layer.
3. The "kernel escape hatch" (CUDA/Triton/CUTLASS) is why a new model lands in weeks on
   NVIDIA and in months on a closed-compiler machine.
4. Open stacks (ROCm, Tenstorrent) close the gap on commodity workloads but lag on the
   frontier kernel tail — the moat's real location.
5. Hardware FLOPs × software-stack maturity = real tokens/s; one zero makes the product.

## Related
- `08-nvidia-gpu-scaling.md` — the fabric the stack runs collectives over
- `11-amd-instinct-architecture.md` — the ROCm counterpoint
- `19-ai-chip-software-stacks.md` — all six stacks side by side
- `../GPU-Systems/Triton.md`, `../GPU-Systems/Kernel-Stack.md`, `../GPU-Systems/Inference-Engines.md`
- `../Serving-Engines/vLLM.md`, `../Serving-Engines/SGLang.md`, `../Serving-Engines/TensorRT-LLM.md`

## References
- NVIDIA CUDA C++ Programming Guide, PTX ISA [F]
- CUTLASS (github.com/NVIDIA/cutlass [F: repo])
- Triton (github.com/triton-lang/triton [F: repo])
- NCCL (github.com/NVIDIA/nccl [F: repo])
- TensorRT-LLM / vLLM / SGLang [F: repos]
