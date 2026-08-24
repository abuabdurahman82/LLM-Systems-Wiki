# AI Chip Architecture 80/20 — The 20% That Explains 80% of the Field
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference.

## 30-Second Explanation
The *field* *is* *large* (six *flagships,* *three* *regimes,* *five* *scheduling* *styles,* *four* *precision* *formats,* *two* *memory* *philosophies,* *three* *interconnect* *topologies,* *four* *software* *stacks, *plus* *the* *tail). *But* *almost* *all* *of* *it* *collapses* *into* *five* *first-principles* *facts:*
1. *The* *AI* *workload* *is* *a* *matmul* *with a* *memory* *footprint* *(pages* *02,* *22).*
2. *The* *memory wall* *is* *the* *first-order* *constraint* *(page* *03);* *the* *roofline* *is* *the* *first-order* *model* *(page* *23).*
3. *The* *chip* *is* *a* *point* *in a* *design space, *not* *a* *product: (precision, *compute, *on-chip memory, *off-chip bandwidth, *scheduling, *interconnect, *power) [E: this section].
4. *The* *scheduling* *is* *the* *second-order* *differentiator* (page 16): *hardware-scheduled* vs *software-scheduled* *is* *the* *P99* *question.
5. *The* *software/eco system* *is the* *third-order* *differentiator* (pages 19, 25): *the* *chip* *is* *the input; the* *stack* *is the* *product.
*The* *80/20* *is this:* **know these five facts and the roofline, *and you* *can* *reason about any chip in the* *field — *the* *H100, *the* *TSP, *the* *WSE, *the* *TPU, *the* *MI300X, *the* *Trainium* — *from first principles, *without memorizing a* *spec* *sheet.* *The* *rest* *is* *detail: *the* *exact* *TFLOPS,* *the* *exact* *topology, *the* *exact* *core* *count* (the *20%* *that the* *vendor* *markets* *and the* *buyer* *ignores, *page 27). *This* *page* *is* *the* *distillation: *five* *facts, *five* *consequences, *and the* *twenty* *questions* *a* *chip* *expert* *can answer* *from them.

## The five first-principles facts
**Fact 1. The AI workload is a matmul with a memory footprint.** (pages 02, 22)
*The* *transformer* *layer* *is* *a* *matmul* *(the* *linear* *projections), *a* *softmax* *(the* *attention, *page 22), *and a* *residual* *add; *the* *memory* *footprint* *is* *the* *weights (the* *model) *plus* *the* *KV cache* *(decode, *page 17) *plus* *the* *activations (prefill, *page 22). *Every* *chip* *in* *the* *field* *is* *a* *machine* *that* *moves* *those* *bytes* *and* *does* *the* *matmul* — *the* *H100* *moves* *them* *between HBM* *and* *the* *Tensor Core, *the* *TSP* *moves* *them* *between* *SRAM slices* *and* *the* *MXM, *the* *WSE* *moves* *them* *between* *SRAM* *and* *the* *core* *(no off-chip move), *the* *TPU* *moves* *them* *between HBM* *and* *the* *systolic* *array. *The* *workload* *is* *invariant; *the* *machine* *is* *the* *variable* [I].

**Fact 2. The memory wall is the first-order constraint; the roofline is the first-order model.** (pages 03, 23)
*The* *compute* *grew* *faster* *than the* *bandwidth* *for* *twenty* *years* *(page* *01);* *the* *AI* *workload* *is* *the* *workload* *that* *meets* *the* *wall* *(the* *matmul* *is* *the* *compute,* *the* *weights/KV* *are the* *bytes). *The* *roofline* *is the* *model:* [E] `achieved_FLOPs ≤ min(peak, bandwidth × arithmetic_intensity)`; *the* *ridge* *is* *the* *point* *where* *the* *two* *meet* *(H100-BF16: ~295 FLOP/byte, *H100-FP8: ~591, *page 23). *Every* *chip* *in* *the* *field* *has* *a* *ridge, *and the* *workload* *sits* *on one* *side of it* *(page 22's *prefill* *is* *above, *decode* *is* *below). *The* *chip* *is* *the* *ridge* *you* *pay* *for* [I].

**Fact 3. The chip is a point in a 7-axis design space.** (pages 15, 21)
*The* *seven* *axes: precision* *(INT8/FP16/BF16/FP8/FP4, *page* *20), *compute* *(the* *matmul* *engine), *on-chip* *memory* *(SRAM* *MiB–GB), *off-chip* *(HBM* *GB–TB/s, *or* *none), *scheduling* *(hardware warp* *vs software-scheduled, *page* *16), *interconnect* *(NVLink/Infinity/ICI/PCIe, *page* *18), *power* *(watts* *per chip/rack, *page* *24). *Every* *flagship* *is a* *point:* [E] H100 = (FP8/FP16, 989 TFLOPS BF16 dense, 50 MB L2 [F: NVIDIA H100 datasheet], 80 GB HBM3 @3.35 TB/s [F: p05], hardware warp, NVLink4 @900 GB/s [F: p18], 700 W TDP SXM5-class [F: NVIDIA]); *TSP* = (INT8/FP16, 737/184 TOPS/TFLOPS [E: p14], 220 MiB SRAM, *no HBM, *software-scheduled, *on-chip 64 streaming lanes @20 TiB/s aggregate [F: 2020 workshop deck], *inter-chip* *path* *is* *the* *compiler-scheduled* *Dragonfly, *3.3 kW/8-chip* *box [F: 2020* *deck]); *WSE-2* = (FP16/INT8, 40 GB on-wafer SRAM [F: Cerebras, p12], *no off-chip HBM, *hardware dataflow* *wavelets, *on-wafer* *NoC, *~850k* *dataflow* *cores [F: Cerebras], *CS-2* *system* *~25 kW-class [I]); *TPU v4* = (BF16/INT8, 32 GiB HBM2e @1.2 TB/s [F: ISCA 2023, p10] *—* *the* *TPU* *does* *have* *off-chip* *HBM, *it* *is* *the* *one* *HBM* *flagship* *on* *this* *list, *and the* *32 GiB* *is of the* *same* *order as the* *WSE-2's* *40 GB* *on-wafer* *SRAM, *so the* *"no off-chip" axis* *is* *WSE-only, *not TPU-only [I]). *The* *point* *is the* *chip; *the* *space* *is* *the* *field* [I].

**Fact 4. The scheduling is the second-order differentiator (the P99 question).** (page 16)
*The* *same* *matmul* *on* *the same* *bytes, *two* *schedulers: the* *warp* *scheduler* *(NVIDIA, *hardware-driven, *the* *tail* *is the* *OS/compiler/NCCL) *vs* *the* *software* *scheduler* *(Groq, *the* *tail* *is* *scheduled* *out, *the* *P99* *is* *the* *P50, *ISCA 2022 §5.4: BERT-Large P99 < 1,225 µs / P100 = 1,300 µs on 4 TSPs [F]). *The* *P99* *is the* *product* *for the* *chat/agent* *workload* (page 22); *the* *P50* *is* *the* *product* *for the* *batch* *workload. *The* *scheduling* *is* *the* *axis* *that* *separates* *the* *two* *products on the* *same* *silicon* [I].

**Fact 5. The software/ecosystem is the third-order differentiator (the moat question).** (pages 19, 25)
*The* *chip* *is* *the input; *the* *stack* *is* *the* *product: the* *CUDA* *developer* *is* *the* *reason, *not the* *Tensor Core* (page 25). *The* *escape* *hatches* *(page 19): the* *ROCm* *HIP, *the* *JAX/XLA, *the* *Neuron* *SDK, *the* *Groq/Cerebras* *API. *The* *quadrant* *(page 25): the* *open/open* (AMD), *the* *closed/open* (NVIDIA), *the* *closed-cloud* (Google/AWS), *the* *service* (Groq/Cerebras). *The* *ecosystem* *is* *the* *axis* *that* *separates* *the* *buyers on the* *same* *ridge* [I].

## The five consequences (what the five facts buy)
| Fact | Consequence (the 20% that does the 80%) | The 20% detail it makes unnecessary |
|---|---|---|
| 1 (matmul + memory) | you can *estimate* the FLOPs and bytes of any workload before you buy (page 22: Llama-2-70B prefill P=4,096, B=1 → 555 TFLOP, 135.6 GB weights [E]) | the vendor's "optimized for LLMs" claim |
| 2 (roofline) | you can *predict* which regime the workload is in (above/below the ridge; page 23: H100-FP8 ridge 591 → batch-1 decode at ~1 FLOP/byte is ~591× below) | the "peak TFLOPS" spec |
| 3 (design space) | you can *compare* any two chips on 7 axes (page 21's two matrices) without a 200-line spec sheet | the exact topology, the exact core count, the exact SRAM slice count |
| 4 (scheduling) | you can *predict* the P99 from the scheduler (hardware → tail; software → no tail; page 16) | the vendor's "low-latency" marketing |
| 5 (ecosystem) | you can *predict* the migration cost from the quadrant (page 25) | the "CUDA-compatible" marketing (the HIP port is real, the depth is not [I]) |

## The twenty questions (the expert's test)
*The* *five* *facts* *buy* *the* *answers* *to these* *twenty* *questions (the *80/20* *of the* *interview* *and the* *buying* *decision):
1. *What* *is the* *workload's* *arithmetic* *intensity? *→ Fact 1+2 (page 23).
2. *Is it* *above* *or* *below* *the* *ridge? *→ Fact 2.
3. *Does the model fit on-chip? *→ Fact 1+3 (page 17: Llama-2-70B-INT8 = 67.8 GB [E] → 1 HBM chip, 576 TSPs [F: NP 2023]).
4. *What* *is the* *bandwidth* *requirement* *at decode? *→ Fact 1 (the KV cache: Llama-2-70B GQA, 320 KiB/token FP16 [E: p17]).
5. *Which* *precision* *can* *the* *workload* *run in? *→ Fact 3 (page 20: the FP8 microscaling question).
6. *Is* *the* *accumulate* *in* *FP32? *→ Fact 3 (page 20: the FP8→FP32 accumulate).
7. *What* *is the* *on-chip memory? *→ Fact 3 (page 21 matrix A).
8. *What* *is the* *off-chip memory and bandwidth? *→ Fact 3 (page 21 matrix A).
9. *What* *is the* *ridge? *→ Fact 2 (page 23: 5 numbers).
10. *What* *is the* *scheduler? *→ Fact 4 (page 16).
11. *What* *is the* *P99/P50* *gap? *→ Fact 4 (ISCA §5.4 [F]).
12. *What* *is the* *interconnect* *and* *its* *bandwidth? *→ Fact 3 (page 18: NVLink4 900 GB/s, ICI, PCIe).
13. *Does the* *model* *fit in one* *node/rack? *→ Fact 1+3 (page 24).
14. *What* *is the* *collective* *pattern? *→ Fact 3 (the all-reduce at decode, page 18).
15. *What* *is the* *power* *per* *rack? *→ Fact 3 (page 24: 3.3 kW box vs ~120–165 kW DGX-H100 rack).
16. *What* *is the* *$/token* *at my* *batch? *→ Facts 2+5 (page 28's *pricing; *page 27's *Q5).
17. *What* *is the* *software* *stack* *maturity? *→ Fact 5 (page 19).
18. *What* *is the* *ecosystem* *quadrant? *→ Fact 5 (page 25).
19. *What* *is the* *roadmap* *risk? *→ Fact 5 (the NVIDIA–Groq deal, page 25 [F: press]).
20. *What* *is the* *failure* *condition of the* *choice? *→ the *tree* (page 27's *Q1–Q7).
*The* *twenty* *questions* *are the* *interview:* **answer* *them* *from* *the* *five* *facts, *and you* *are* *the* *expert; *memorize* *the* *spec* *sheets, *and you* *are the* *vendor's* *salesperson* [I].

## The 20% detail (what the five facts do NOT buy)
*The* *five* *facts* *buy* *the* *80%; *the* *20%* *detail* *is* *where* *the* *vendor* *markets:
- *the* *exact* *TFLOPS* *at* *each* *precision* *(the* *dense* *vs* *the* *sparse; the* *theoretical* *vs* *the* *achieved, *page 21's* *footnote) [F: vendors].
- *the* *exact* *topology* *(the* *NVLink* *ring, *the* *Infinity* *Fabric, *the* *ICI* *torus, *the* *Dragonfly, *the* *Boardfly, *page 18) [F: vendors].
- *the* *exact* *core/slice* *count* *(the* *132 SMs on* *H100,* *the* *45 SRFs on* *TSP, *the* *~850k–900k* *dataflow* *cores on* *WSE-2/3, page 12/14) [F: vendors].
- *the* *exact* *process* *node* *(the* *4 nm, *the* *7 nm, *the* *TSMC* *N4/N5, page 05–14) [F: vendors].
- *the* *exact* *benchmark* *number* *(the* *tokens/s* *at* *the* *exact* *batch, *the* *exact* *model; *page* *14's* *576-TSP* *Llama-2* *is* *the* *one* *verified* *number, *page 21's matrix B) [F: Next Platform 2023].
*The* *20%* *is* *the* *marketing, *and it* *is* *where* *the* *buyer* *gets* *confused* *(the* *spec* *sheet* *is* *the* *20% that* *the* *five* *facts* *make* *irrelevant) [I].

## How to read this page against the others
- **vs. page 27 (decision tree):** the tree is the *application* of the five facts; this page is the *facts*.
- **vs. page 23 (roofline):** Fact 2 is page 23's one-line summary.
- **vs. page 16 (scheduling):** Fact 4 is page 16's one-line summary.
- **vs. page 25 (ecosystem):** Fact 5 is page 25's one-line summary.
- **vs. page 21 (comparison matrices):** the matrices are Fact 3's *worked* form (the 7 axes, filled in for the six flagships).
- **vs. page 29 (zero-to-hero):** the *five* *facts* *are* *level* *5–6* of page 29's path (the *first-principles* *level); *the* *twenty* *questions* *are* *level* *8–9.
- **vs. page 31 (big idea):** the *five* *facts* *are* *the* *five* *of the* *eight* *axes* *in* *page 31's* *design* *space* (the *other* *three* *are* *the* *workload, *the* *data center, *the* *roadmap).
