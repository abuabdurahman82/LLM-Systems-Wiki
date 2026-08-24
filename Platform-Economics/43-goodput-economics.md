# 43 — Goodput Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

**Throughput** counts *all* work processed; **goodput** counts only work that
actually satisfies the SLO — the *useful, accepted, on-time, correct-enough*
output. The economic punchline: **cheap tokens that violate the SLO are worth
~nothing**, because they consumed GPU time, cost money, and produced output the
user couldn't use. The platform's real unit cost is therefore **Cost per Good
Request**, not cost per token or per request — which is exactly why this page
sits at the heart of the section's thesis.

## Throughput vs goodput

| Term | Definition |
|---|---|
| **Throughput** | total work processed / time (e.g. tokens or requests per second) |
| **Goodput** | useful requests meeting the SLO / time |

A saturated pool can have **high throughput and collapsing goodput**: lots of
tokens per second, but they arrive late (SLO-violating) or wrong
([05-gpu-utilization-economics](05-gpu-utilization-economics.md),
[12-quality-cost-latency-frontier](12-quality-cost-latency-frontier.md)). What
the tenant experiences — and what creates value — is goodput.

## Cost per Good Request

$$\text{Cost per Good Request} = \frac{\text{Platform cost of the request}} {\text{request meets SLO and quality bar}}$$

Or, over a window:

$$
\text{Cost per Good Request} = \frac{\text{total platform cost}}{\text{good requests delivered}}
$$

where *good* = within latency SLO + correct-enough + accepted (not
rejected/errored). This mirrors the **fully loaded cost** idea from
[03](03-llm-inference-unit-economics.md) with an SLO/quality filter on the
denominator.

### Worked implication
Two pools running the same cost:
- Pool A: 10k req/s, 95% good → goodput 9.5k/s.
- Pool B: 10k req/s, 40% good (overloaded, [05](05-gpu-utilization-economics.md)) → goodput 4k/s.

At equal spend, **Pool A's cost per good request is ~2.4× lower**. Output that
misses its SLO isn't "cheap" — it's wasted capacity.

## Why cheap SLO-violating tokens are worthless

A token that arrives after the user gave up, or that produces a wrong answer
that must be retried, doesn't just fail to create value — it often *creates
negative* value (frustration, rework, support cost, [45-cost-of-failure](45-cost-of-failure.md)).
So **optimizing for low $/token without an SLO/quality filter optimizes the
wrong thing**. This is the core argument for making **goodput** (and its cost
form) the platform's headline economic metric — the thesis tested in
[56-open-research-questions](56-open-research-questions.md).

## Closes the loop with the chain

Goodput is where the whole value chain ([01](01-multi-tenant-llm-platform-overview.md))
lands: GPU → tokens → tenant consumption → **quality + latency** → cost. The
"quality + latency" milestone defines goodput, and cost-per-good-request prices
it. Everything upstream exists to maximize **good requests per dollar**.

## Related

[05-gpu-utilization-economics](05-gpu-utilization-economics.md) ·
[17-slo-economics](17-slo-economics.md) · [03-llm-inference-unit-economics](03-llm-inference-unit-economics.md) ·
[Production-Operations/03-goodput-vs-throughput](../Production-Operations/03-goodput-vs-throughput.md) ·
[56-open-research-questions](56-open-research-questions.md)

## Key takeaways

1. Throughput = all work; goodput = work meeting the SLO (useful output).
2. Cost per Good Request = platform cost ÷ good requests delivered.
3. Cheap SLO-violating tokens are ~worthless — wasted capacity, not savings.
4. Maximize good requests per dollar; make goodput the headline metric.
