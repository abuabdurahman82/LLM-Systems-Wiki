# 02 — SLI, SLO, SLA for LLMs

`LAST_UPDATED: 2026-08-23` · Status: foundational page

## 30-Second Explanation

- **SLI** = what you actually *measure* (a number).
- **SLO** = the *target* you commit to internally ("we aim to keep P95 TTFT under 1.5 s").
- **SLA** = a *contractual* commitment a customer can hold you to (financial or otherwise).

The classic mistake for LLM systems is carrying over a *traditional* availability
SLO into a domain where availability is the least informative number you have.

## SLI vs SLO vs SLA

| Term | Question | Example |
|---|---|---|
| **SLI** | What do we measure? | P95 time-to-first-token; request success rate; output-token rate |
| **SLO** | What do we target? | P95 TTFT < 1.5 s over a 30-day window |
| **SLA** | What do we contractually promise? | "If monthly uptime < 99.9%, you get a service credit" |

An **error budget** (the gap between 100% and the SLO) is the amount of failure
you have *planned for*; it is what makes rolling releases and experiments safe.
See [06-error-budgets-for-ai-systems](06-error-budgets-for-ai-systems.md).

## Traditional SLOs an LLM platform inherits

- Availability ≥ 99.9%
- API error rate < 0.1%
- P95 API latency < some bound
- Throughput above some minimum

These matter, but they answer "is the box up and fast" — not "was the answer
any good." For LLM systems we add a second family.

## LLM-specific SLIs and example SLOs

> The numbers below are **illustrative targets** (`[A]` assumptions), not
> universal truths. Choose them from your own measured baselines and cost
> model. None are fabricated as "the right" value.

| SLI | Example SLO (illustrative `[A]`) | Why it matters |
|---|---|---|
| TTFT | P95 < 1.5 s | First impression; feels like empty waiting |
| TPOT / ITL | P95 < 50 ms/token | Streaming smoothness; total time to finish |
| E2E time-to-completion | P95 < bound | Whole-request wall time |
| Request success | > 99.95% | Percentage of requests that complete without error/timeout |
| Tool-call success | > 99% | Agent/tool path works |
| RAG groundedness | > threshold on eval set | Answers trace to retrieved context |
| Quality score | > threshold (judge/human) | Output quality doesn't regress |
| Goodput | > target | Fraction of requests meeting ALL SLOs (see [03](03-goodput-vs-throughput.md)) |
| GPU OOM rate | < threshold per week | Capacity/KV health |
| Cost per successful request | < budget | Economic reliability (see [33](33-cost-as-an-sre-signal.md)) |

## Why 99.9% availability ≠ 99.9% useful answers

A traditional SLO counts a request as *good* if the service answered without an
HTTP error. For an LLM system, all of these can be "available" yet *bad*:

- the model **hallucinates** (no HTTP error, wrong answer);
- a **refusal regression** makes the model refuse valid requests;
- **incorrect reasoning** yields a confident wrong answer;
- streaming starts fast but the response is **truncated** or cut at a tool boundary;
- the answer is **grounded in stale or poisoned RAG context**;
- the answer is technically fine but **wrong model** was routed (a tiny model
  silently answered a hard question);
- the request returned but **exceeded its cost/token budget** (runaway agent).

In each case the service was "up" and the request "succeeded" under a
traditional SLI, yet the user got something useless or harmful. Hence:

> **"99.9% availability" does NOT mean "99.9% useful answers."**

Measuring availability alone hides exactly the failures that matter most for
LLMs. This is the motivation for **goodput** ([03](03-goodput-vs-throughput.md))
and **quality observability** ([24](24-quality-observability.md)).

## Building an SLO in practice

1. **Pick SLIs from user-visible outcomes** (TTFT, TPOT, completion, quality) —
   not just internal gauges.
2. **Set the target from your measured baseline**, not from a guess. If you
   don't know your P95 TTFT, you cannot promise one.
3. **Window the SLO** (e.g. over 30 days) and compute the error budget over that
   window.
4. **Make the SLO actionable**: an SLO that does not pause risky releases when
   its budget is burnt is a dashboard ornament.

## Related

`03-goodput-vs-throughput.md` · `06-error-budgets-for-ai-systems.md` ·
`Inference/Production-Serving/12-observability-and-slos.md` · SRE definition of
SLI/SLO/SLA (Google SRE Book — see `08` references)

## Key takeaways

1. SLI = measure, SLO = target, SLA = contract.
2. LLM reliability needs a second family of SLOs beyond uptime: TTFT, TPOT,
   goodput, groundedness, quality.
3. Availability is the least informative number: every "bad but successful"
   outcome hides behind it.
4. Set SLOs from measured baselines and make them gate risky changes.
