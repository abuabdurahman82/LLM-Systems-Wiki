# EVALUATION — AI-Factory-Networking (independent evaluator pass + adjudication)
`LAST_UPDATED: 2026-08-26 · Status: evaluation record · Evaluator: deepseek-v4-flash-0731 @ 10.1.1.51:8888/v1 (user-approved).`

## 30-Second Explanation
Every page in this section was sent, one at a time, to an **independent LLM endpoint** (a different model family from the one that wrote the pages) with an adversarial-reviewer prompt, then I re-verified **every flag it raised against the live file + the primary source** before applying a fix. The evaluator surfaced ~40 live issues; after adjudication I applied ~40 discrete corrections across ~30 pages (convention/unit errors, a systemic per-node vs per-GPU Clos mixup on [52], a missing IPv4 header on [51], and a batch of factual/attribution corrections), and recorded the false positives it raised (a handful, refuted on re-verification). All 56 pages pass the section verifier, cross-links resolve, and 6 sampled pages hydrate under headless docsify. This page is the record of that pass so the *adjudication is visible* — the point of running a second set of eyes is that you can see which flags were real and which were not.

## What was run
- **56/56 pages** (README + 01–55), one `/v1/chat/completions` call each, adversarial system prompt, `max_tokens=16000`; 4 parallel workers (14/14/14/11), all exited 0.
- 6 pages (14, 17, 41, 45, 53, README) returned **degenerate reasoning loops** — a reasoning-model failure mode where the whole budget is consumed by a repeated phrase and no structured verdict lands. Re-run with a tightened "outline-only" prompt; where a usable verdict still did not land, the parent re-verified the flagged spans manually.
- All 56 per-page JSONs retained in `research/ai-networking/eval/`.

## Adjudication summary
Hit rate was higher than the ~50–70% baseline because this section's `[E]` numbers were all machine-verified against the constants bank **before** evaluation, so most live flags were **presentation/convention** errors rather than arithmetic [I: the [E] pre-verification pass made flag adjudication cheap].

### Convention / unit errors (highest-signal)
- **busbw target** (21 pages): pages had written "healthy busbw ≈ `2(n-1)/n × link`" — a *target form* of the *definition* `busbw = algbw × 2(n-1)/n`. At ring saturation algbw → link·n/(2(n−1)), so busbw → **link**, not `2(n−1)/n × link`. Corrected every target form to `0.95 × link (× rails)`; left the definition and the ring time formula `2(n−1)/n · M/B + 2(n−1)·α` intact. Verified against nccl-tests `PERFORMANCE.md` + a nebius 64-rank H100 IB run (busbw/algbw = 1.969 = 2(n−1)/n @ n=64).
- **UET header** ([51](./51-complete-packet-journeys.md)): 78 B omitted the 20 B IPv4 the RoCEv2 58 B comparison included — apples-to-oranges. Corrected to **98 B** (TSS 126 B, native-IP 94 B); bank row updated.
- **UALink** ([02](./02-ai-networking-taxonomy.md) + research note): 800 **GB/s** per x4 → 800 **Gb/s** (= 100 GB/s).
- **Meta SIGCOMM'24 no-DCQCN** ([22](./22-roce-cc-and-load-balancing.md), [24](./24-vendor-landscape.md)): reason was "firmware/CNP bugs" → actually **poor DCQCN performance for training collectives + correct-CNP-counting problems** (verified against the dl.acm.org PDF).
- **Page 16 RoCEv2**: mixed the IPv4 EtherType (0x0800) with IB's 0x8915 and mislabeled the IP-proto byte. Corrected to `EtherType=0x0800 (IPv4) / IP proto=17 (UDP) / UDP dst=4791 (RoCEv2; RoCEv1 = 0x8915, no IP/UDP)`.
- **Page 41 100G row**: 100GBASE is **NRZ 64b/66b**, not PAM4; PAM4+256b/257b starts at 200G.
- **Page 42 fat-tree cite**: "Al-Fares et al., *Horse-racing Hypercubes*" → Al-Fares, Loukissas & Vahdat, *"A Scalable, Commodity Data Center Network Architecture"*, SIGCOMM 2010.

### Factual / attribution errors
- **[50](./50-ai-networking-myths.md) NVL576**: "8-rack NVLink domain is bounded, so scale-out is backend" stated backwards — NVL576 *is* 576 GPUs in **one** NVLink domain across 8 racks. Rewrote the myth; NVL576 fact cited `[F: NVIDIA]`.
- **[52](./52-reference-architectures.md) two-abstraction conflict**: the page quoted the bank's **per-node** Clos rows (bisection 0.2/0.8/6.4 TB/s) while its own A.5b/A.6 described a **1×400G-per-GPU** fabric (12.8 Tb/s). The contradiction "12.8 Tb/s edge ⇒ bisection = 0.200 TB/s" is now explicit: A.1 names both abstractions (8× apart = NICs/node); the A.5b table is internally consistent (radix-16 = 8 down + 8 up, 32 uplinks = 12.8 Tb/s = bisection); the cheat table labels which column is per-node vs per-GPU. Bank `[E]` values preserved verbatim.
- **[48](./48-kubernetes-slurm.md) placement**: "4 nodes under ONE leaf" was arithmetically impossible (16 downlinks/leaf = 2 nodes at 8 GPUs/node) → rewritten as a 16-GPU / 2-node job = one leaf.
- **[26](./26-arista-etherlink.md)**: "64 × 800GbE = 6.4 Tb/s" → **51.2 Tb/s** (off by 8×; [25](./25-nvidia-spectrum-x.md) already had it right).
- **[24](./24-vendor-landscape.md)**: Huawei iNOF/Atlas (not public NIC/DPU); Thor is a NIC (Stingray is the DPU); G200/P200/Spectrum-4 are in-house, not merchant silicon; MRC co-developers now include NVIDIA.
- **Page 13 "Nue" routing engine** (2 pages): not a real OpenSM engine → removed.
- **Page 15**: "DNS of one extra DMA" → "the duration of one extra DMA"; GID index "auto-negotiated on native IB" → user-set index, not auto-negotiated.
- **Page 08**: inline data "auto-elected per WQE" → "application sets `IBV_SEND_INLINE`".
- **Page 09 (8 flags)**: READ byte counts, "< 1% overhead" → "< ~1.6%", DestQP-for-UD, BTH TVer 6→4 bit, "ACK echoes PSN" → ACK carries MSN, "every RDMA_READ_RESPONSE has AETH" → only LAST, "2 round trips (READ)" → 1 request + 1 response, per-switch Demux → destination NIC.
- **Page 06**: "XDR400 = 4 × 100" (nonexistent) → NDR400/NDR800/XDR800 split; "~45–49 GB/s" → "~45–47.5 GB/s".
- **Page 44**: `ethtool -I` → `ethtool -i`; "0.006714" → "0.0474".
- **Page 37**: BlueField-3 SuperNIC is 400 Gb/s-class, not "dual 400G / 1×800G" (800G = ConnectX-8); adaptive routing is BF-3 SuperNIC; "fully proprietary" IB → "open IBTA standard, NVIDIA-dominated".
- **Page 39**: "DCQCN credit pool" → "deep-buffer pool"; incast timing now has the `[E]` derivation.
- **Pages 19/20 K-min vs K-max**: ECN marking starts at **K-min**; "ECN marks before PFC" = **K-min < XOFF**; RFC 6040 VXLAN outer ECN derived from the inner packet.
- **Page 18**: "Run RoCEv2 and you are already running DCB" → "with PFC **on** you run the DCB machinery; RoCEv2 itself does not require DCB (PFC-off is lossy)".
- **Page 47 M_Key**: management key (SM/SMP), not memory key; memory windows = R_Key/L_Key + PD.
- **Page 49 entropy**: "entropy (fixed dst port 4791)" → "low hash entropy".

### False positives (refuted on re-verification)
- **Page 13 "AR default on IB"**: IBTA default is no-AR (opt-in per QP); the page wording is correct.
- **Page 44 PPS**: 400GbE@1518B = 32.94 Mpps, @9018B = 5.54 Mpps; 100GbE@1518B = 8.23 Mpps — all machine-verified against the bank.
- **Pages 42/44 bisection**: E=128 = 128 nodes × 1 NIC/rail plane is the section's rail-optimized coherent model; 6.4 TB/s/plane × 8 = 51.2 Tb/s is correct, not an error.

### Noted, not fixed (within declared scope)
- **Pages 07/08 non-canonical section order** (References before Related): the verifier checks presence, not order; reordering would violate the append-only backfill rule and is not a correctness issue.

## Verification
- `verify-afn-page.py` (section-local): **56/56 OK**.
- Cross-link audit (all `](./NN-`, `](../`, `](/` targets): **0 broken**.
- docsify headless render (6 sampled pages incl. the most-edited 52/51/48/53/26/README): **6/6 hydrated**.
- Residue sweep (`Nue`, `iNOF/Atlas`, `0.006714`, `Horse-racing Hypercubes`, `DNS of one extra`, `UET std hdr = 78`, `1.90 %`, `6.4 Tb/s → 800`): all clean.
- All 56 pages carry `LAST_UPDATED: 2026-08-26`.

## Key Takeaways
1. The evaluator is a strong second set of eyes but **not a source of truth** — every flag was re-checked against the live file and (where factual) the primary source before a fix was applied, and a meaningful minority were refuted.
2. **Pre-verify your own `[E]` numbers first**: because the constants bank was machine-checked before evaluation, most live flags were convention/presentation errors (busbw target form, UET missing IPv4, per-node vs per-GPU), not arithmetic.
3. **Convention drift is the dominant failure class** — `2(n-1)/n` (a definition/time factor) misused as a *target*; a header byte count that omitted IPv4; Gb/s vs GB/s. State the convention at the point of use.
4. Reasoning-model evaluators can **degenerate into loops** with no verdict (6/56 pages here); detect the loop, re-run with a budget-constrained prompt, and fall back to manual re-verification — a degenerate chunk is neither a pass nor a refutation.
5. Keep the **adjudication visible**: this record (accepted + refuted + noted) is what makes the pipeline trustworthy.

## Related
- [52-reference-architectures.md](./52-reference-architectures.md) — the page with the most adjudicated flags (two-abstraction Clos fix).
- [51-complete-packet-journeys.md](./51-complete-packet-journeys.md) — the UET 98 B header fix.
- [44-performance-metrics-benchmarking.md](./44-performance-metrics-benchmarking.md) — PPS math and the busbw gate.
- [42-clos-fat-tree-math.md](./42-clos-fat-tree-math.md) — the [E] shape bank behind the bisection adjudications.
- [55-cheat-sheet.md](./55-cheat-sheet.md) — the section's one-page recap.

## References
- Independent evaluator: `deepseek-v4-flash-0731` served via vLLM at `10.1.1.51:8888/v1` (OpenAI-compatible `/v1/chat/completions`), user-approved; per-page JSONs in `research/ai-networking/eval/` [E: 56/56 completed].
- nccl-tests `PERFORMANCE.md` (busbw = algbw × 2(n-1)/n definition) + nebius 64-rank H100 IB run (busbw/algbw = 1.969) [F].
- Meta, "RDMA over Ethernet for Distributed AI Training at Meta Scale", SIGCOMM 2024 — no-DCQCN rationale [F: dl.acm.org PDF].
- UEC/UET spec 1.0 → 1.0.3 (2025-06-11 → 2026-07-16) — PDS/SES header sizes [F].
- Section constants bank: `research/ai-networking/verified-constants.md` [E].
- `verify-afn-page.py` (section verifier) and the docsify headless render check [E: 2026-08-26].
