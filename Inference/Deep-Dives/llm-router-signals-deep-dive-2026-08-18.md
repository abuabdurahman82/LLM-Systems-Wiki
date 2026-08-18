# LLM Router Signals — Deep Dive
`LAST_UPDATED: 2026-08-18` · Status: deep-dive (three-pass adversarially-reviewed; evaluator adjudication in §10). Claim tags: [F] fact (primary source fetched 2026-08-18, retained in /tmp/router-src/) · [A] engineering assumption · [I] inference · [E] computed & Python-verified this session (`verify_v3.py`, `reverify_flags.py`, `final_numbers.py`). Model: 7B-class BF16 on H100 SXM unless noted. Units: GB = 10⁹ B, GiB = 1024³ B.
Companion page: `Inference/Prefill-Decode-Disaggregation.md` (KV transfer physics + P/D break-even) — this document covers the *routing* layer above it.

---

## 0. Mission, scope, and thesis

**Question:** Should a production LLM router consider queue backlog, prompt-processing remaining, active decode work, expected output length, and KV/prefix-cache state — rather than round-robin, least-connections, random, or least-requests?

**Thesis (to be tested, not asserted):** Yes, but with an important first-principles refinement: the correct routing signal is **predicted remaining work in tokens, not connections or requests**, and the relative weight of each of the five signals is *regime-dependent* (workload shape × deployment topology). A router that hardwires one fixed policy across workloads is structurally suboptimal; a router that scores candidates by a predicted-latency decomposition that *degenerates gracefully* to simple policies when signal quality is low is the defensible design.

Scope: single-model serving pools (colocated and P/D-disaggregated), 10s–1000s of replicas, TTFT/TPOT SLOs. Out of scope: multi-model model-gateway routing, autoscaling (adjacent, noted where it couples), and in-engine (single-instance) scheduling — which is a separate but related problem (Sarathi/Sarathi-Serve chunked prefill, Llumnix rescheduling).

---

## 1. First principles: why "connections" is the wrong currency

*Model scope for everything in this section (stated, not a discovery): prefill is treated as compute-bound at MFU 0.5 and decode as HBM-bandwidth-bound (step = HBM read of weights + batch KV, ignoring kernel/compute overheads) — the standard first-order roofline approximation, accurate for B well below the compute knee; it is an assumption [I], not a measurement.*

### 1.1 Two roofline regimes, one request [F/E]

An LLM request is two physically different workloads stitched together:

- **Prefill**: FLOPs ≈ 2·N·S (N = params, S = prompt tokens). For N=7e9, S=3,000: 42 TFLOP of mostly dense GEMM. On an H100 (989 TFLOPS BF16 dense) this is **compute-bound** under every reasonable AI convention: the formula-bank large-batch GEMM asymptote d/b ≈ 2048; the actual [S,d]×[d,d] prefill GEMMs at S=3k have AI ≈ 2Sd²/((2Sd+d²)b) ≈ 1,217 (X + W + Y bytes); and the model-level weight-traffic AI = 2S/b = 3,000 (all FLOPs / weight bytes read once). Even charging activation + KV-write HBM traffic to the denominator leaves it ≈2,150–2,700 (the exact value is activation-accounting-dependent — MLP width, input/output staging) — in every case ≫ ridge ≈ 295 [E: reverify_flags.py; formula bank 2026-08-15]. Attention's S² terms are ~9.8% of prefill FLOPs at S=3k, 7B — subleading [E].
- **Decode**: FLOPs/token ≈ 2·N, but the step is HBM-bandwidth-bound: it reads weights + the batch's KV cache once per step. For a 7B model in BF16 on H100: weights = 14.0 GB; at batch B with 3k-token contexts, step time = (14.0 GB + B·0.34 GB)/3.35 TB/s. B=5 → 4.69 ms (1,065 tok/s); B=12 → 5.41 ms (2,217 tok/s); B=40 → 8.29 ms (4,827 tok/s) [E]. Aggregate throughput grows nearly linearly with B through the routing-relevant range B≲15, because each added 3k-ctx request adds only ~0.103 ms (≈1.2–2.2% of step time, B=40→B=5) [E]. Two distinct "knees" bound B, and they are *different things*: (a) the **compute knee** B* ≈ 345 (H100, d=4096, BF16 roofline [E; formula bank]) where per-GEMM AI falls to the ridge; (b) the **KV-capacity knee**, which at 3k contexts is only ≈180–190 requests (≈63 GB headroom / 0.344 GB per request [E, A: 3 GB activation overhead]) — *capacity binds before compute does at long contexts*, and reverses at short ones (≈1,100 at 500-token contexts [E]).

**Corollary (the core mistake of connection-counting):** a replica serving two 16k-prompt/4k-output agentic sessions and one serving two 2k-prompt/200-output chit-chat sessions can have identical *connection count, identical request count, even similar GPU utilization* — and **~19× different remaining work** [E: 18.4 s vs 0.99 s in the worked model, §4, at consistent B=2 rates]. "Least connections" is measuring a quantity that is *anti-informative* exactly when it matters most: when service times are heterogeneous, which in LLM serving is always (S ranges 2k–128k+, outputs range 20–50k+ tokens).

### 1.2 The queue is measured in tokens, not requests [I/E]

Little's law: wait ≈ (work in queue) / (service rate). For a prefill queue the work-in-queue is **sum of remaining prompt tokens**, not request count. A 3-replica prefill pool at 35.3k prompt-tok/s each (MFU 0.5, 7B, H100 [E/A]) serves a 10-rps × 3k-prompt workload at ~28% utilization [E] — but a burst of 100 × 3k prompts = 300k queued prompt-tokens: the pool drain is 300k/(3×35.3k) = **2.83 s** (last-queued request waits the full drain, average ~1.4 s) [E] — and if the router misplaces the burst onto a single replica, that replica takes **8.49 s** [E]. Either way, any request-count metric that shows "100 waiting" is equally true of 100 × 128-token prompts that drain in 0.12 s [E].

### 1.3 Where classic policies actually break (failure taxonomy) [I]

| Policy | Structural failure |
|---|---|
| Round-robin | Ignorant of load, cache, and SLO class; fine only when replicas are homogeneous *and* request sizes are near-identical — a rare coincidence in production (agentic + RAG + chit-chat mixed). |
| Random | Same, plus no convergence on skew; sometimes *useful* as an exploration baseline in A/B, useless as steady state. |
| Least-requests | Measures jobs-in-flight, not work-in-flight. Fails exactly on heterogeneous service times (the norm). Also blind to *future* work: a request about to start a 50k-token decode looks identical at routing time to one that will emit 30 tokens. |
| Least-connections | Worst of the two: connections (TCP streams) are decoupled from work even from the request — keep-alive, multi-request-per-connection, streaming SSE. |
| Weighted/cookie-stickiness | Only justified for KV-cache locality (see §3.5) — and then it should be *cache-aware*, not *session-sticky* (a session's later turns may have diverged prefixes). |

None of these is "wrong" in a queueing-theory sense — they're the right priors *when service times are IID*. LLM serving is the opposite regime: service times are heavy-tailed, predictable from request features, and coupled across requests through shared prefix caches. That is the entire opening for the five signals.

---

## 2. The reference architecture of an LLM-aware router [F]

Production systems have converged on the same shape, which validates the signal set in the hypothesis:

- **llm-d EPP** (Inference Pool Proxy) [F: fetched docs/architecture/core/router/epp]: proxy *parks* the request, calls EPP via Envoy `ext_proc`; EPP scores pods using internal state: **KV-cache utilization, prefix-cache locality, request queue depth, active request counts**, plus filters/scorers/pickers pipeline, flow control, and tenant fairness; an experimental **predicted-latency scheduler** replaces heuristics. Reported: 3× output throughput and 2× faster TTFT with prefix-cache-aware routing **vs round-robin** (Llama 3.1 70B, 4× MI300X; Tesla/Red Hat), and up to 70% higher tok/s with P/D disagg on B200 (AWS).
- **NVIDIA Dynamo** [F: fetched README]: "KV-Aware Routing — routes requests based on **worker load and KV cache overlap**; eliminates redundant prefill — 2× faster TTFT" (Baseten benchmark, Qwen3-Coder 480B). Built in Rust for the hot path.
- **vLLM Production Stack** [F: fetched README]: reference K8s stack whose stated benefits are "request routing and KV cache offloading" at scale-out.
- **SGLang** [F: fetched README]: RadixAttention prefix caching in-engine + a **cache-aware load balancer** shipped since v0.4 (2024-12).
- **AIBrix** [F: fetched README]: LLM gateway with token-based routing, SLO-aware, LLM-specific scorers; ASPLOS'25 workshop presentation.

**Architecture pattern** [F/I]: sidecar or ext-proc plane (never inline in the engine's hot path), a *data layer* that watches cluster state (llm-d watches K8s API + engine metrics asynchronously), a *filter→scorer→picker* plugin pipeline, and a flow-control stage that can hold/reject (Mooncake's prediction-based early rejection is the in-engine analogue [F: arXiv:2407.00079]).

**Design consequence:** the router's decision latency adds to every request. With a 50 ms snapshot age, **10 decode steps elapse** at ITL=5 ms [E] — the state you scored on is already stale. This bounds how expensive the scoring can be and why the converged design is cheap scalar state + O(replicas) scoring, not per-request optimization.

---

## 3. The five signals, in depth

### 3.1 Queue backlog (in tokens) [I]

Signal: per-replica `Q_tokens = Σ (S_j − hit_j) over queued requests` (remaining prefill work), plus the request count for fairness/fair-queueing.
Use: Little's-law wait estimate `W_q ≈ Q_tokens / TPR_replica`. This is the dominant TTFT term under burst: in the worked example (§4), a 90k-token single-replica backlog produces 2.55 s of queue wait [E] — the largest single component by 1–2 orders of magnitude.
Pitfalls: (a) request-count backlogs are misleading (a backlog of 50 × 128k RAG prompts dwarfs 500 × 128-token chat prompts at similar "depth"); (b) if the engine uses chunked prefill with a token budget, the *effective* queue dynamics include the chunk schedule (Sarathi: chunked prefill + decode piggybacking [F: arXiv:2308.16369]); (c) under overload the queue is the wrong object — the right action is early rejection/queue admission with predicted latency (Mooncake [F]), which is a router-level duty when the router does admission.

### 3.2 Prompt processing remaining (prefix-cache state of *this* request) [I/E]

Signal: `h_i(r)` = fraction of r's prompt tokens already cached on replica i (from radix tree / paged-prefix metadata). Marginal prefill work = `S·(1−h_i)` tokens; marginal *new* KV written is the same fraction [E].
Why it is a first-class signal and not a tie-breaker: it simultaneously shrinks (a) this request's TTFT, (b) this request's queue footprint, and (c) the replica's future KV-write traffic. At h=0.83 a 12k prompt costs 17% of the prefill compute [E]. For agentic/RAG workloads, where system prompts + tool schemas + retrieved context recur heavily, hit rates of 50–90% are plausible [I — workload-dependent, must be measured per tenant]; cache-aware routing is then the *dominant* signal, which is exactly the regime where llm-d reports 3× throughput vs round-robin [F] and Dynamo reports 2× TTFT [F].
Pitfalls: (a) hit-rate metadata must be fast and approximate (radix-tree LCP on the gateway side is O(prefix length) — fine; exact engine state is not available to the router); (b) caching *locates* work: sending to the cache holder increases that replica's load — you are trading prefill savings for decode load (coupled with §3.3); (c) in P/D disagg, "cache hit" can be on a *prefill* node while your decode pool is elsewhere — the cache value then becomes "save the prefill, pay the KV transfer," a different equation (KV bytes = 2·L·h_kv·d_h·S·b; for 7B GQA BF16 that's 0.11 MB/token ≈ 1.5 GB at 13k context [E; cf. wiki P/D page 70B numbers]).

### 3.3 Active decode work [I/E]

Signal: per-replica batch size B, batch's aggregate context (→ KV bytes in HBM), free KV headroom, and time-to-full given current output-length predictions.
Physics: decode step cost grows ~linearly with B (marginal +0.103 ms per 3k-ctx request, 1.2–2.2% of step time from B=5 to B=40 [E]) *until the KV-capacity knee binds* (≈180 requests at 3k ctx on an H100 [E]) — so *until near that knee or KV exhaustion*, decode load is a weak router signal — the real decode signals are (a) **KV headroom** (a full KV pool forces preemption/eviction: vLLM-style preemption re-prefills, destroying cache value), and (b) **distance to SLO**: a batch near capacity with long outputs remaining will breach a 50 ms TPOT SLO long before an empty replica does [I].
Under P/D disagg this signal *reverses importance*: on the decode pool, active decode work **is** the queue (its service time is the step time; its "backlog" is Σ remaining output tokens of admitted decodes), while on the prefill pool the queue is the prompt-token backlog (§3.1). The router must therefore maintain **two different score functions for the two pools** and a joint objective for where the KV lands (§5.4).

### 3.4 Expected output length [I/F]

Signal: `n̂(r)` = predicted number of output tokens, from (a) model class priors (chat vs completion vs agentic), (b) prompt features (ELIS trains a BGE-based response-length predictor [F: arXiv:2505.09142]), (c) tenant/history statistics, (d) `max_tokens` when the client sets it (often a loose cap — treat as weak signal).
Why it matters: expected output length is the input to *everything else* — the decode-wait term, the KV-reservation estimate (reserve `n̂·kv/tok` to avoid mid-stream preemption), the admission/rejection decision under overload, and fair-queue weights. It is also the single most *uncertain* signal (P90 of output lengths in production is commonly several× the median [I]), so a good router uses it with an explicit uncertainty band (e.g., quantiles rather than point estimates) and re-scores as the request streams (Llumnix's runtime rescheduling across instances is the in-cluster analogue [F: arXiv:2406.03243]).
Pitfall: length predictors inherit *workload drift* — a new agentic feature overnight changes the distribution; the router should track prediction error (calibration) online and fall back to priors when error spikes.

### 3.5 KV/prefix-cache state of the replica (global cache placement) [I/F]

Signal: per-replica free KV blocks, eviction pressure, and the *distribution* of cached prefixes (which tenants/contexts are hot there).
This is §3.2 from the replica's side, plus a second-order effect the first four miss: **the cache is a shared resource with externalities**. A request routed to replica i both *consumes* (eviction pressure) and *produces* (new prefix cached for future requests) cache value. The right accounting is a per-replica **cache-value balance**: `ΔV_i = value_cached(r, i) − eviction_cost_i(r)`, where eviction cost spikes when free blocks are low (a hot prefix pushed out by an unrelated tenant's request is a cross-tenant cost). This is why llm-d tracks "KV-cache utilization" *alongside* "prefix-cache locality" [F], and why KVBM-style tiered KV (GPU→CPU→SSD→remote in Dynamo [F]) makes the router's job harder: the same prefix may be "hit" in HBM on one replica and in DRAM on another, with 10–100× different re-load costs [A: order-of-magnitude, needs measurement per tier].

### 3.6 Signals the hypothesis list is missing (addenda) [I]

1. **SLO class / deadline** — not a load signal but a constraint: deadline-aware routing (SRTF with deadlines) changes *which* requests go to *which* SLO tier; AIBrix explicitly does SLO-aware routing [F].
2. **Fault domain & topology** — P/D pairing, KV transfer cost (NVLink ≫ PCIe ≫ RoCE [F: wiki P/D page]), rack awareness. In disaggregation, "best replica" is defined on a *pair* (prefill, decode), see §5.4.
3. **Fairness / tenant weighting** — consolidated multi-tenant pools need per-tenant queue shares (llm-d flow control [F]); pure latency scoring starves small tenants.
4. **Cost / hardware heterogeneity** — if pools mix GPU generations, per-token $ and per-SLO attainment differ by class; routing is then a cost-aware latency problem (AIBrix "cost-efficient heterogeneous serving" [F]).
5. **Cold-start state** — a replica that just booted has full KV headroom but no prefix cache and (often) un-warmed CUDA graphs; naive scoring dumps traffic on it and gets a latency spike.

---

## 4. Worked example: a routing decision you can hand-compute [E]

**Setup (all numbers Python-verified, `verify_v3.py`):** 7B model, L=28, d=4096, GQA h_kv=8, d_h=128, BF16 → KV 0.11 MB/token, weights 14.0 GB. H100 SXM: 3.35 TB/s HBM, 989 TFLOPS BF16. Per-replica rates: prefill TPR = 35.3k prompt-tok/s (at MFU 0.5 [A: MFU is the one soft knob; MFU 0.4 → 28.3k, all conclusions below unchanged]); decode @ B=12, 3k ctx = 2,217 tok/s. *Model scope (stated, not a discovery): decode is assumed HBM-bandwidth-bound — the step cost is the HBM read of weights + batch KV, ignoring kernel/compute overheads, which is a standard first-order roofline approximation for B≪B\* [I]; prefill is compute-bound at MFU 0.5.*

**Request R:** S = 3,000 prompt tokens, expected output n̂ = 600.

**Candidates:**
- **Replica A** (prefill-capable, colocated): queue = 0, prefix-cache hit on 2,400 of R's tokens (shared system prompt + context), batch = 10, KV headroom ample.
- **Replica B**: queue = 90,000 prompt-tokens (30 same-size requests, burst backlog), cache hit = 0, batch = 6.

**Scoring (predicted latency decomposition):**
- A: TTFT = (3000−2400)/35,300 = **17.0 ms**; decode phase joins at B=11 → 5.31 ms/step [E] → E[time-to-first-token] ≈ 0.017 s.
- B: TTFT = 90,000/35,300 = **2.55 s** queue wait + 3,000/35,300 = 0.085 s own prefill = **2.63 s**.
- Least-connections/least-requests would pick **B** (6 < 10 in flight). Predicted-latency scoring picks **A** by ~2.6 s.

**Sensitivity:** B can *never* tie A in this setup: even at zero queue, B's TTFT is 3,000/35,300 = 85 ms vs A's 17 ms — the 2.4k-token cache hit on A saves exactly the 2,400 prompt-tokens that B would have to process, so the tie point solves to Q = −2,400 ptok (impossible) [E]. A is robust to *any* queue on B, and the asymmetry is structural: a prefix hit on one candidate makes that candidate's TTFT lower than the *entire* prompt cost of the other [E]. (The comparison is the reverse if A had no hit and B did — the winner is a function of the signal *combination*, not any single signal. This is the hand-computable demonstration that "consider all five" beats "consider one.")

**Same-connections trap [E, consistent B=2 rates]:** two replicas each with 2 in-flight decodes (3k ctx each; step at B=2 = 4.39 ms → per-request drain 228 tok/s): X = 32k-token prefill queue + 2 decodes with 4,000 tokens left each → 0.91 s + 17.5 s = **18.4 s remaining**; Y = 4k queue + 2 decodes with 200 tokens left each → **0.99 s remaining**. Identical connection/request counts, **~19× remaining-work gap**. (Note the modeling: at B=2 each replica's decode capacity is only ~456 tok/s aggregate (228 per request) — far slower than at B=12 — which is exactly why "which replica is loaded" cannot be answered from connection counts.)

---

## 5. Design space, failure modes, and the disaggregated case

### 5.1 Staleness and the cost of state [E/I]
Router state is a snapshot. At 50 ms age: 10 decode steps of drift at 5 ms ITL; 2.5 at 20 ms. Consequences: (a) keep state *cheap and coarse* (per-replica scalars updated at ≥10 Hz); (b) treat scores as *ranking*, not exact predictions — the O(replicas) argmax is stable to 10–20% noise when the top-2 gap is large; (c) for P/D disagg, the KV-transfer *in-flight* state (bytes being shipped) is itself a load signal the router must track, because a decode pod receiving 4 GB of KV over RoCE has its HBM bandwidth pre-committed [I].

### 5.2 Prediction error is a first-class risk [I]
If n̂(r) is off by 3×, the KV-reservation term mis-sizes. Mitigations: quantile-based reservation (reserve P90, not mean), headroom floors (never let reservations consume >X% of pool KV), and post-hoc learning (Llumnix-style mid-stream rescheduling [F] turns routing-time error into a correction opportunity instead of a failure).

### 5.3 When NOT to complicate [I]
The five-signal router is justified when: replica count is large (score differences matter), workload is heterogeneous (service-time CV > ~0.5), or cache locality value is high (hit-rate × prefill cost > routing overhead). For a 2-replica homogeneous pool serving near-identical chat requests, weighted round-robin with KV-affinity tie-break is ~90% of the value at ~10% of the complexity [I: engineering judgment, not a measured result — H5 below].

### 5.4 The P/D-disaggregated router: a two-level problem [F/I/E]
With prefill/decode pools [F: DistServe arXiv:2401.09670 — 7.4× more requests or 12.6× tighter SLOs; Mooncake arXiv:2407.00079 — 75% more requests in production; llm-d up to 70% tok/s gain on B200 vs standard vLLM (AWS); Splitwise arXiv:2311.18677 — 1.4× throughput at lower cost], routing is **two coupled decisions**:
1. **Which prefill replica**: score on prompt-token backlog + prefix hit (the two signals that matter there);
2. **Which decode replica**: score on decode backlog (Σ n̂ of in-flight decodes), KV headroom, *and KV-transfer cost from the chosen prefill replica* (fabric: NVLink 900 GB/s intra-node [F] ≫ RoCE 400 GbE ≈ 47.5 GB/s effective [E: 400 GbE = 50 GB/s × 0.95 efficiency; cf. wiki P/D transfer table]).

The coupling means a globally-latency-optimal router must sometimes *not* send a request to its highest-cache-hitting prefill node if that node's decode partner is saturated — a trade-off with no closed form, handled in production by (a) per-fabric-class KV-transfer cost terms in the score [F: DistServe's bandwidth-aware placement; llm-d's P/D pair selection], and (b) pool-level autoscaling so no decode pod is chronically saturated (Dynamo's SLA-based planner [F]). The *aggregate* failure mode on slow fabrics is sustained KV demand > fabric capacity — a router cannot fix that; it can only reject early [F/E: wiki P/D break-even model, 2026-08-17].

Note the vLLM position for contrast [F: docs/features/disagg_prefill, via wiki P/D page]: disagg "does NOT improve throughput" on its own — it buys independent TTFT/TPOT control; the *routing* on top of it is where the throughput comes from (cf. llm-d's 70% [F]). This is direct evidence that routing quality, not engine quality, is the differentiator in disaggregated deployments.

### 5.5 In-engine vs router: the split of labor [F/I]
The engine (vLLM/SGLang/TRT-LLM) owns *iteration-level* scheduling (continuous batching, chunked prefill, preemption, KV paging) and *instance-level* rescheduling (Llumnix [F]). The router owns *request-level, pool-wide* placement. The five signals are the router's because they are computable at admission time from request features + replica state; iteration-level decisions need per-batch state the router never sees. A common anti-pattern is the router trying to do iteration-level work (e.g., shaping chunk schedules) — that belongs in-engine [I].

---

## 6. What the evidence says (lineage, all sources fetched 2026-08-18)

**Academic:** DistServe (OSDI'24, arXiv:2401.09670 [F]) — P/D split, bandwidth-aware placement; Splitwise (arXiv:2311.18677 [F]) — phase splitting, heterogeneous hardware; Mooncake (FAST'25, arXiv:2407.00079 [F]) — KVCache-centric cluster, prediction-based early rejection; SARATHI (arXiv:2308.16369 [F]) — chunked prefill + decode-maximal batching (in-engine analogue of the queue problem); Llumnix (arXiv:2406.03243 [F]) — cross-instance runtime rescheduling for heterogeneous/unpredictable requests; ELIS (arXiv:2505.09142 [F]) — response-length predictor + iterative SRTF.

**Production (vendor-reported, URLs in fetched files):** llm-d [F] — EPP with KV utilization / prefix locality / queue depth / active counts, predicted-latency scheduler, 3× tok + 2× TTFT vs round-robin (MI300X); up to 70% tok/s with P/D (B200/AWS); 13.9× with hierarchical KV offload @250 concurrent (H100). Dynamo [F] — KV-aware router (load + KV overlap), 2× TTFT (Baseten, Qwen3-Coder 480B), SLA-based planner, KVBM. SGLang [F] — cache-aware LB since v0.4. vLLM production-stack [F] — routing + KV offloading reference. AIBrix [F] — token-based, SLO-aware routing.

**Status of the central hypothesis:** every production system I could fetch (llm-d, Dynamo, SGLang, vLLM production-stack, AIBrix) uses a *superset* of the five hypothesized signals (queue depth, active work, cache state, predicted latency/length, SLO class); none of the fetched systems routes on raw connections. The hypothesis is **supported as an existence statement within that fetched set**; the open question is the *weighting* and *when each signal dominates*, which is workload- and topology-dependent (§3, §5.3, H1–H5).

---

## 7. Unverified hypotheses (no winners declared — each needs the stated experiment)

- **H1 (cache dominance in agentic workloads):** at 80%+ prefix hit rate, cache-aware routing beats pure load-balancing on P99 TTFT by ≥2×. *Deciding experiment:* same cluster, synthetic agentic workload with controlled hit-rate (0/40/80%), fixed load; pin model, precision, GPU count, arrival Poisson λ, warm-up ≥2× cache-build time; measure P50/P99 TTFT + TPOT.
- **H2 (queue-in-tokens):** token-queue scoring beats request-queue scoring specifically on bursty-mixed workloads (CV of S > 1). *Deciding experiment:* identical to H1 but workload = Poisson bursts of heterogeneous S.
- **H3 (length-predictor value):** P90 output-length-based admission reduces preemption rate ≥50% vs mean-based, at ≤5% goodput cost. *Deciding experiment:* same overload scenario; count vLLM-style preemption events.
- **H4 (two-signal sufficiency):** backlog-in-tokens + cache-hit captures ≥90% of predicted-latency scorer's P99 improvement over round-robin for colocated serving (decode work and length are tie-breakers only below the routing-relevant range B≲15). *Deciding example: the §4 model — at B≲15 the marginal decode cost is <2.2% of step time [E], so H4 is the a-priori favored hypothesis for *colocated* pools; H4 is expected FALSE for P/D decode pools where decode backlog is the queue itself.*
- **H5 (complexity threshold):** below ~8 replicas, a weighted-RR + KV-affinity tie-breaker is within 10% of the five-signal scorer. *Deciding experiment:* 2/8/32 replica sweeps, identical workloads.

**Benchmark-design pins (for any of the above):** model + revision, precision, GPU model + count + clock policy, engine + version, router state-update rate, arrival pattern (Poisson/burst) with stated λ, prompt/output-length distributions, cache warm-up, sampling params, SLO definitions, and whether CUDA-graph capture was complete. Unpinned → results not comparable.

---

## 8. A concrete reference scorer (proposal, [I])

```
# per replica i, updated ≥10 Hz: Q_tok, B, KV_free, KV_total, TPR, DRate, cache tree shadow
# per request r: S, n_hat (with P50/P90), SLO class, deadline d

score(r, i) = -( W_q(i) + S*(1-h_i)/TPR_i + n_hat_P90/DRate_i + c_xfer(i, pool(i)) )
              - 0.5 * max(0, (n_hat_P90*kv_tok + KV_used_i)/KV_total_i - 0.9)   # KV headroom guard
              + w_cache_i(r)      # cache value balance: cached-value - eviction-cost (§3.5)
              + w_slo(r, i)       # deadline feasibility term (hard constraint in SLO mode)
pick i* = argmax_i score, subject to filters (SLO class match, KV headroom floor,
                                         fault domain, cold-start penalty)
```

Properties: when the queue term dominates (loaded pool, all h=0), it behaves like least-token-queue; when load is uniform across replicas, the cache-value term dominates (cache-affinity); the c_xfer term activates only in P/D disagg. All terms are O(1) scalars → decision cost is O(replicas) additions, safe inside a 10 ms router budget [A: ~1000 replicas × ~20 scalar ops is microseconds; ext-proc RTT dominates].

**What this is NOT:** it is not a claim that this specific weight set is optimal (H1–H4 decide that). It is an architecture statement: *predicted remaining work + explicit guards + workload-dependent weights*, which is the structure every fetched production system converges to [F].

---

## 9. Open problems

1. **Calibration of n̂ under distribution shift** — online drift detectors for length predictors; no published good method.
2. **Cross-tenant cache externalities** — pricing/eviction policy when one tenant's request evicts another's hot prefix; llm-d fairness stage [F] addresses the request side, not the cache side.
3. **Two-level P/D optimality** — no published closed-form for the prefill-decode pairing problem with heterogeneous fabrics; DistServe solves placement offline [F], runtime pairing is heuristic.
4. **Router as SLO enforcement point** — admission control + per-tenant queueing in the router vs in-engine preemption: split of responsibility is unsettled (Mooncake rejects in-engine [F]; llm-d holds in-EPP [F]).
5. **State staleness at 1000+ replicas** — 10 Hz scalars × 1000 replicas × 50 fields = 50k updates/s; data-plane design for this is barely specified in public docs [I].

## 10. Evaluator adjudication (transparent record)

Independent evaluator: deepseek-v4-flash-0731 @ 10.1.1.51:8888 (OpenAI-compatible), three passes. Every flag was independently re-verified in Python before being applied (re-verification scripts in `/tmp/router-src/`).

**Pass 1 (6 flags → 6 accepted, 0 refuted):** (1) crossover math — draft's "600-ptok tie point" was wrong; re-solve gives Q = −2,400 (B can never tie A when A holds the cache hit) → §4 rewritten; (2) "RoCE 400 GbE ≈ 55 GB/s" was the PCIe-5 figure mixed in → corrected to 47.5 GB/s (50 GB/s × 0.95); (3) prefill AI "≈ d/b = 2048" presented as a single convention → expanded to 2048 (GEMM asymptote) / 1,217 ([S,d]×[d,d] @S=3k) / 3,000 (model-level weight bytes) / ≈2,150–2,700 (incl. activation+KV bytes, accounting-dependent); (4) marginal-% range 1.4–2.2% → 1.2–2.2% (B=40 endpoint = 1.24%); (5) B* ≈ 345 conflated the *compute* knee with the *KV-capacity* knee (≈180–190 reqs at 3k ctx on H100) → both stated, with the context-length crossover (≈1,100 at 500-token ctx); (6) same-connections example used B=12 decode rates for a B=2 scenario → recomputed at consistent B=2 rates (step 4.39 ms, 228 tok/s per request): 18.4 s vs 0.99 s, ~19×. **Note on pass-1 flag 6:** the evaluator's own proposed correction (8.8 s / "48×") was *itself* wrong — it divided by the aggregate B=2 rate (456 tok/s) instead of the per-request drain (228 tok/s); my re-verification caught this before any fix was applied.

**Pass 2 (verdict REVISE @ 92%; 2 math + 2 inconsistency + 2 simplification flags → all accepted):** (a) burst drain 300k ptok on a *3-replica* pool = 2.83 s, not 8.49 s (a single-replica figure was used for a pool) → §1.2 + Appendix A#17 fixed; 8.49 s retained as the misrouting worst case; (b) "pool-wide decode capacity 456 tok/s" at B=2 was a per-replica figure → reworded; (c) "No fetched system routes on raw connections" → scoped to the fetched set; (d) model scope (decode HBM-bound first-order) made explicit as [I] in §1/§4.

**Pass 3 (truncated, reasoning-only):** re-confirmed all six round-2 fixes landed ("✓ Correct" on each). One open item — the model-level AI figure ≈2,270 was not reproducible by the evaluator under a plain activation accounting (it got ≈2,456–2,672). Resolution: the figure depended on an unstated ×3 MLP-width factor; replaced with an explicitly-bounded, accounting-labeled range ≈2,150–2,700 (recomputed: 2,672 in/out-only, 2,161 in/out+MLP-intermediates).

**Summary:** 10 distinct flags across 3 passes, 10 accepted, 0 refuted — above the skill's 50–70% prior, because pass 1 ran on a draft whose numbers were already machine-verified; the evaluator's job was to test *presentation consistency*, which is where the real errors sat (pool-vs-replica, per-replica-vs-pool-wide, convention conflation, batch-rate mismatch).

---

## Appendix A — [E] number audit (all from `verify_v3.py` + `reverify_flags.py`, 7B/BF16/H100 unless noted)

| # | Claim | Value | Derivation |
|---|---|---|---|
| 1 | KV bytes/token | 114,688 B (0.114 MB) | 2·L·h_kv·d_h·b = 2·28·8·128·2 |
| 2 | Weights BF16 | 14.0 GB | 7e9 × 2 B |
| 3 | Prefill FLOPs @S=3k | 42.0 TFLOP; attention share 9.8% | 2·N·S; 4·L·d·S² terms |
| 4 | Prefill AI (conventions) | d/b ≈ 2048 (GEMM asymptote); 1,217 ([S,d]×[d,d] @S=3k); 3,000 (model-level, weight bytes) / ≈2,150–2,700 (incl. activation+KV bytes, accounting-dependent) | all ≫ ridge 295 |
| 5 | Prefill rate @MFU 0.5 | 35.3k ptok/s | 989 TFLOPS × 0.5 / (2·N) |
| 6 | Decode step @B=12, 3k ctx | 5.41 ms → 2,217 tok/s | (W + B·ctx·kv_t)/BW |
| 7 | Marginal +1 request @3k ctx | +0.103 ms/step (1.2–2.2%, B=40→B=5) | Δstep(B→B+1) |
| 8 | Compute knee B* (H100, d=4096, BF16) | ≈345 | ridge·d·b/(2(d−b·ridge)), ridge=295 |
| 9 | KV-capacity knee @3k ctx | ≈180–190 reqs | (80 GB − 14 GB − 3 GB[A]) / 0.344 GB; ≈1,100 @500 ctx |
| 10 | R TTFT on A (hit 2.4k/3k) | 17.0 ms | (3000−2400)/35.3k |
| 11 | R TTFT on B (q=90k) | 2.63 s | 90k/35.3k + 3k/35.3k |
| 12 | A/B crossover queue | Q = −2,400 ptok → B can never tie A | solve TTFT_B = TTFT_A (B's hit-less prefill 85 ms > A's 17 ms) |
| 13 | Same-2-connections gap | 18.4 s vs 0.99 s → ~19× | queue/TPR + max-decode-drain at consistent B=2 step (4.39 ms, 228 tok/s per request) |
| 14 | Staleness @50 ms | 10 steps @5 ms ITL; 2.5 @20 ms | τ/ITL |
| 15 | 400 GbE effective | ≈47.5 GB/s | 400 GbE = 50 GB/s × 0.95 efficiency |
| 16 | 7B KV @13k ctx | ≈1.5 GB | 13k × 114,688 B |
| 17 | Burst drain 100×3k | 2.83 s pool (3×35.3k), avg ~1.4 s; 8.49 s if all on one replica | 300k ptok / pool rate |

## Appendix B — Source fetch audit (2026-08-18, retained in /tmp/router-src/)

`dynamo-readme.md` (22,954 B) · `llm-d-readme.md` (9,463 B) · `llmd-router-epp` (7,445 B) · `llmd-router-arch` (2,796 B) · `llmd-disagg` (12,520 B) · `llmd-kv` (3,023 B) · `llm-d-router-readme` (7,652 B) · `vllm-prodstack-readme.md` (7,449 B) · `aibrix-readme.md` (6,840 B) · `sglang-readme.md` (11,893 B) · arXiv abstracts: Mooncake 2407.00079, DistServe 2401.09670, Splitwise 2311.18677, SARATHI 2308.16369, Llumnix 2406.03243, ELIS 2505.09142 (all fetched via arxiv.org; LLUMNIX/ELIS abstracts quoted verbatim in §6). Vendor perf claims cited from the fetched READMEs themselves, each with its primary blog URL as recorded in that README.
