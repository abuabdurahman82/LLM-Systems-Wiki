# KV-Cache Eviction & Pruning — Research Tracker
`LAST_UPDATED: 2026-08-16` · Status: research tracker (preprints move fast; re-verify before citing)

For each method: algorithm / retention rule / eviction rule / complexity / quality impact /
memory savings / best workload / failure modes.

## Sliding Window Attention (SWA)
- **Mechanism:** attend only to last W tokens (+ global). **Retention:** most recent W.
  **Eviction:** oldest beyond W. **Complexity:** O(S·W) vs O(S²). **Quality:** strong for
  local syntax; loses long-range facts. **Savings:** KV ∝ W, constant. **Best:** high-
  throughput short-range workloads. **Failure:** long-doc QA, coreference.
  [F: Belt et al. 2013 "Searching a Million-Point Needle" arXiv:1302.10143; Longformer arXiv:2004.05150]

## Attention Sinks / StreamingLLM
- **Mechanism:** the first tokens accumulate huge attention mass ("attention sinks");
  dropping them collapses generation. **Retention:** first k sink tokens + rolling window
  of W. **Eviction:** middle tokens. **Complexity:** O(S·(k+W)). **Quality:** near
  full-attention at 4k window on long streams (vendor-reported ~100× speedup to 4M tokens
  [F: Xiao et al. 2023 arXiv:2309.17453, NeurIPS'23]). **Savings:** KV constant.
  **Best:** infinite streaming. **Failure:** tasks needing arbitrary historical tokens.

## H2O — Heavy-Hitter Oracle
- **Mechanism:** attention mass concentrates on a small "heavy-hitter" set; keep those
  + recent. **Retention:** top-k attention scores + sliding window. **Eviction:** rest,
  LRU-ish. **Complexity:** O(S) scoring per layer per head. **Quality:** matches
  full-attention on many long-context tasks at ~2× less KV (paper-reported [F:
  Zhang et al. 2023 ICLR'24 arXiv:2306.14048]). **Best:** long-context chat/QA.
  **Failure:** importance shifts over time; static heavy-hitters go stale.

## SnapKV
- **Mechanism:** use the last C prompt tokens' attention distributions to score earlier
  tokens; keep top-k per head. **Retention:** prompt-time selection, then frozen during
  decode. **Eviction:** one-shot at prefill boundary. **Complexity:** O(C·(S−C)).
  **Quality:** competitive at 20–30% budget on PG-19 etc. (paper-reported [F:
  Li et al. 2024 arXiv:2404.14469]). **Best:** long-context QA with a fixed prompt.
  **Failure:** long generation after pruning (importance drift).

## PyramidKV
- **Mechanism:** layer-wise budgets; early layers keep more tokens than late layers
  (pyramid). **Retention/eviction:** per-layer top-k by attention. **Complexity:**
  O(L·S). **Quality:** better than uniform budgets at same total KV (paper-reported [F:
  Cai et al. 2024 arXiv:2406.12243]). **Best:** long-context QA. **Failure:** layer
  importance varies by task.

## Learned / Importance-Prediction Eviction
- **Mechanism:** a small learned scorer (per-head MLP or shared) predicts token
  importance → budget allocation. Includes "KVQuant" (quantize+select, [F: arXiv:2402.02750])
  and 2026-era work: **DistillCache** (KL-guided adaptive eviction, preprint 2026-08),
  **RippleKV** (cross-layer allocation via perturbation propagation, preprint 2026-08),
  **CommitKV** (lifecycle-aware compression for multi-turn agents, preprint 2026-08),
  **SPECTRA** (spectral transform coding past the "2-bit cliff", preprint 2026-08),
  **KVDiagnosis** (diagnostic benchmark for KV compression in long-ctx LMs, preprint
  2026-08). All [preprint, UNVERIFIED quality claims until reproduced].
- **Status [I]:** learned eviction is the open question "can it beat fixed heuristics?"
  (see open questions list in `README.md`). Evidence so far: learned methods help at
  aggressive budgets; heuristics (H2O/SnapKV) remain simple and strong at 25–50% budgets.

## Layer-Dependent / Head-Dependent
- Early layers encode local syntax; later layers encode facts/long-range
  (layer-wise analysis in the Transformer Circuits literature [I]).
- Per-head budgets: some heads are "sinks" (need few), some "induction heads" (need many)
  [I: consistent with attention-pattern literature].

## Best-Workload Summary
| Budget | Use |
|---|---|
| 100% (no eviction) | short ctx, correctness-critical |
| 50–80% | H2O/SnapKV/SWA hybrid; RAG long-doc |
| 25–50% | learned or layer-wise (PyramidKV-style) |
| <25% | research territory; expect quality cliffs [I] |

## Failure-Mode Taxonomy
1. **Stale importance** — selected tokens stop mattering mid-generation.
2. **Sink collapse** — dropping attention sinks degrades output coherency.
3. **Cross-layer mismatch** — pruning in one layer that another layer needs.
4. **Eval leakage** — benchmarks short of the original context length don't exercise eviction.

## Related
`KV-Cache/README.md` · `Attention/README.md` · `Labs/Lab-11` (experiment with eviction).

## Key Takeaways
Eviction is a *quality-vs-memory* trade, not free. The open frontier (2026): lifecycle-
aware, agent-aware, learned budgets.
