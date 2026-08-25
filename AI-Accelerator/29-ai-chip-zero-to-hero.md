# AI Chip Zero-to-Hero — A 10-Level Learning Path
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference.

## 30-Second Explanation
*This* *page* *is* *the* *roadmap* *from* *binary* *arithmetic* *to* *architecture* *research, *in* *ten* *levels, *each* *with* *the* *deliverable* *(the* *thing* *you* *can* *do* *at* *the* *level) *and the* *page(s)* *that* *teach* *it. *The* *path* *is* *deliberately* *first-principles-ordered:* *the* *workload* *before* *the* *chip, *the* *roofline* *before* *the* *topology, *the* *scheduler* *before* *the* *fabric* (page 28's *five* *facts, *in* *learning* *order). *The* *levels* *are* *cumulative:* *level* *N* *assumes* *levels* *1–N-1; *the* *deliverable* *is* *the* *proof* *you* *have* *reached* *the* *level* (a *hand calculation, *a* *diagram, *a* *decision, *not a* *fact* *you* *remembered*). *The* *first-principles* *rule:* **at* *every* *level, *the* *deliverable* *is a* *number* *you* *computed* *or a* *decision* *you* *justified, *never a* *spec* *you* *recalled* — *the* *spec* *is* *the* *20% detail* (page 28); *the* *number* *is* *the* *80% [I].

## The ten levels
**Level 1. Binary arithmetic and the FLOP.** (pages 02, 20)
- *The* *content: the* *FLOP, *the* *MAC, *the* *2×MAC* *identity (a* *dot* *product* *of* *N* *is* *2N* *FLOPs), *and* *the* *matmul* *is* *2×M×N×K* *FLOPs. *The* *deliverable: compute* *the* *FLOPs* *of* *a* *70B* *layer* *(Q/K/V/O + the* *FFN, *d = 8,192): [E] a 70B layer ≈ **1.71 GFLOP/token** (the exact 7-GEMM count [E]); *the* *whole* *model* (80 layers, *Llama-2-70B) → [E] ~136.9 GFLOP/token. *The* *2-param* *shortcut* (2 × 68.98e9 = 137.95 GFLOP/token, *page* *22) *agrees* *within* *1%* — *use* *it.*
- *The* *pages: 02* *(workloads), 20* *(numerics).

**Level 2. The memory footprint.** (pages 03, 17)
- *The* *content: the* *bytes* *are* *the* *weights (param × bytes), *the* *KV cache (page 17's* *per-token* *formula), *and the* *activations. *The* *deliverable: compute* *the* *Llama-2-70B* *weight* *bytes* *at* *INT8* *and* *FP16:* [E] 68.98e9 × 1 B = **68.98 GB INT8**; 68.98e9 × 2 B = **137.95 GB FP16**; *and* *the* *KV cache* *at* *1,024* *tokens:* [E] 1,024 × 320 KiB/token (GQA 8 KV heads, *head_dim* *128, FP16 [E: p17]) = **320 MiB**.
- *The* *pages: 03* *(memory wall), 17* *(KV cache).

**Level 3. The roofline.** (page 23)
- *The* *content: the* *ridge, *the* *arithmetic* *intensity, *the* *`min(peak, bandwidth × AI)`* *law. *The* *deliverable: compute* *the* *H100-BF16* *ridge* *and* *the* *decode* *tokens/s:* [E] ridge = 989/3.35 ≈ **295 FLOP/byte**; *decode* *AI* ≈ 1 FLOP/byte (page 22) → *below* *the* *295 ridge* → *bandwidth-bound* → [E] 3.35e12 / 17.24e9 (the ⅛-shard, *page* *15) ≈ **~194 tok/s at 100% efficiency**, *~58–97 at* *30–50% [I] (the *roofline* *prediction, *page 23's *worked example).
- *The* *pages: 23* *(roofline), 22* *(workload mapping).

**Level 4. The memory hierarchy.** (pages 03, 15, 17)
- *The* *content: the* *SRAM vs HBM* *regime, *the* *bytes-per-bit, *the* *on-chip vs* *off-chip* *bandwidth* *gap. *The* *deliverable: compute* *the* *bandwidth* *gap:* [E] TSP SRAM 20 TiB/s [F: p14] vs H100 HBM3 3.35 TB/s [F: p05] ≈ **6×** (the *SRAM regime's* *bandwidth* *is* *the* *reason* *the* *decode* *AI* *sits* *above* *the* *ridge* *on the* *TSP); *and* *the* *capacity* *gap:* [E] 220 MiB SRAM [F: p14] vs 80 GB HBM [F: p05] ≈ **347×** (the *SRAM regime's* *capacity* *is* *the* *reason* *the* *70B* *model* *needs* *576* *TSPs, *page 21).
- *The* *pages: 03, 15* *(memory philosophies → page 17), 17.

**Level 5. The scheduling.** (page 16)
- *The* *content: the* *hardware warp* *vs software-scheduled* *dataflow, *the* *P99/P50* *question. *The* *deliverable: *explain, *in one* *paragraph, *why* *the* *TSP's* *P99* *is* *the* *P50* *(the* *schedule* *is* *computed* *at* *compile* *time; *the* *data* *arrives* *when* *it* *is* *scheduled, *not* *when* *the* *warp* *wins* *the* *arbiter); *and* *the* *ISCA* *number:* [F] BERT-Large P99 < 1,225 µs / P100 = 1,300 µs on 4 TSPs (ISCA 2022 §5.4 [F], page 14).
- *The* *pages: 16* *(scheduling), 14* *(Groq).

**Level 6. The interconnect.** (page 18)
- *The* *content: the* *NVLink/Infinity/ICI/PCIe* *hierarchy, *the* *on-chip vs* *off-chip* *bandwidth, *the* *collective* *pattern. *The* *deliverable: compute* *the* *all-reduce* *bandwidth* *requirement:* [E] at decode, *each* *chip* *must* *receive* *the* *reduced* *output* *of* *the* *attention* *(a* *d-dim* *vector* *per* *token, *per* *head); *the* *NVLink4* *900 GB/s* *total* [F: p18] *is* *the* *per-GPU* *aggregate; *the* *ICI* *per-chip* *bandwidth* *is* *the* *TPU's* *equivalent* (the *v4* *per-chip* *ICI* *Gb/s* *is* *UNVERIFIED, *page 18's *flag); *the* *first-principles* *number: *the* *PCIe* *4.0 x16* *32 GB/s* *is* *the* *floor, *the* *NVLink* *900 GB/s* *is* *the* *ceiling, *and the* *collective* *is* *the* *workload that* *lives* *on* *that* *ceiling.
- *The* *pages: 18* *(interconnects).

**Level 7. The numerics.** (page 20)
- *The* *content: the* *FP32 → BF16/FP16 → FP8 → FP4* *ladder, *the* *microscaling, *the* *FP32* *accumulate. *The* *deliverable: *explain, *in one* *paragraph, *why* *the* *FP8* *E4M3* *is* *the* *inference* *format* *(the *4× compute* *at* *half the* *bytes, *the* *microscaling* *recovers* *the* *dynamic* *range, *the* *FP32* *accumulate* *preserves* *the* *sum), *and* *why* *the* *FP4* *NVFP4* *is* *the* *next* *descent* *(the *2× compute* *at* *quarter the* *bytes, *the* *block-scaled* *is* *the* *precision* *safety).
- *The* *pages: 20* *(numerics).

**Level 8. The design space.** (pages 15, 21, 28)
- *The* *content: the* *7-axis* *design* *space* *(page 28's *Fact 3), *the* *two* *matrices* *(page 21), *the* *philosophies* *(page 15). *The* *deliverable: *place* *the* *six* *flagships* *on* *the* *7-axis* *space* *(the* *page 21* *matrices, *filled* *in), *and* *name* *the* *axis* *on which* *each* *flagship* *is* *the* *extreme* *(the* *TSP* *is* *the* *software-scheduling* *extreme, *the* *WSE* *is* *the* *on-chip-capacity* *extreme, *the* *H100* *is* *the* *off-chip-bandwidth* *extreme, *the* *TPU* *is* *the* *systolic* *extreme).
- *The* *pages: 15, 21, 28.

**Level 9. The workload and the decision.** (pages 22, 24, 27)
- *The* *content: the* *prefill/decode* *mapping* *(page 22), *the* *rack* *is* *the* *computer* *(page 24), *the* *decision* *tree* *(page 27). *The* *deliverable: *run* *the* *page 27* *tree* *for* *your* *workload:* *answer* *Q1–Q7, *name* *the* *first-hypothesis* *chip, *and* *state* *the* *failure* *condition. *The* *hand* *calculation: *the* *$/token* *at* *your* *batch* *(page 28's *Q5; *the* *kW/rack* *at* *your* *scale* *(page 24).
- *The* *pages: 22, 24, 27.

**Level 10. The research frontier.** (pages 26, 31)
- *The* *content: the* *tail* *(page 26), *the* *big* *idea* *(page 31). *The* *deliverable: *pose, *in one* *paragraph, *a* *first-principles* *question* *the* *flagships* *have* *not* *answered* *(the* *reconfigurable* *dataflow's* *determinism* *trade, *the* *CIM's* *precision* *limit, *the* *photonic* *matmul's* *energy, *the* *NPU's* *on-device* *ceiling), *and* *the* *measurement* *that* *would* *answer* *it. *The* *frontier* *is* *the* *space* *the* *five* *facts* *have* *not* *covered, *and the* *research* *is* *the* *five* *facts* *extended.
- *The* *pages: 26, 31.

## The cumulative check (the hero's test)
*At* *each* *level, *the* *hero* *is* *the* *person* *who* *can* *do the* *deliverable:*
| Level | The deliverable (the hero's test) |
|---|---|
| 1 | [E] the 70B forward pass ≈ 137.95 GFLOP/token (2-param shortcut) |
| 2 | [E] the 68.98 GB INT8 / 137.95 GB FP16; the 320 MiB KV at 1,024 tokens |
| 3 | [E] the 295 FLOP/byte ridge; the ~194 tok/s decode roofline (⅛-shard, 100% efficiency) |
| 4 | [E] the 6× bandwidth gap; the 347× capacity gap; the 576-TSP reason |
| 5 | the P99-is-P50 paragraph; the ISCA §5.4 number [F] |
| 6 | the all-reduce bandwidth paragraph; the 32 → 900 GB/s floor/ceiling [F] |
| 7 | the FP8-is-inference paragraph; the NVFP4 descent |
| 8 | the six-flagship placement on the 7-axis space; the extreme-axis naming |
| 9 | the Q1–Q7 run for your workload; the $/token and kW/rack |
| 10 | the frontier question and its measurement |

*The* *ten* *deliverables* *are* *the* *hero's* *test:* **pass* *them* *all, *and you* *can* *reason* *about* *any* *AI* *chip* *from* *first* *principles* (the *page 28* *eighty/twenty, *operationalized) [I].

## How to read this page against the others
- **vs. page 28 (80/20):** the *ten* *levels* *are* *the* *five* *facts* *in* *learning* *order* (the *facts* *are the* *content; *the* *levels* *are the* *path).
- **vs. page 27 (decision tree):** level 9 *is* *the* *tree, *operationalized.
- **vs. page 31 (big idea):** level 10 *is* *the* *big* *idea, *operationalized* (the *frontier* *is* *the* *space* *the* *big* *idea* *has* *not* *covered).
- **vs. the section README:** the *README* *is* *the* *map; this* *page* *is* *the* *route* (the *map* *tells* *you* *what* *is* *where; *the* *route* *tells* *you* *the* *order).
