# Lab 8 — Monitor GPU with DCGM

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [10-gpu-reliability](../10-gpu-reliability.md), [20-llm-observability-stack](../20-llm-observability-stack.md)

## Goal
Collect NVIDIA GPU telemetry with **DCGM Exporter** and see the key `DCGM_FI_*`
metrics that drive the GPU view ([10](../10-gpu-reliability.md)).

## Prereq
A host with an NVIDIA GPU and driver, and `docker`. **If none present, skip — do
not fake GPU numbers.**

## Method
> Commands below are from official NVIDIA DCGM-Exporter docs (`[F]`), verified
> 2026-08-23; run only where a GPU + driver exist.

```bash
# 1. Run dcgm-exporter (from NVIDIA docs)
docker run -d --rm --gpus all --cap-add SYS_ADMIN -p 9400:9400 \
  nvcr.io/nvidia/k8s/dcgm-exporter:latest

# 2. Read the metrics (prometheus text)
curl localhost:9400/metrics
```

Key metrics to identify (`[F]`-sample names from NVIDIA docs/`[E]`):
- `DCGM_FI_DEV_SM_CLOCK`, `DCGM_FI_DEV_MEM_CLOCK` (clock MHz)
- `DCGM_FI_DEV_MEMORY_TEMP` (temp °C)
- `DCGM_FI_DEV_MEM_COPY_UTIL`, SM/power/memory metrics (confirm exact names on
  your version: `curl localhost:9400/metrics | grep DCGM_FI_`)

Compare with `nvidia-smi` output.

## Interpretation
- **Clocks+temp**: sustained throttle ⇒ thermal/power ([10](../10-gpu-reliability.md)).
- Wire into the GPU dashboard ([21](../21-production-dashboard.md)) and trend ECC
  (`nvidia-smi -q -d ECC`) for early DBE detection.

## Safety
Read-only monitoring; `docker` on your own GPU host. Do **not** reset or modify
GPUs. If you only touch synthetic data, say so in your notes (no fake GPU results).
