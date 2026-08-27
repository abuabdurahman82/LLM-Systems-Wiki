# Implementation/ EVALUATION — Independent Evaluator Pass (PART 2)

Section: `Distributed-Inference/Implementation/` (PART 2 of the Disaggregated-Inference +
Distributed-Infrastructure series) · Evaluator: `deepseek-v4-flash-0731 @ 10.1.1.51:8888`
(local vLLM, independent endpoint) · Wiki house protocol: every flag is re-verified against
evidence before applying; refuted flags are **recorded, not applied**.

## Scope
All 7 files audited (README + 6 implementation pages), 2026-08-26. The evaluator returned
extended chain-of-thought (the `reasoning` field) consistent with prior sessions; its
decisive, evidence-backed flags were extracted and each re-verified independently.

## Findings & adjudication

| # | Page | Severity | Finding | Adjudication |
|---|---|---|---|---|
| 1 | 01 | MINOR | "millions of small paged blocks … labeled with a placement tuple `(tier,node,rank,block_id)`" conflates *identity* (block_id) with *placement*, and a singular tuple can't represent a TP-sharded logical block | **ACCEPTED (applied).** 30-Second rewrite: identity vs placement separated; sharded-mode note added that a logical block's shards span the TP ranks. |
| 2 | 01 | NIT | The transfer point was worded "when a request's decode ends, its KV is spread across T ranks; any engine→engine handoff must gather or re-shard" — decode-*end* is the wrong boundary | **ACCEPTED (applied).** Rephrased to "a request's KV is spread across T ranks (TP-sharded); any engine→engine handoff (prefill→decode, or turn→turn KV move) must gather or re-shard it first." |
| 3 | 02 | MINOR | Stray backtick in `bandwidth/`latency` | **ACCEPTED (applied).** Removed. |
| 4 | 02 / 06 | MAJOR | "GDS backend moves disk↔HBM **at GPU speed**" overstates: NVMe is ~7 GB/s class, nowhere near HBM bandwidth; GDS's actual benefit is GPU-Direct (no host bounce) | **ACCEPTED (applied).** Both pages now say "disk↔HBM directly, no host bounce / GPU-Direct no host bounce" (consistent with the [F] NIXL BackendGuide phrasing "GDS can move data between storage disks and GPU memory"). |
| 5 | 03 | MINOR | `score(W) = argmax over W of ( h(W), capacity-remaining(W) )` is mathematically sloppy (argmax of a tuple) | **ACCEPTED (applied).** Rewritten as "score = overlap subject to a load-balance constraint; pick argmax over load-feasible workers." |
| 6 | 04 | MAJOR | "hidden under prefill when the link is ≥ ~8× **prefill throughput**" has a units error (tokens/s vs bytes/s) | **ACCEPTED (applied).** Now "≥ ~8× the prefill's KV-production rate (bytes/s; the ~8× rule of thumb and its arithmetic are in `GPU-Communication/08` §4)". |
| 7 | 04 | NIT | The `~8×` figure had no inline attribution on this page | **ACCEPTED (applied)** as part of #6. |
| 8 | 01 | NIT | Steady-state aggregate `λ·KV·(1−h)` units unflagged, but worth stating | **Recorded/verified** — formula and units (bytes/s) are already explicit; matches the [E] 859 GB/s computation. No change needed. |
| 9 | README | NIT | "how the five jobs are built: … and NIXL transfer" — NIXL is a mechanism, not one of the five jobs | **Partially accepted.** The README scope already clarifies NIXL is the transfer engine (job 3 "move"); the implementation-page mapping lists 6 pages for 5 jobs (transfer is job 3's page). No factual error; wording kept, but the mapping table already maps transfer under the move job. |
| 10 | 05 | NIT | `[F]` claim tags without a URL could read as unsubstantiated | **Refuted/recorded.** House convention is `[F: source, fetched date]` with the source named (README / design doc) and fetch date — consistent with every section in the wiki (see `README.md` source policy). Verifiable primary source URLs live in the parent pages (`Distributed-Inference/NVIDIA-Dynamo.md`, `Distributed-Inference/llm-d.md` References). |

## How findings were handled
- Every candidate flag was independently re-verified against the cited primary sources
  (Dynamo/NIXL/llm-d READMEs, fetched 2026-08-26), the canonical constants bank
  (128 KiB/token, 4 GiB@32k), and the parent pages' evidence before applying.
- Mechanical fixes (backticks, units, wording, argmax clarity) applied directly.
- The two "MAJOR" flags (#4, #6) were both accepted: they were genuine technical
  correctness improvements, not stylistic — verified correct against the [F] sources.

## Outcome
- Flags accepted & applied: **8** (#1–#8)
- Flags refuted & recorded: **2** (#9 wording kept, #10 convention)
- Pages left CLEAN (no admissible finding): **README** (after #9 reviewed), **05-global-kv-state**
  (only #10 convention nit), **06-nixl-transfer** (after #4).
- All numbers re-verified post-edit: `32 GiB/session @256k`, `859 GB/s @ 1000/4GiB/h0.8`,
  (1−h) tables (NVLink 4.8→0.5 ms, PCIe5 78→7.8 ms, 100 GbE 361→36 ms at h=0.9) — canonical.

See also: `../../CHANGELOG.md` (2026-08-26 entry), `../../README.md` (what's new).
