"""Bottom-up stressed financials: project each obligor's P&L, cash and debt along a macro scenario,
recompute credit ratios and re-rate the obligor with the PD scorecard.

Mechanics per projection year t (annual):
  revenue growth  g = trend_s + b_gdp,s (GDP_r,t - trend_r) + b_oil,s dOil_t + b_prop,s (dProp_t - trend)
  EBITDA margin   m_t = m_{t-1} + (DOL_s - 1) x (g - trend_s) x m_0        (operating leverage)
  interest        debt_{t-1} x [fixed share x coupon + floating share x (policy rate_t + spread)]
  capex           capex ratio x revenue, cut by up to 50% when revenue under-performs trend
  tax             25% of max(0, EBITDA - interest - D&A), D&A = 60% of capex
  free cash flow  EBITDA - interest - capex - tax
  cash / debt     FCF accrues to cash; excess over the target cash balance is distributed; any
                  shortfall below a 2%-of-revenue minimum is funded by drawing additional debt
  liquidity       current ratio moves with the cash balance relative to its target
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from cibst.data.macro import Scenario
from cibst.models.features import credit_ratios, interest_expense

MIN_CASH_TO_REVENUE = 0.02
OTHER_CURRENT_ASSETS_TO_REVENUE = 0.20
TAX_RATE = 0.25


def project_financials(obl: pd.DataFrame, sectors: pd.DataFrame, scenario: Scenario,
                       region_trend: dict, property_trend: float) -> list[pd.DataFrame]:
    """Return a list of financial states for t = 0..H (t=0 is the reporting-date position)."""
    p = sectors.loc[obl["sector"]]
    f = lambda c: p[c].to_numpy(dtype=float)  # noqa: E731
    trend, b_gdp, b_oil, b_prop = f("trend_growth"), f("beta_gdp"), f("beta_oil"), f("beta_property")
    dol, capex_ratio = f("dol"), f("capex_ratio")
    region = obl["region"].to_numpy()
    gdp_trend = pd.Series(region_trend).reindex(region).to_numpy(dtype=float)

    rev0 = obl["revenue"].to_numpy(dtype=float)
    m0 = obl["ebitda"].to_numpy(dtype=float) / rev0
    cash0_ratio = obl["cash"].to_numpy(dtype=float) / rev0
    cr0 = obl["current_ratio"].to_numpy(dtype=float)

    state0 = pd.DataFrame({
        "revenue": rev0, "ebitda": obl["ebitda"].to_numpy(dtype=float), "debt": obl["debt"].to_numpy(dtype=float),
        "cash": obl["cash"].to_numpy(dtype=float), "interest_expense": obl["interest_expense"].to_numpy(dtype=float),
        "current_ratio": cr0, "revenue_growth": 0.0, "fcf": np.nan,
    })
    states = [state0]
    rev, margin, debt, cash = rev0.copy(), m0.copy(), state0["debt"].to_numpy().copy(), state0["cash"].to_numpy().copy()

    for t in scenario.paths.index:
        path = scenario.paths.loc[t]
        gdp = scenario.regional_gdp.loc[t].reindex(region).to_numpy(dtype=float)
        g = (trend + b_gdp * (gdp - gdp_trend) / 100 + b_oil * path["oil_price_change"]
             + b_prop * (path["property_price_growth"] - property_trend) / 100)
        g = np.maximum(g, -0.60)
        shock = g - trend
        rev = rev * (1 + g)
        margin = margin + (dol - 1) * shock * np.abs(m0)
        margin = np.clip(margin, -0.5 * np.abs(m0), np.maximum(1.5 * m0, m0 + 0.05))
        ebitda = margin * rev
        interest = interest_expense(debt, obl["floating_share"], obl["fixed_coupon"], obl["floating_spread"],
                                    path["policy_rate"])
        capex = capex_ratio * rev * np.clip(1 + 2.5 * np.minimum(shock, 0), 0.5, 1.0)
        tax = TAX_RATE * np.maximum(0.0, ebitda - interest - 0.6 * capex)
        fcf = ebitda - interest - capex - tax

        target_cash = cash0_ratio * rev
        cash = cash + fcf
        cash = np.minimum(cash, target_cash)                    # excess distributed
        min_cash = MIN_CASH_TO_REVENUE * rev
        draw = np.maximum(min_cash - cash, 0.0)                 # liquidity shortfall funded by debt
        debt = debt + draw
        cash = cash + draw
        oca = OTHER_CURRENT_ASSETS_TO_REVENUE * rev
        cr = cr0 * (cash + oca) / (target_cash + oca)

        states.append(pd.DataFrame({
            "revenue": rev.copy(), "ebitda": ebitda, "debt": debt.copy(), "cash": cash.copy(),
            "interest_expense": interest, "current_ratio": cr, "revenue_growth": g, "fcf": fcf,
        }))
    return states


def stressed_pd_paths(obl: pd.DataFrame, sectors: pd.DataFrame, scenario: Scenario, scorecard,
                      region_trend: dict, property_trend: float) -> tuple[np.ndarray, list]:
    """PD per obligor for t = 0..H, shape (n, H+1). Defaulted obligors carry PD = 1."""
    states = project_financials(obl, sectors, scenario, region_trend, property_trend)
    sector_margin = sectors.loc[obl["sector"], "margin_mean"].to_numpy(dtype=float)
    out = np.empty((len(obl), len(states)))
    for t, s in enumerate(states):
        r = credit_ratios(s["revenue"], s["ebitda"], s["debt"], s["interest_expense"], s["current_ratio"], sector_margin)
        out[:, t] = scorecard.predict_pd(r, obl["sector"].to_numpy())
    out[obl["default_flag"].to_numpy(dtype=bool), :] = 1.0
    return out, states
