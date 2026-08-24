# 45 — Cost of Failure

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Failures have an **expected economic cost**, and pricing reliability means
budgeting for them. The framework is classic risk math: **Expected Loss =
Probability × Impact**, applied to AI-specific failures (GPU failure, network
failure, model failure, provider outage, OOM, queue collapse, bad rollout,
hallucination incident, security breach). Reliability engineering
([Production-Operations/](../Production-Operations/README.md)) is what *reduces*
probability and impact; economics is what decides *how much* to spend reducing
them ([17-slo-economics](17-slo-economics.md)).

## Failure catalog & economic analysis

| Failure | Probability driver | Impact | Mitigation (cost trade) |
|---|---|---|---|
| **GPU failure** | hardware MTBF | service loss, lost work | N+1, DR ([17](17-slo-economics.md), [Production-Operations/10-gpu-reliability](../Production-Operations/10-gpu-reliability.md)) |
| **Network failure** | fabric/links | requests fail/hang | redundancy, retries |
| **Model failure** | bad model/quality drift | wrong answers ([24-quality-observability](../Production-Operations/24-quality-observability.md)) | evals, canary ([25-model-governance](25-model-governance.md)) |
| **Provider outage** | third-party dependency | burst path down ([28](28-cloud-bursting-economics.md)) | fallback/multi-provider |
| **OOM** | memory/KV pressure ([08](08-kv-cache-economics.md)) | request loss, instability | quotas, admission ([21](21-admission-control-governance.md)) |
| **Queue collapse** | overload near ρ=1 ([05](05-gpu-utilization-economics.md)) | latency blowup | admission control |
| **Bad rollout** | release without canary | widespread errors ([27-canary-deployment](../Production-Operations/27-canary-deployment.md)) | canaries/rollback |
| **Hallucination incident** | model confabulation | user-visible wrong output | evals, guardrails ([36-evaluator-economics](36-evaluator-economics.md)) |
| **Security breach** | isolation weakness ([23](23-tenant-security-isolation.md)) | data exposure, legal, trust | isolation, audit |

## Expected Loss model

$$\text{Expected Loss} = \sum_{f} P(f) \times \text{Impact}(f)$$

where $f$ ranges over failure modes. This gives a **rational budget for
reliability**: spend up to Expected Loss (reduced) on prevention, not more.
That's the connective tissue between **reliability engineering** and
**economics**: every reliability dollar buys a reduction in `P × Impact`.

### Worked illustration (illustrative)
If a provider outage has P = 0.5%/yr and impact = $40k/yr of burst-path loss,
Expected Loss ≈ $200/yr — so spending $2k/yr on multi-provider fallback that
*fails to move P materially* is not justified; spending $150/yr on a cheap
circuit-breaker that halves the impact (→ $100 saved) is marginal. The reliabia
investment must beat the reduced Expected Loss. (Illustrative; your P and I
define the real answer.)

## Connect to the rest of the section

- **Cost per good request** ([43](43-goodput-economics.md)) excludes failed work —
  failure inflates it.
- **Goodput vs throughput** ([43](43-goodput-economics.md)) is degraded by
  queue collapse and bad rollouts.
- **SLO tiers** ([17](17-slo-economics.md)) price the redundancy that lowers
  failure probability for premium tenants.

## Related

[17-slo-economics](17-slo-economics.md) · [43-goodput-economics](43-goodput-economics.md) ·
[Production-Operations/09-llm-failure-taxonomy](../Production-Operations/09-llm-failure-taxonomy.md) ·
[Production-Operations/10-gpu-reliability](../Production-Operations/10-gpu-reliability.md) ·
[23-tenant-security-isolation](23-tenant-security-isolation.md)

## Key takeaways

1. Expected Loss = Probability × Impact per failure mode, summed.
2. AI failures: GPU, network, model, provider, OOM, queue collapse, bad rollout, hallucination, breach.
3. Spend on reliability up to the Expected Loss it reduces — not beyond.
4. Reliability engineering and economics are two sides of the same Expected-Loss coin.
