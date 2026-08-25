# AI Hardware Ecosystem Strategies — Open vs. Vertically Integrated
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
The *silicon* *is* *half* *the* *product. *The other* *half* *is* *the ecosystem: *the* *software* *stack, *the* *compiler, *the* *collectives* *library, *the* *reference* *designs, *the* *developer* *momentum, *and the* *cloud* *integration. *This* *page* *maps* *the* *six* *vendors' ecosystem* *strategies on* *two* *axes:
- *Axis 1 (openness):* *is the* *software* *open-source* (NVIDIA CUDA *is* *binary-only; ROCm is open; Neuron is open; XLA is open; Groq and Cerebras compilers are closed)?
- *Axis 2 (vertical integration):* *does the vendor own the stack end-to-end* (Google owns *TPU + XLA + GCP + JAX/TF*; AWS owns *Trainium + Neuron + EC2*; *NVIDIA* *owns* *GPU + CUDA + NVLink + DGX + NIM*; AMD *sells* *to* *the* *ecosystem* (OEMs, *clouds); *Groq* *owns* *chip + compiler + cloud* (GroqCloud); *Cerebras* *owns* *wafer + compiler + CS system)?

*The* *first-principles* *lesson:* **the* *ecosystem* *is the* *moat, *and the* *moat* *is built* *at the* *software* *layer, *not the* *silicon* *layer* (the *silicon* *is* *a* *commodity, *the* *stack* *is* the *product). *A* *chip* *can* *be* *beaten* *on the* *spec sheet; *an* *ecosystem* *cannot* (the *CUDA* *developer* *is* *the* *reason, *not* the *Tensor Core). *But* the *ecosystem* *also* *is a* *liability: it* *locks in* *the* *workloads* *and* *the* *software, *and a* *new* *silicon* *bet* *(Groq, *Cerebras) *has to* *build* *the ecosystem* *from* *scratch* (which *is why* they *sell a service, *not the* *silicon) [I].

## Axis 1 — Openness
| Vendor | Software stack | Open-source? | Compiler open? | Escalation: what a new user installs first |
|---|---|---|---|---|
| NVIDIA | CUDA + cuDNN + cuBLAS + NCCL | binary-only (PTX ISA is documented; the CUDA toolkit is proprietary) | closed (nvcc) | the CUDA toolkit + PyTorch [F: NVIDIA] |
| AMD | ROCm + HIP + ROCBLAS + MIOpen + RCCL | **open-source** (ROCm is Apache-2.0) | open-source (ROCm compiler) | ROCm + hipify + PyTorch [F: AMD] |
| Google | XLA + JAX/TF + TPU runtime | XLA is open-source; JAX is open-source; the TPU *runtime* is GCP-locked | open-source (XLA), but the *TPU target* is GCP-only | JAX + TF + a GCP account [F: Google] |
| AWS | Neuron SDK (compiler + runtime) | **open-source** (the Neuron compiler and SDK are Apache-2.0) | open-source | Neuron SDK + PyTorch/JAX, on EC2 [F: AWS] |
| Groq | Groq compiler + Groq API | closed | closed | the GroqCloud API (no on-prem install) [F: ISCA 2022] |
| Cerebras | Cerebras CS-3 compiler + PyTorch/JAX front-ends | front-ends open; compiler closed | closed | the Cerebras CS system + their compiler [F: Cerebras] |

*The* *first-principles* *read:* **openness** *is a* *developer-attraction* *lever, *and it* *works* *best when the* *silicon* *is* *commodity* *(AMD, *AWS: the* *open* *stack* *is* the *way to* *win* *the* *developer*). *It* *works* *worst* *when the* *silicon* *is* *the* *differentiator* *(Groq, *Cerebras: the* *closed* *compiler* *is* *the* *product, *and the* *service* *is* the *delivery). *NVIDIA* *is the* *outlier: a* *binary-only* *stack* *with the* *largest* *ecosystem* *— the* *momentum* *is so* *large* *that* *the* *openness* *is* *irrelevant* (the *developers* *install* *CUDA* *because it* *is* *CUDA, *not because it* *is open) [I].

## Axis 2 — Vertical integration
| Vendor | Owns the chip | Owns the software | Owns the cloud | Owns the reference system | The integration depth |
|---|---|---|---|---|---|
| NVIDIA | yes (TSMC fab) | yes (CUDA) | no (sells to clouds) | yes (DGX, HGX) | *deep* on chip+software, *open* on cloud [F] |
| AMD | yes (TSMC fab) | yes (ROCm) | no (sells to clouds/OEMs) | partial (EPYC+MI300 APU; sells to OEMs) | *deep* on chip, *open* on software, *open* on cloud [F] |
| Google | yes (TSMC foundry [A: historical; no foundry stated in verified TPU sources]) | yes (XLA) | **yes** (GCP) | yes (TPU pods on GCP) | *deepest* integration: chip→software→cloud→system [F] |
| AWS | yes (TSMC fab) | yes (Neuron) | **yes** (EC2) | yes (UltraServer) | *deep* on chip→software→cloud, *cloud-locked* [F] |
| Groq | yes (14 nm GlobalFoundries [F: 2020 workshop deck, p14]) | yes (closed compiler) | **yes** (GroqCloud) | n/a (service only) | *service-integrated*: the chip is *internal* to the service [F: ISCA 2022] |
| Cerebras | yes (TSMC fab, wafer-level) | yes (closed compiler) | no (sells CS systems) | yes (CS-1/CS-2/CS-3) | *system-integrated*: the wafer is the system [F: Cerebras] |

*The* *first-principles* *read:* **vertical integration** *is the* *latency-and-cost* *advantage, *but it* *is the* *cloud-lock* *liability.* *Google* *and* *AWS* *own* *the* *cloud, *so* the *chip* *is* *optimized* *for* *their* *cloud's* *workloads. *Trainium* *is* *strictly* *EC2-locked* (no on-prem path in the verified sources) [F: AWS]; *TPU* *has* *an* *on-premises* *path* *(TPU* *in* *GDC / TPOD deployments, *per* *Google* *TPU* *docs) *but* *the* *primary* *target* *is* *GCP* [F: Google, via p10] (TPU-on-Azure, *announced* *late* *2024, *is* *UNVERIFIED* *against* *the* *primary* *sources* *verified* *here). *NVIDIA* *and* *AMD* *sell* *the* *chip* *to* *the* *clouds, *so* the *chip* *is* *optimized* *for* *the* *clouds'* *workloads* *and* *the* *clouds* *own* *the* *integration* *(the* *DGX* *on* *Azure, *the* *MI300* *on* *Oracle/AMD-own). *Groq* *and* *Cerebras* *are* *the* *opposite* *extreme: they* *own* *the* *service, *and* the *chip* *is* *a* *component* *of* the *service* (the *user* *never* *sees* *the* *chip, *only the* *token) [I].

## The strategy matrix
*Combining* *the* *two* *axes* *gives* *the* *strategy matrix* (the *cloud axis* *has three* *cells, *because* *"sell the* *token"* *is a* *third* *cloud* *posture, *not a* *fourth* *combination of the* *two* axes):
| | Open software | Closed software |
|---|---|---|
| **Open cloud (sell to clouds)** | **AMD** (ROCm open, sells to clouds/OEMs) | **NVIDIA** (CUDA closed, sells to clouds) — the *momentum* *overrides* the *closedness* [I] |
| **Closed cloud (own the cloud)** | **AWS** (Neuron open, but EC2-locked) | **Google** (XLA open, but GCP-locked) — the *cloud* *is* the *lock, *the* *software* *openness* *is* *a* *courtesy* [I] |
| **Service (sell the token)** | — | **Groq** (closed compiler, service-only), **Cerebras** (closed compiler, CS systems) [F] |

*The* *first-principles* *read:* **the* *cell* *is* the *business* *model, *and the* *silicon* *is* *the* *input.* *AMD* *is the* *only vendor* *in the* *open/open* *cell* *— that* *is its* *position* (the *ROCm* *parity* *is the* *product). *NVIDIA* *is* *the* *closed/open* *cell* *with the* *largest* *ecosystem* *— the* *CUDA* *momentum* *is the* *product. *Google* *and* *AWS* *are* *the* *closed-cloud* *row* *— the* *cloud* *lock* *is the* *product. *Groq* *and* *Cerebras* *are* *the* *service* *row* *— the* *token* *is the* *product. *The* *silicon* *spec* *is* *the same* *question* *in* *all cells, *but the* *ecosystem* *answers it* *differently* [I].

## What each strategy buys and costs
| Strategy | Buys | Costs |
|---|---|---|
| Open/open (AMD) | the developer, the cloud, the OEM (the widest market) | the per-chip differentiation (the silicon is a commodity; the ROCm parity is the moat, not the chip) [I] |
| Closed/open (NVIDIA) | the momentum (the CUDA developer is the moat) | the flexibility (the binary stack is slow to add new features; the closedness is a tax on the open-source community) [I] |
| Closed-cloud (Google/AWS) | the end-to-end optimization (chip→software→cloud→system, the lowest $/token at scale) | the portability (the chip is cloud-locked for most users — Trainium has no on-prem path; TPU has a limited on-prem path via Google Distributed Cloud/TPOD, but the toolchain is GCP-native; the workloads are cloud-shaped) [I] |
| Service (Groq/Cerebras) | the determinism (the closed compiler + the owned cloud = the known P99) | the market (the service is the product; the silicon is not a product; the scale is limited by the service's capacity) [I] |

*The* *first-principles* *read:* **the* *strategy* *is a* *bet on* *where* *the* *value* *is* (the *silicon, *the* *stack, *the* *cloud, *or the* *token). *The* *silicon* *spec* *is* *the* *same* *question* *in* *all four; *the* *ecosystem* *answers it* *differently, *and the* *answer* *is the* *business model.*

## The NVIDIA–Groq deal (2025-12-24) through this frame
The *~$20.6B* *licensing* *deal* (page 14) *is* *an* *ecosystem* *event, *not a* *silicon* *event: *NVIDIA* *(the* *closed/open* *quadrant) *buys* *the* *service* *quadrant's* *determinism* *IP* (the *Groq* *scheduled* *fabric), *while* *Groq* *keeps* *the* *service* *and* *loses* *the* *silicon* *roadmap* (the *TSP* *v2* *becomes* *an* *NVIDIA* *chip, *rumored) [F: press; *UNVERIFIED* *on* the *v2 details]. *The* *strategic* *read* [I]: *NVIDIA* *buys* *the* *P99* *guarantee* *that its* *own* *stack* *cannot* *offer* (the *CUDA* *warp* *scheduler* *is* *hardware-driven, *not* *scheduled), *and* *Groq* *keeps* *the* *revenue* *(the* *service) *while* *selling* *the* *design* *IP. *It* *is the* *first* *time* *a* *service-quadrant* *vendor* *has* *sold* *its* *architecture* *to a* *silicon-quadrant* *vendor* *— the* *quadrants* *are* *not* *hereditary; *they are* *traded* [I].

## How to read this page against the others
- **vs. page 19 (software stacks):** page 19 is the *technical* side (the stack, the compiler, the escape hatch); this page is the *strategic* side (the quadrant, the moat, the business model).
- **vs. page 14 (Groq):** page 14's *NVIDIA deal* section is the *silicon* side; this page is the *ecosystem* side.
- **vs. page 26 (emerging):** page 26 is the *new entrants*; this page is the *incumbents' strategies*.
- **vs. page 27 (decision tree):** the *ecosystem* *cell* *is a* *constraint* *on* the *decision tree (the *cloud* *cell* *is a* *hard* *constraint on* *where* *the* *workload* *can run).
- **vs. page 31 (big idea):** the *ecosystem* *is the* *fifth axis* of *page 31's* *design space* (the *four* *are* *silicon, *memory, *scheduling, *interconnect; the *fifth* *is the* *stack/ecosystem).
