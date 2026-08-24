# 39 — Multimodal Economics

`LAST_UPDATED: 2026-08-24` · Status: core page

## 30-Second Explanation

Multimodal inputs (image, audio, video) change the economics because they route
through **encoders** and add **sequence tokens, storage, and bandwidth** on top
of text. There is **no universal "1 image = N tokens" ratio** — the token count
depends on the model's vision/audio encoder and preprocessing, so pricing and
cost must be *measured per model*, not assumed. Respect the model's documented
tokenization; don't invent a conversion factor. (Full multimodal mechanics:
[Multimodal/](../Multimodal/README.md).)

## Cost dimensions

| Dimension | What it adds |
|---|---|
| **Tokenization** | images/audio → many tokens via encoder patches/embeddings |
| **Encoder cost** | a vision/audio encoder pass runs before the LLM |
| **Storage** | source media (images/audio/video) held for processing/retry |
| **Bandwidth** | moving large media bytes to the serving endpoint (and cloud, [28](28-cloud-bursting-economics.md)) |
| **Latency** | encoding adds time; video adds frames |

## Why no universal ratio

Different models encode differently:
- An image may be a *handful* of visual tokens in one model and *hundreds* in
  another, depending on patch size / resolution / encoder.
- Video/audio tokenization depends on frames/sec and sampling.

So **"given any image costs X tokens" is a false universal**. The correct move:
- Read the **model's documented tokenization** (how many tokens per image /
  per second of audio/video its encoder produces).
- **Measure** the actual cost on your platform for your media profile
  ([13-tenant-metering](13-tenant-metering.md)).

>[I] If a provider doesn't publish an exact ratio, treat the implicit ratio as
> `UNVERIFIED` and measure it rather than assuming a round number.

## Multi-tenant implications

- Multimodal traffic can be **disproportionately expensive per request**
  (encoder + many tokens + storage/bandwidth) — meter it like reasoning tokens
  ([06-token-economics](06-token-economics.md),
  [15-llm-platform-pricing-models](15-llm-platform-pricing-models.md)).
- **Storage/retention** of user media interacts with data governance
  ([24-data-governance](24-data-governance.md)).
- **Bandwidth/egress** for media can dominate where it's large or cloud-routed
  ([28](28-cloud-bursting-economics.md)).

## Related

[Multimodal/](../Multimodal/README.md) · [06-token-economics](06-token-economics.md) ·
[24-data-governance](24-data-governance.md) · [13-tenant-metering](13-tenant-metering.md) ·
[28-cloud-bursting-economics](28-cloud-bursting-economics.md)

## Key takeaways

1. Multimodal adds encoder cost + sequence tokens + storage + bandwidth.
2. There is no universal "1 image = N tokens" — measure per model.
3. Treat implicit token ratios as UNVERIFIED until documented/measured.
4. Meter multimodal like reasoning tokens; watch storage and egress.
