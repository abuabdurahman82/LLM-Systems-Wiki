# Workload-to-Chip Mapping — Training, Prefill, Decode, and Why tokens/s Is Not a Metric
`LAST_UPDATED: 2026-08-24` · Status: synthesis page · `[F]` = primary source cited inline; `[E]` = computed from `[F]` data; `[A]` = assumption; `[I]` = inference; `UNVERIFIED` = not confirmed against a primary source.

## 30-Second Explanation
An LLM service is *not one workload* — it is *two*, with *opposite* hardware requirements:
- **Prefill** (the *prompt*): a *large GEMM* (the *whole prompt* at once), *high* *arithmetic intensity* (~thousands of FLOPs/byte), *compute-bound*, *batch-friendly*.
- **Decode** (the *output*, *one token at a time*): a *GEMV* (the *weights* streamed per token), *low* *arithmetic intensity* (~1–2 FLOPs/byte), *bandwidth-bound*, *batch-unfriendly at batch-1*.

The *mapping* is: *prefill* → *the HBM/peak* *chip* (NVIDIA, AMD, TPU, Trainium); *batch-1 decode* → *the SRAM/determinism* *chip* (Groq, Cerebras). This page makes the *mapping* *quantitative* (the *arithmetic intensity* of each phase, the *FLOPs/byte* threshold, the *token rate* formula), and shows *why* "*tokens/s*" *is not a* *metric* *without a* *batch size* and a *latency target*.

## The two phases, quantified
Take *Llama-2 70B* (67.8 B params, 80 layers, hidden 8,192, 64 heads, 8 KV heads [F: Meta HF]).

### Prefill (prompt of length P, batch B)
- *FLOPs:* [E] `2 × 67.8e9 × P × B` (the *forward pass* is ~2 FLOPs/param/token). At *P = 4,096, B = 1*: [E] 2 × 67.8e9 × 4,096 ≈ **555 TFLOP**.
- *Memory moved:* the *weights* (135.6 GB FP16) are *read once* (the *prompt* is *short* vs. the *weights), plus the *KV* *writes*. So *~135.6 GB* *moved* *for* the *entire* *prefill* (the *weights* *dominate).
- *Arithmetic intensity:* [E] 555e12 FLOP / 135.6e9 byte ≈ **4,100 FLOP/byte**.
- *The regime:* *far* *above* *the* *roofline* *ridge* point (page 23) → *compute-bound*. The *FLOPs/second* *is* the *limiting* factor; the *HBM* *bandwidth* is *irrelevant*.

### Decode (one token, batch 1, context C)
- *FLOPs:* [E] `2 × 67.8e9` = 135.6 GFLOP *per token* (the *weights* are *read* once *per token).
- *Memory moved:* the *weights* (135.6 GB FP16, sharded) *per token*, plus the *KV read* (~320 KB × C [E], page 17). At *C = 4,096*: *~135.6 GB + 1.28 GB ≈ 136.9 GB*.
- *Arithmetic intensity:* [E] 135.6e9 / 136.9e9 ≈ **~1 FLOP/byte**.
- *The regime:* *at* *the* *roofline* *ridge* point *or below* → *bandwidth-bound*. The *HBM* *bandwidth* *is* the *limiting factor; the FLOPs* are *irrelevant* (the *compute* is *idle* *waiting* for the *memory).

*The* *first-principles* *insight:* **the* *same* *model, the *same chip*, runs at *~4,000 FLOP/byte* in *prefill* and *~1 FLOP/byte* in *decode.* The *hardware* *that is* *right* *for one is *wrong* *for the *other* — *and that is* *why* *disaggregated* *systems* (a *prefill* *node* + a *decode* *node) exist [I].

## The tokens/s formula (and why it is not a metric)
The *token rate* for *batch-1 decode* is:
```
token rate = HBM-bandwidth / (weights-per-chip × bytes-per-param)   [E]
```
*The* *number* *is* *meaningless* *without* *three* *qualifiers:
1. *the bytes-per-param* (FP16? FP8? INT8? — *a 2× range, page 20).
2. *the HBM efficiency* (a *decode* *kernel* *hits* *~30–50%* *of* *peak* *bandwidth*, *not* *100%, *because* the *kernel is latency-bound on the GEMV, page 17).
3. *the batch size* (a *batch-N* *decode* *streams* *the same weights N times per step, so the *per-token* *rate is *the same* but the *throughput* *is N× higher — a *tokens/s* *number* *without a* *batch size is *uninterpretable).

*The* *worked* *example* (page 15): *8×H100*, *Llama-2 70B FP16*, *batch-1*: [E] 3.35 TB/s / 16.95 GB = *198 tok/s at 100% efficiency*, *~60–100 tok/s* *at* *30–50%* efficiency [I]. *That* *range* *(60–198)* *is* *the* *point:* *the* *tokens/s* *number* *is* *a* *range* *until you specify* *the* *efficiency* *and* *the* *batch*.

*The* *Groq* *counterpoint:* *the* *Groq 576-TSP* *system* *reports* *> 300 tok/s* *at* *INT8*, *512-in/1024-out* [F: Next Platform]. *That* *number* *is* *meaningful* *because* *the* *precision* *(INT8), *the* *batch* *(1), *and* the *shape* *(512/1024)* *are* *stated*. *Without* *those*, *"> 300 tok/s"* *is* *a* *marketing* *number*, *not* a *metric*.

## The mapping table
| Workload | Arithmetic intensity | Regime | Right chip(s) | Why |
|---|---|---|---|---|
| Training (large batch, mixed precision) | high (GEMM + GEMM for backprop) | compute-bound | NVIDIA (CUDA ecosystem), TPU (per-flop efficiency), AMD | The *ecosystem* + the *peak* + the *scale-up domain* dominate; the *latency* is irrelevant [I] |
| Prefill (long prompt, batch-N) | ~4,000 FLOP/byte [E] | compute-bound | NVIDIA, AMD, TPU, Trainium | The *FLOPs/second* is the limit; the *HBM* is irrelevant [E] |
| Batch-N decode (throughput) | ~N FLOP/byte (the weights are shared) | bandwidth-bound, batch helps | NVIDIA, AMD, TPU, Trainium | The *batch* *raises* the *arithmetic intensity* (the *weights* are read once, served N×); the *HBM* *bandwidth* is the limit [E] |
| **Batch-1 decode (latency-critical)** | **~1 FLOP/byte [E]** | **bandwidth-bound, batch=1** | **Groq** (deterministic SRAM), **Cerebras** (on-wafer SRAM) | The *HBM* *bandwidth* *is the* limit on *HBM* chips; the *SRAM* *chip* *eliminates* the *HBM* *hop* (page 17) [E/I] |
| Batch-1 decode (cost-critical) | ~1 FLOP/byte [E] | bandwidth-bound | NVIDIA, TPU, Trainium (cheapest $/token) | The *latency* *is less* important *than the* *cost; the HBM* chip *wins on $/token* [I] |
| HPC / scientific (irregular) | data-dependent | memory-bound, irregular | NVIDIA (CUDA generality) | The *cache* *speculation* *is the* right bet (page 17) [I] |
| Real-time (voice, search, translation) | ~1 FLOP/byte [E] | latency-bound | **Groq** | The *P99* *is the* product; the *compile-time* guarantee is worth the closed stack [I] |

*The* *first-principles* *read:* **the* *mapping is* *the* *arithmetic intensity* *versus* *the* *chip's* *regime.* A *chip* is *right* *for a* *workload* *if its* *regime* *matches the* *workload's* *arithmetic intensity: a* *compute-bound* *workload* *wants a* *high-peak* *chip* (the *roofline* *ceiling), *and a* *bandwidth-bound* *batch-1* *workload* *wants a* *high-bandwidth* or *SRAM* *chip* (the *roofline* *floor, *page 23).

## Why "tokens/s" is not a metric (the three missing qualifiers)
A *bare* "tokens/s" *number* is *uninterpretable* *without:
1. *The batch size:* *batch-1* *60 tok/s* *and* *batch-64* *3,840 tok/s* *are the* *same* *per-token* *rate* (the *throughput* is *64×, the *latency* is *the same).
2. *The latency target:* *a* *60 tok/s* *at* *P99 = 50 ms* *is a* *different* *product* *from a* *60 tok/s* *at* *P99 = 500 ms* (the *Groq* *sells the* *former; the* *H100* *sells* the *latter* *for* *batch-N).
3. *The precision + efficiency:* *a* *60 tok/s* *at* *FP16* *is a* *different* *silicon* *from a* *60 tok/s* *at* *FP8* (the *bytes-per-param* *differs 2×, page 20), *and a* *60 tok/s* *at* *50% efficiency* *implies a* *different* *peak* *than a* *60 tok/s* *at* *100%*.

*The* *rule:* **report tokens/s with (batch size, P99 latency, precision, and HBM efficiency).** The *Groq 576-TSP* "512-in/1024-out, INT8, batch-1, > 300 tok/s" [F: Next Platform] *is a complete* *report; a* "300 tok/s" *without those* *is not*.

## How to read this page against the others
- **vs. page 02 (workloads):** page 02 is the *workload taxonomy*; this page is the *workload → chip* mapping.
- **vs. page 15 (philosophies):** this page is the *workload* axis of page 15's *decision frame*.
- **vs. page 17 (memory):** this page's *arithmetic intensity* *is* the *memory-wall* *quantified* (page 03's *wall, *page 17's *regime).
- **vs. page 23 (roofline):** page 23 is the *compute* *side* of this mapping; this page is the *workload* *side*.
- **vs. page 27 (decision tree):** this page's *mapping table* *is* the *input* to page 27's *decision tree*.
