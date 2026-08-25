# NVIDIA Memory Hierarchy & Data Movement
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = NVIDIA architecture docs.

## 30-Second Explanation
NVIDIA's answer to the memory wall is **layered hiding**: registers and an explicit
shared-memory/L1 tile buffer the matmul engine, hardware L1/L2 caches hide DRAM latency,
occupancy hides HBM latency, and — since Hopper — dedicated *bulk-copy* hardware (TMA) and
*asynchronous barriers* (mbarrier) move data without the issuing thread babysitting it.
The trajectory across generations is: **synchronous loads → cp.async (Ampere) → TMA
(Hopper) → more autonomous data movement (Blackwell)** — the SM is steadily freed from
"move data" so it can spend its cycles on "multiply data".

## The tiers
```
registers      256 KB/SM (65,536 x 32-bit)   the thread's private values + MMA fragments
TMEM           (Blackwell) dedicated tensor-memory for tcgen05 accumulators
SMEM/L1        up to 228 KB/SM (Hopper)      UNIFIED: partitioned between hardware L1
                                              cache and programmer-visible shared memory
L2             50 MB (H100) / 126 MB/die (Blackwell)  hardware cache, shared across SMs
HBM            80 GB HBM3 (H100) -> 192/288 GB HBM3e (B200/B300) -> ~288 GB HBM4 (Rubin)
```
[E: KB/GB as labeled; H100/B200 figures [F: vendor spec].] The two philosophies coexist on
one chip: **shared memory is the scratchpad half** (programmer places tiles explicitly —
the same bet as TPU VMEM/Trainium SBUF, but smaller and alongside a cache) and **L1/L2 are
the cache half** (hardware-managed). This hybrid is unique to NVIDIA among the six: AMD is
cache-dominant, TPU/Trainium/Cerebras/Groq are scratchpad-dominant. (Deep: `17`.)

## The data-movement progression
```
synchronous global loads      (G80->Kepler: thread issues LDG, waits on the value)
   -> cp.async (Ampere)        (copy global->shared ASYNC, decoupled from the consumer
                                 thread; the MMA can start on earlier tiles while later
                                 tiles stream in)
   -> TMA (Hopper)             (Tensor Memory Accelerator: a dedicated unit takes a
                                 *descriptor* (tensor coords, strides, box size) and moves
                                 a whole tile HBM<->SMEM with no per-element SM work;
                                 multicast across an SM cluster)
   -> Blackwell                (TMA continues; tcgen05 reads operands from TMEM/SMEM;
                                 more of the copy+compute pipeline is autonomously
                                 staged by the hardware)
```
Why this is a *design trend*, not just a feature list: each step removes data movement
from the critical path of the compute thread. In the cp.async era, one warp in the CTA
issued the copies and others did math; with TMA, copies are descriptor-driven bulk
operations that essentially "just happen", so the SM's instruction budget goes to the matmul
and the softmax. [I: mechanism; per-gen feature set [F: vendor spec]]

## Producer warps / consumer warps / warp specialization
The Hopper-era GEMM/attention kernel structure (`06`'s K-loop, made explicit):
```
CTA (e.g., 384 threads = 12 warps)
├── producer warps  -> issue TMA copies: stage A/B tiles (and K-chunk k+1) into SMEM
├── consumer warps  -> issue wgmma/tcgen05: consume staged tiles, accumulate D
└── mbarrier objects -> the handshake: producer arrives when a tile lands; consumer
                         waits on the barrier, signals when done with a stage
Pipeline: multi-stage ring buffer in SMEM (3+ stages typical) so that while the Tensor
Core computes stage i, the producer is staging stage i+1 and prefetching i+2.
```
- **Warp specialization:** some warps have a single job (move data) for the kernel's whole
  life; others have a single job (compute). No warp ever context-switches between roles,
  so no register/branch overhead, and each role is trivially scheduled.
- **mbarrier:** an async barrier with phases; unlike a CTA barrier it does not require all
  threads to arrive — a producer arrives *when data is ready*, a consumer arrives *when it
  is done*. This is the hardware primitive that makes software pipelining robust. [F: PTX docs]
- **Software pipelining:** the unrolling of the K-loop into the multi-stage ring buffer.
  Depth = number of in-flight K-chunks = SMEM budget / tile size. Deeper pipeline = more
  latency hidden, up to the point where HBM bandwidth (not latency) is the limit.

## What this buys (and costs) for LLM workloads
- **Prefill GEMMs:** deep K + fat tiles → the producer/consumer pipeline saturates HBM and
  Tensor Cores simultaneously; utilization is the engineering game
  (`../GPU-Systems/Profiling.md` measures it).
- **Decode:** the GEMV has no K-loop depth and small tiles; the pipeline has nothing to
  pipeline. The machine's advantage becomes *keeping HBM busy across many CTAs* — i.e.,
  batch size and kernel count, not Tensor Core depth. This is the structural reason
  batching is decode's main lever (`../Inference/Continuous-Batching.md`).
- **KV cache:** lives in HBM; attention kernels stream K/V tiles through SMEM with the same
  TMA/mbarrier machinery (FlashAttention-3 structure [F: arXiv:2407.08608]).
- **The cost of the hybrid:** maintaining two memory models (explicit SMEM + implicit
  L1/L2) is a real programming burden — tile layout, double-buffering, and barrier
  phases are where CUDA kernel bugs live. The scratchpad-only machines (TPU/Trainium)
  trade that burden for *compiler* burden instead (the schedule must be right; there is no
  cache fallback) (`17`).

## Numbers to keep
```
H100 SXM:  3.35 TB/s HBM, 989 TFLOP BF16 dense -> ridge ~295 FLOP/byte   [E, F]
B200:      ~8 TB/s HBM3e, 4.5 PF FP8 dense / 9 PF FP4 dense              [F: vendor spec]
Rubin:     ~13 TB/s HBM4 (projected), ~17 PF FP8 dense                   [F: vendor spec]
L2 H100 50 MB; SMEM 228 KB; registers 256 KB/SM                          [F: vendor spec]
HBM latency ~ hundreds of cycles; L1 hit ~1 cycle; SMEM ~1 cycle         [I: order-of-magnitude]
```
The ~600× spread [A: L1-vs-HBM gap estimate] between an L1 hit and an HBM miss is the whole motivation for the
tile-in-SMEM discipline: a well-tiled GEMM touches HBM ~2–3× (A, B, C) while doing
thousands of FLOPs per byte.

## Key Takeaways
1. NVIDIA uniquely runs *both* a hardware cache (L1/L2) and a software scratchpad
   (SMEM) — the cache hides latency, the scratchpad guarantees the matmul's tiles.
2. cp.async → TMA → Blackwell autonomy is one trajectory: data movement is being moved
   off the compute thread's critical path.
3. Producer/consumer warp specialization + mbarrier + multi-stage SMEM ring buffer is the
   canonical Hopper/Blackwell GEMM structure.
4. Decode has no pipeline depth to exploit — the machine wins it by keeping HBM busy
   across many CTAs, which is why batch size is the dominant decode knob.
5. The hybrid memory model is a burden as well as a power: kernel bugs cluster in tile
   layout and barrier phases.

## Related
- `05-nvidia-gpu-overview.md` — machine context; `06` — the compute side of the same tiles
- `../GPU-Systems/Memory-Hierarchy.md` — full engineering treatment
- `../GPU-Systems/FlashAttention.md` — the kernel that runs this machinery on attention
- `17-ai-chip-memory-philosophies.md` — cache vs scratchpad, cross-machine
- `../Inference/Roofline.md` — why the ridge point matters for tile choices

## References
- NVIDIA PTX ISA (cp.async, TMA, mbarrier [F])
- NVIDIA Hopper Architecture whitepaper (TMA, SMEM 228 KB [F: vendor spec])
- CUTLASS pipeline examples (producer/consumer [F: repo])
- FlashAttention-3 (arXiv:2407.08608) [F: bank]
- `../GPU-Systems/_STYLE.md` — H100 constants (cross-checked)
