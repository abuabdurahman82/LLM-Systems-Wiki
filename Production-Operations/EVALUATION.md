# Production-Operations — Qwen Reviewer Evaluation

`LAST_UPDATED: 2026-08-23` · Status: evaluation record

Independent technical review of the **Production-Operations/** section, run per
the DeepSeek→Qwen review workflow:
- **Draft / adjudicator:** DeepSeek V4 Flash (main model, local vLLM, dual DGX Spark GB10).
- **Reviewer:** Qwen3.8 27B (`qwen38-nvfp4`) in the skeptical-production-SRE role
  (local vLLM, RTX 5090 workstation), via `delegate_task` (eval id `deleg_ec188ca8`).

**Method:** reviewer deep-read highest-risk pages + breadth-by-grep across the
section, returned 15 findings (1 critical, 4 major, 7 minor, 3 nit). DeepSeek
adjudicated **each finding independently against evidence** — the evaluator is
**not** presumed correct.

## Adjudication

### Finding 1 — [critical] "Fabricated Xid symbolic names with false [F] tag" (page 10)
- **REVIEW CLAIM:** Xid 48/94/95/140 symbolic names (`ROBUST_CHANNEL_*`,
  `UNRECOVERABLE_ECC_ERROR_ESCAPE`) are invented and wrongly tagged `[F]`; real
  catalog describes Xid 48 as "ECC page retirement or double-bit ECC error".
- **EVIDENCE (DeepSeek):** these exact code↔symbol pairs were taken **verbatim
  from the fetched `docs.nvidia.com/deploy/xid-errors/latest` Xid catalog
  (2026 revision)** during the research pass: the source explicitly lists
  `XID 48 ROBUST_CHANNEL_GPU_ECC_DBE`, `XID 94/95 ROBUST_CHANNEL_CONTAINED_ERROR`,
  `XID 140 UNRECOVERABLE_ECC_ERROR_ESCAPE`, `XID 92 EXCESSIVE_SBE_INTERRUPTS`,
  `XID 168 REDUCED_GPU_MEMORY_CAPACITY`. The reviewer based its claim on the
  **older** catalog that described Xid 48 differently (no symbolic name).
- **DECISION: REJECTED** as an accusation of fabrication/verification-fraud — the
  `[F]` source is real and current. **PARTIALLY ACCEPTED** on the legitimate core:
  NVIDIA changes Xid symbol names/numbers across driver generations, so the
  "symbol→meaning" mapping should not be treated as universal. **Action:** added a
  catalog-version caveat to page 10 making the 2026-catalog provenance and the
  generation-drift caveat explicit, and restated Xid as a diagnostic starting point.

### Finding 2 — [major] M/M/1 presented as governing LLM serving without caveat (page 08)
- **CLAIM:** M/M/1 (single-server, Poisson, exponential, infinite queue, FCFS) is
  not how continuous-batched, multi-resource LLM serving behaves.
- **EVIDENCE:** correct — LLM serving is compute+HBM+KV multi-resource with
  preemption; M/M/1 is a directional analogy, not the operating model.
- **DECISION: ACCEPTED.** Added a model caveat to page 08 and cross-linked the
  LLM-specific treatment in `Inference/Production-Serving/04`.

### Finding 3 — [major] Missing NCCL process-group-wide stall; hot-rebuild unrealistic (page 11)
- **CLAIM:** NCCL collectives are process-group-scoped; a rank failure blocks all
  group collectives; most frameworks don't support clean hot-rebuild of a TP group.
- **EVIDENCE:** correct and operationally important.
- **DECISION: ACCEPTED.** Rewrote mitigation #5: NCCL group-scoped stalling noted,
  recovery = fail the group as a unit / restart the whole TP pod (not hot-rebuild).

### Finding 4 — [major] Lab 2 Python has a syntax/plotting bug (page Labs/02)
- **CLAIM:** `c,[ag,tt,p95]=zip(*rows)` raises ValueError (4-tuples into 2 targets);
  `plt.plot(c,[tt,p95])` is wrong.
- **EVIDENCE:** confirmed by inspection — the code as written was not runnable.
- **DECISION: ACCEPTED.** Fixed to `c,ag,tt,p95 = zip(*rows)` and two explicit
  `plt.plot` lines.

### Finding 5 — [major] Retry guidance missing capacity-vs-transient distinction (page 14)
- **CLAIM:** retrying GPU OOM / KV exhaustion is pointless (capacity, not transient);
  correct response is admission control/backpressure, not retry.
- **EVIDENCE:** correct and the most common LLM retry-into-failure pattern.
- **DECISION: ACCEPTED.** Added explicit transient-vs-capacity guidance + admission
  control pointer to page 14's operational practice.

### Finding 6 — [minor] Queue depth conflated with Little's-Law L (page 08)
- **CLAIM:** queue depth is L_q (waiting), not L (in-system).
- **EVIDENCE:** correct SRE nuance (`L_q = ρ²/(1−ρ)` vs `L = ρ/(1−ρ)` in M/M/1).
- **DECISION: ACCEPTED.** Segregated the waiting part L_q in the Little's Law table.

### Finding 7 — [minor] SLO phrasing ambiguous: percentile vs fraction (page 02)
- **CLAIM:** "P95 TTFT < 1.5 s over a window" is ambiguous vs the standard
  fraction-of-requests SRE formulation.
- **EVIDENCE:** correct — the two differ under skew; standard SRE uses the fraction.
- **DECISION: ACCEPTED.** Reformulated the SLO example as the fraction form and
  added an explanatory note.

### Finding 8 — [minor] GPU Operator: container-runtime hook mischaracterised (page 18)
- **CLAIM:** nvidia-container-toolkit (runtime hook) is host-level, not a k8s
  DaemonSet/StatefulSet.
- **EVIDENCE:** correct.
- **DECISION: ACCEPTED.** Rewrote the GPU Operator paragraph to distinguish
  k8s workloads (driver/device-plugin/dcgm-exporter) from host-level
  container-toolkit install.

### Finding 9 — [nit] Broken self-referencing link `[13→13-multitenancy]` (page 13)
- **CLAIM:** leftover link to a non-existent page.
- **EVIDENCE:** confirmed.
- **DECISION: ACCEPTED.** Replaced with a cross-link to the real multi-tenancy page.

### Finding 10 — [nit] vLLM `[F]` overstates per-request metrics (page 20)
- **CLAIM:** default vLLM Prometheus endpoint is server-level; per-request may
  need flags.
- **EVIDENCE:** fair; hedge warranted.
- **DECISION: ACCEPTED.** Scoped the `[F]` tag to the default server-level endpoint
  and flagged per-request as version-dependent.

### Finding 11 — [nit] Garbled "lossy/loss" text (page 09)
- **CLAIM:** unparseable phrase.
- **EVIDENCE:** confirmed.
- **DECISION: ACCEPTED.** Reworded.

### Finding 12 — [minor] Quality error budget lacks measurement cadence (page 06)
- **CLAIM:** no mechanism described for measuring quality continuously enough to gate.
- **EVIDENCE:** fair; the gap between golden-set eval and production sampling.
- **DECISION: ACCEPTED.** Added a measurement-cadence note (golden per-release/
  nightly + sampled production traffic on a tight cadence; interpolation between
  runs).

### Finding 13 — [nit] Fallback example names models/providers without a tag (page 15)
- **CLAIM:** `local Qwen → GLM via OpenRouter` looks verified without a tag.
- **EVIDENCE:** fair.
- **DECISION: ACCEPTED.** Added an `[A]` illustrative-example note.

### Finding 14 — [nit] Little's Law table attributes an M/M/1 corollary to Little's Law (page 08)
- **CLAIM:** "high ρ ⇒ high L" is an M/M/1 corollary, not a Little's Law consequence.
- **EVIDENCE:** technically correct attribution nit.
- **DECISION: ACCEPTED.** Retagged the row as an M/M/1-style corollary.

### Finding 15 — [minor] Streaming-retry idempotency subtlety missing (page 14)
- **CLAIM:** a retry of a streamed request is a new non-deterministic response,
  not a continuation.
- **EVIDENCE:** correct and distinct from classic idempotency.
- **DECISION: ACCEPTED.** Added the streaming caveat to the idempotency control row.

## Outcome summary

| Decision | Count |
|---|---|
| ACCEPTED | 11 (numeric review findings 2,3,4,5,6,7,8,9,10,11,12,13,14,15 → 14 accepted in full or as scoped) |
| PARTIALLY ACCEPTED | 1 (Finding 1 — rejected as fabrication, accepted as a worthwhile caveat + hardened) |
| REJECTED | 0 outright (Finding 1's "fabrication with false [F] tag" framing REJECTED while the caveat was adopted) |

All accepted fixes were applied to the section files (2026-08-23). **No review
finding was accepted merely because the evaluator is the reviewer** — each was
checked against the page text and, for the GPU/Xid claim, against the fetched
primary source.
