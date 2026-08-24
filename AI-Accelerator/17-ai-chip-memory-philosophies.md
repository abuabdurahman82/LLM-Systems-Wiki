# AI Chip Memory Philosophies — Cache vs. Scratchpad vs. Distributed SRAM
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
"Where does the next tensor come from?" has three answers in this section, and they are *philosophies*, not implementation details:
1. **Cache** (GPU, AMD, Cerebras-wafer-SRAM as a cache): hardware *speculates* what you'll need, pulls it into a fast on-chip store, and *misses* when it guesses wrong. The cost of a miss is *hidden by occupancy*.
2. **Scratchpad** (TPU, Trainium): the *compiler* decides what lives on-chip, the hardware just *streams* it. No speculation, no misses — but the model must be *placed* in advance.
3. **Distributed SRAM** (Groq, Cerebras-on-wafer): the on-chip store is the *entire* memory system. There is *no* off-chip DRAM at all. The model *must fit*, and if it does, there is *no memory wall* — the batch-1 decode is compute- or schedule-bound, not bandwidth-bound.

This page maps the three philosophies, quantifies the SRAM-vs-HBM trade, and shows *why* the distributed-SRAM regime (Groq) is the only one where a batch-1 decode's latency is *knowable in advance*.

## The three philosophies

### 1. Cache — hardware speculates
A cache is a *hardware* mechanism that *guesses* the next memory access and *prefetches* it. The L1/L2/HBM hierarchy is a *cache hierarchy*: each level is a *bigger, slower* store, and the hardware *moves data between levels* based on *locality* (temporal + spatial). When the guess is wrong, it is a *cache miss*, and the latency of the miss (hundreds of cycles for HBM) shows up *unless* the warp scheduler can switch to another warp (page 16).

- **The bet:** *locality* — the next access is *near* the last access.
- **When it wins:** irregular workloads (HPC, scientific, GNNs) where the access pattern is *data-dependent* and *not known in advance*.
- **When it fails:** *regular, dense, dependent* workloads (matmuls) where the access pattern *is* known in advance — the cache is *speculating* what the compiler already *knows*. This is the *waste* that the scratchpad eliminates.
- **The cost:** the cache *consumes power* (the tags, the ECC, the hit/miss logic) and *occupies die area* that could be used for compute. A 50 MB L2 on an H100 is *real die area* that a Groq TSP uses for *SRAM + compute*.

### 2. Scratchpad — the compiler decides
A scratchpad is a *software-managed* on-chip store. The *compiler* (XLA, Neuron, Groq's compiler) decides *exactly* which tensors live in the scratchpad, and the *hardware* just *streams* them in and out. There is *no speculation*, *no miss*, *no snoop*. The tensor is *where the compiler put it*, and the *time* to access it is *fixed*.

- **The bet:** *the model is static* — the compiler can see the *entire* model before it runs.
- **When it wins:** LLM inference (the model is *fixed*, the *access pattern* is *regular* and *known*).
- **When it fails:** dynamic workloads (the model *changes at runtime*, or the *branch* depends on the *data*). A scratchpad cannot *re-allocate* at runtime without a *compiler pass*.
- **The cost:** the *compiler* must be *as good as the model* — if the compiler *mis-places* a tensor, the *latency* is *bad*. There is *no hardware fallback* (no cache to *catch* the miss).

### 3. Distributed SRAM — the on-chip store is the whole system
Groq's TSP (and Cerebras's WSE, in a *single-wafer* form) takes the scratchpad philosophy and *eliminates the off-chip DRAM entirely*. The on-chip SRAM is the *entire* memory system. There is *no HBM*, *no cache*, *no DRAM controller*. The *model must fit* in the *aggregate* SRAM, and if it does, the *batch-1 decode* is *compute-bound* or *schedule-bound*, not *bandwidth-bound*.

- **The bet:** *the model fits* — the *aggregate* SRAM of the *scale-up domain* is *big enough* for the *target model*.
- **When it wins:** *batch-1, latency-critical* inference (the *memory wall* is *eliminated*, not just *hidden*).
- **When it fails:** *large models* (the *aggregate* SRAM is *not big enough*) or *large batches* (the *KV cache* exceeds the *SRAM headroom*).
- **The cost:** *the model must fit*, and *the scale-up domain* must be *big enough*. A 70B model at FP16 (135.6 GB [E]) *does not fit* in one Groq TSP (220 MiB [F]) — it must be *spread* across *576 TSPs* (page 14). The *scheduled Dragonfly* is what makes that *576-chip spread* *feel like one machine*.

## The SRAM-vs-HBM trade (quantified)
The *core* trade is *SRAM density* vs. *HBM capacity*. Let's quantify it for a 70B model at batch-1.

**The model footprint (Llama-2 70B, 67.8 B params [F: Meta HF]):**
- FP16: [E] 67.8 × 2 = **135.6 GB** of weights.
- INT8: [E] 67.8 × 1 = **67.8 GB** of weights.
- FP8: [E] 67.8 × 1 = **67.8 GB** of weights (same bytes, different numerics).

**The memory systems:**
| System | Aggregate fast memory | 70B at FP16? | 70B at INT8? |
|---|---|---|---|
| H100-8 (HBM) | 8 × 80 GB = 640 GB | yes (with 500 GB headroom) | yes (with 570 GB headroom) |
| MI300X-8 (HBM) | 8 × 192 GB = 1,536 GB | yes | yes |
| TPU v4-4 (HBM) | 4 × 32 GiB = 128 GiB | *barely* (135.6 GB > 128 GiB, needs sharding across 4) | yes |
| Trainium2-8 (HBM) | 8 × 96 GiB = 768 GiB | yes | yes |
| Groq 576-TSP (SRAM) | [E] 576 × 220 MiB = **123.75 GiB ≈ 132.5 GB** | **no** (135.6 GB > 132.5 GB) | **yes** (67.8 GB, with 64.7 GB headroom) |
| Cerebras WSE-2 (SRAM) | 40 GB | **no** | **no** (needs RealScale) |

The *first-principles* read: **the HBM systems *always* have the 70B model; the SRAM systems *only* have it *if the precision is low enough*.** This is the *load-bearing constraint* of the SRAM regime: *the model size is bounded by the aggregate SRAM*, and *the precision* is *the knob* that makes it fit.

## Why the SRAM regime wins batch-1 (the memory wall, page 03)
The *memory wall* (page 03) is the *ratio* of *HBM bandwidth* to *HBM capacity*. For a batch-1 decode, the *token rate* is:

```
token rate ≈ HBM-bandwidth / (model-size × bytes-per-param)
```

For an H100 (3.35 TB/s, 80 GB HBM [F: NVIDIA]):
- A 7B model at FP16 (14 GB): [E] 3.35e12 / 14e9 ≈ **239 tok/s** (at 100% HBM efficiency).
- A 70B model at FP16 (135.6 GB, sharded across 8 → 16.95 GB/chip): [E] 3.35e12 / 16.95e9 ≈ **198 tok/s** per chip at 100% efficiency (page 15's worked example).

For a Groq TSP (220 MiB SRAM, *no* HBM [F: ISCA 2022]):
- A 7B model at INT8 (7 GB): *does not fit* in one TSP (7 GB > 220 MiB). It must be *spread* across ~32 TSPs ([E] 7 GB / 220 MiB ≈ 32). The chip's *internal* SRAM streaming runs at 20 TiB/s *aggregate across the 64 lanes* [F: 2020 workshop] — the *per-TSP* token-rate ceiling is therefore set by that internal streaming bandwidth *and* by the *scheduling* (the 32-TSP spread must be *scheduled* through the Dragonfly, and the *inter-TSP* AllReduce-style reduction overhead dominates) [I]. The *qualitative* point stands: the *SRAM-regime* token rate is *not* bounded by the *HBM bandwidth* (there is no HBM); it is bounded by the *SRAM streaming bandwidth* and the *scheduled inter-chip path*.

The *point* is not the *exact number* — it is that **the SRAM regime's token rate is *not* bounded by the *HBM bandwidth*, it is bounded by the *SRAM bandwidth* (which is *orders of magnitude* faster) and the *scheduling overhead*.** The *memory wall* is *eliminated*, not just *hidden*.

## The KV-cache constraint (why SRAM systems need headroom)
The *weights* are the *fixed* footprint; the *KV cache* is the *variable* footprint. For a batch-1 decode with a context of *C* tokens, the KV cache is [E] `2 × num_layers × num_kv_heads × head_dim × bytes-per-kv-element × C` (the factor of 2 is for K and V). For Llama-2 70B (80 layers, 8 KV heads, 128 head_dim, FP16):
- Per token: [E] 2 × 80 × 8 × 128 × 2 bytes = **327,680 bytes ≈ 320 KB/token**.
- At C = 4,096 tokens: [E] 320 KB × 4,096 = **1.28 GB** of KV cache *per request*.

For the Groq 576-TSP system (132.5 GB aggregate SRAM, 67.8 GB INT8 weights):
- Headroom: [E] 132.5 − 67.8 = **64.7 GB** for KV + activations.
- Max batch-1 context: [E] 64.7 GB / 320 KB ≈ **205,000 tokens** — so the *KV cache* is *not* the constraint at C = 4,096; the *weights* are [I].

For an H100-8 (640 GB HBM, 135.6 GB FP16 weights):
- Headroom: [E] 640 − 135.6 = **504.4 GB** for KV + activations.
- Max batch-1 context: [E] 504.4 GB / 320 KB ≈ **1.6 million tokens** — the *KV cache* is *not* the constraint here either; the *HBM bandwidth* is [I].

The *first-principles* read: **at batch-1, the *weights* dominate the memory footprint, and the *KV cache* is a *small* addition. The *SRAM* constraint is *the weights*; the *HBM* constraint is *the bandwidth*.**

## The three philosophies, compressed
| Philosophy | Who decides what's on-chip | Misses? | Model must fit? | Best for |
|---|---|---|---|---|
| Cache | hardware (speculation) | yes (hidden by occupancy) | no | irregular, data-dependent workloads |
| Scratchpad | compiler (placement) | no (streamed) | *in HBM* (the scratchpad is a *window* into HBM) | static, regular workloads (LLM inference) |
| Distributed SRAM | compiler (placement) | no (no off-chip) | **yes, in the aggregate SRAM** | batch-1, latency-critical inference |

The *progression* is *speculation → placement → elimination*. Each step *trades flexibility for determinism*, and the *payoff* is the *P99 latency* (page 16).

## How to read this page against the others
- **vs. page 03 (memory wall):** page 03 *establishes* the memory wall; this page shows *which regime* *eliminates* it.
- **vs. page 07 (NVIDIA memory hierarchy):** page 07 is the *cache* philosophy in depth; this page is the *comparison* of all three.
- **vs. page 14 (Groq):** page 14 is the *distributed-SRAM* philosophy in depth; this page is the *comparison*.
- **vs. page 16 (scheduling):** page 16 is the *scheduling* axis; this page is the *memory* axis. The two are *coupled*: the *scheduling regime* determines the *memory regime* (a *hardware* scheduler *needs* a *cache*; a *software* scheduler *can* use a *scratchpad*; a *dataflow* scheduler *eliminates* the *off-chip* memory).
- **vs. page 23 (roofline):** the roofline makes the *bandwidth-vs-FLOPS* trade *precise*; this page is the *memory-architecture* side of that trade.
