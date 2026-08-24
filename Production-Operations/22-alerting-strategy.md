# 22 — Alerting Strategy

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

Alerting is where observability becomes *action*. The goal is to page on
**symptoms that matter to users**, not on every raw gauge — otherwise you get
**alert fatigue**, and real incidents drown in noise. Prefer outcome-based
alerts with a clear diagnosis.

## Symptoms vs causes

The classic failing alert is a **cause gauge fired in isolation**:

> **Bad alert:** `GPU utilization > 90%`

A GPU at 95% during a healthy batch peak is *not* an incident — it may be normal.
It only matters when it produces a user-visible symptom.

> **Better alert:**
> `P95 TTFT > target`
> **AND** `queue depth increasing`

Now you're paging on "users are waiting too long AND the queue is building" —
a real, actionable symptom of overload ([08](08-queueing-theory-for-llm-sre.md)).
The cause (GPU%) is a *diagnostic context* you add after the fact, not the alert
itself.

**Principle** ([I]): alert on *outcome signals* (SLO violation: TTFT/TPOT/
goodput/error-rate) and use cause gauges (GPU, KV) to enrich and to predict —
never page on a cause gauge alone without a user-visible consequence.

## Severity tiers

| Severity | What it means | Action |
|---|---|---|
| **Warning** | within budget, but trending wrong | notify, dashboard; no escalation |
| **Critical** | approaching / hitting SLO budget | alert on-call; likely intervention |
| **Page** | active user impact / SLO breach | page a human; incident response ([30](30-llm-incident-response.md)) |

## Avoiding alert fatigue

1. **Alert on SLO burn, not raw gauges** — an alert only fires when users actually
   experience the failure.
2. **Require duration + multiple signals** — "P95 TTFT high AND queue rising AND
   lasting 5 min" filters transient blips.
3. **Rate-limit and dedupe** — group noisy repeated alerts.
4. **Kill dead alerts** — an alert nobody acts on should be fixed or removed,
   not ignored.
5. **Review alert effectiveness** — audit which alerts produced real incidents;
   prune the rest.

## Burn-rate alerts (`[F]`-concept, Google SRE / burn-rate)

A **burn-rate alert** fires when the error budget is being consumed *too fast*
for the window. If the SLO error budget is 0.1%/month and you're burning budget
at a rate that would exhaust it in an unacceptable time (e.g. multi-day-rate for
a page), you page. This gives:

- one consistent SLO-based model across latency/error/quality budgets,
- faster paging for severe burn (short window, high threshold) and slower for
  mild burn (long window),
- clear rollback/change gates tied to budget ([06](06-error-budgets-for-ai-systems.md)).

## Pattern examples

| Alert | Signals |
|---|---|
| Latency SLO burn | TTFT/TPOT goodput burn rate over window |
| Overload | queue depth trend + admission/reject ↑ |
| KV exhaustion risk | KV util ≥ x% with rising evictions ([12](12-kv-cache-reliability.md)) |
| GPU degradation | ECC rate trend / Xid count / sustained throttle ([10](10-gpu-reliability.md)) |
| Quality regression | golden-set pass rate drop ([24](24-quality-observability.md), [28](28-llm-regression-testing.md)) |
| Retry storm | retry amplification ratio ↑ ([14](14-retries-timeouts-circuit-breakers.md)) |

## Related

`02-sli-slo-sla-for-llms.md` · `06-error-budgets-for-ai-systems.md` ·
`21-production-dashboard.md` · `30-llm-incident-response.md` ·
`Labs/07-build-prometheus-dashboard.md`

## Key takeaways

1. Page on symptoms (SLO violations), not isolated cause gauges.
2. "GPU > 90%" is a bad alert; "P95 TTFT > target AND queue rising" is a good one.
3. Warning / critical / page tiers, and kill alert fatigue at the root.
4. Burn-rate alerts tie paging to error-budget consumption.
