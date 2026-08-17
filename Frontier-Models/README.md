# Frontier Models — Closed / API-first
`LAST_UPDATED: 2026-08-16` · Status: current-coverage page (verified live 2026-08-16; benchmark
numbers are **vendor-reported [F: vendor]** — treat as claims, not independent results)

## OpenAI
- **GPT-5.6 family** (2026-08) [F: openai.com RSS, 2026-08-13]: "GPT-5.6" with tiered
  variants; **GPT-5.6 Sol "Ultrafast"** mode at up to 14× speed (vendor claim); GPT-5.6
  Luna tier expanded to free users (2026-08-06). Builder's guide published 2026-08-13.
  Architecture/params: not publicly detailed.
- Lineage: GPT-3 (175B, 2020) → GPT-4 (2023) → o1/o3 (reasoning, 2024–25) → GPT-5.x (2025–26).
  OpenAI's "effort levels" make test-time compute a product knob [F: docs].
- Daybreak (cyber-defense model tier, 2026-08 [F: RSS]).

## Anthropic Claude
Model line per Anthropic newsroom [F: anthropic.com/news, verified 2026-08-16]:
- **Opus 5** (2026-07-24): "comes close to the frontier intelligence of Claude Fable 5
  at half the price"; SOTA on Frontier-Bench v0.1, GDPval-AA, ARC-AGI 3 (3× next-best,
  vendor-reported), OSWorld 2.0; effort-level tuning; default on Claude Max.
- **Sonnet 5** (2026-06-30): "most agentic Sonnet yet" — planning, browser/terminal tools,
  autonomous runs; close to Opus 4.8 on agentic evals; $2/$10 per MTok (permanent
  intro price, vendor).
- **Fable 5 / Mythos 5**: higher tiers (Fable 5: frontier ceiling; Mythos 5: ahead of
  Opus 5 on cybersecurity tasks per Opus-5 announcement). "Redeploying Fable 5"
  (2026-06-30) followed a global pause [F: newsroom].
- Pricing reference (from Sonnet 5 post): Opus 4.8 at $5/$25 per MTok [F].
- **Claude Code** — the dominant coding-agent product line; "Making of Claude Code"
  (2026-07-06) [F].
- Safety: jailbreak-severity industry framework (with Amazon/Microsoft/Google + Glasswing
  partners, 2026-06) [F]; text watermark explainer (2026-08-14) [F].

## Google DeepMind / Gemini
- **Gemini 3.7 Flash** (Aug 2026) [F: deepmind.google news] — new Flash-tier generation.
- Model family [F: DeepMind site]: Gemini (flagship), **Gemini Omni** ("create anything
  from anything"), Nano Banana (image), Gemini Audio, Veo (video), Imagen, Lyria (music),
  Gemma (open weights), Genie 3 (world models), SIMA 2 (embodied agents), Gemini Robotics
  ER 2 (2026-07).
- Open: **Gemma** line continues (Gemma 3, 2024–25 [F: HF]).

## xAI
- Latest release: **UNVERIFIED** as of 2026-08-16 (vendor site not reachable at research
  time; Grok-4-class era [A: prior knowledge]).

## Notes
- "Effort levels" / "thinking budgets" are now a cross-vendor product dimension
  (OpenAI, Anthropic, Gemini all expose them) [F: docs] — test-time compute is a SKU.
- Vendor benchmark claims (Frontier-Bench, GDPval-AA, ARC-AGI 3, OSWorld, SWE-bench
  family) are the 2026 evaluation vocabulary; independent verification is limited —
  see `Evaluation/README.md` on saturation/contamination.
