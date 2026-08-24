# The Rack Is the AI Computer — Card → Server → Rack → Pod → AI Factory
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
The *center of gravity* of AI engineering has moved *up the stack*: from the *card* (a die + HBM) to the *server* (8 cards + NVLink/ICI domain), to the *rack* (the *power + cooling + cabling* boundary), to the *pod* (the *scale-up fabric's* limit), to the *AI factory* (the *rack-scale* *power* *budget as the* *first-order* constraint). This *page* *walks* *up that* *stack for the* *six vendors, *quantifies* the *power/cooling* *per* *level, *and* *shows why* the *rack* — *not* the *card* — *is the* *unit of engineering* *in 2025–26: the* *power* (kW/rack), *the* *cooling* (air → liquid → immersion), *and the* *cabling* (the *scale-up* *fabric* *leaves* the *card* and *enters the rack) *are decided at* the *rack, *and they* *constrain* the *card* *more than* the *silicon* *does* [I].

## The hierarchy
```
card (die + HBM + VRM)          -> the silicon budget (TDP: 700–1,000 W per H100/B200 [F: NVIDIA])
  x 8                           -> the server / GroqBox / UltraServer (the scale-up domain)
  x N                           -> the rack (the power + cooling boundary: ~120–165 kW/rack for DGX-H100-class [E: p24])
  x M                           -> the pod / supercomputer (the scale-up fabric's limit: 4,096–10,440 chips)
  x P                           -> the AI factory (the power budget: 100 MW–10 GW [F: press])
```
*The* *rule:* **each level up adds a new resource that becomes the binding constraint:** the *card* is bounded by *die + HBM*; the *server* by *the scale-up fabric*; the *rack* by *power + cooling*; the *pod* by *the fabric's topology limit*; the *factory* by *grid power* [I].

## Card → Server (the scale-up domain)
*The server is* *the* *smallest* *unit* *that* *is a machine*: it *contains a complete scale-up domain* (the *chips* *talk to each other* *inside it, *no* PCIe hop):
| Vendor | Server unit | Chips per server | Scale-up fabric |
|---|---|---|---|
| NVIDIA | DGX H100 | 8 H100 (NVLink 4) | 900 GB/s total/GPU [F] |
| NVIDIA | DGX B200 | 8 B200 (NVLink 5) | 1.8 TB/s total/GPU; 14.4 TB/s aggregate [F: NVIDIA DGX B200] |
| Google | TPU tray/host | 4 TPU v4 (per ISCA 2023, the v4 host board carries the ICI links) [F: arXiv:2304.01433] | ICI 3D torus |
| AMD | MI300X node | 8 MI300X | XGMI / Infinity Fabric [F: p11] |
| Groq | GroqBox ("node") | 8 TSP (4U, 8× TSP-100 cards) | C2C, 240 GB/s bisection [F: 2020 workshop] |
| AWS | Trn2 UltraServer | 64 Trn2 chips (4×4×4 3D torus) | NeuronLink, 1,280 GB/s/chip [F: p13] |

*Note the* *scale-up domain size varies 8→64 chips between vendors* (the *Trn2* *UltraServer* *is a 64-chip server, *not a* *8-chip* one) [F: AWS]. *The* *domain* *is the* *architectural choice, *not a* *physical law* (page 18).

## Server → Rack (the power + cooling boundary)
*The* *rack* *is where* *power* *and* *cooling* *become the* *constraint:
| System | Chips per rack [F/I] | Power per rack | Cooling |
|---|---|---|---|
| DGX H100 rack (12–16 systems) [I] | ~96–128 H100 | ~120–165 kW [E: 10.2 kW/system] | liquid (front-door) / air (rear) [I] |
| Groq rack (ISCA 2022) | 72 TSP [F: ISCA 2022] | not stated (UNVERIFIED) | liquid [I] |
| Trn2 rack | 64–128 chips [I] | not public (UNVERIFIED) | liquid [I] |

*The* *Groq* *ISCA* *2022* *spec* *gives* *the* *rack* *count* *directly: 145 racks × 72 TSP = 10,440 TSP* [F: ISCA 2022] — *the* *rack* *is a* *first-class* *unit* *in the* *paper's* *topology* *spec. *The* *power* *per rack* *is not stated* *in the* *paper* *I* *verified* (UNVERIFIED), *but* the *2020* *deck* *gives a* *3.3 kW/GroqBox* *figure for the* *8-TSP node* [F: 2020 workshop] *— at* *that* *number, *a* *72-TSP rack is* *~29.7 kW plus* *the* *fabric/switch* *overhead* [E] (*a* *useful order-of-magnitude* *anchor, *not a* *spec).

*The* *first-principles* *read:* **the* *rack* *is the* *power* *boundary.* *A* *100 kW rack* *is a* *~100* *unit* *of the* *AI factory's* *power* *budget; the* *card's* *TDP* *(700–1,000 W)* *matters* *only* *as* *the* *input* *to* the *rack's* *power* *design* [I]. *This* *is* *why* *the* *vendors' 2025–26* *announcements* *(AMD* *6 GW* *OpenAI/Meta* *clusters, *page 11) *are stated* *in GW, *not in* *TFLOPS: the* *binding* *constraint has* *moved up* *to the* *grid.*

## Rack → Pod (the scale-up fabric's limit)
*The* *pod* *is* *the* *largest N* *that the scale-up fabric* *reaches without a* *scale-out* *hop:
| Vendor | Pod size | Fabric |
|---|---|---|
| NVIDIA NVL72 | 72 GPUs [F] | NVLink switch [F] |
| Google TPU v4 | 4,096 chips [F: ISCA 2023] | ICI torus + OCS [F] |
| Google Ironwood | 9,216 chips [F: p10] | ICI [F] |
| Google TPU v8 | 9,600-chip superpod [F: p10] | Boardfly [F] |
| Cerebras CS-3 | 1–4 wafers (RealScale) [F: p12] | on-wafer + RealScale [F] |
| Groq | 264 TSP (33-node Dragonfly, full connectivity) [F: ISCA 2022]; 10,440 max [F] | scheduled Dragonfly [F] |
| AWS Trn2 | 64 chips (UltraServer) [F: p13] | NeuronLink torus [F] |

*The* *first-principles* *read:* **the* *pod* *defines* *the* *largest model* *that* *behaves* *like* *one* *machine* (page 15, *axis 4). *A* *70B* *model* *at* *FP16* *(135.6 GB)* *fits* *in* *an* *8×H100* *server* *with* *room* *for KV; *a* *400B* *model* *at* *FP8* *(~400 GB)* *needs* *a* *pod, *not* *a* *server* [E]. *The* *pod* *size* *is* *the* *model* *size* *ceiling* *for* *"one machine."

## Pod → AI factory (the power budget is the spec)
*The* *factory* *level* *is where* *the* *GW* *number* *is the* *spec. *The* *verified* *anchors:
- *AMD:* *6 GW* *of* *MI300/MI350* *compute* *for* *OpenAI* *(announced* *Oct 2025)* *and* *Meta* *(announced* *Feb 2026)* [F: press, via p11].
- *The* *H100* *era:* *a* *"AI* *factory"* *is* *commonly* *stated* *as* *~750 H100* *per* *MW* (a *DGX* *H100* *is ~10.2 kW for 8 H100 [F: NVIDIA], *so* *784 H100/MW* *at* *PUE 1.0 [E]). *A* *100 MW* *factory* *at* *PUE 1.5* *is* *~66.7 MW compute* *≈ 6,500* *DGX* *H100s* *≈ 52K* *H100s* [E]. *That* *is an order-of-magnitude* *anchor, *not a* *spec* (the *real* *density* *depends* *on* the *rack design, *page 21).
- *The* *Groq* *counterpoint:* *a* *10,440-TSP* *system* *at* *3.3 kW per GroqBox* (the 2020 deck's 4U 8-TSP box figure [F: 2020 workshop]) is [E] 10,440/8 × 3.3 kW = **~4,290 kW ≈ 4.3 MW** for the compute alone, before the inter-rack fabric, spares, and data-center overhead. *The* *factory* *power* *is the* *spec, *and the* *TSP* *is* *a* *modest-TDP* *chip* *by* *design* (the *SRAM* *regime* *needs* *fewer* *watts* *than* *the HBM* *regime* *for the* *same* *batch-1* *throughput* [I]).

*The* *first-principles* *read:* **at* the *factory* *level, the* *spec sheet is* *the power budget, *and the* *chip's* *watts-per-useful-token* *is* *the* *metric that* *matters* (page 28's *80/20*). *The* *TFLOPS* *number* *stops* *being* *the* *spec; the* *GW* *number* *becomes* it.

## The hierarchy's binding constraint, per level
| Level | Binding constraint | What it bounds |
|---|---|---|
| Card | die + HBM (TDP 700–1,000 W [F]) | the per-chip peak, the SRAM/HBM size |
| Server | the scale-up fabric (NVLink/ICI/NeuronLink/C2C) | the largest model that behaves like one machine (8–64 chips) |
| Rack | power + cooling (DGX-H100-class ~120–165 kW/rack [E]; Groq-class ~30 kW [E]) | the number of servers, the cooling architecture |
| Pod | the fabric's topology limit (72–10,440 chips [F]) | the largest single-machine model |
| AI factory | grid power (100 MW–10 GW [F]) | the total compute, the $/token at scale |

*The* *ladder* *is the* *point:* **each level up, a new resource becomes the binding constraint, and the engineering moves with it.** *The* *silicon* *engineer* *works* *at the card; *the* *systems* *engineer* *works* *at the rack; *the* *AI* *factory* *planner* *works* *at the GW* (the *power* *budget). *The* *six* *architectures* *in this section* *are* *six different answers* *to the* *question, "which level do you engineer at?"* — *NVIDIA* *and* *AMD* *at the card/server, *Google* *and Groq* *at the pod/fabric, *AWS* *at the rack (the UltraServer)*, *and* *all of them, in 2025–26, at the factory* (the *GW* *announcement) [I].

## How to read this page against the others
- **vs. pages 05–14:** those are the *card* level; this page is the *rack/factory* level.
- **vs. page 18 (interconnects):** page 18 is the *fabric*; this page is the *hierarchy the fabric spans*.
- **vs. page 21 (comparison matrix):** page 21's *Matrix B* (system) *is the pod level*; this page adds the *rack* and *factory* levels.
- **vs. page 28 (80/20):** the *watts-per-useful-token* metric *at the factory level* is one of page 28's *10 ideas*.
- **vs. page 31 (big idea):** this page's *hierarchy* is the *spatial* axis of page 31's *design-space* synthesis.
