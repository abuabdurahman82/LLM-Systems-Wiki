# Lab 7 — Build a Prometheus Dashboard

`LAST_UPDATED: 2026-08-23` · `Status: lab` · Paired with [20-llm-observability-stack](../20-llm-observability-stack.md), [21-production-dashboard](../21-production-dashboard.md)

## Goal
Stand up a minimal **Prometheus + Grafana** stack, scrape a synthetic metrics
exporter, and build the **minimum dashboard** from [21](../21-production-dashboard.md).

## Why
Observability is the control loop that tells you *which* axis/layer is off
([20](../20-llm-observability-stack.md)).

## Method
1. **A tiny exporter** exposing Prometheus text metrics on `:9100`:
```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import random, time
class M(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            body = f"""# TYPE llm_requests_total counter
llm_requests_total {random.randint(0,100)}
# TYPE llm_ttft_seconds histogram
llm_ttft_seconds_bucket{{le="1"}} {random.randint(0,50)}
llm_ttft_seconds_bucket{{le="2"}} {random.randint(50,100)}
# TYPE llm_kv_util gauge
llm_kv_util {random.random()}
"""
            self.send_response(200); self.send_header("Content-Type","text/plain"); self.end_headers()
            self.wfile.write(body.encode())
    def log_message(self,*a): pass
HTTPServer(("127.0.0.1",9100),M).serve_forever()
```
2. **Prometheus** (`prometheus.yml`): scrape `localhost:9100`, port 9090.
3. **Grafana**: add Prometheus data source; add panels:
   requests/sec (rate), TTFT buckets, KV utilization, queue depth, goodput.

## Interpretation
Build the *minimum* dashboard set from [21](../21-production-dashboard.md) (requests,
tokens, TTFT/TPOT P50/P95/P99, queue, KV util, GPU, errors, goodput). Pair latency
with queue/KV so panels read as a story ([04](../04-llm-golden-signals.md)). Add an
SLO line on the TTFT panel ([02](../02-sli-slo-sla-for-llms.md)).

## Safety
Local ports; synthetic metrics only — this lab touches no real service.
