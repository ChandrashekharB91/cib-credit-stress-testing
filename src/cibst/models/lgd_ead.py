"""Facility-level LGD and EAD models, including scenario-conditioned collateral values and CCF stress."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cibst.data.macro import Scenario

RECEIVABLES_GDP_SENSITIVITY = 1.5


def collateral_index(fac: pd.DataFrame, obl_region: np.ndarray, scenario: Scenario, horizon: int,
                     region_trend: dict) -> np.ndarray:
    """Collateral value index (t=0 -> 1.0) per facility along the scenario path, shape (m, H+1)."""
    m = len(fac)
    idx = np.ones((m, horizon + 1))
    paths = scenario.paths
    ctype = fac["collateral_type"].to_numpy()
    for t in range(1, horizon + 1):
        prop = 1 + paths.at[t, "property_price_growth"] / 100
        oil = 1 + paths.at[t, "oil_price_change"]
        gdp = scenario.regional_gdp.loc[t].reindex(obl_region).to_numpy()
        trend = pd.Series(region_trend).reindex(obl_region).to_numpy(dtype=float)
        recv = np.clip(1 + RECEIVABLES_GDP_SENSITIVITY * np.minimum(gdp - trend, 0.0) / 100, 0.5, 1.0)
        step = np.select([ctype == "property", ctype == "commodity", ctype == "receivables"], [prop, oil, recv], 1.0)
        idx[:, t] = idx[:, t - 1] * step
    return idx


def ead_path(fac: pd.DataFrame, cfg: dict, scenario_name: str, horizon: int) -> np.ndarray:
    """EAD = drawn + CCF x undrawn; scenario CCF uplift applies from year 1 (utilisation rises in stress)."""
    ccf = fac["product"].map(cfg["ead"]["ccf_model"]).to_numpy(dtype=float)
    uplift = float(cfg["ead"]["ccf_stress_uplift"].get(scenario_name, 0.0))
    drawn = fac["drawn"].to_numpy(dtype=float)
    undrawn = np.maximum(fac["limit"].to_numpy(dtype=float) - drawn, 0.0)
    out = np.empty((len(fac), horizon + 1))
    out[:, 0] = drawn + ccf * undrawn
    stressed_ccf = np.where(fac["product"].to_numpy() == "term_loan", ccf, np.minimum(1.0, ccf + uplift))
    out[:, 1:] = (drawn + stressed_ccf * undrawn)[:, None]
    return out


def lgd_path(fac: pd.DataFrame, cfg: dict, coll_idx: np.ndarray, ead: np.ndarray) -> np.ndarray:
    """Best-estimate LGD = (1 - c) x base LGD + c x workout cost, c = haircut collateral cover of EAD."""
    lcfg = cfg["lgd"]
    base = np.where(fac["seniority"].to_numpy() == "subordinated", lcfg["subordinated_base"], lcfg["unsecured_base"])
    hc = fac["collateral_type"].map(lcfg["collateral_haircut"]).fillna(1.0).to_numpy(dtype=float)
    value = np.maximum(fac["collateral_value"].to_numpy(dtype=float), 0.0)[:, None] * coll_idx
    cover = np.clip(value * (1 - hc)[:, None] / np.maximum(ead, 1e-9), 0.0, 1.0)
    lgd = (1 - cover) * base[:, None] + cover * lcfg["workout_cost"]
    return np.clip(lgd, lcfg["floor"], 1.0)


def downturn_lgd(lgd0: np.ndarray, cfg: dict) -> np.ndarray:
    return np.minimum(1.0, lgd0 + cfg["lgd"]["downturn_addon"])
