"""One-at-a-time sensitivity analysis around a reference scenario (tornado inputs)."""
from __future__ import annotations

import pandas as pd

from cibst.engine import Shocks, StressTestEngine

SENSITIVITIES = [
    ("PD x1.20", "PD x0.80", "pd_mult", 1.20, 0.80),
    ("LGD +5pp", "LGD -5pp", "lgd_add", 0.05, -0.05),
    ("CCF +10pp", "CCF -10pp", "ccf_add", 0.10, -0.10),
    ("GDP -1pp", "GDP +1pp", "gdp_add", -1.0, 1.0),
    ("Oil x0.80", "Oil x1.20", "oil_mult", 0.80, 1.20),
    ("Rates +100bp", "Rates -100bp", "rate_add", 1.0, -1.0),
]


def _metrics(res) -> dict:
    s = res.summary
    return {"ecl_peak": s["ecl"].max(), "cum_impairment": s["cum_impairment"].iloc[-1],
            "rwa_peak": s["rwa"].max(), "cet1_trough": s["cet1_ratio"].min()}


def run_sensitivities(engine: StressTestEngine, scenario: str = "severe") -> pd.DataFrame:
    base = _metrics(engine.run_scenario(scenario))
    rows = []
    for up_name, dn_name, field, up, dn in SENSITIVITIES:
        for name, val, side in ((up_name, up, "adverse"), (dn_name, dn, "favourable")):
            m = _metrics(engine.run_scenario(scenario, Shocks(**{field: val})))
            rows.append({
                "driver": up_name.split()[0], "shock": name, "direction": side,
                "cum_impairment": m["cum_impairment"],
                "d_cum_impairment": m["cum_impairment"] - base["cum_impairment"],
                "rwa_peak": m["rwa_peak"], "d_rwa_peak": m["rwa_peak"] - base["rwa_peak"],
                "cet1_trough": m["cet1_trough"],
                "d_cet1_trough_bps": (m["cet1_trough"] - base["cet1_trough"]) * 1e4,
            })
    out = pd.DataFrame(rows)
    out.attrs["base"] = base
    out.attrs["scenario"] = scenario
    return out
