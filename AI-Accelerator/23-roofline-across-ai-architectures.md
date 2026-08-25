# The Roofline Across AI Architectures — One Model, Six Ways to Move It
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
The *roofline model* (Williams, Waterman & Patterson, 2009 — originally for multicore CPUs, now the standard tool for GPUs and accelerators) says: *a kernel's* *achieved* *rate* is *capped by* *the* *minimum* *of* *two* *roofs*:
```
achieved = min( peak-FLOPS,  bandwidth × arithmetic-intensity )
```
*The* *roofline* is *the* *single* *most useful* *one-page* *model* in this *section*, *because* it *explains* *why* *the* *same chip* *is* *great at* *prefill* *and* *bad at* *batch-1 decode*, *and* *why* *the six* *architectures* *are* *in different places on* *the same chart*. This *page* *builds* *the roofline* *for the six* *chips* (the *peak* *roof* and the *bandwidth* *slope*, *both* *precision-dependent*, *page 20), *places* the *two* *LLM phases* (prefill, *decode), *and* *shows the* *six ways* *an* *architecture moves* *its* *position* on *the chart* (raise *the* *peak, *raise* the *slope, *change* the *workload's* *intensity, *change the* *precision, *eliminate* the *bandwidth roof* (SRAM regime), *or* *schedule* the *latency* (Groq).

## The model, restated
*The* *roofline* has *two* *parameters:
- *The* *peak* *roof* (*horizontal*): the *chip's* *maximum* *FLOP rate* *at the* *working precision* (*page* 20's *ladder).
- *The* *bandwidth* *slope* (*the* *rising* *line*): *bandwidth* (bytes/s) *× arithmetic* *intensity* (FLOP/byte). *A* *kernel* with *intensity* *I* *reaches* *bandwidth × I* *FLOP/s* *— the* *slope* *is* *the* *memory* *wall* (page* 03) *in* *FLOP* units.

*The* *ridge* *point* is *where the* *two* *roofs meet: at* *intensity* `= peak / bandwidth`, *the* *kernel* *switches* *from* *bandwidth-bound* *to* *compute-bound. Below* the *ridge, *the* *bandwidth* *rules; above* it, *the* *peak* *rules.*

*The* *six* *architectures'* *rooflines* (at *the* *stated* *precision*, *dense*, *per* chip; H100 appears once per precision):

| Chip | Peak roof [F] | Bandwidth [F] | Slope (FLOP/s per FLOP/byte) | Ridge point (FLOP/byte) [E] |
|---|---|---|---|---|
| NVIDIA H100 (BF16) | 989 TFLOPS | 3.35 TB/s | 3.35e12 × I | [E] 989e12 / 3.35e12 ≈ **295** |
| NVIDIA H100 (FP8) | 1,979 TFLOPS | 3.35 TB/s | 3.35e12 × I | [E] ≈ **591** |
| AMD MI300X (FP16) | ~1,307 TFLOPS | 5.3 TB/s | 5.3e12 × I | [E] ≈ **247** |
| Google TPU v4 (BF16) | ~275 TFLOPS | 1.2 TB/s | 1.2e12 × I | [E] ≈ **230** |
| Cerebras WSE-2 (FP16) | ~750 TFLOPS | on-wafer SRAM (not HBM; 20 PB/s aggregate for WSE-2 [F: p12]) | n/a (SRAM regime) | **no ridge — SRAM regime** [I] |
| Groq TSP (INT8) | ~737 TOPS | on-chip streaming 20 TiB/s aggregate [F: p14] | n/a (SRAM regime) | **no ridge — SRAM regime** [I] |
| AWS Trainium2 (cFP8) | ~1,300 TFLOPS (= 8 × 158 core-level [F: p13]) | 2.9 TB/s | 2.9e12 × I | [E] ≈ **448** |

*The* *first-principles* *read:* **the* *ridge point is* *the* *chip's* *batch-1 threshold.* *A* *batch-1 GEMV* (decode) *has* *intensity* *~1* (page* 22) *— far* *below* *every* *HBM* *chip's* *ridge* (230–591) *— so* *batch-1 decode* is *bandwidth-bound* *on* *every* *HBM* chip. *That* *one* *number* *is* *the* *entire* *memory* *wall* *argument* (page* 03) *made* *quantitative.

## Placing the two LLM phases
*Using* *page 22's* *intensities* for *Llama-2 70B:
- **Prefill** (*intensity* ~4,100 [E]): *above* *the* *ridge* of *every* *HBM chip* → *compute-bound*. The *achieved* rate *is* *the* *peak* (theoretical 100%; GEMM kernels realistically land near ~90%). *The* *FLOP* ceiling *is* the *limit.
- **Batch-1 decode** (*intensity* ~1 [E]): *below* *the* *ridge* of *every* *HBM chip* → *bandwidth-bound. The* *achieved* rate *is* *bandwidth × 1* (at 100% bandwidth efficiency — the ceiling), *i.e.,* *the* *HBM bandwidth* *in* *tokens/s* (page* 22's *formula). *The* *peak* *roof* *is* *irrelevant* (the *compute* *sits idle.

*The* *consequence:* **an* *HBM chip is* *wasted on* *batch-1 decode* — *its* *FLOPs* *are* *idle* *while* *the* *HBM* *streams.* The *SRAM* *chips* (Groq, *Cerebras) *eliminate* the *bandwidth roof* entirely (the *weights* are *already* in *the fastest* memory), *so* *the* *decode* *rate* is *set* by *the* *SRAM* *streaming* + *the* *schedule*, *not* *the* *HBM* [I].

## The six ways to move the roofline
*An* *architecture* *can* *improve* *its* *position on* *the* *roofline* in *six* *ways* (the *same* *six* *bets* from *page 15, *restated in* *roofline* terms):
1. **Raise the peak roof** (more FLOPs at the working precision): *NVIDIA* (the *Tensor Core* *ladder, FP16→FP8→FP4, page 20), *AMD* (the *matrix* *core). *Cost:* *power, *die area, *yield.
2. **Raise the bandwidth slope** (more HBM bandwidth): *H200* (141 GB HBM3e, 4.8 TB/s vs. H100's 80 GB, 3.35 TB/s [F: p05/21]), *MI300X* (5.3 TB/s). *Cost:* *HBM stack cost, *power.
3. **Change the workload's intensity** (make the kernel above the ridge): *batching* (the *decode batch* *raises* the *intensity* from ~1 to ~N, page 22), *continuous batching* (the *vLLM* *technique, the *GPU-Systems* section). *Cost:* *latency (batching *adds* the *P99).
4. **Change the precision** (raise both roofs at once): *FP16→FP8* *doubles* *the* *peak* *roof* (the *bandwidth* *roof* *does not move), *and halves* the *bytes-per-param,* *so* *the* *ridge* *doubles* *and* *the* *workload's* *intensity* *doubles* *in* *lockstep* (page* 20). *Cost:* *accuracy (recovered by *microscaling.
5. **Eliminate the bandwidth roof** (the SRAM regime): *Groq* (220 MiB/TSP, *no HBM), *Cerebras* (40 GB on-wafer). *The* *roofline* *degenerates:* *the* *bandwidth* *roof* *is* *the* *SRAM* *streaming* (orders* of *magnitude* *faster* *than HBM), *so* *the* *decode* *is* *compute- or schedule-bound.* *Cost:* *the* *model must fit* (the *aggregate* SRAM *bounds* the *model size, *page 17).
6. **Schedule the latency** (Groq's *third* *thing): even* *inside* *the SRAM* regime, *the* *Groq* *TSP* *schedules* the *inter-chip* *path*, *so the* *P99* *is* *known* *at compile time* (*the* *< 3 µs* *worst-case, page 18). *The* *roofline* *gains a* *latency* *dimension: the* *roof* *is* *not just* *the* *rate, *it is* the *known* *rate.* *Cost:* *the* *model must be compiled* (the *escape hatch* is *closed, *page 19).

*The* *first-principles* *read:* **the* *six* *ways are* *the* *six* *bets.* *NVIDIA* *bets* on *1+2+3* (raise *the roofs, batch the* *workload). *Groq* *bets* on *5+6* (eliminate *the roof, schedule* the *latency). *TPU/Trainium* *bet* on *4* (precision, *the* *per-flop* efficiency). *The* *roofline* *is* *the* *map* *that* *makes* the *bets* *visible.*

## A worked roofline (H100, Llama-2 70B)
*The* *H100* at *BF16* (989 TFLOPS, 3.35 TB/s, ridge ≈ 295 [E]):
- *Prefill* (intensity 4,100 [E]): *4,100 > 295* → *compute-bound.* Achieved ≈ *989 TFLOPS × efficiency.* At *~90%* GEMM efficiency [I]: [E] ~890 TFLOPS. A *4,096-token* prompt (565 TFLOP [E]: page 22) takes [E] 565e12 / 890e12 ≈ **~0.64 s** *on one H100* (in practice sharded across 8, faster).
- *Batch-1 decode* (intensity ~1 [E]): *1 < 295* → *bandwidth-bound.* Achieved ≈ 3.35e12 FLOP/s × 1 (per chip, at 100% bandwidth efficiency). The *token rate* is [E] 3.35e12 / 17.24e9 (the ⅛-shard, page 15) ≈ **194 tok/s at 100% efficiency**, ~58–97 at 30–50% [I].

*The* *two* *phases* *on the* *same* *roofline*: *prefill* *touches* the *peak roof* (the *989* *line); *decode* *touches* the *slope* (the *3.35* *line at* *intensity 1). *The* *chip* *is* *used* *at* *~90%* *of* its *compute* in *prefill* and *at* *only* *~0.3–0.6%* *of* its *compute* in *decode* (the *bandwidth* *is* *the* *limit, *the* *compute* *is* *idle). *That* *asymmetry* *is* *the* *reason* *for* *disaggregated prefill/decode systems* [I].

## How to read this page against the others
- **vs. page 03 (memory wall):** this page is the *roofline* restatement of page 03's *memory wall* (the *ridge point* *is* the *wall).
- **vs. page 22 (workload mapping):** page 22 is the *workload* side; this page is the *compute/memory* side.
- **vs. page 21 (comparison matrix):** this page *places* page 21's *chips* on *the roofline* (the *two* *columns: peak* and *bandwidth).
- **vs. page 15 (philosophies):** this page's *six ways* are the *six bets* in *roofline terms*.
- **vs. the GPU-Systems roofline page:** this page extends the *single-chip* roofline to *the six architectures* and to *the SRAM regime* (where the *roofline degenerates*).
