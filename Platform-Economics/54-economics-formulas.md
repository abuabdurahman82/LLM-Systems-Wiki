# 54 — Economics Formulas (Mathematical Toolkit)

`LAST_UPDATED: 2026-08-24` · Status: reference page · Every number computed in
[scripts/economic_foundation.py](scripts/economic_foundation.py) — **do not trust
mental arithmetic; re-run the script.** For each formula: variables, assumptions,
worked example. **Avoid false precision** — these are illustrative, dated 2026-08.

## 1. GPU-hour cost (fully loaded)

$$\frac{\$}{\text{GPU-hr}} = \frac{\text{Annualized fleet cost}}{\text{GPUs} \times 8760 \times \text{utilization}}$$

- **Variables:** annualized fleet cost (capex/3yr + power×PUE + ops + software),
  GPU count, utilization.
- **Assumptions:** 3-yr depreciation, PUE, $/kWh, ops per node — declared in the script.
- **Worked:** 8×H100 node ≈ $104k/yr → **$1.49/GPU-hr @100%**, **$2.13 @70%**, **$7.45 @20%**.

## 2. Cost per 1M tokens

$$\frac{\$}{\text{1M tokens}} = \frac{1{,}000{,}000}{\text{tok/s}} \cdot \frac{\$/\text{GPU-hr}}{3600}$$

- **Variables:** tokens/sec (measured per model/engine), $/GPU-hr.
- **Worked:** decode 25k tok/s @ $2.13/GPU-hr → **≈ $0.02/1M** (self-host); vs
  API GPT-4.1 **$2 in / $8 out** per 1M.

## 3. Utilization-adjusted cost

$$\text{adjusted} = \frac{\text{nominal}}{\text{utilization}}$$

- **Worked:** 20% → 5× nominal; 70% → 1.43×; 90% → 1.11× ([05](05-gpu-utilization-economics.md)).

## 4. Fully loaded cost

$$\text{Fully loaded} = \text{GPU} + \text{CPU} + \text{RAM} + \text{storage} + \text{network} + \text{licenses} + \text{power} + \text{cooling} + \text{ops} + \text{support} + \text{software} + \text{idle} + \text{replication} + \text{availability}$$

## 5. Break-even volume (local vs API)

$$\text{Break-even req/mo} = \frac{\text{Fixed monthly local cost}}{\text{API \$/req}}$$

- **Worked:** fixed node ~$8,703/mo → **16.6M req/mo** vs gpt-4o-mini (~$0.0005/req),
  **1.2M** vs GPT-4.1 ($0.007), **0.39M** vs gpt-5.6-sol ($0.0225) ([29](29-local-vs-api-economics.md)).

## 6. Cloud/local break-even (burst)

$$\text{Burst Value} = \text{Avoided Queue Cost} + \text{SLO Protection} - \text{Cloud Premium} - \text{Data Risk}$$

Burst when value > 0 ([28-cloud-bursting-economics](28-cloud-bursting-economics.md)).

## 7. Expected model-routing cost

$$\mathbb{E}[C] = P(\text{small ok}) C_{\text{small}} + P(\text{escalate})(C_{\text{small}} + C_{\text{large}})$$

- **Worked:** $P=0.8$, $C_s{\$}0.0004$, $C_l{\$}0.004$ → **$0.0012/req** vs $0.004
  always-large = ~70% saving ([11](11-economic-model-routing.md)).

## 8. Cache ROI

$$\text{Cache Value} = \text{Avoided Prefill Cost} - \text{Memory Opportunity Cost}$$

- **Worked:** $0.07 − $0.02 = **$0.03/1M** at 0.6 hit (self-host; cloud API is a
  bigger $ win) ([08](08-kv-cache-economics.md)).

## 9. SLO headroom

$$\text{Headroom} = 1 - \rho_{\text{target}}, \quad \rho = \lambda/\mu$$

$$\text{Extra cost} = \frac{\text{Fixed cost}}{\rho_{\text{target}}} - \text{Fixed cost}$$

- **Worked:** running at 50% vs 70% raises effective $/GPU-hr ~40% ([17](17-slo-economics.md)).

## 10. Agent task cost

$$\text{Agent task} = \sum_{\text{calls}} \text{cost}_{\text{call}} + \text{retry/failure cost}$$

- **TAF** = model calls per user task; 27 calls ≈ **27×** one-shot ([35](35-agent-economics.md)).

## 11. Cost per good request (goodput)

$$\text{Cost/Good Request} = \frac{\text{total platform cost}}{\text{good requests delivered}}$$

where *good* = SLO-compliant + acceptable quality ([43-goodput-economics](43-goodput-economics.md)).

## Cost discipline

- All numbers above **ILLUSTRATIVE**, $USD, **price date 2026-08**, with declared
  assumptions; re-run [scripts/economic_foundation.py](scripts/economic_foundation.py)
  after any change. Cloud prices (H100 $6.88–11.06/GPU-hr; API $0.15–30/1M) are
  dated snapshots from provider/aggregator pages (2026-07/08) — **verified-at-time,
  not live quotes**.

## Related

[03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[49-llm-platform-economic-simulator](49-llm-platform-economic-simulator.md) ·
[51-multi-tenant-llm-platform-80-20](51-multi-tenant-llm-platform-80-20.md)

## Key takeaways

1. All formulas are implemented (and re-runnable) in the section's scripts.
2. Every worked example rests on declared variables, assumptions, and a price date.
3. Don't create false precision — round, label, and re-verify.
