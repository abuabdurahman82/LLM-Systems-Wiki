# Multimodal Models
`LAST_UPDATED: 2026-08-16` · Status: section page

## 30-Second Explanation
LLMs that also perceive images/audio/video/speech and act on physical or computer
environments. The core architectural question: *how do non-text tokens enter the model?*

## Modality coverage (2026 state)
- **Text + image:** VLMs are mature (GPT-4o-class, Gemini, Claude, Qwen-VL, Llama
  multimodal, Meta **Muse Glimmer** 30B multimodal Apache-2.0 [F: HF blog 2026-08-10]).
- **Audio/speech:** speech-to-speech ("omni") models: GPT-4o realtime (2024), Gemini
  Audio (2026 [F: DeepMind site]), Qwen-Audio/Omni-class.
- **Video:** video-understanding (Gemini 2.x/3.x, Sora-class generation separate).
- **Computer interaction:** screenshots as vision + UI actions (computer-use agents)
  [F: Anthropic/OpenAI docs].
- **Robotics / world models:** Gemini Robotics ER 2 (2026 [F]), Genie 3 interactive worlds
  (2025 [F]), VLA models (RT-2 lineage [F: arXiv:2307.15818]).

## Architectural strategies
| Strategy | Mechanism | Examples |
|---|---|---|
| **Separate encoder + projection** (the dominant design) | CNN/ViT encoder → tokens → projector (MLP/attention) → LLM input space | LLaVA (arXiv:2304.08469 [F]) template; most 2024+ VLMs |
| **Shared token space** | all modalities tokenized to one discrete/vectorspace; single Transformer | GPT-4o-class end-to-end [F: OpenAI], Gemini native-multimodal claims [F] |
| **Native multimodal training** | trained from scratch on mixed modalities (not bolted-on) | frontier 2024+ models [I: reported] |
| **Perception encoder (2026)** | dedicated small vision model (e.g. 2B ViT-style) fused with a text decoder | Muse Glimmer (2B encoder + 28B decoder) [F: HF blog] |
| **Diffusion/flow heads** | generation side (image/video) separate from understanding | FLUX, Veo, Sora [F] |

## Why the encoder+projector design won
The LLM was already trained on text; a frozen/fine-tuned vision encoder + cheap
projector lets the LLM *reuse* its text priors for new modality tokens — far less
training data needed than fully-native multimodal pretraining [I: LLaVA-line reasoning].

## Limits & open problems
- Resolution vs token budget (image = 256–1000+ vision tokens; video = thousands).
- Temporal reasoning in video remains weak [I].
- Cross-modal grounding (spatial reasoning, chart reading) — active benchmark territory
  (MMMU, ScreenSpot Pro, OmniDocBench — see `Benchmarks/`).
- Safety: visual jailbreaks, unsafe image generation [F: vendor safety docs].

## Related
`Agents/README.md` (computer use) · `Benchmarks/README.md` · `Safety/README.md`.

## Key Takeaways
Understanding: encoder+projector into a text LLM (dominant). Generation: diffusion
heads. 2026: native multimodal frontier + open local multimodal (Muse Glimmer).
