# The Big Idea — One Design Space, Eight Axes, No Universally Optimal Chip
`LAST_UPDATED: 2026-08-24` · Status: synthesis page (the section's conclusion) · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference.

## 30-Second Explanation
*The* *thirty* *pages* *of* *this* *section* *collapse* *into* *one* *picture:* *AI* *chips* *are* *not* *a* *ladder* *(bigger* *is* *better), *they* *are* *a* *space.* *Each* *chip* *is a* *point* *defined* *by* *eight* *axes* *(the* *five* *silicon* *axes* *of* *page* *28* *plus* *workload, *interconnect* *scope, *and* *deployment). *The* *six* *flagships* *are* *six* *different* *points,* *the* *tail* *(page* *26) *is* *the* *rest* *of the* *space, *and the* *"best* *chip"* *does* *not* *exist:* *for* *every* *workload* *(page* *22) *there* *is a* *region* *of* *the* *space* *where* *the* *roofline* *(page* *23) *and* *the* *memory* *wall* *(page* *03) *pick* *a* *winner, *and* *that* *region* *moves* *when* *the* *workload* *moves* *(training* *→* *prefill* *→* *decode, *the* *page* *22* *axis). *The* *big* *idea* *is* *not* *"which* *chip," *it* *is* *"which* *region*" [I].

## The eight axes
*Page* *28's* *five* *silicon* *axes* *(precision, *compute, *on-chip* *memory, *off-chip* *bandwidth, *scheduling) *plus* *three* *that* *the* *card* *cannot* *see:
| Axis | The question it answers | The page that quantifies it |
|---|---|---|
| 1. Precision | What format does the matmul run in (FP16/BF16/FP8/FP4/INT8)? | p20 |
| 2. Compute engine | What is the peak, at that precision, dense? | p05–14, p21 |
| 3. On-chip memory | How many MiB–GB of SRAM, and is it cache or scratchpad? | p17 |
| 4. Off-chip bandwidth | How many GB/s of HBM (or none, the SRAM regime)? | p17, p23 |
| 5. Scheduling | Who orders the data movement — hardware warp or software schedule? | p16 |
| 6. Interconnect scope | How many chips can it talk to at full speed (the pod)? | p18, p24 |
| 7. Workload match | Is the target workload compute-bound (prefill/train) or bandwidth-bound (decode)? | p22 |
| 8. Deployment | Where does the chip run — your data center, a cloud, or a service you only buy tokens from? | p24, p25 |

*The* *first* *five* *axes* *are* *the* *chip; *the* *last* *three* *are* *the* *system* *and* *the* *business. *A* *chip* *that* *wins* *on* *axes* *1–5* *but* *loses* *on* *8* *is* *a* *chip* *you* *cannot* *buy* *(TPU* *off-GCP, *Trainium* *off-EC2, *page* *25). *The* *deployment* *axis* *is* *the* *one* *the* *spec* *sheet* *never* *shows [I].

## The six flagships as points
*Placed* *on* *the* *eight* *axes* *(the* *values* *are* *the* *verified* *numbers, *page* *21's* *two* *matrices):
- *NVIDIA* *H100: *high* *on* *2* *(989/1,979 TFLOPS), *medium* *on* *3* *(50 MB L2), *high* *on* *4* *(3.35 TB/s, *80 GB), *low* *on* *5* *(hardware* *warp, *the* *tail* *is* *real), *medium* *on* *6* *(72-GPU* *NVL72), *high* *on* *7* *(prefill/training), *open* *on* *8* *(sold* *to* *everyone) [F: p05/18/24].
- *Groq* *TSP: *low* *on* *2* *(737 TOPS INT8 [E: p14]), *tiny* *on* *3* *(220 MiB), *zero* *on* *4* *(no* *HBM), *extreme* *on* *5* *(software-scheduled, *P99* *is* *P50, *ISCA* *2022), *extreme* *on* *6* *(the* *scheduled* *Dragonfly), *extreme* *on* *7* *(batch-1* *decode), *closed* *on* *8* *(service* *only) [F: p14/25].
- *Cerebras* *WSE-2: *high* *on* *2* *(~750 TFLOPS FP16/wafer [F: p12]), *extreme* *on* *3* *(40 GB on-wafer), *zero* *on* *4, *high* *on* *5* *(compiler-placed dataflow), *low* *on* *6* *(the* *wafer* *is* *the* *domain, *RealScale* *for* *more), *high* *on* *7* *(large-model* *inference), *closed* *on* *8* *(CS* *systems) [F: p12].
- *TPU* *v4/v7: *medium* *on* *2* *(275 TFLOPS v4 BF16 [F: ISCA 2023]; *4,614 TFLOPS v7 FP8 [F: Google]), *high* *on* *4* *(1.2→7.4 TB/s), *high* *on* *6* *(4,096→9,216-chip* *pods), *balanced* *on* *7, *closed-cloud* *on* *8* [F: p10/24].
- *AMD* *MI300X: *high* *on* *2* *(~1,307 TFLOPS dense/package [F: AMD spec]), *high* *on* *3* *(256 MB Infinity Cache), *high* *on* *4* *(5.3 TB/s), *low* *on* *5, *medium* *on* *6, *open* *on* *8* *(the* *ROCm* *escape* *hatch) [F: p11].
- *Trainium2: *medium* *on* *2* *(~1.3 PF FP8 dense/chip = 8 × 158 core-level cFP8 [F: AWS]), *high* *on* *4* *(2.9 TB/s), *high* *on* *6* *(64-chip* *UltraServer), *high* *on* *7* *(the* *$/token* *inference* *regime), *closed-cloud* *on* *8* [F: p13/24].

*The* *six* *points* *do* *not* *rank:* *the* *Groq* *TSP* *is* *"worse"* *on* *axes* *2–4* *and* *"better"* *on* *5–7* *than* *the* *H100, *in* *the* *same* *order. *There* *is* *no* *scalar* *that* *makes* *one* *dominate; *the* *space* *is* *genuinely* *multi-dimensional [I].

## Why no universally optimal chip exists
*Three* *independent* *arguments, *each* *one* *a* *first-principles* *proof:
1. *The* *roofline* *argument* *(page* *23): *the* *same* *chip* *sits* *on* *different* *parts* *of* *its* *own* *roofline* *for* *different* *workloads* *(prefill* *on* *the* *peak* *roof, *decode* *on* *the* *bandwidth* *slope, *page* *22's* *4,100* *vs* *1 FLOP/byte). *A* *chip* *optimized* *for* *the* *peak* *roof* *(the* *H100's* *989* *TFLOPS) *is* *wasted* *on* *the* *slope* *(its* *compute* *is* *idle* *at* *decode); *a* *chip* *optimized* *for* *the* *slope* *(the* *SRAM* *chips, *which* *eliminate* *the* *bandwidth* *roof) *is* *wasted* *on* *the* *peak* *(their* *SRAM* *cannot* *hold* *the* *batch* *N* *training* *set). *The* *two* *regimes* *want* *different* *silicon [E: p22/23].
2. *The* *memory* *argument* *(page* *03/17): *the* *weights* *are* *the* *fixed* *footprint,* *the* *KV* *cache* *is* *the* *variable* *footprint,* *and* *the* *two* *have* *opposite* *sizing* *pressures* *(weights* *want* *capacity, *KV* *wants* *headroom). *The* *HBM* *chip* *solves* *it* *with* *192 GB* *and* *5.3 TB/s; *the* *SRAM* *chip* *solves* *it* *with* *a* *576-chip* *cluster* *and* *a* *compiler. *Both* *solutions* *are* *right* *for* *their* *regime; *neither* *is* *right* *for* *both [E: p17].
3. *The* *deployment* *argument* *(page* *24/25): *the* *rack* *is* *the* *computer* *(the* *kW/rack, *the* *cooling, *the* *fabric), *and* *the* *GW* *is* *the* *spec* *(the* *AMD* *6 GW* *OpenAI/Meta* *clusters, *the* *Groq* *4.3 MW* *10,440-TSP* *system, *page* *24). *A* *chip* *that* *is* *optimal* *at* *the* *card* *level* *may* *be* *unbuildable* *at* *the* *rack* *level* *(the* *TDP* *does* *not* *fit* *the* *cooling, *the* *fabric* *does* *not* *fit* *the* *cable), *or* *unbuyable* *at* *the* *cloud* *level* *(the* *deployment* *axis, *page* *25). *The* *silicon* *that* *wins* *the* *datasheet* *may* *lose* *the* *datacenter [I].

*The* *synthesis:* **the* *optimal* *chip* *is* *a* *function* *of* *the* *workload,* *not* *a* *constant.* *The* *page* *27* *decision* *tree* *(Q1–Q7) *is* *the* *procedure:* *answer* *the* *questions, *and* *the* *region* *of* *the* *space* *is* *the* *answer* — *never* *a* *brand [I].

## The one design space, drawn
*The* *eight* *axes* *make* *a* *space,* *the* *six* *flagships* *are* *six* *points,* *and the* *workloads* *are* *regions:*
```
                 precision
                   |
  on-chip memory  |   compute
      (SRAM)      |  (peak)
        +---------+---------+  off-chip (HBM)
        |  Groq   | H100    |
        | Cerebras| MI300X  |   <-  the HBM regime (high peak, high bandwidth)
        +---------+---------+
        |  TPU    | Trainium|
        | (v4/v7) | (Trn2/3)|
        +---------+---------+
        |  NPUs   | DPUs    |
        +---------+---------+   <-  the edge / peripheral regime (low watt, small model)
   scheduling (hardware <-> software)    x    interconnect (card <-> pod)    x    deployment (open <-> service)
```
*The* *HBM* *regime* *occupies* *the* *top* *half; *the* *edge* *regime* *the* *bottom; *the* *scheduling* *axis* *splits* *each* *row* *(the* *Groq/Cerebras* *column* *is* *software-scheduled, *the* *rest* *is* *hardware); *the* *deployment* *axis* *splits* *each* *row* *again* *(the* *open* *left* *half, *the* *closed* *right* *half). *Every* *chip* *in* *the* *field, *including* *the* *tail* *(page* *26), *sits* *in* *one* *cell [I].

## What the big idea is (and is not)
*It* *is:* *a* *map* *that* *predicts* *why* *each* *vendor* *makes* *the* *silicon* *it* *makes* *(NVIDIA* *raises* *the* *peak, *Groq* *schedules* *the* *latency, *Cerebras* *grows* *the* *SRAM, *TPU/Trainium* *descend* *the* *precision, *page* *23's* *six* *ways); *a* *map* *that* *explains* *why* *no* *deal* *is* *a* *concession* *(the* *NVIDIA–Groq* *deal, *~$20.6B* *Dec* *24 2025 [F: press], *is* *NVIDIA* *buying* *a* *point* *in* *the* *space* *it* *did* *not* *own: *the* *scheduled-dataflow* *cell); *and* *a* *map* *that* *tells* *you* *where* *the* *next* *chip* *will* *come* *from* *(the* *empty* *cells: *software-scheduled* *HBM* *chips, *the* *open* *SRAM* *cluster, *the* *edge* *dataflow).
*It* *is not:* *a* *winner.* *The* *space* *has* *no* *center, *no* *scalar* *rank, *no* *"the* *best* *AI* *chip."* *Any* *page* *in* *this* *section* *that* *names* *a* *winner* *for* *all* *workloads* *is* *wrong; *any* *page* *that* *names* *a* *winner* *for a* *stated* *workload* *(with* *batch, *P99, *precision, *and* *deployment* *stated, *page* *22's* *four* *qualifiers) *is* *correct.* *That* *is* *the* *80/20* *(page* *28) *in* *one* *sentence: *know* *the* *space, *state* *the* *workload, *and* *the* *answer* *follows* — *the* *spec* *sheet* *is* *the* *detail [I].

## How to read this page against the others
- **vs. page 15 (philosophies):** page 15 is the *six bets*; this page is the *space the bets occupy* (the six points, and the empty cells).
- **vs. page 23 (roofline):** page 23 is the *two-roof model*; this page adds the *axes that move the roofline* (the six ways, plus the deployment axis the roofline cannot see).
- **vs. page 28 (80/20):** the *five facts* *in* *page* *28* *are* *the* *five* *silicon* *axes* *of* *this* *page, *restated* *as* *facts; *this* *page* *adds* *the* *three* *system* *axes.
- **vs. page 30 (provenance):** *the* *eight* *axes* *are* *the* *synthesis* *of* *the* *audit: *every* *axis* *is* *traceable* *to a* *primary* *source, *never* *to* *the* *seed.
- **vs. the section README:** *the* *README* *is* *the* *map; *this* *page* *is* *the* *claim* *the* *map* *supports.
