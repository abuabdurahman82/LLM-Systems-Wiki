# 11 — Economic Model Routing

`LAST_UPDATED: 2026-08-24` · Status: core page · Economics from
[scripts/economic_foundation.py](scripts/economic_foundation.py).

## 30-Second Explanation

The cheapest inference is the inference you **don't run on the big model**. A
**cascade router** tries a cheap model first and escalates to a premium one only
when confidence is low. The expected cost of cascading is
`P(small suffices)·Cost_small + P(escalate)·(Cost_small + Cost_large)`, which is
*strictly less* than always using the large model whenever `P(small ok) > 0` —
and with a strong small model the saving is large (in our worked example,
**~70%** vs always-large). Routing is thus a **cost lever that does not have to
sacrifice quality**, because the premium model still catches the hard cases.

## Architecture

```
Request
   ↓
Router
   ├── small model
   ├── medium model
   ├── premium reasoning model
   └── external cloud model
```

Router mechanics and signals live in
[Inference/Production-Serving/05-routing-policies-from-classic-to-llm-aware](../Inference/Production-Serving/05-routing-policies-from-classic-to-llm-aware.md)
and [06-router-architectures](../Inference/Production-Serving/06-router-architectures.md);
here we price the policy.

## Cascade routing

```
Cheap Model
    ↓
confidence sufficient?   YES → return
    ↓ NO
Premium Model
```

**Expected-cost model:**

$$\mathbb{E}[\text{Cost}_{\text{cascade}}] = P(\text{small suffices}) \cdot C_{\text{small}} + P(\text{escalate}) \cdot \big(C_{\text{small}} + C_{\text{large}}\big)$$

Compare against **always-large**: `C_large`.

### Worked example (computed)

- $P(\text{small ok}) = 0.80$, $C_{\text{small}} = \$0.0004$, $C_{\text{large}} = \$0.004$
- $\mathbb{E}[C_{\text{cascade}}] = 0.8(0.0004) + 0.2(0.0004+0.004) = \$0.0012$/req
- Always-large = $\$0.004$/req → cascade saves **~70%**.

The saving grows with $P(\text{small ok})$. The *quality* risk is managed by a
calibrated confidence gate (a small model that mis-gates escalates when it
shouldn't or returns garbage when it should escalate) — the gate is itself an
eval artifact ([Evaluation-Engineering/](../Evaluation-Engineering/README.md)).

## Router scoring beyond price

In production the router scores more than cost — it combines
**quality, latency, budget, privacy, and SLO** (see the Utility model in
[22-budget-aware-routing](22-budget-aware-routing.md)). The budget-aware router
is this page with a *remaining-budget* term added, and data-policy routing adds
a *cannot-use-cloud* term ([24-data-governance](24-data-governance.md)). So the
economic cascade and the policy router are the same machine with more terms.

## Failure & operating modes

- **Miscoverage**: small model confidently wrong → silent quality loss (needs
  evals + guardrails).
- **Escalation storms**: gate too loose → everything escalates, saving vanishes.
- **Cache interplay**: a cascade can *break* prefix-cache locality by changing
  model between calls ([08-kv-cache-economics](08-kv-cache-economics.md)).
- **Budget gating**: router must respect remaining tenant budget
  ([22](22-budget-aware-routing.md)) and tenant model entitlements
  ([26-model-access-control](26-model-access-control.md)).

## Related

[10-model-economics](10-model-economics.md) · [22-budget-aware-routing](22-budget-aware-routing.md) ·
[43-goodput-economics](43-goodput-economics.md) ·
[Inference/Production-Serving/05-routing-policies-from-classic-to-llm-aware](../Inference/Production-Serving/05-routing-policies-from-classic-to-llm-aware.md) ·
[15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)

## Key takeaways

1. Cascade = cheap-first, escalate-on-low-confidence; expected cost < always-large whenever P(small ok)>0.
2. E[Cascade] = P(small)·C_small + P(esc)·(C_small+C_large); worked example ~70% saving.
3. Routing optimizes cost *without* sacrificing quality by keeping the premium model for hard cases.
4. Production routers add latency, budget, privacy, and SLO terms on top of price.
