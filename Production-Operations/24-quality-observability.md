# 24 — Quality Observability

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

**System health ≠ answer quality.** You can watch every GPU, every queue, every
KV block, and every HTTP status — and the model can still be broken. "The GPU is
healthy" says nothing about whether the *answer* is useful. LLM operations must
measure quality as a first-class signal for exactly this reason.

## Why infrastructure health isn't enough

A platform can be **infra-healthy and quality-broken**:

- model hallucinates (GPU healthy, answer wrong),
- refusal regression (service up, refuses valid requests),
- format/schema break (structured output invalid),
- grounding/stale RAG (answers confidently from old context),
- tool-call failures at scale,
- judge/eval score drop in production traffic.

`SYSTEM HEALTH ≠ ANSWER QUALITY` — the second table on this page monitors what
the first cannot see.

## The quality-SLIs to observe

| Signal | What it measures | How |
|---|---|---|
| **Groundedness** | answer supported by retrieved context | RAG-eval checks, citation adherence ([35](35-rag-sre.md)) |
| **Correctness** | answer is right | eval-set correctness, human audits |
| **Toxicity / safety** | harmful output | safety classifiers, red-team eval ([Safety], [Safety-Red-Teaming]) |
| **Tool success** | tools actually work | tool-call success rate ([34](34-agent-sre.md)) |
| **Retrieval success** | RAG finds the right context | recall/robustness, miss rate |
| **Structured-output validity** | JSON/schema conformity | parse/schema pass rate |
| **Judge scores** | LLM-as-judge quality ratings | judge harness ([LLM-as-a-Judge]) |
| **Human feedback** | thumbs/the relationship signal | product feedback loop |

## Making it operational (`[I]`)

1. **Continuous quality telemetry** — sample production requests, score them
   (judge/classifier), track distributions as SLIs.
2. **Golden-set regression** — fixed eval set run per release ([28](28-llm-regression-testing.md)).
3. **Alert on quality SLIs** — golden pass-rate drop and judge-score shift fire
   burn-rate alerts ([22](22-alerting-strategy.md)) and spend the *quality error
   budget* ([06](06-error-budgets-for-ai-systems.md)).
4. **Tie quality to provenance** — quality degraded? attribute via model_id,
   prompt version, RAG index version, engine ([23](23-llm-tracing.md),
   [25](25-model-release-engineering.md)).
5. **Scope cost** — quality eval consumes tokens; budget it like a probe
   ([19](19-llm-health-checks.md), [33](33-cost-as-an-sre-signal.md)).

## Related

`03-goodput-vs-throughput.md` · `06-error-budgets-for-ai-systems.md` ·
`22-alerting-strategy.md` · `28-llm-regression-testing.md` ·
`35-rag-sre.md` · `Evaluation-Engineering/LLM-as-a-Judge.md`

## Key takeaways

1. System health ≠ answer quality; the GPU can be fine while the answers are broken.
2. Monitor groundedness, correctness, toxicity, tool/retrieval success, schema
   validity, judge scores, human feedback.
3. Make quality an SLI with its own error budget and alerts.
4. Attribute quality changes via provenance (model/prompt/index/engine versions).
