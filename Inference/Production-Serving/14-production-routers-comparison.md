# Production Routers & Gateways — Comparison Matrix
`LAST_UPDATED: 2026-08-22` · Status: matrix page · All cells tagged:
[F] = from fetched primary source (2026-08-22, audit `/tmp/ps-research/SOURCES.md`);
[F*] = vendor-reported performance claim (not independently verified);
[I] = inference. Projects move fast — re-fetch before quoting.

## The landscape at a glance
Two distinct product categories get conflated; keep them separate:
- **L0 gateways** (tenant/auth/quota/model-name routing, classic balancing):
  LiteLLM, Envoy AI Gateway.
- **L1 LLM-ware routers** (KV/cache/SLO-aware placement): llm-d, Dynamo,
  SGLang router, vLLM Production Stack, AIBrix; GIE is the *standard* that
  turns k8s gateways into inference gateways via an EPP.

## Matrix

| System | Layer | Routing signals | Cache-aware | P/D support | Admission / flow control | Extensibility | Notes |
|---|---|---|---|---|---|---|---|
| **llm-d (EPP)** | L1, k8s-native | KV util, prefix locality, queue depth, active counts [F] | Yes [F] | Yes (P/D pair selection, disagg serving) [F] | Flow control + tenant fairness stage [F] | filter→scorer→picker plugins; experimental predicted-latency scheduler [F] | Vendor-reported 3× throughput, 2× TTFT vs RR with cache-aware routing; up to 70% tok/s with P/D on B200 [F*] |
| **NVIDIA Dynamo** | L1+L3, engine-adjacent | worker load + KV overlap [F] | Yes [F] | Yes (disaggregated prefill/decode workers) [F] | SLA-based planner (capacity side) [F] | Rust data plane; planner/planner-driven scaling [F] | KVBM tiered KV offload; vendor-reported 2× TTFT (Baseten, Qwen3-Coder 480B) [F*] |
| **SGLang router** | L1 sidecar | cache-aware load balancing [F] | Yes — RadixAttention in-engine + router [F] | Yes (disaggregation support) [F] | In-engine | Engine-coupled | Ships with SGLang since v0.4 (2024-12) [F] |
| **vLLM Production Stack** | L1, k8s reference | KV-cache-aware + prefix-aware routing [F] | Yes [F] | Reference configs incl. disaggregated [F] | Router-level [I] | K8s reference stack, pluggable router [F] | Positioned as reference architecture; pairs with vLLM engines [F] |
| **AIBrix** | L0/L1 gateway | token-based, SLO-aware, LLM-specific scorers [F] | KV-cache awareness [F] | Partial [I] | SLO-guarantee oriented [F] | Pluggable policies | ByteDance-origin; heterogeneous-hardware cost routing [F] |
| **LiteLLM (proxy/Router)** | L0 | weighted pick (default), least-busy, latency-based, usage(TPM/RPM)-aware v2, cost-based [F: docs.litellm.ai/docs/routing] | No (no engine KV visibility) [I] | No [I] | Per-tenant RPM/TPM quotas, cooldowns, fallbacks, retries [F] | Custom routing strategy hook [F] | The right L0; not an L1 router — pair it with one |
| **Envoy AI Gateway** | L0 (ext-proc capable) | model-name routing, provider fallback [F] | No [I] | No [I] | Rate limits at gateway [I] | Envoy ext-proc → any EPP [F] | Becomes inference-aware when paired with a GIE EPP [F/I] |
| **Gateway API Inference Extension (GIE)** | standard + reference EPP | model-server metrics incl. prefix-cache status, LoRA availability; "kv-cache and request cost aware" [F] | Yes (prefix-cache-aware LB pattern) [F] | Disaggregated serving in scope [F] | Serving priority per model [F] | Any ext-proc gateway (Envoy Gateway, kgateway, GKE) [F]; production EPP = e.g. llm-d-router [F] | The standardization layer; reference EPP is for conformance, not production [F] |

## How to choose
- **Home lab / few replicas, OpenAI-compatible backends**: LiteLLM as L0
  (auth, quotas, fallbacks) + engine-native prefix caching; add an L1 router
  when replica count × heterogeneity justifies it (05's ladder, Lab 2). This
  is the running-example stack (01).
- **Kubernetes, multi-replica, mixed workloads**: GIE-capable gateway + a
  production EPP (llm-d), or Dynamo if you want the planner/KVBM bundle.
- **SGLang shops**: the bundled router covers cache-aware balancing with zero
  new infrastructure.
- **Regulated/multi-tenant**: prioritize the fairness/flow-control row
  (llm-d) and token-based quotas (LiteLLM) — see
  [13](13-multi-tenancy-fairness-priority.md).

## Caveats
- Vendor performance numbers ([F*]) are unreplicated marketing-adjacent
  claims; the deep-dive lists the deciding experiments (H1–H5).
- Matrix rows age in months; the *architecture pattern* (06) is the durable
  content.
- "Cache-aware" means different depths: router-side radix shadow (SGLang),
  metrics-reported locality (llm-d/GIE), or KV-overlap indexing (Dynamo).

## Related
[05-routing-policies-from-classic-to-llm-aware](05-routing-policies-from-classic-to-llm-aware.md) ·
[06-router-architectures](06-router-architectures.md) ·
`../../Serving-Engines/README.md` ·
`../Deep-Dives/llm-router-signals-deep-dive-2026-08-18.md` §2/§6

## Key Takeaways
1. Separate L0 gateways (LiteLLM, Envoy AI GW) from L1 LLM-aware routers
   (llm-d, Dynamo, SGLang, vLLM stack, AIBrix); you often want one of each.
2. GIE is the standard interface; llm-d/Dynamo are production EPP-class
   implementations of it.
3. Every L1 system routes on a superset of the five signals — none on raw
   connections [F].
