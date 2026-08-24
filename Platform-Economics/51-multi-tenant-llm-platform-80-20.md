# 51 — The 80/20 Guide: Multi-Tenant LLM Platform Economics & Governance

`LAST_UPDATED: 2026-08-24` · Status: summary page

> ## "The 20% of Platform Economics & Governance That Explains 80% of a Shared LLM Service"

Fifteen levers do most of the work. Master these; the rest of the section fills
in the mechanics.

1. **GPUs are fixed capacity; demand is variable.** You pay for capacity whether
   or not it works — so variable demand against fixed supply is the core
   economic tension ([04-capex-vs-opex-ai-platform](04-capex-vs-opex-ai-platform.md),
   [05-gpu-utilization-economics](05-gpu-utilization-economics.md)).

2. **Cost per token depends heavily on utilization.** 20%→70% utilization is
   ~3.5× per-token cost. Utilization, not sticker price, is the real lever
   ([05-gpu-utilization-economics](05-gpu-utilization-economics.md)).

3. **Output tokens often cost more than input tokens.** Decode is
   bandwidth-bound; price in/out separately ([06-token-economics](06-token-economics.md),
   [07-prefill-decode-economics](07-prefill-decode-economics.md)).

4. **Strict SLOs require spare capacity.** Headroom = idle = cost. Reliability
   is priced, not free ([17-slo-economics](17-slo-economics.md)).

5. **Tenants must be metered before they can be governed.** No metering, no
   allocation, no fairness ([13-tenant-metering](13-tenant-metering.md)).

6. **Showback should usually precede chargeback.** Build trust in the cost model
   before moving money ([14-showback-chargeback](14-showback-chargeback.md)).

7. **Fairness requires more than FIFO.** Enforce shares, priority, and quotas
   ([18-tenant-fairness](18-tenant-fairness.md),
   [20-quota-engineering](20-quota-engineering.md)).

8. **KV cache is both a performance and an economic resource.** It consumes
   memory and saves prefill ([08-kv-cache-economics](08-kv-cache-economics.md)).

9. **Model routing can optimize cost without always sacrificing quality.**
   Cascade = cheap-first, escalate smartly ([11-economic-model-routing](11-economic-model-routing.md)).

10. **Agentic workflows can multiply model usage dramatically.** 1 task → N
    calls; budget at the run level ([35-agent-economics](35-agent-economics.md)).

11. **Cloud bursting trades cost for elasticity.** Burst only when value >
    premium + risk ([28-cloud-bursting-economics](28-cloud-bursting-economics.md)).

12. **Governance should be enforced as policy, not documentation alone.**
    Policy-as-code, not prose ([27-policy-as-code](27-policy-as-code.md)).

13. **Goodput matters more than raw throughput.** SLO-violating cheap tokens are
    worthless ([43-goodput-economics](43-goodput-economics.md)).

14. **Data sensitivity should influence model/provider routing.** Classify then
    route ([24-data-governance](24-data-governance.md)).

15. **Cost per successful task is more meaningful than cost per token.** Retries
    and failures dominate ([43-goodput-economics](43-goodput-economics.md),
    [10-model-economics](10-model-economics.md)).

## The two-page version

- **Economics:** GPU capacity is fixed → utilization turns it into unit cost →
  SLOs force headroom → price by what you spend, hybrid (reserved + tokens +
  tier) → meter everything → allocate (showback → chargeback) → watch goodput.
- **Governance:** identity tenant → classify data → authorize models → cap with
  quotas+budgets → enforce with policy-as-code → admit/route within budget/SLO →
  isolate per tenant → audit → recognize exceptions are temporary.

## Related

[52-multi-tenant-platform-zero-to-hero](52-multi-tenant-platform-zero-to-hero.md) ·
[57-economics-governance-big-picture](57-economics-governance-big-picture.md) ·
[54-economics-formulas](54-economics-formulas.md) ·
[55-governance-antipatterns](55-governance-antipatterns.md)

## Key takeaways

1. Utilization, SLO headroom, token shape, and metering drive most of the cost story.
2. Fairness, caching, routing, budgets, policy, and goodput drive most of the
   governance/quality story.
3. The 15 levers above are the 20% that explains 80%.
