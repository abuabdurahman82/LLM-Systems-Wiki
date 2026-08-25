# AMD Instinct / CDNA Architecture
`LAST_UPDATED: 2026-08-23` · Status: core page · `[F]` = AMD docs/press, [F: secondary] = reputable press.

## 30-Second Explanation
AMD's Instinct line is a *real GPU* — SIMT, wavefronts, a matrix engine, HBM — but its
architectural ambition lives **outside the compute unit**, in how many of them can be
bonded into one coherent package (chiplets), how much memory capacity it carries, and how
it participates in *open* interconnect standards. NVIDIA's innovation is inside the SM
(new tensor primitives, TMA, async MMA each generation); AMD's is in the package, the
memory, and the ecosystem. The market position as of 2026 is real: OpenAI (6 GW, Oct 2025)
and Meta (6 GW, Feb 2026) have both committed to gigawatt-scale MI450/Helios deployments
[F: AMD press releases, 2025-10-06 & 2026-02-24].

## Genealogy
| Gen | Year | Chips | Key facts |
|---|---|---|---|
| GCN (heritage) | 2012– | (Radeon) | the compute-unit lineage Instinct descends from; "wave64" since GCN [F: AMD docs] |
| CDNA 1 | 2020 | MI100 | first datacenter CDNA; first MFMA matrix cores; native BF16; 120 CUs; monolithic 7nm; 32 GB HBM2e [F: AMD] |
| CDNA 2 | 2021 | MI210/MI250(X) | dual-GCD MCM package; full-rate FP64 matrix (the Frontier/El Capitan HPC bet); 220 CUs on MI250X; 64 GB [F: AMD] |
| CDNA 3 | 2023 | MI300A/MI300X | **3D-stacked chiplets**: 8 XCDs hybrid-bonded (TSMC SoIC) onto IODs; FP8; 256 MB Infinity Cache; 192–256 GB HBM3/3e; 304 CUs; coherent CPU+GPU APU on MI300A; powered El Capitan (11,039 nodes) [F: AMD] |
| CDNA 3 refresh | 2024 | MI325X | same compute, HBM3E 256 GB @ 6.0 TB/s [F: AMD] |
| CDNA 4 | 2025 | MI350X/MI355X | native FP4/FP6 with **OCP MX microscaling**; mixable A/B precision in one MFMA; FP64 matrix halved (AI-first inflection); 256 CUs, 160 KB LDS, 288 GB HBM3E @ 8 TB/s [F: AMD] |
| CDNA "Next" (MI400) | 2026 | MI430X/MI440X/MI455X | HBM4; **Helios rack** (72-GPU MI455X, UALink-over-Ethernet at launch, native UALink from 2027) — AMD's first rack-scale scale-up domain, answering NVL72 [F: AMD/Advancing AI 2026] |

## Terminology map (AMD ↔ NVIDIA)
| AMD | NVIDIA |
|---|---|
| Compute Unit (CU) | Streaming Multiprocessor (SM) |
| Wavefront (wave64: 64 threads) | Warp (warp32) |
| Matrix Core | Tensor Core |
| MFMA (wavefront-issued) | mma.sync / wgmma / tcgen05.mma |
| VGPR / SGPR | register file |
| LDS (Local Data Share, 64 KB, software-managed) | SMEM (shared memory) |
| Infinity Fabric (IF) | NVLink-class role |

The wave64 detail matters: a wavefront is 64 lanes across 4×16 SIMDs [E], and **a half-empty [A: typical utilization]
wave64 wastes 32 lanes where a half-empty warp32 wastes 16** — the divergence tax of CDNA.
For uniform control flow it is a small price; for irregular work it hurts. [I: analysis]

## The CU, and what did *not* change
Per CU: four 16-lane SIMDs (elementwise: activations, normalization, residuals, address
arithmetic), one shared scalar unit, a 64 KB LDS scratchpad, an L1 vector cache, a
per-SIMD VGPR file + CU-shared SGPR pool, and — since CDNA 1 — a **Matrix Core** running
MFMA. "The shape hasn't meaningfully changed since GCN in 2012; what scales is the *count*
(120 → 220 → 304 → 256 CUs) and the *packaging* that bonds them." [F: Peake article,
consistent with AMD product docs — the CU conservatism is the documented AMD stance.]

The matrix engine's curve vs NVIDIA's: NVIDIA's Tensor Core *climbed the thread hierarchy*
(warp → warp-group → single-thread async + 2-SM cluster); AMD's Matrix Core **stayed
wavefront-scoped** — one wave64 issues a single MFMA, the four SIMDs cooperate, operands
come from the wave's registers (A/B from VGPRs, C/D usually from a dedicated AGPR file).
CDNA 4 added a dedicated MFMA transpose-load from LDS (small in spirit to TMA), but the
matmul is still wave-issued. Consequences:
- **Overlap:** NVIDIA's async, descriptor-driven matmul decouples issue from execution —
  the issuer fires and runs softmax while the Tensor Core works. AMD's wave-collective
  MFMA means the issuing wave *cannot* do meaningful vector work while the matmul is
  pending; overlap must be staged across separate wavefronts with explicit barriers, in
  software. [I: kernel-engineer consensus, consistent with ISA docs]
- **Where it shows up:** pure dense GEMM (Frontier, El Capitan) — both engines saturate,
  async buys little, and AMD has historically led exascale HPC. Transformer attention
  (FlashAttention-3/4 interleaves matmul + softmax + KV reads) — the async overlap is the
  kernel's structure, and AMD recreates it by hand, lagging NVIDIA's hardware support.
  MoE dispatch, paged attention, speculative decode: same camp — address-irregular work
  that wants to run *alongside* the matmul. [I]

## Memory: the Infinity Cache and the capacity bet
```
LDS (64 KB, software-managed scratchpad, AMD's SMEM analog)
 -> L1 vector cache (16->32 KB)
 -> per-XCD L2 (few MB; NOT coherent across XCDs)
 -> Infinity Cache: 256 MB on MI300X, distributed across the IODs, 16-way,
    ~12 TB/s measured, >2x the HBM bandwidth on the same chip
 -> HBM (32 -> 64 -> 128 -> 192 -> 256 -> 288 GB across MI100..MI350X)
```
- **Infinity Cache** originated on RDNA gaming GPUs to compensate for narrow GDDR buses;
  AMD reused the IP for AI where attention KV reuse and weight reuse fit a large LLC
  unusually well. The architectural bet: *NVIDIA bought HBM bandwidth; AMD bought a cache*
  between L2 and HBM to absorb the reuse NVIDIA must hit HBM for. [F: AMD docs; Peake
  (measured ~12 TB/s, secondary cross-check)]
- **Capacity as strategy:** AMD has matched or beaten the contemporary NVIDIA flagship on
  HBM *capacity* every generation since 2021 (192→256→288 GB vs NVIDIA's 80→192→288).
  The thesis: inference is increasingly capacity-bound (large models, long contexts), and
  the chip with more memory wins the box-level inference market. 8× MI300X = 1.5 TB HBM
  vs 8× H100 = 640 GB — a 405B model in FP8 fits in one MI300X box; on 8× H100 it needs
  careful sharding. [E: 8×192=1536 GB vs 8×80=640 GB; F: capacity specs]

## Chiplets: where CDNA stops looking like NVIDIA
- **MI250X (CDNA 2):** first MCM — two GCDs side-by-side on 2.5D EFB, 4 in-package IF
  links at 400 GB/s aggregate, but *two separate GPUs* to software.
- **MI300X (CDNA 3):** the move. 8 XCDs (TSMC N5, ~115 mm²) stacked 3D via SoIC hybrid
  bonding onto 4 IODs (N6); each IOD hosts 2 XCDs above + 2 HBM stacks beside; IODs carry
  the Infinity Cache, HBM PHYs, IF links, PCIe; IF stitching across IODs at 4.8 TB/s
  bisection so the 153B-transistor package presents as **one GPU**. AMD got to 3D
  stacking a generation before NVIDIA (NVIDIA stayed monolithic through H100, went to two
  reticle dies on B200). [F: AMD docs; Peake (geometry, secondary)]
- **MI300A (the APU):** replace 2 XCDs with 3 Zen-4 CCDs; CPU and GPU share one physical
  address space with hardware coherence — no host-device copy, no pinned memory, no PCIe
  in the path. El Capitan (11,039 nodes × 4× MI300A) is the deployment that justified it.
  [F: AMD/LLNL]
- **MI355X (CDNA 4):** 8 XCDs (now N3P, 32 CUs each = 256 total, 160 KB LDS) on 2 wider
  IODs; 256 MB Infinity Cache (128 MB per IOD); IF bisection 5.5 TB/s; 12-Hi HBM3E,
  288 GB @ 8 TB/s; 185B transistors; still one GPU to the kernel. [F: AMD]

The thesis (verify, don't repeat as absolute): "NVIDIA puts significant innovation inside
the SM; AMD has also invested heavily in memory capacity, chiplets, package-level
integration, and open interconnect standards." The documented evidence: AMD's 3D-stacked
chiplet lead, the Infinity Cache, and the open-standards direction (UALink/UEC/OCP MX) —
while NVIDIA's per-SM tensor/async/TMA roadmap is the inside-the-SM bet. Both are true;
neither is universally better. [I: synthesis of AMD + NVIDIA documented roadmaps]

## Software: ROCm and the open-standards bet
```
ROCm (open-source, GitHub-native)
  HIP (CUDA-compatible C++; hipify ports bulk HPC at 80–95%, modern AI kernels worse)
  rocBLAS / hipBLASLt (cuBLAS/cuBLASLt) · MIOpen (cuDNN) · RCCL (NCCL)
  Composable Kernel / ck-tile (CUTLASS) · rocprofv3 (Nsight)
  Triton ROCm backend (AOTriton) · AITER (AMD operators)
  vLLM (dedicated ROCm CI: test pass 37% -> 93% across early 2026 [F: AMD])
  PyTorch first-class (eager since 2018; torch.compile lowers through Triton)
```
- **No XLA-style IR**: ROCm compiles direct to HIP/Triton/CK. The bet: Triton's Python DSL
  becomes the cross-vendor lingua franca, sidestepping the need for a CUDA-equivalent
  kernel ecosystem.
- **FlashAttention is the load-bearing case:** FA2 is production on MI300X (Composable
  Kernel); FA3 (Hopper-tuned) is partially supported via AITER+CK, Dao-AILab's canonical
  impl remains CUDA-only; **FA4 (Blackwell) has no ROCm port** — the tail where NVIDIA's
  moat is most durable. HipKittens (Hazy Research's MI355X port of ThunderKittens, 2025-11)
  claims forward-pass parity with AITER in ~500 lines. The pattern: open-source academic
  kernels close the AMD tail *months* after NVIDIA's, not years. [F: repos; Peake (secondary)]
- **The honest gap:** independent benchmarks (Phoronix, 2026-03) put ROCm 7.2 at 10–25%
  slower than equivalent CUDA on standard PyTorch/vLLM/SGLang workloads, at equivalent
  precision on equivalent silicon — "ROCm 7 reached feature parity but not perf parity."
  [F: secondary (Phoronix); treat as directional, not a universal constant]
- **CUDA-compat mapping** (full table in `19-ai-chip-software-stacks.md`):
  cuBLAS→rocBLAS, cuBLASLt→hipBLASLt, cuDNN→MIOpen, NCCL→RCCL, CUTLASS→Composable Kernel,
  Nsight→rocprofv3, CUDA→HIP, Triton→Triton-ROCm, TensorRT-LLM→(vLLM+AITER, no 1:1).

## Scale-up / scale-out: open standards, not vertical integration
- **Through MI355X, scale-up = the 8-GPU OAM box** over Infinity Fabric (7 IF links, 128
  GB/s each on MI300X → 896 GB/s per-GPU mesh; MI350X ~1,075 GB/s). Same OCP UBB 2.0
  mechanical socket as an NVIDIA HGX baseboard — server vendors ship AMD or NVIDIA in the
  same chassis.
- **The gap:** no rack-scale NVL72 equivalent through MI355X. Customers scaled across
  8-GPU boxes over Ethernet, paying scale-out latency for what NVIDIA users kept in
  scale-up. That gap matters for frontier *training*.
- **Helios (2H 2026):** AMD's first rack-scale domain — 72 MI455X GPUs, ~31 TB HBM4,
  1.4 PB/s aggregate HBM, 2.9 ExaFLOPS FP4 / 1.4 ExaFLOPS FP8, 260 TB/s scale-up, 43 TB/s
  scale-out; Open Rack Wide (Meta's OCP form factor); fabric is **UALink** (Ultra
  Accelerator Link, open consortium AMD helped found), tunnelled over Ethernet at launch
  (UALoE) with native UALink switching from 2027 (MI500).
- **Scale-out = Ethernet, no InfiniBand:** UEC (Ultra Ethernet Consortium) UET RDMA
  transport; Pensando NICs (Pollara 400, Vulcano 800); Broadcom Tomahawk 6 switch ASIC
  (AMD has no in-house switch/CPO — partner silicon). NVIDIA owns its entire network stack
  in-house; AMD bets open standards + best-of-breed partners outpace vertical integration.
  Dell'Oro: Ethernet handled >2× the AI scale-out fabric volume of InfiniBand in 2025.
  [F: AMD/UEC/OCP; Peake (Dell'Oro, secondary)]

## The AMD bets (condensed)
1. **HPC then AI** — full-rate FP64 matrix through CDNA 3, then bifurcate at CDNA 4 toward
   AI density (per-CU FP64 halved).
2. **Memory capacity** — match/beat NVIDIA on HBM capacity every gen since 2021 + 256 MB
   Infinity Cache.
3. **Early 3D stacking** — SoIC XCDs-on-IODs in 2023, a generation before NVIDIA.
4. **Coherent CPU+GPU** — MI300A APU, El Capitan as the proof.
5. **Open scale-up fabric** — UALink + OCP MX, not NVLink + proprietary FP4.

## Key Takeaways
1. AMD's innovation is *outside* the CU: chiplets, memory capacity, open interconnects —
   the CU itself is deliberately conservative (wave64 MFMA, unchanged since 2012).
2. The wave64 MFMA is wavefront-scoped and *not* async — the overlap gap that shows up on
   attention/MoE workloads, not on dense GEMM.
3. Infinity Cache (256 MB) + HBM capacity is the memory bet: reuse in a cache, capacity
   in HBM, vs NVIDIA's "more HBM bandwidth" bet.
4. Helios (72-GPU, UALink) is AMD's answer to NVL72, arriving 2H 2026 — closing the
   rack-scale training gap.
5. ROCm's open-standards strategy converges with NVIDIA on commodity workloads but lags
   on the frontier kernel tail (FA4, Blackwell primitives).

## Related
- `05-nvidia-gpu-overview.md` — the inside-the-SM counterpoint
- `11` companion; `19-ai-chip-software-stacks.md` — the full ROCm vs CUDA mapping
- `18-ai-accelerator-interconnects.md` — UALink/UEC vs NVLink/IB
- `../GPU-Systems/Architecture.md` — SIMT engineering
- `../Distributed-Inference/README.md` — why the 8-GPU-vs-rack gap matters

## References
- AMD Instinct MI100/MI250/MI300/MI350 product pages & CDNA docs [F: vendor]
- AMD press: OpenAI 6 GW (2025-10-06), Meta 6 GW (2026-02-24) [F: press]
- UALink 200G 1.0 (2025-04), UEC 1.0 (2025-06) [F: consortia]
- OCP MX microscaling spec (AMD, NVIDIA, Intel, Meta, Microsoft, Qualcomm, ARM) [F]
- El Capitan (LLNL) — 11,039 nodes × MI300A [F]
- Phoronix ROCm 7.2 benchmarks (2026-03) [F: secondary]
- Jacob Peake "AI Chip Architectures" (secondary anchor; geometry/claims cross-checked to AMD)
