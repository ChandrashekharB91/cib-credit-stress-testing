"""Financial-ratio features shared by the data generator, PD scorecard and stressed-financials model."""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["ln_leverage", "ln_icr", "margin_rel", "ln_current_ratio", "ln_revenue"]
LEVERAGE_CAP = 25.0
ICR_FLOOR, ICR_CAP = 0.1, 50.0


def credit_ratios(revenue, ebitda, debt, interest, current_ratio, sector_margin) -> pd.DataFrame:
    """Transformed ratios used by the PD scorecard.

    ln_leverage      log(gross debt / EBITDA), capped at 25x; EBITDA <= 0 maps to the cap
    ln_icr           log(EBITDA / interest), bounded to [0.1, 50]
    margin_rel       EBITDA margin relative to the sector norm (margin / sector mean - 1)
    ln_current_ratio log(current assets / current liabilities)
    ln_revenue       log(revenue, USD m) — size
    """
    revenue = np.asarray(revenue, float)
    ebitda = np.asarray(ebitda, float)
    debt = np.asarray(debt, float)
    interest = np.asarray(interest, float)
    pos = ebitda > 0
    lev = np.where(pos, debt / np.where(pos, ebitda, 1.0), LEVERAGE_CAP)
    lev = np.clip(lev, 0.05, LEVERAGE_CAP)
    icr = np.where(pos, ebitda / np.maximum(interest, 1e-9), ICR_FLOOR)
    icr = np.clip(icr, ICR_FLOOR, ICR_CAP)
    margin = ebitda / np.maximum(revenue, 1e-9)
    return pd.DataFrame(
        {
            "ln_leverage": np.log(lev),
            "ln_icr": np.log(icr),
            "margin_rel": np.clip(margin / np.asarray(sector_margin, float) - 1.0, -3.0, 2.0),
            "ln_current_ratio": np.log(np.clip(np.asarray(current_ratio, float), 0.1, 10.0)),
            "ln_revenue": np.log(np.maximum(revenue, 1.0)),
        }
    )


def interest_expense(debt, floating_share, fixed_coupon, floating_spread, policy_rate_pct):
    r = np.asarray(policy_rate_pct, float) / 100.0
    fs = np.asarray(floating_share, float)
    return np.asarray(debt, float) * (
        (1 - fs) * np.asarray(fixed_coupon, float) + fs * (r + np.asarray(floating_spread, float))
    )
