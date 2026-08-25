# AI Accelerator Interconnects — Scale-Up vs. Scale-Out Across All Vendors
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
Every AI system is a *hierarchy of two domains*:
- **Scale-up domain:** the largest N of chips that behaves like *one machine* — a *shared* memory or a *scheduled* fabric, with *no* PCIe/NIC hop. The *collectives* (AllReduce, AllGather) run *inside* this domain at *line-card* speed.
- **Scale-out domain:** everything *beyond* the scale-up domain, connected by *networks* (InfiniBand, Ethernet, or a vendor's own scale-out fabric). The *collectives* here run at *network* speed, and the *latency* is *measured in microseconds-to-milliseconds*, not *nanoseconds*.

The *boundary* between the two domains is *the* architectural decision: it defines *the largest model that behaves like one machine* (page 15, axis 4), and it determines *the cost of a tensor-parallel step* (the AllReduce on every layer). This page maps the six vendors' interconnects, quantifies the scale-up/scale-out boundary, and shows *why* the Groq *scheduled Dragonfly* is a *third* thing — neither a scale-up fabric nor a scale-out network, but a *compiler-scheduled dataflow* that *straddles* the boundary.

## The two domains, defined
- **Scale-up:** *chips talk to each other* via a *dedicated* interconnect (NVLink, ICI, NeuronLink, XGMI, RealScale, or Groq's C2C). The *bandwidth* is *per-chip* (TB/s), the *latency* is *nanoseconds-to-microseconds*, and the *collectives* are *implemented in the interconnect* (not in the network).
- **Scale-out:** *racks talk to each other* via a *network* (InfiniBand, Ethernet, or a vendor's own fabric). The *bandwidth* is *per-rack* (hundreds of Gb/s per port), the *latency* is *microseconds-to-milliseconds*, and the *collectives* are *implemented in the network stack* (NCCL, RCCL, or the vendor's own).

The *first-principles* distinction: **scale-up is *memory*; scale-out is *network*.** A scale-up chip *sees* its neighbor's memory *as if it were local* (the ICI, NVLink, and NeuronLink all expose a *shared* address space). A scale-out chip *sends a packet* to its neighbor (the InfiniBand, Ethernet, and Groq's inter-rack links all *route* packets).

## The six vendors' interconnects

### NVIDIA — NVLink (scale-up) + InfiniBand/Ethernet (scale-out)
- **Scale-up:** NVLink 4 on H100/H200 at *900 GB/s total NVLink bandwidth per GPU* (18 links [F: NVIDIA datasheet]); NVLink 5 on Blackwell (B200) doubles this to *1.8 TB/s per GPU* [F: NVIDIA]. The *NVLink domain* is *8 GPUs* (DGX H100) or *72 GPUs* (NVL72, via the NVLink switch) [F: NVIDIA].
- **Scale-out:** InfiniBand NDR (400 Gb/s per port) or Ethernet (RoCE), via the *SHARP* in-network compute for AllReduce [F: NVIDIA].
- **The collectives:** *NCCL* (NVIDIA Collective Communication Library) — the *de facto* standard. NCCL *detects* the topology (NVLink vs. IB) and *chooses* the fastest path.
- **The first-principles read:** NVIDIA's *scale-up domain* (72 GPUs in NVL72) is the *largest* in this section. The *NVLink switch* (NVL72) is what makes the *72-GPU domain* *feel like one machine* — the *AllReduce* inside the domain runs at *NVLink* speed, not *IB* speed.

### Google TPU — ICI (scale-up, both intra- and inter-chip)
- **Scale-up:** ICI (Inter-Core Interconnect) — a *torus* (v4) or *Boardfly* (v8) that *straddles* the *chip-to-chip* and *pod-to-pod* boundary [F: Google ISCA 2023, Google v8 blog]. The *ICI* is *not* a *separate* scale-up/scale-out fabric — it is *one* fabric that *scales* from *1 chip* to *9,216 chips* (Ironwood pod) or *9,600 chips* (v8 superpod) [F: Google].
- **The ICI bandwidth:** each v4 chip embeds *4 ICI links in a 2×2 mesh*, plus *16 external ICI links per tray* for the 3D torus [F: ISCA 2023]. The *per-chip aggregate ICI bandwidth* in Gb/s is *not* stated in the ISCA 2023 v4 paper's extracted text (UNVERIFIED); page 10 notes the per-chip ICI grew to *4,800 Gbps/chip by v5p* and *19.2 Tb/s by v8* [F: Google, via page 10].
- **The collectives:** *XLA* places the *collectives* into the *ICI* schedule — the *AllReduce* is *not a network operation*, it is a *compiler-placed* data movement over the *ICI* [F: ISCA 2023].
- **The first-principles read:** the TPU's ICI is the *cleanest* example of *scale-up as a fabric*: the *same* interconnect *scales* from *1 chip* to *9,600 chips*, and the *collectives* are *compiler-scheduled*, not *network-routed*. This is *closer* to Groq's *scheduled* model than to NVIDIA's *routed* model (page 16).

### AMD — Infinity Fabric (scale-up) + InfiniBand/Ethernet (scale-out)
- **Scale-up:** XGMI (eXternal Global Memory Interconnect) — the *Infinity Fabric* link between *MI300X* GCDs (Graphics Data Die) and between *cards* [F: AMD]. The *scale-up domain* is *8 GPUs* (MI300X-8) [F: AMD].
- **Scale-out:** InfiniBand NDR or Ethernet (RoCE), via *RCCL* (AMD's NCCL equivalent) [F: AMD].
- **The first-principles read:** AMD's *scale-up domain* (8 GPUs) is *smaller* than NVIDIA's (72 in NVL72) — a *consequence* of the *XGMI* bandwidth *per GPU* being *lower* than *NVLink 5* [I]. This is one reason the *MI300X* is *competitive* on *per-GPU* performance but *not* on *scale-up domain size* [I].

### Cerebras — RealScale (scale-up, multi-wafer)
- **Scale-up:** the *WSE-2* is *one wafer* = *one chip* (40 GB on-wafer SRAM) [F: Cerebras]. The *RealScale* interconnect *links* multiple WSEs into a *single system* (up to *256+* WSEs in a *CS-3* system) [F: Cerebras]. The *RealScale* bandwidth *per WSE* is *UNVERIFIED* (Cerebras has not published a clean per-WSE figure in the sources I've verified).
- **The first-principles read:** Cerebras's *scale-up domain* is *defined by the wafer* — the *on-wafer SRAM* is the *fast* memory, and the *RealScale* is the *slow* fabric that *links* wafers. The *collectives* are *implemented in the RealScale* fabric [I].

### AWS Trainium — NeuronLink (scale-up) + EFA (scale-out)
- **Scale-up:** NeuronLink — the *NVLink equivalent* for Trainium. Trn2: *8 chips* per *NeuronLink group* (96 GiB HBM3e each, 2.9 TB/s) [F: AWS]. Trn3: *128 chips* per *NeuronLink group* (144 GiB HBM3e each, 4.9 TB/s) [F: AWS] — *UNVERIFIED* on the *exact* Trn3 group size (the AWS docs I fetched specify *per-chip* specs; the *group size* for Trn3 is *UNVERIFIED*).
- **Scale-out:** EFA (Elastic Fabric Adapter) — AWS's *InfiniBand equivalent*, at *400 Gb/s* per *EFA2* instance [F: AWS].
- **The first-principles read:** Trainium's *scale-up domain* *grew* from *8* (Trn2) to *128* (Trn3) — a *16×* increase in *one generation* [F: AWS]. This is *aggressive* scaling, and it *tracks* the *model size* (a *128-chip* domain *holds* a *much larger* model *as one machine* than an *8-chip* domain) [I].

### Groq — C2C + Dragonfly (a *third* thing: scheduled, not routed)
- **Scale-up (intra-node):** C2C (chip-to-chip) links between the *8 TSPs* in a *GroqNode* — a *direct, full-mesh* connection (the *node* is an *8-way SMP* domain) [F: ISCA 2022]. The *bisection bandwidth* within a node is *240 GB/s* [F: 2020 workshop].
- **Scale-up (inter-node):** the *Dragonfly* — a *hierarchical* topology (9 nodes per rack, 145 racks max) that *scales* from *8 TSPs* to *10,440 TSPs* [F: ISCA 2022]. The *Dragonfly* is *scheduled by the compiler*, not *routed by hardware* (page 14).
- **The first-principles read:** Groq's *Dragonfly* is *not* a *scale-up fabric* (like NVLink or ICI) and *not* a *scale-out network* (like InfiniBand). It is a *compiler-scheduled dataflow* that *straddles* the boundary: the *inter-chip* path is *scheduled* (deterministic, known latency) *and* *scales* to *10,440 TSPs*. This is *why* the *worst-case end-to-end latency* is *< 3 µs* [F: ISCA 2022] — the *scheduler* *chose* the path, and the *path is the latency*.

## The scale-up/scale-out boundary, quantified
The *boundary* is *the largest N of chips that behaves like one machine*. Let's quantify it for a *tensor-parallel* 70B model (Llama-2 70B, 68.98 B params [F: HF checkpoint index]).

**The AllReduce cost per layer (tensor-parallel):**
In tensor-parallelism, *each* layer does *two* AllReduce operations (one after the *row-parallel* linear, one after the *column-parallel* linear). The *AllReduce* moves *2 × hidden_dim × bytes-per-element × batch* bytes *per chip* (the *reduce-scatter* + *all-gather* halves). For Llama-2 70B (hidden_dim = 8,192, batch-1, FP16):
- Per AllReduce: [E] 2 × 8,192 × 2 bytes = **32,768 bytes = 32 KB** per chip.
- Per layer (2 AllReduce): [E] 64 KB per chip.
- Per forward pass (80 layers): [E] 80 × 64 KB = **5.12 MB per chip**.

**The AllReduce latency (scale-up vs. scale-out):**
| Domain | AllReduce latency (32 KB, 8 chips) | Source |
|---|---|---|
| NVLink 5 (8 GPUs) | ~1–2 µs | [I] (NVLink 5: 900 GB/s per GPU; 32 KB / 900 GB/s ≈ 0.07 µs transfer + ~1 µs latency) |
| ICI (8 TSPs, v4) | ~1–3 µs | [I] (ICI 480 Gb/s per chip; 32 KB / 60 GB/s ≈ 0.5 µs + latency) |
| Groq C2C (8 TSPs) | ~0.5–1 µs | [I] (C2C: 240 GB/s bisection per node; 32 KB / 240 GB/s ≈ 0.13 µs + latency) |
| InfiniBand NDR (8 GPUs) | ~5–10 µs | [I] (IB NDR: 400 Gb/s per port; 32 KB / 50 GB/s ≈ 0.6 µs + ~5 µs latency) |

The *first-principles* read: **the AllReduce latency is *1–2 orders of magnitude* lower inside the scale-up domain than outside it.** This is *why* the *scale-up domain size* is *the* architectural decision: a *70B* model that *fits* in the *scale-up domain* (e.g., 8 H100s, 576 TSPs) runs *10× faster* than the *same* model that *spills* into the *scale-out domain* (e.g., 32 H100s over InfiniBand) [I].

## The Groq "third thing" — why it matters
The Groq *Dragonfly* is the *only* interconnect in this section that is *compiler-scheduled*, not *hardware-routed*. This is *not* a *scale-up fabric* (it is *not* a *shared* memory) and *not* a *scale-out network* (it is *not* a *routed* packet network). It is a *scheduled dataflow* that *straddles* the boundary.

The *consequence* is the *< 3 µs worst-case end-to-end latency* [F: ISCA 2022] — a *guarantee* that *no* routed fabric (NVLink, ICI, NeuronLink, XGMI, RealScale) can offer. The *routed* fabrics *can* be *faster* on *average* (the *adaptive routing* finds the *shortest path*), but they *cannot* guarantee the *worst case* (a *congested* link *adds* latency). The *scheduled* fabric *chooses* the path *in advance*, so the *worst case is the scheduled case* — *known at compile time* [I].

This is the *third* memory/scheduling philosophy (page 17, page 16): *elimination* (not *hiding*, not *speculation*). The *Dragonfly* is the *interconnect* that *makes* the *elimination* *possible* at *scale*.

## How to read this page against the others
- **vs. page 15 (philosophies):** this page is the *interconnect* axis of page 15's six-axis frame.
- **vs. pages 05–14:** those are the per-chip deep dives; this is the cross-chip interconnect comparison.
- **vs. page 16 (scheduling):** the *scheduled* vs. *routed* distinction is the *interconnect* side of page 16's *scheduling* spectrum.
- **vs. page 17 (memory):** the *scale-up domain* is the *fast memory* domain; the *scale-out domain* is the *slow* domain. This page is the *boundary* between the two.
- **vs. page 24 (rack-scale):** page 24 is the *rack* as the *unit of engineering*; this page is the *interconnect* that *defines* the *rack's* scale-up/scale-out boundary.
