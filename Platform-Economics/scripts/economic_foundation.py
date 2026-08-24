# =============================================================================
# economic_foundation.py
# LLM Systems Wiki — Platform-Economics section.
# Numerical foundation for every cost figure cited across the section.
#
# POLICY: All monetary figures below are ILLUSTRATIVE reference points, NOT
# verified live quotes at publish time. Every material assumption is declared
# in ASSUMPTIONS and printed. Cloud prices are dated snapshots (2026-07/08).
# Re-run `python3 economic_foundation.py` after changing any assumption.
#
# This script is the single source of truth for the section's arithmetic.
# =============================================================================

def fmt(x, nd=2):
    return f"{x:,.{nd}f}"

# -----------------------------------------------------------------------------
# ASSUMPTIONS (all declared)
# -----------------------------------------------------------------------------
# Date of price snapshot
PRICE_DATE = "2026-08"
REGION     = "US (us-east-1 / us-central1 reference)"
CURRENCY   = "USD"

# Hardware reference: NVIDIA H100 80GB SXM
GPU_CAPEX        = 25000   # illustrative $ per H100 80GB SXM (board-level; NRE)
DEPRECIATION_YRS = 3
NODE_GPUS        = 8
NODE_NON_GPU     = 45000   # $: CPU, HBM system, NVLink/IB, chassis, PSU, storage
GPU_TDP_W        = 700
NODE_TDP_W       = GPU_TDP_W * NODE_GPUS     # 5600 W GPU-only for 8x
PUE              = 1.35    # illustrative data-center Power Usage Effectiveness
ELEC_PRICE       = 0.08    # $/kWh commercial DC, illustrative
HOURS_PER_YEAR   = 8760

# Utilization (share of a GPU's time doing useful work)
UTIL_LOW, UTIL_MID, UTIL_HIGH = 0.20, 0.70, 0.95

# Model throughput assumptions (ILLUSTRATIVE, single H100, served with
# continuous batching; ~70B-class dense model, FP8/BF16 mixed)
PREFILL_TOK_S  = 30000   # prefill tokens/s/GPU (batched)
DECODE_TOK_S   = 25000   # aggregate decode tokens/s/GPU at moderate concurrency
# (explicitly illustrative; real numbers depend on model, precision, seq len,
#  batch, engine (vLLM/SGLang/TRT-LLM). See Serving-Engines/.)

# Token economics example: average request shape
AVG_IN_TOKENS   = 1500
AVG_OUT_TOKENS  = 500
REQUESTS_PER_DAY_REF = 200_000

# Cloud GPU on-demand ($/GPU-hr), dated 2026-07/08, US regions [F-search]
CLOUD = {
    "aws_p5":       6.88,   # on-demand, us-east-1
    "azure":        6.98,   # on-demand, eastus
    "gcp":         11.06,   # on-demand, us-central1
    "lambda":       3.99,   # neocloud on-demand
    "runpod":       2.99,   # neocloud on-demand
    "spot":         2.30,   # illustrative spot midpoint (AWS ~2.10-2.50)
}
# OpenAI-compatible API per-1M-tokens, dated 2026 [F-search]
API = {
    "gpt41":      {"in": 2.00,  "cached": 0.50, "out": 8.00},
    "gpt4o":      {"in": 2.50,  "cached": 1.25, "out": 10.00},
    "gpt4o_mini": {"in": 0.15,  "cached": 0.075,"out": 0.60},
    "gpt56_sol":  {"in": 5.00,  "cached": 0.50, "out": 30.00},
}

# -----------------------------------------------------------------------------
# 1. On-prem fully-loaded cost per GPU-hour
# -----------------------------------------------------------------------------
def onprem_gpu_hour(util=1.0):
    node_capex       = NODE_GPUS*GPU_CAPEX + NODE_NON_GPU
    capex_per_yr     = node_capex / DEPRECIATION_YRS
    # Power (IT + cooling via PUE), per node per year
    node_avg_w       = NODE_TDP_W * 0.9                      # not full TDP always
    kwh_per_yr       = node_avg_w/1000 * HOURS_PER_YEAR
    power_cost_yr    = kwh_per_yr * ELEC_PRICE * PUE
    ops_support_yr   = 18000   # illustrative $/node/yr: staff, software, mgmt
    total_yr         = capex_per_yr + power_cost_yr + ops_support_yr
    per_gpu_hour_nom = total_yr / (NODE_GPUS * HOURS_PER_YEAR)
    return per_gpu_hour_nom / util    # utilization-adjusted

base_onprem = onprem_gpu_hour(1.0)
print("="*76)
print("ON-PREM H100 FULLY-LOADED $/GPU-hr (illustrative)")
print(f"  price snapshot: {PRICE_DATE} | region {REGION} | {CURRENCY}")
print(f"  node capex (8xH100): 8*25k + 45k = ${NODE_GPUS*GPU_CAPEX+NODE_NON_GPU:,.0f} over {DEPRECIATION_YRS} yr")
print(f"  nominal (100% util)  : ${base_onprem:.2f}/GPU-hr")
for u in (UTIL_LOW, UTIL_MID, UTIL_HIGH):
    print(f"  at {u*100:.0f}% utilization  : ${onprem_gpu_hour(u):.2f}/GPU-hr  "
          f"({(base_onprem/u)/ (base_onprem/0.5) - 1:+.0%} vs 50%)")

# -----------------------------------------------------------------------------
# 2. Cost per million tokens (compute-derived, self-hosted)
# -----------------------------------------------------------------------------
def cost_per_1m(gpu_hour, prefill_ts=PREFILL_TOK_S, out_tok_s=DECODE_TOK_S):
    # Time to produce 1M tokens as pure prefill or pure decode
    t_prefill = 1_000_000 / prefill_ts   # seconds on the GPU
    t_decode  = 1_000_000 / out_tok_s
    return (t_prefill/3600)*gpu_hour, (t_decode/3600)*gpu_hour

print("\n" + "="*76)
print("SELF-HOSTED 70B $/1M TOKENS (compute-limited, illustrative)")
print(f"  prefill {PREFILL_TOK_S:,}/s, aggregate decode {DECODE_TOK_S:,}/s on H100")
for u in (UTIL_LOW, UTIL_MID, UTIL_HIGH):
    gh = onprem_gpu_hour(u)
    c_in, c_out = cost_per_1m(gh)
    print(f"  util {u*100:.0f}%: ${gh:.2f}/GPU-hr -> prefill ${c_in:.2f}/1M, "
          f"decode ${c_out:.2f}/1M")

# -----------------------------------------------------------------------------
# 3. Cost per request (self-hosted) and vs API
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("COST PER REQUEST — example request shape "
      f"{AVG_IN_TOKENS} in / {AVG_OUT_TOKENS} out")
for u in (UTIL_LOW, UTIL_HIGH):
    gh   = onprem_gpu_hour(u)
    c_in, c_out = cost_per_1m(gh)
    per_req = (AVG_IN_TOKENS*c_in + AVG_OUT_TOKENS*c_out) / 1_000_000
    print(f"  self-host util {u*100:.0f}% : ${per_req:.4f}/req  "
          f"(${per_req*1e6/1000:,.0f} per 1k req)")
for name, m in API.items():
    per_req_api = (AVG_IN_TOKENS*m["in"] + AVG_OUT_TOKENS*m["out"])/1_000_000
    print(f"  API {name:<11}         : ${per_req_api:.4f}/req")

# -----------------------------------------------------------------------------
# 4. Utilization economics — effective cost multiplier
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("UTILIZATION IMPACT ON EFFECTIVE COST (fixed fully-loaded capex)")
# same $/GPU-hr nominal; effective cost scales as 1/util
for u in (0.10, 0.20, 0.50, 0.70, 0.90):
    print(f"  util {u*100:3.0f}% -> effective $/GPU-hr {base_onprem/u:6.2f} "
          f"({(1/u):5.1f}x nominal)")

# -----------------------------------------------------------------------------
# 5. Break-even: on-prem/self-host vs cloud API
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("BREAK-EVEN: fixed self-host vs variable API cost")
# Fixed monthly cost of running 8xH100 node (capacity reserved) at util U
# vs metered API cost. Here: fixed = reserved on-prem node even if idle.
node_monthly_nom = base_onprem * NODE_GPUS * 730   # 730 h/mo, 100% util
for u in (0.20, 0.70):
    # "effective" if we only value productive hours; fixed cost still full
    fixed = base_onprem * NODE_GPUS * 730           # full-month node cost
    per_1m_out_local = cost_per_1m(base_onprem/u)[1]
    print(f"  node effective util {u*100:.0f}%: fixed ${fixed:,.0f}/mo; "
          f"local decode ${per_1m_out_local:.2f}/1M out")
# simpler: tokens/mo to break even vs gpt-4o-mini API
api_out = API["gpt4o_mini"]["out"]; api_in = API["gpt4o_mini"]["in"]
cost_per_req_api = (AVG_IN_TOKENS*api_in + AVG_OUT_TOKENS*api_out)/1_000_000
node_fixed = base_onprem * NODE_GPUS * 730
be_requests = node_fixed / cost_per_req_api
print(f"  break-even: node (${node_fixed:,.0f}/mo) vs gpt-4o-mini "
      f"(${cost_per_req_api:.4f}/req) at {AVG_IN_TOKENS}/{AVG_OUT_TOKENS} "
      f"-> {be_requests/1e6:,.1f}M req/mo")

# -----------------------------------------------------------------------------
# 6. Model routing expected cost (cascade)
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("CASCADE ROUTING EXPECTED COST (illustrative)")
P_small_ok = 0.80                       # prob small model suffices
C_small    = 0.0004                     # $/req small (self-host small model)
C_large    = 0.0040                     # $/req large/premium
C_escalate = C_small + C_large
E_cascade  = P_small_ok*C_small + (1-P_small_ok)*C_escalate
print(f"  P(small ok)={P_small_ok}, C_small=${C_small}, C_large=${C_large}")
print(f"  E[cascade] = {P_small_ok}*{C_small} + {1-P_small_ok}*({C_small}+{C_large})"
      f" = ${E_cascade:.5f}/req")
print(f"  always-large = ${C_large:.5f}/req -> saving {(1-E_cascade/C_large)*100:.1f}%")

# -----------------------------------------------------------------------------
# 7. Cache ROI
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("KV/PREFIX CACHE ROI (illustrative)")
avoid_prefill_1m = cost_per_1m(base_onprem/UTIL_LOW)[0]
cache_hit = 0.6
mem_opp_cost_1m = 0.02  # $ per 1M cached tokens' memory opportunity (illustrative)
value = cache_hit*(avoid_prefill_1m - mem_opp_cost_1m)
print(f"  avoid prefill ${avoid_prefill_1m:.2f}/1M; cache hit {cache_hit}; "
      f"mem opp ${mem_opp_cost_1m:.2f}/1M")
print(f"  cache value ≈ ${value:.2f}/1M requests when hit")

# -----------------------------------------------------------------------------
# 8. Agent amplification cost
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("AGENT TASK AMPLIFICATION (illustrative)")
n_calls = 27                                   # model calls per agent task
per_call = (1500*API["gpt4o_mini"]["in"] + 500*API["gpt4o_mini"]["out"])/1e6
print(f"  one agent task -> {n_calls} model calls; per-call ${per_call:.4f} "
      f"(gpt-4o-mini)")
print(f"  agent task ≈ ${n_calls*per_call:.4f} vs one-shot ${per_call:.4f} "
      f"= {n_calls}x (Task Amplification Factor)")

# -----------------------------------------------------------------------------
# 9. Queueing: utilization vs tail latency (M/M/1)
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("M/M/1 P99 WAIT vs UTILIZATION (illustrative; T_service=0.5s)")
import math
Ts = 0.5
for rho in (0.20, 0.50, 0.70, 0.80, 0.90, 0.95):
    # P99 of response time ~= (Ts/(1-rho)) * ln(100)? Use classic approx:
    # T_p99_queue = (1/(mu - lambda)) * ln(1/(1-0.99))  -> CDF of M/M/1 wait
    Tq_p99 = (Ts * rho / (1 - rho)) * math.log(100)   # queue wait, p99
    T99 = Ts + Tq_p99
    print(f"  rho={rho:.2f}: p99 response ~{T99*1000:.0f} ms")

# -----------------------------------------------------------------------------
# 10. Forecasting headroom (P90 vs mean)
# -----------------------------------------------------------------------------
print("\n" + "="*76)
print("PROVISIONING FOR PEAK: as-if-normal safety factor")
# If mean daily demand D with ~Poisson-ish variance, P99 ~ D + 3*sqrt-ish
D = 2_000_000   # mean tokens/hr
import statistics
# illustrative: provision to P99 of 15-min arrival rate
print(f"  mean {D:,}/h; provisioning only to mean risks queue blowup (see §17/31)")

print("\nAll figures ILLUSTRATIVE and dated:", PRICE_DATE)
