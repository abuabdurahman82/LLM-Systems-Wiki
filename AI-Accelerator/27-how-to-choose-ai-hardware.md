# How to Choose AI Hardware — The Workload-Driven Decision Tree
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference. No universal winner: this page frames every recommendation as a *workload-dependent hypothesis* and states its failure conditions.

## 30-Second Explanation
The *question is not* "which chip is the *best? *It is:* *for* *which* *workload, *at* *which* *batch* *size, *at* *which* *latency* *target, *on* *which* *budget, *in* *which* *data center, *at* *which* *software maturity, *and* *what* *do I* *need* *the* *chip to* *do tomorrow? *This* *page* *is* the *decision* *tree: *seven* *questions, *each* *with* *the* *answer* *that* *eliminates* *half* *the* *field. *The* *tree* *is* *workload-driven,* *not* *spec-driven: *it* *asks* *about* *the* *workload* *first* *(page* *22), *the* *roofline* *second* *(page* *23), *the* *software* *third* *(page* *19), *and* the *silicon* *last. *The* *first-principles* *lesson:* **the* *chip* *is a* *consequence of* *the* *workload, *not a* *premise of* *it* — the *H100* *is* *the* *right* *chip* *for a* *batch-4,096* *prefill* *on* *CUDA, *and a* *wrong* *chip* *for a* *P99-latency* *chatbot, *and* *both* *answers are* *the* *same* *silicon, *which is why* *the* *decision* *is* *workload-shaped, *not silicon-shaped* [I].

## The seven questions (the tree)
**Q1. What is the workload?** (page 22)
- *Training* (batch-4,096+, compute-bound, ridge ≫ 400 FLOP/byte on H100-BF16 [E: p23]) → the HBM regime is *required* (the SRAM regime cannot hold the model; page 17). Candidates: H100/H200, MI300X, TPU v5p/Ironwood, Trainium2/3. *Eliminated:* Groq (SRAM cannot hold the training model at this scale [I]), Cerebras (wafer-scale is training-capable [F: Cerebras] but the ecosystem is limited [I]).
- *Batch-1/low-latency inference* (AI chat, agents, tool-calling; roofline-irrelevant, SRAM-friendly) → the SRAM regime is *favored* (page 17). Candidates: Groq (deterministic P99 [F: ISCA 2022]), NPU-class on-device, any HBM chip running small batch [I].
- *High-throughput batch inference* (the "AI factory" regime; page 24) → the HBM regime + the $/token metric (page 28). Candidates: H100/H200, MI300X, TPU, Trainium2/3 — *all four are viable*; the choice is on Q2–Q7.
- *Edge/on-device* → NPU (Apple, Snapdragon, AMD XDNA; page 26). The *flagships do not compete here* [I].

**Q2. What is the model size, and where do its weights live?** (pages 17, 21)
- [E] Llama-2-70B: 68.98B params → 68.98 GB INT8 / 137.95 GB FP16. One H100 (80 GB HBM) cannot hold it in FP16; two can (TP2). One Groq node (1.72 GiB SRAM [E: p14]) cannot hold it at all — 574–576 TSPs were needed for the 2023 INT8 deployment [F: Next Platform 2023-11-27, via p14]. *The rule:* [E] chips needed ≥ model_bytes / per_chip_capacity; the *interconnect must carry the all-reduce at decode* (page 18).
- *The elimination test:* if your model fits in one HBM stack, you are overpaying for a multi-chip fabric; if it does not fit in any SRAM, Groq is not a single-chip answer (it is a *cluster* answer, and the cluster's cost must be priced at Q5).

**Q3. What is the latency contract?** (page 16, page 22)
- *P99-bound* (chat, agentic loops, real-time voice) → scheduling matters more than peak (page 16). Groq's scheduled dataflow *removes the tail* [F: ISCA 2022]; the warp-scheduled GPU *has a tail* (the warp scheduler is hardware-driven; page 16). [I] A P99 contract is the *one workload where* the deterministic fabric buys a real premium — and it is priced at Q5.
- *Throughput-bound* (batch, offline) → the roofline dominates; peak and bandwidth are the spec (pages 22, 23); scheduling tails do not matter (the queue absorbs them [I]).

**Q4. What software stack am I running today?** (page 19)
- *CUDA-locked* (PyTorch+CUDA, cuDNN, NCCL, NIM) → NVIDIA is the *lowest-friction* answer; ROCm parity is real but the ecosystem depth differs (page 19) [F/I].
- *JAX/TF* → the TPU is the *lowest-friction* answer *inside GCP* [F: Google]; XLA also compiles to TPU and GPU [F: Google].
- *Framework-agnostic / on-prem* → the Neuron SDK (AWS, open) or ROCm (AMD, open) are the *open-software* paths [F: AWS, AMD]; Cerebras/Groq compilers are closed (page 19) [F].
- *The elimination test:* a closed ecosystem (Groq, Cerebras, TPU-on-GCP) is a *hard constraint* — you are buying the *service or the cloud*, not the chip (page 25).

**Q5. What is the budget: capex, opex, or both?** (pages 24, 28)
- *Capex* (on-prem) → NVIDIA/AMD (the chip is a product; DGX/HGX reference designs [F]); TPU on-prem exists via GDC/TPOD [F: Google, via p25] but the ecosystem target is GCP [I]; Trainium is EC2-only (capex not available [F: AWS]).
- *Opex* (cloud $/token) → the cloud-quadrant chips (TPU on GCP, Trainium on EC2, GroqCloud, Cerebras CS) are priced per-token; the *first-principles* comparison is **$ per useful token** at your batch size, not peak TFLOPS (page 28). [I]
- *The 80/20 anchor [E: p28]:* for a 70B-class model at batch-4,096 on H100, the HBM3 bandwidth (3.35 TB/s) sets the decode ceiling; for the same model at batch-1, the SRAM regime (Groq) competes on *per-token latency*, not throughput. *Budget follows the regime.*

**Q6. What is the data-center constraint?** (page 24)
- *Power* (kW/rack): DGX H100-class racks are ~41 kW [F, p24]; Groq's 8-TSP box is 3.3 kW [F: 2020 workshop deck, via p24] — the *same tokens at a fraction of the rack power* is the SRAM regime's factory argument (page 24).
- *Cooling*: NVL72/GB200-class systems are *liquid-cooled* (the rack power exceeds air-cooling [F/I: NVIDIA, p24]); an air-cooled data center *cannot host* the newest rack-scale systems — a hard physical constraint.
- *Fiber/fabric*: 10,440-TSP-class or Ironwood-class clusters need the inter-rack fabric sized at page 18; a *fabric-limited* data center cannot add the next rack.

**Q7. What do I need the chip to do tomorrow?** (the roadmap question, page 25)
- *Model growth* → the HBM capacity question (the 2027 model is 2–4× the 2026 model [I]); HBM4-class capacity (H200: 141 GB [F: NVIDIA]) is the *minimum* for the 2027 70B-class at FP16 on one chip [I].
- *Precision descent* → FP8/FP4 support (page 20): H100 (FP8 [F: NVIDIA]), B200 (FP4/NVFP4 [F: NVIDIA, via p20/21]); the older the silicon, the slower the precision-descent path.
- *Ecosystem drift* → the NVIDIA–Groq deal (page 25) shows *roadmaps can be bought*; a *service-only* chip's roadmap is the vendor's, not yours [I].

## The tree, collapsed (the hypothesis map)
| Workload shape | First-hypothesis chip | Why | The failure condition |
|---|---|---|---|
| Training, 100s-of-GB model, CUDA shop | H100/H200 HGX | Q1+Q2+Q4 all point here [F/I] | the $/token at scale vs TPU/Trainium must be checked (Q5); the P99 of *training* is not the P99 of inference (page 16) |
| Training, JAX shop, GCP | TPU v5p/Ironwood | Q4 lowest-friction [F: Google] | the on-prem/other-cloud requirement breaks Q4 |
| Batch-4,096+ prefill, throughput | H100/MI300X/TPU/Trainium all viable | Q1 compute-bound; roofline favors HBM3/3e ridge (page 23) | the *specific* winner depends on Q4 (stack), Q5 ($/token), Q6 (rack) — *no universal winner* [I] |
| P99-bound chat/agents, small batch | Groq (service) or on-prem NPU-class | Q3: scheduled fabric removes the tail [F: ISCA 2022] | the model must fit the SRAM cluster (Q2: 576-TSP-class for 70B-INT8 [F: NP 2023]); the closed ecosystem (Q4) and service-capacity (Q5) are the price [I] |
| On-device LLM | NPU (Apple/Snapdragon/AMD XDNA) | Q1 edge; page 26 | the model must fit on-device memory (a 7B INT8-class model, [I]) |
| AI factory at GW scale | the cloud-quadrant chip or DGX-class rack | Q5+Q6: $/token and kW/rack dominate (pages 24, 28) | the fabric (Q6) and the software (Q4) decide; the GW number is the spec (page 24) |

## How to use this tree (the discipline)
1. *Answer* *Q1–Q7* *in order; *each* *answer* *eliminates* *candidates — *do not* *skip* *Q1* (the *spec-sheet* *buyer* *skips* *Q1 and* *buys* *peak* *TFLOPS, *which is* *the* *workload-agnostic* *metric, page 22).
2. *Price at* *Q5* *with* *the* *80/20* *metric* (page 28): the *$/useful-token* *at your* *batch, *not the* *TFLOPS.
3. *Check* *Q6* *before* *Q7: the* *data center* *is a* *hard* *constraint* (the *power, *the* *cooling, *the* *fabric), *the* *roadmap* *is a* *soft* *constraint.
4. *State the failure condition of every recommendation* — the tree's output is *hypotheses with* *failure conditions, *not* *winners* (the *repo rule: no universal winners*).

## How to read this page against the others
- **vs. page 22 (workload mapping):** page 22 is the *roofline input* (the workload shapes); this page is the *decision* on those shapes.
- **vs. page 23 (roofline):** the roofline is Q1+Q2's *quantitative* engine.
- **vs. page 19 (software stacks):** Q4 is page 19's *escape-hatch* question, decision-shaped.
- **vs. page 25 (ecosystem strategies):** Q4/Q7's *hard constraints* are page 25's quadrants.
- **vs. page 28 (80/20):** Q5's pricing metric is page 28's core.
- **vs. page 29 (zero-to-hero):** this tree is *level 9* of page 29's path (the *architecture* *choice* *is the* *final* *level).
