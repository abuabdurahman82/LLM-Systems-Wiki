# Benchmarks — Per-Benchmark Reference
`LAST_UPDATED: 2026-08-16` · Status: reference page
(Format: what it tests / does NOT test / how scores mislead. [F] = established; [I] = inference.)

- **MMLU** (2020, arXiv:2009.03300 [F]) — 57-subject multiple-choice. Tests: breadth +
  world knowledge. NOT: reasoning depth, tool use, current events. Misleads: *saturated*
  for frontier models + heavily *contaminated*. Use MMLU-Pro instead.
- **MMLU-Pro** (2024 [F]) — harder, 10-way. Tests: deeper multi-step + knowledge. NOT:
  agentic.
- **GSM8K** (2021, arXiv:2110.14118 [F]) — grade-school math. Tests: basic reasoning.
  NOT: competition math. *Saturated*.
- **MATH** (2021, arXiv:2112.00111 [F]) — competition math. Tests: multi-step reasoning +
  test-time compute. NOT: faithfulness of CoT.
- **AIME** (annual) — olympiad math. Tests: hard reasoning + test-time compute. NOT:
  broad capability. (2026 variants referenced in open-model tables.)
- **HumanEval** (2021, arXiv:2107.03374 [F]) / **MBPP** (2021 [F]) — single-function code.
  Tests: function-level coding. NOT: repo-scale, multi-file. *Saturated*.
- **SWE-bench** (2023, arXiv:2310.06770 [F]) / **SWE-bench Verified** (2024 [F]) — real
  GitHub issues, multi-file. Tests: repo-scale SWE agent. NOT: non-coding. Misleads:
  *scaffold-sensitive* — same model, different harness, big deltas.
- **SWE-bench Pro** (2025 [F]) — harder/harder-to-game. Tests: robust SWE. NOT: breadth.
- **GPQA** (2021, arXiv:2111.09133 [F]) — expert-level Q (bio/phys/chem); GPQA Diamond
  = hardest subset. Tests: expert STEM reasoning. NOT: agentic.
- **LiveBench** (2024 [F]) — living, contamination-resistant. Tests: general + current.
- **Chatbot Arena / LMArena** (2023 [F]) — human pairwise preference (Elo). Tests:
  perceived open-ended quality. NOT: reproducible, cheap, or safety-specific.
- **Terminal Bench** (2025 [F: repo]) — terminal/CLI agent tasks. Tests: agentic tool
  use in a shell. NOT: GUI.
- **Tool-use benchmarks** — **GAIA** (2023, arXiv:2311.17172 [F]), **AgentBench** (2023,
  arXiv:2308.03688 [F]), **τ³-bench / tau-bench** (2024 [F]), **ToolBench** (2023 [F]).
  Tests: tool selection + multi-step. NOT: cost/safety.
- **Long-context** — **LongBench** (2023 [F]), **RULER** (2024 [F]), **Needle-in-a-Haystack**,
  **Beam** (referenced in 2026 open-model tables, e.g. "Beam 128K" [F: HF blog]). Tests:
  retrieval within long input. NOT: *usable* length (lost-in-the-middle).
- **Agent / computer-use** — **OSWorld / OSWorld-Verified** (2024, arXiv:2404.07972 [F]),
  **WebArena** (2023, arXiv:2307.13854 [F]), **BrowseComp** (2024 [F: OpenAI]),
  **GAIA2** (2025 [F]). Tests: real environment interaction. NOT: cheap/fast.
- **Safety** — **AgentDojo** (2024, arXiv:2406.13352 [F]) prompt-injection; jailbreak
  suites; Siren (referenced in 2026 open-model safety tables [F: HF blog]).
- **Frontier/agentic (2026 vendor)** — **Frontier-Bench**, **GDPval-AA**, **ARC-AGI 3**,
  **AutomationBench (Zapier)**, **DeepSearchQA**, **HLE (Humanity's Last Exam)**,
  **WildClawBench**, **CharXiv Reasoning**, **OmniDocBench**, **SkillsBench** (all
  referenced in 2026 open/frontier model tables [F: vendor/HF]). Vendor-reported.

## The contamination & saturation cheat-sheet
| Era | Saturated / contaminated |
|---|---|
| Pre-2023 | MMLU, HumanEval, GSM8K |
| 2024– | GPQA Diamond (frontier approaching), SWE-bench Verified (racing) |
| 2026 | agentic frontier sets (Frontier-Bench, GDPval-AA) moving; live sets preferred |

## Related
`Evaluation/README.md` · `Frontier-Models/README.md` · `Open-Source-Models/README.md`.

## Key Takeaways
Match the benchmark to the capability. Report the protocol. Prefer live/holdout for the
frontier. Remember agentic benchmarks are harness-sensitive.
