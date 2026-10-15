"""Basel IRB credit risk-weighted assets for corporate and institution exposures (BCBS CRE31 / Basel 3.1).

  R   = 0.12 w + 0.24 (1 - w),  w = (1 - e^{-50 PD}) / (1 - e^{-50})
        - 0.04 (1 - (S - 5) / 45)                    SME firm-size adjustment, S in [5, 50] (turnover, m)
        x 1.25                                       large regulated financial institutions (assets >= 100bn)
  b   = (0.11852 - 0.05478 ln PD)^2
  K   = [LGD N((G(PD) + sqrt(R) G(0.999)) / sqrt(1 - R)) - PD LGD] x (1 + (M - 2.5) b) / (1 - 1.5 b)
  RWA = K x 12.5 x EAD x scaling factor
Defaulted exposures: A-IRB K = max(0, downturn LGD - best-estimate LGD); F-IRB K = 0.
Approach: obligors with revenue above the large-corporate threshold are restricted to F-IRB (Basel 3.1).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

G999 = norm.ppf(0.999)


def irb_correlation(pd_: np.ndarray, sales_musd: np.ndarray | None = None, large_fi: np.ndarray | None = None,
                    sme_threshold: float = 50.0) -> np.ndarray:
    pd_ = np.asarray(pd_, float)
    w = (1 - np.exp(-50 * pd_)) / (1 - np.exp(-50))
    R = 0.12 * w + 0.24 * (1 - w)
    if sales_musd is not None:
        s = np.clip(np.asarray(sales_musd, float), 5.0, 50.0)
        R = R - np.where(np.asarray(sales_musd, float) < sme_threshold, 0.04 * (1 - (s - 5) / 45), 0.0)
    if large_fi is not None:
        R = np.where(np.asarray(large_fi, bool), R * 1.25, R)
    return R


def maturity_adjustment(pd_: np.ndarray, m: np.ndarray) -> np.ndarray:
    b = (0.11852 - 0.05478 * np.log(np.asarray(pd_, float))) ** 2
    return (1 + (np.asarray(m, float) - 2.5) * b) / (1 - 1.5 * b)


def irb_k(pd_: np.ndarray, lgd: np.ndarray, m: np.ndarray, R: np.ndarray) -> np.ndarray:
    pd_ = np.asarray(pd_, float)
    lgd = np.asarray(lgd, float)
    cond = norm.cdf((norm.ppf(pd_) + np.sqrt(R) * G999) / np.sqrt(1 - R))
    return np.maximum(lgd * cond - pd_ * lgd, 0.0) * maturity_adjustment(pd_, m)


def irb_risk_weight(pd_, lgd, m, sales_musd=None, large_fi=None) -> np.ndarray:
    R = irb_correlation(pd_, sales_musd, large_fi)
    return irb_k(pd_, lgd, m, R) * 12.5


@dataclass
class RWAStatic:
    approach: np.ndarray       # "F-IRB" / "A-IRB"
    sales: np.ndarray
    large_fi: np.ndarray
    m_eff: np.ndarray
    lgd_unsecured_firb: np.ndarray
    lgd_secured_firb: np.ndarray
    firb_haircut: np.ndarray
    airb_floor_secured: np.ndarray
    collateral_value: np.ndarray
    secured: np.ndarray
    drawn: np.ndarray
    undrawn: np.ndarray
    ccf_firb: np.ndarray


def build_rwa_static(fac: pd.DataFrame, obl: pd.DataFrame, cfg: dict) -> RWAStatic:
    r = cfg["rwa"]
    o = obl.set_index("obligor_id").loc[fac["obligor_id"]]
    approach = np.where(o["revenue"].to_numpy(dtype=float) > r["firb_revenue_threshold_musd"], "F-IRB", "A-IRB")
    is_fi = o["sector"].to_numpy() == "financial_institutions"
    large_fi = is_fi & (o["total_assets"].to_numpy(dtype=float) >= r["large_fi_assets_threshold_busd"] * 1000)
    sen = fac["seniority"].to_numpy()
    lgd_u = np.where(sen == "subordinated", r["firb_lgd_subordinated"],
                     np.where(is_fi, r["firb_lgd_senior_fi"], r["firb_lgd_senior"]))
    ctype = fac["collateral_type"].to_numpy()
    drawn = fac["drawn"].to_numpy(dtype=float)
    return RWAStatic(
        approach=approach,
        sales=o["revenue"].to_numpy(dtype=float),
        large_fi=large_fi,
        m_eff=np.clip(fac["maturity_years"].to_numpy(dtype=float), r["maturity_floor"], r["maturity_cap"]),
        lgd_unsecured_firb=lgd_u,
        lgd_secured_firb=pd.Series(ctype).map(r["firb_secured_lgd"]).fillna(lgd_u.mean()).to_numpy(dtype=float),
        firb_haircut=pd.Series(ctype).map(r["firb_collateral_haircut"]).fillna(1.0).to_numpy(dtype=float),
        airb_floor_secured=pd.Series(ctype).map(r["airb_lgd_floor_secured"]).fillna(r["airb_lgd_floor_unsecured"]).to_numpy(dtype=float),
        collateral_value=np.maximum(fac["collateral_value"].to_numpy(dtype=float), 0.0),
        secured=ctype != "none",
        drawn=drawn,
        undrawn=np.maximum(fac["limit"].to_numpy(dtype=float) - drawn, 0.0),
        ccf_firb=fac["product"].map(r["firb_ccf"]).to_numpy(dtype=float),
    )


def rwa_at_t(st: RWAStatic, pd_rating: np.ndarray, lgd_be: np.ndarray, lgd_downturn: np.ndarray,
             ead_model: np.ndarray, coll_index: np.ndarray, survival: np.ndarray, cfg: dict) -> dict[str, np.ndarray]:
    """Facility-level regulatory EAD, LGD, risk weight, RWA and regulatory expected loss at one date."""
    r = cfg["rwa"]
    firb = st.approach == "F-IRB"
    # defaulted obligors carry PD = 1 but zero performing weight; clip so the formula stays finite
    pd_reg = np.clip(pd_rating, r["pd_floor"], 0.9999)

    ead_firb = st.drawn + st.ccf_firb * st.undrawn
    ead_reg = np.where(firb, ead_firb, ead_model)

    coll = st.collateral_value * coll_index
    cover_firb = np.clip(coll * (1 - st.firb_haircut) / np.maximum(ead_reg, 1e-9), 0.0, 1.0)
    lgd_firb = (1 - cover_firb) * st.lgd_unsecured_firb + cover_firb * st.lgd_secured_firb
    cover_airb = np.where(st.secured, cover_firb, 0.0)
    floor_airb = (1 - cover_airb) * r["airb_lgd_floor_unsecured"] + cover_airb * st.airb_floor_secured
    lgd_airb = np.maximum(np.maximum(lgd_downturn, lgd_be), floor_airb)
    lgd_reg = np.where(firb, lgd_firb, lgd_airb)

    R = irb_correlation(pd_reg, st.sales, st.large_fi, r["sme_turnover_threshold_musd"])
    rw_perf = irb_k(pd_reg, lgd_reg, st.m_eff, R) * 12.5 * r["scaling_factor"]
    k_def = np.where(firb, 0.0, np.maximum(lgd_downturn - lgd_be, 0.0))
    rw_def = k_def * 12.5 * r["scaling_factor"]

    rwa = (survival * rw_perf + (1 - survival) * rw_def) * ead_reg
    el_reg = (survival * pd_reg * lgd_reg + (1 - survival) * np.where(firb, lgd_reg, lgd_be)) * ead_reg
    return {"ead_reg": ead_reg, "lgd_reg": lgd_reg, "pd_reg": pd_reg, "rw_perf": rw_perf, "rwa": rwa, "el_reg": el_reg}
