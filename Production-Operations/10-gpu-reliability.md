# 10 — GPU Failure Engineering

`LAST_UPDATED: 2026-08-23` · Status: operational page

> GPU claims on this page are **verified against NVIDIA official documentation**
> (`docs.nvidia.com`, checked 2026-08-23) and tagged `[F]` where so. We do **not**
> invent error-code meanings. Where a specific code/behaviour is not verified it
> is marked `UNVERIFIED` and left unasserted.

## 30-Second Explanation

GPUs fail, degrade, throttle and vanish — and their failures are *different* from
CPU failures (ECC, Xid, thermal, disappear-from-bus). Operators must recognise
each failure class, know which commands surface it, and have a manual for it.

## Failure classes

| Class | What it is | How surfaced | Notes |
|---|---|---|---|
| **GPU OOM** | memory allocation fails | CUDA error, engine OOM, container kill | capacity/KV problem, often recoverable by retry ([13](13-overload-protection.md)) |
| **ECC (correctable SBE / uncorrectable DBE)** | memory soft/hard errors | `nvidia-smi` ECC counts; Xid 48 on DBE | SBE tolerable, watch rate; DBE requires reset ([F]) |
| **Xid** | driver-reported GPU error to kernel log | `dmesg`, `journalctl`, grep `NVRM: Xid` | diagnostic, not prescriptive ([F]) |
| **Thermal throttling** | GPU reduces clocks to protect hardware | `nvidia-smi` temp + throttling flags, DCGM | sustained → fix cooling/power |
| **Clock throttling** | power/utilization-based clock drop | `nvidia-smi -q` clocks, `nvidia-smi dmon` | may be power-cap/bios, not a fault |
| **PCIe failures** | link problems, device errors | dmesg, `lspci -vvv`, `nvidia-smi` errors | reseat/RMA path |
| **NVLink failures** | intra-node fabric errors | dmesg, NVLink health, DCGM | breaks multi-GPU topologies ([11](11-distributed-inference-failures.md)) |
| **Driver crashes** | kernel driver fault | dmesg, Xid, application CUDA errors | often recoverable by pod restart |
| **GPU reset** | device-level reset (often after DBE) | dmesg `NVRM`, Xid | in-flight work lost |
| **GPU disappearance** | device drops off the bus | `nvidia-smi` shows N-1 GPUs, dmesg | node typically needs reboot/reinstall |

## Xid errors — what they are (`[F]`)

Per NVIDIA *XID Errors* documentation:
- A **Xid message** is an error report from the NVIDIA driver written to the OS
  kernel/event log; it indicates a general GPU error occurred, "most often due to
  the driver programming the GPU incorrectly or to corruption of the commands
  sent to the GPU," and may indicate a hardware, NVIDIA-software, or
  user-application problem.
- Xid messages are **debugging guides, not exact diagnoses** — many problems
  have multiple possible root causes, so an Xid value alone is not conclusive.
- The meaning of each message is **consistent across driver versions**.
- On Linux they are logged to the kernel log buffer and typically to
  `/var/log/messages` or `/var/log/syslog`; **grep for `NVRM: Xid`**.

Examples from the official catalog (verified `[F]`):
- **Xid 48** `ROBUST_CHANNEL_GPU_ECC_DBE` — *Double Bit ECC Error*; a GPU reset
  or node reboot is needed to clear it; `nvidia-smi` gives an ECC-error summary.
  (Note: Xid "48" in the 2026 catalog corresponds to the historically-known 48.)
- **Xid 63** — GPU memory remapping event (excess ECC handled via row remap).
- **Xid 64** — memory remapping **failure**; suggests reset, then vendor support.
- **Xid 92** `EXCESSIVE_SBE_INTERRUPTS` — high single-bit (correctable) rate.
- **Xid 94/95** `ROBUST_CHANNEL_CONTAINED_ERROR` — contained memory errors
  starting with A100: 94 affects one app (restart app; reset GPU when convenient),
  95 affects multiple apps (reset GPU before restart).
- **Xid 140** `UNRECOVERABLE_ECC_ERROR_ESCAPE` — uncorrectable ECC escaped;
  reset GPU, then vendor support.
- **Xid 168** `REDUCED_GPU_MEMORY_CAPACITY` — WPR write-protected-region errors
  (typically seen with ECC disabled).

**Do not over-interpret:** Xid is a starting point; combine with hardware
diagnostics. Refer to NVIDIA *GPU Debug Guidelines* / `nvidia-bug-report.sh` for
deeper steps (`[F]` documentation recommendation).

## The operator's toolset

| Tool | What it shows | Notes |
|---|---|---|
| `nvidia-smi` | temp, clocks, power, memory, ECC counts, GPU list | first stop; `nvidia-smi -q` for detail, `nvidia-smi dmon` for live (`[F]`) |
| `nvidia-smi -q -d ECC` / `-d CLOCK` / `-d THERMAL` | specific domains | isolate the signal |
| **DCGM** (Data Center GPU Manager) | active health monitoring, diagnostics, system alerts, power/clock governance (`[F]`) | NVIDIA's datacenter GPU mgmt suite |
| **DCGM Exporter** | Prometheus GPU metrics (`DCGM_FI_*`) on `/metrics` :9400 (`[F]`) | feeds dashboards ([20](20-llm-observability-stack.md), [Labs](Labs/08-monitor-gpu-with-dcgm.md)) |
| `dmesg` / `journalctl -k` | kernel log, Xid, NVLink, reset events | grep `NVRM` |
| `nvidia-smi --gpu-reset` | targeted reset where supported | disruptive; drain first |
| `nvidia-bug-report.sh` | full diagnostic bundle | attach to vendor/RMA tickets (`[F]`) |

**DCGM diagnostics** is a health check that can check ECC presence, PCIe
problems, bandwidth and CUDA-running problems (`[F]`).

## Operational playbook

1. **Monitor continuously**: DCGM Exporter → Prometheus/Grafana for temp, clocks,
   power, memory, ECC rate, Xid count ([20](20-llm-observability-stack.md)).
2. **Alert on *trends*** (rising ECC rate, sustained throttling) before hard
   failure, not only on crashes ([22](22-alerting-strategy.md)).
3. **Drain before reset**: move work off the GPU/pod before a reset (k8s
   cordon/drain) to avoid killing in-flight requests.
4. **Correlate Xid with workload** — a user-application fault and a hardware fault
   need different responses; trace helps ([23](23-llm-tracing.md)).
5. **Treat DBE as a ticket**: reset, run diagnostics; persistent →
   RMA/vendor per NVIDIA guidance (do not attempt field repair beyond documented
   steps).

## Related

`09-llm-failure-taxonomy.md` · `11-distributed-inference-failures.md` ·
`20-llm-observability-stack.md` · `GPU-Systems/Diagnostics.md` ·
`GPU-Systems/GPU-Metrics.md` · `Labs/08-monitor-gpu-with-dcgm.md`

## Key takeaways

1. GPU failure classes include OOM, ECC, Xid, thermal/clock throttling, PCIe/NVLink,
   driver crash, reset, and disappearance — each with distinct signals.
2. Xid messages are debugging guides with consistent meaning, not exact diagnoses
   (`[F]`). Grep `NVRM: Xid`.
3. Toolset: `nvidia-smi`, DCGM, DCGM Exporter, `dmesg`, `journalctl`.
4. Monitor trends, drain before reset, and escalate persistent DBE via documented
   vendor path — don't improvise field repairs.
