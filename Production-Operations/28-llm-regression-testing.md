# 28 — LLM Regression Testing

`LAST_UPDATED: 2026-08-23` · Status: operational page

## 30-Second Explanation

**Regression testing** for LLMs catches whether a change (model, quant, prompt,
engine, kernel, RAG index, agent harness) *broke something that used to work* —
in quality, latency, throughput, memory, tools, RAG, or safety. It is the gate
that makes releases safe (see [25](25-model-release-engineering.md)) and the
guard on the *quality error budget* ([06](06-error-budgets-for-ai-systems.md)).

## Test categories

| Category | What it guards | How |
|---|---|---|
| **Quality regression** | output correctness/quality | golden set + judge/human comparison |
| **Latency regression** | speed didn't regress | TTFT/TPOT buckets vs baseline |
| **Throughput regression** | capacity didn't drop | tok/s, goodput under load |
| **Memory regression** | footprint stable | peak GPU/host mem, KV use |
| **Tool regression** | tool calling still works | tool-selection/call success |
| **RAG regression** | retrieval/grounding intact | retrieval recall, groundedness |
| **Safety regression** | safety didn't regress | safety/toxicity suites ([Safety-Red-Teaming]) |

## The golden-dataset flow

```
Golden Dataset
    ↓
candidate release
    ↓
comparison (vs baseline/reference)
    ↓
PASS / FAIL
```

- **Golden dataset** = fixed, curated eval set representative of production
  (prompts of varying difficulty/length incl. tails). See
  `Evaluation-Engineering/` for design.
- **Comparison** = candidate outputs vs baseline (and/or a reference model)
  scored by judge/human/metrics.
- **Gate** = PASS only if inside the quality error budget and no latency/
  throughput/memory/safety regression ([06](06-error-budgets-for-ai-systems.md)).

## Operational practice (`[I]`)

1. **Keep the golden set versioned and free of contamination**
   (`Evaluation-Engineering/Benchmark-Contamination.md`).
2. **Run per candidate release** and on schedule against production
   ([24](24-quality-observability.md)).
3. **Include tails** — long prompts, adversarial, out-of-distribution — not just
   the happy path.
4. **Gate CI/CD** — a failing golden set blocks promotion to canary/production.
5. **Track regression history** — trend over releases to catch slow drift, not
   just hard failures.

## Cross-link: Evaluation Engineering

Deep treatment of eval design lives in **`Evaluation-Engineering/`** (fundamentals,
benchmark design, judging, statistics). This page covers the *operational* role:
regression testing as a production gate, wired into releases and the error budget.

## Related

`06-error-budgets-for-ai-systems.md` · `24-quality-observability.md` ·
`25-model-release-engineering.md` · `27-canary-deployment.md` ·
`Evaluation-Engineering/README.md`

## Key takeaways

1. Regression testing catches broken-that-used-to-work for model/quant/prompt/
   engine/kernel/RAG/agent changes.
2. Categories: quality, latency, throughput, memory, tool, RAG, safety.
3. Flow: golden dataset → candidate → comparison → PASS/FAIL.
4. Gate CI/CD on it and trend regressions over releases.
