# =============================================================================
# economic_simulator.py
# LLM Systems Wiki — Platform-Economics.  Interactive economic simulator.
#
# Turns the section's cost model into a number machine across scenarios:
#   private GPU / public GPU / cloud API / hybrid.
# Every number is computed from declared ASSUMPTIONS (no hidden constants).
# All outputs are ILLUSTRATIVE with a stated price date — NOT a substitute
# for a live provider quote or your own measured throughput.
#
# Usage:
#   python3 economic_simulator.py                      # run all scenarios
#   python3 economic_simulator.py --scenario hybrid    # one scenario
#   python3 economic_simulator.py --json scenario.json # JSON override
# =============================================================================
import json, sys

PRICE_DATE = "2026-08"
CURRENCY   = "USD"

# --- Default assumptions (edit here or override via JSON) ------------------
A = {
    # hardware
    "gpu_capex": 25000, "depreciation_yrs": 3, "node_gpus": 8,
    "node_non_gpu": 45000, "gpu_tdp_w": 700, "pue": 1.35,
    "elec_price": 0.08, "ops_support_per_node_yr": 18000,
    # model/serving (ILLUSTRATIVE; measure yours)
    "prefill_tok_s": 30000, "decode_tok_s": 25000, "utilization": 0.70,
    # demand
    "requests_per_day": 200000, "in_tokens": 1500, "out_tokens": 500,
    "cached_in_tokens": 400,
    # cloud
    "cloud_api_in_per_1m": 2.00, "cloud_api_out_per_1m": 8.00,
    "cloud_api_cached_per_1m": 0.50, "cloud_gpu_per_hr": 6.88,
    # other
    "staff_per_node_yr_extra": 0, "avail_headroom_frac": 0.0,
    # cloud API alternative (for break-even)
    "api_alternative_in_per_1m": 0.15, "api_alternative_out_per_1m": 0.60,
}

# --- Cost core -------------------------------------------------------------
def fully_loaded_gpu_hr(A, util=None):
    util = util if util is not None else A["utilization"]
    node_capex = A["node_gpus"]*A["gpu_capex"] + A["node_non_gpu"]
    capex_yr   = node_capex / A["depreciation_yrs"]
    node_w     = A["gpu_tdp_w"]*A["node_gpus"]*0.9
    kwh_yr     = node_w/1000 * 8760
    power_yr   = kwh_yr * A["elec_price"] * A["pue"]
    ops_yr     = A["ops_support_per_node_yr"] + A["staff_per_node_yr_extra"]
    total_yr   = capex_yr + power_yr + ops_yr
    nominal    = total_yr / (A["node_gpus"] * 8760)
    return nominal / util          # utilization-adjusted, fully loaded

def per_1m(gpu_hr, A):
    cin  = (1_000_000 / A["prefill_tok_s"]) / 3600 * gpu_hr
    cout = (1_000_000 / A["decode_tok_s"])  / 3600 * gpu_hr
    return cin, cout

def scenario_private(A):
    gh  = fully_loaded_gpu_hr(A)
    cin, cout = per_1m(gh, A)
    req = (A["in_tokens"]*cin + A["out_tokens"]*cout)/1e6
    monthly = A["requests_per_day"]*30.44 * req
    return {
        "scenario":"private-gpu","util":A["utilization"],
        "gpu_hr":gh,"prefill_1m":cin,"decode_1m":cout,"req":req,
        "monthly_platform":monthly,"gpus":A["node_gpus"],
    }

def scenario_public(A):
    # cloud GPU instance, assume same serving throughput, pays instance price
    gh = A["cloud_gpu_per_hr"]
    cin, cout = per_1m(gh, A)
    req = (A["in_tokens"]*cin + A["out_tokens"]*cout)/1e6
    monthly = A["requests_per_day"]*30.44 * req
    return {"scenario":"public-gpu","util":1.0,"gpu_hr":gh,
            "prefill_1m":cin,"decode_1m":cout,"req":req,
            "monthly_platform":monthly,"gpus":A["node_gpus"]}

def scenario_api(A):
    # cloud API pricing on tokens, incl. cached input discount
    cin  = A["cloud_api_in_per_1m"];  cc = A["cloud_api_cached_per_1m"]
    cout = A["cloud_api_out_per_1m"]
    fresh = A["in_tokens"] - A["cached_in_tokens"]
    req = (fresh*cin + A["cached_in_tokens"]*cc + A["out_tokens"]*cout)/1e6
    monthly = A["requests_per_day"]*30.44 * req
    return {"scenario":"cloud-api","util":"-","gpu_hr":None,
            "prefill_1m":cin,"decode_1m":cout,"req":req,
            "monthly_platform":monthly,"gpus":0}

def scenario_hybrid(A):
    # fixed private base at utilization; overflow (above a cap) to API
    priv_base = A["requests_per_day"]*A["utilization"]        # serve locally
    overflow  = A["requests_per_day"]*(1-A["utilization"])    # to cloud API
    p = scenario_private(A)
    cin, cout = per_1m(fully_loaded_gpu_hr(A), A)
    local_req = (A["in_tokens"]*cin + A["out_tokens"]*cout)/1e6
    c_in  = A["cloud_api_in_per_1m"]; c_c = A["cloud_api_cached_per_1m"]
    c_out = A["cloud_api_out_per_1m"]
    fresh = A["in_tokens"]-A["cached_in_tokens"]
    api_req = (fresh*c_in + A["cached_in_tokens"]*c_c + A["out_tokens"]*c_out)/1e6
    monthly = (priv_base*local_req + overflow*api_req)*30.44
    return {"scenario":"hybrid","util":A["utilization"],"gpu_hr":p["gpu_hr"],
            "prefill_1m":cin,"decode_1m":cout,
            "req":(local_req, api_req),"monthly_platform":monthly,
            "overflow_frac":1-A["utilization"],"gpus":A["node_gpus"]}

# --- break-even ------------------------------------------------------------
def break_even(A):
    # Fixed monthly node cost: nominal (100%-util) fully-loaded, held regardless
    # of utilization — this is the true "reservation" cost vs metered API.
    node_fixed_monthly = fully_loaded_gpu_hr(A, util=1.0) * A["node_gpus"] * 730
    c_in  = A["api_alternative_in_per_1m"];  c_out = A["api_alternative_out_per_1m"]
    req_cost = (A["in_tokens"]*c_in + A["out_tokens"]*c_out)/1e6
    return node_fixed_monthly, req_cost, node_fixed_monthly/req_cost

RUNNERS = {"private":scenario_private,"public":scenario_public,
           "api":scenario_api,"hybrid":scenario_hybrid}

def show(d):
    print(f"  {d['scenario']:<11} util={str(d['util']):<6} "
          f"$/req={d['req'] if isinstance(d['req'],float) else d['req']} "
          f"marginal $/mo={d['monthly_platform']:,.0f}  "
          f"(variable token cost at stated sizing; EXCLUDES the fixed node "
          f"reservation — see break-even below)")

def main():
    args = sys.argv[1:]
    scenario = None
    if "--scenario" in args:
        scenario = args[args.index("--scenario")+1]
    if "--json" in args:
        path = args[args.index("--json")+1]
        A.update(json.load(open(path)))

    print(f"Economic simulator — price snapshot {PRICE_DATE}, {CURRENCY}")
    print("Assumptions:", json.dumps(A, indent=0))

    if scenario and scenario in RUNNERS:
        show(RUNNERS[scenario](A))
    else:
        for name in RUNNERS:
            show(RUNNERS[name](A))

    f, req_cost, be = break_even(A)
    print(f"\nBreak-even (private node @ ${f:,.0f}/mo vs API alt "
          f"${req_cost:.5f}/req): {be/1e6:,.2f}M req/mo")

if __name__ == "__main__":
    main()
