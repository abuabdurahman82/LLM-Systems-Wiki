# Context Budget (token & memory arithmetic)
`LAST_UPDATED: 2026-08-19` · Status: core page

## 30-Second Explanation
Every context decision is an allocation against **two** hard budgets:
1. **The token budget** — nominal context length N (e.g. 128k). Every byte of
   system prompt, tool schema, history, retrieval, and tool output is a token.
2. **The KV-memory budget** — each cached token occupies HBM
   (`../KV-Cache/README.md` memory equation). At long context, the KV cache,
   not the weights, is the capacity constraint.

Getting these two budgets right is what separates a context policy that *fits*
from one that OOMs or silently degrades. Everything else in this section
(`Lost-in-the-Middle-and-Long-Context-Reality.md`, `Context-Compaction.md`,
`Agent-Memory.md`) is a strategy for spending these budgets well.

## Budget 1 — the token line-item (hand-computable)
An agent step's context is a sum of line items. A representative 2026 coding-agent
step [E: arithmetic; sizes [A: typical, not measurements]]:

| Line item | Tokens | Notes |
|---|---|---|
| System prompt + agent instructions | 3–8k | stable → prefix-cacheable |
| Tool schemas (N tools × 200–500) | 10–25k at N=50 | the hidden cost; see `../Agents/Tool-Use.md` § Seam 1 |
| Task spec / goal | 0.5–2k | keep re-anchored |
| Retrieved files / context | 5–30k | agentic search decides |
| Tool outputs (this step) | 0.5–10k | the bloat source |
| Conversation / trajectory history | grows each step | the compaction target |
| Reasoning / scratchpad | 1–5k | CoT-style |
| **Total** | **~20–80k** | against a 128k–1M nominal window |

**Key insight:** the *stable* portion (system + tools) can be 30–40k; the *variable*
portion (history + outputs) is what grows. So the budget is really:
`variable_budget = N − stable_tokens`. For N=128k, stable=32k → **~96k variable
headroom**, which a 30-step trajectory with 3k/step of accumulated tool output
consumes in ~30 steps [E: 3k×30=90k] — i.e. the window fills mid-task, which is
exactly when `Context-Compaction.md`'s trigger fires.

**Prefix-cache economics:** because the stable prefix is identical across steps,
a serving stack with prefix caching (`../KV-Cache/README.md` § prefix caching;
vLLM APC arXiv:2309.06180 [F]; SGLang RadixAttention arXiv:2312.07104 [F]) pays
prefill cost *once* for the stable prefix and only re-reads the *new* tokens each
step. The measurable win [I: consistent across engine docs]: TTFT on step k
scales with `new_tokens` (the delta), not the full context. A 30-step agent run
whose stable prefix is 32k saves 31×32k ≈ **~1M prefill tokens** vs no caching
[E: 31×32,000 = 992,000] — [I: the single biggest agent-serving cost lever,
see `../Inference/Inference-Optimization.md`].

## Budget 2 — the KV-memory line-item (the equation that OOMs you)
From `../KV-Cache/README.md`:
```
KV bytes = 2 · L · B · h_kv · d_h · S · b
```
Worked example [E: arithmetic] for a 7B-class dense model (L=32, h_kv=8, d_h=128,
b=2 BF16) at batch B=1:
- S=8,192 → 2·32·8·128·8192·2 = **1.0 GiB** (matches the wiki's worked example).
- S=128,000 → **15.625 GiB** for a *single* request. [E: 1.0 GiB × (128000/8192) = 15.625]
- At B=8, S=32k → 2·32·8·128·32768·2·8 ≈ **32 GiB** of KV alone. [E]

**The two constraints that bound context:**
1. **Capacity** — HBM holds `KV_bytes ≤ (HBM − weights − activations)`. A 7B in BF16
   is ~14 GB of weights; on a 24 GB card, KV headroom is ~8 GB → single-request
   max S ≈ 8 GiB / (15.625 GiB/128k) ≈ **65k** [E: 8×128000/15.625 = 65,536;
   [A] 24GB card, 14GB weights]. So a "128k model" on a 24GB card *cannot serve*
   128k single-user.
2. **Bandwidth** — long-context prefill is compute-bound; decode at long S is
   *bandwidth-bound on the KV reads* (`../Inference/Roofline.md`). More context
   → more KV to read per decode token → slower ITL even when it *fits*.

**Why GQA/MLA exist (the memory lever):** reducing `h_kv` (GQA, arXiv:2305.13245
[F]) divides the KV budget by the GQA group factor (e.g. 8 KV heads vs 64 MHA
heads = 8× less KV [E: 64/8 = 8]); and a low-rank shared latent (MLA,
DeepSeek-V2 arXiv:2405.04434 [F]) compresses the whole KV into one shared
latent vector read by every head — the paper reports a **~93.3% KV-cache
reduction (~15×)** [F: abstract]. As a bare *dimension-count* illustration
(not a figure from that paper): a full 64-head/d_h=128 MHA stores
704,512 dims/token (64·128·2 per layer, summed over layers), whereas an MLA's
compact latent is an order of magnitude or more smaller — the Inference
section's precision-independent **85× KV-dim ratio** (`../Inference/
Inference-Optimization.md`) [E: dimension arithmetic only, model-agnostic].
The context window you can *serve* is set by `h_kv` (or the latent dim), not just
`N`.

## The budget policy (what a production context manager enforces)
1. **Reserve, don't fill.** Keep the working set at ≤ ~70–80% of N so compaction
   can run *before* hard truncation. (`Context-Compaction.md` § triggers.)
2. **Stable-first ordering.** Put the cacheable prefix at the front so the
   serving stack's prefix cache hits; never interleave variable content ahead of
   it. [I: matches engine docs]
3. **Cap tool outputs.** A 1MB result is a context bomb; budget it to ≤ ~2–5k
   tokens with a "full output available" pointer (`../Agents/Tool-Use.md` § Seam 4).
4. **Budget the trajectory.** The accumulated history is the unbounded term;
   summarize/evict on a schedule, not at the wall (`Agent-Memory.md`).
5. **Mind B×S.** Serving *many* long contexts multiplies KV by B; a "fits at
   B=1" config OOMs at B=8 (§ Budget 2). The serving engineer's context limit is
   a function of the *batch*, not just the window.

## Related
`../KV-Cache/README.md` (memory equation + eviction) ·
`Lost-in-the-Middle-and-Long-Context-Reality.md` (what fits ≠ what works) ·
`Context-Compaction.md` (spending the variable budget) ·
`../Inference/Roofline.md` (bandwidth-bound decode) · `../Agents/Tool-Use.md` § economics.

## Key Takeaways
Two budgets: tokens (the window) and HBM (the KV cache). The stable prefix is
prefix-cacheable — exploit it. The trajectory is the unbounded term — compact it
before the wall. And the *serviceable* context is set by `h_kv` and batch size,
not just the advertised N.
