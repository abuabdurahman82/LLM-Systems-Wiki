# Mixture of Experts (MoE)
`LAST_UPDATED: 2026-08-16` · Status: core page

## 30-Second Explanation
Replace the dense FFN with N experts (small FFNs) + a router that sends each token to
top-k experts (usually 2 of 64–256). Total parameters grow; *activated* parameters stay
roughly constant. You get more model capacity for the same forward compute — at the cost
of routing complexity and memory.

## Mechanism + math
```
router:  g = TopK( softmax( h·W_gate ), k )          W_gate ∈ R^(d × N_experts)
output:  y = Σ_i g_i · E_i(h)                        E_i = expert FFN_i
```
Plus typically **shared experts** (always-on experts) [F: DeepSeek-V2/V3 "shared +
routed" design; Switch Transformer also] — a dense residual path under the sparse one.

## Why it mattered
- GPT-3 showed capacity helps; dense 1T+ was computationally infeasible to *train at
  inference-time cost*. MoE decouples stored capacity from compute. [F: Shazeer 2017
  arXiv:1701.06538; Switch 2021 arXiv:2101.03961]
- Enabled the open frontier: Mixtral 8x7B (2023 [F]), DeepSeek-V3 671B/37B-active
  (2024 [F]), Qwen3-MoE, GPT-OSS (2025 [F: OpenAI]), Kimi/Moonshot (2024+).

## Problems MoE created (all still live research areas)
1. **Training load-balancing** — auxiliary loss to prevent expert collapse (Switch's
   `α·L_aux`) [F].
2. **Expert parallelism + AllToAll** — dispatch/combine communication; the MoE network
   bottleneck (`Distributed-Inference/`); wide-EP optimization is a TRT-LLM/SGLang
  specialty [F: blogs].
3. **Memory** — all expert weights must be resident (or offloaded); decode bandwidth is
   dominated by expert fetches → MoE decode is *more* bandwidth-bound per token than
   dense at equal active params [I: roofline-derived].
4. **Routing at low batch** — at B=1–8, many experts fetch 1 token each: poor
   compute/IO. 2026 work: DeaMoE (small-batch-friendly MoE structure, preprint 2026-08
  [UNVERIFIED]), compute-aware scaling for MoE (preprint 2026-08).
5. **KV cache unaffected** — MoE is FFN-side; KV formula unchanged.

## Variants
- **Sparse routing** (standard) vs **dense MoE** (weighted sum over all experts —
  research).
- **Soft routing** (no top-k, all experts with small weights — e.g. some 2024 designs
  [I]).
- **Multi-token / layer-adaptive** routing — research.
- **Expert-offloading / KV-style paging of experts** — systems work [I: emerging].

## Related
`Training/README.md` (expert parallelism) · `Distributed-Inference/README.md` ·
`Inference/Roofline.md` · `Latest-Research/README.md` (2026 MoE items).

 MoE + Expert Parallelism on the GPU (AllToAll, hot experts, EP+TP): `GPU-Systems/MoE-Expert-Parallelism.md`.

## Key Takeaways
MoE = capacity without compute, paying in memory + communication. The 2024–2026
frontier (DeepSeek, Qwen, GPT-OSS) is MoE; the open problems are expert placement,
small-batch efficiency, and training stability.
