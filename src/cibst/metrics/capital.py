"""CET1 capital projection for the stressed portfolio (illustrative bank balance sheet).

  impairment_t   = ECL_t - ECL_{t-1}                      (static balance sheet, no write-offs)
  profit_t       = (PPNR - impairment_t) x (1 - tax)        (tax losses assumed recoverable)
  EL shortfall_t = max(0, regulatory EL_t - ECL_t)          (IRB shortfall deducted from CET1)
  CET1_t         = CET1_0 + sum_{y<=t} profit_y - (shortfall_t - shortfall_0)
  CET1 ratio_t   = CET1_t / (portfolio RWA_t + other RWA)   (other RWA held flat; no distributions)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def capital_projection(rwa: np.ndarray, ecl: np.ndarray, el_reg: np.ndarray, ead0: float,
                       other_rwa: float, cfg: dict) -> pd.DataFrame:
    c = cfg["capital"]
    h1 = len(rwa)
    total_rwa = rwa + other_rwa
    cet1_0 = c["starting_cet1_ratio"] * total_rwa[0]
    ppnr = c["ppnr_bps_of_ead"] / 1e4 * ead0
    impairment = np.concatenate([[0.0], np.diff(ecl)])
    profit = np.where(np.arange(h1) == 0, 0.0, (ppnr - impairment) * (1 - c["tax_rate"]))
    shortfall = np.maximum(el_reg - ecl, 0.0)
    cet1 = cet1_0 + np.cumsum(profit) - (shortfall - shortfall[0])
    return pd.DataFrame({
        "t": np.arange(h1),
        "ppnr": np.where(np.arange(h1) == 0, 0.0, ppnr),
        "impairment": impairment,
        "after_tax_profit": profit,
        "el_shortfall": shortfall,
        "portfolio_rwa": rwa,
        "total_rwa": total_rwa,
        "cet1_capital": cet1,
        "cet1_ratio": cet1 / total_rwa,
    })
