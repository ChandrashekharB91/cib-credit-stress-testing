"""Top-down challenger: Vasicek single-factor credit-cycle index (Z) linked to macro variables.

1. Asset correlation from the variance of probit default rates:  v = Var(Phi^-1(DR_t)),  rho = v / (1 + v)
2. Implied credit-cycle index:  Z_t = [Phi^-1(PD_bar) - sqrt(1 - rho) Phi^-1(DR_t)] / sqrt(rho)
3. Satellite regression (OLS):  Z_t = a + b' X_t + e_t, driver set chosen from candidate specifications by
   a documented rule: every coefficient has the expected sign and p < 0.10; among those, the lowest
   leave-one-year-out cross-validated RMSE (robust to a single influential year such as 2020).
4. Stressed PD:  PD_i | Z = Phi( [Phi^-1(PD_i) - sqrt(rho) Z] / sqrt(1 - rho) )
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import norm, t as student_t

CANDIDATE_SPECS = [
    ["global_gdp_growth", "unemployment_change", "equity_return"],
    ["global_gdp_growth", "unemployment_change"],
    ["global_gdp_growth", "equity_return"],
    ["unemployment_change"],
    ["global_gdp_growth"],
]
EXPECTED_SIGNS = {"global_gdp_growth": 1, "unemployment_change": -1, "equity_return": 1}
P_THRESHOLD = 0.10


def _ols(X: pd.DataFrame, y: np.ndarray) -> dict:
    Xc = np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    resid = y - Xc @ beta
    n, k = Xc.shape
    s2 = resid @ resid / (n - k)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(Xc.T @ Xc)))
    tstat = beta / se
    coef = pd.DataFrame({"term": ["intercept"] + list(X.columns), "coef": beta, "std_err": se, "t": tstat,
                         "p_value": 2 * student_t.sf(np.abs(tstat), n - k)})
    coef["expected_sign"] = coef["term"].map(EXPECTED_SIGNS)
    coef["sign_ok"] = np.where(coef["expected_sign"].isna(), np.nan, np.sign(coef["coef"]) == coef["expected_sign"])
    tss = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (resid @ resid) / tss
    loo = []
    for i in range(n):
        keep = np.arange(n) != i
        b_i, *_ = np.linalg.lstsq(Xc[keep], y[keep], rcond=None)
        loo.append(y[i] - Xc[i] @ b_i)
    return {"coef": coef, "fitted": Xc @ beta, "resid": resid, "r2": r2,
            "loocv_rmse": float(np.sqrt(np.mean(np.square(loo)))),
            "adj_r2": 1 - (1 - r2) * (n - 1) / (n - k),
            "dw": float(np.sum(np.diff(resid) ** 2) / (resid @ resid))}


@dataclass
class ZFactorModel:
    rho: float = np.nan
    pd_bar: float = np.nan
    drivers: list = field(default_factory=list)
    coef: pd.DataFrame | None = None
    r2: float = np.nan
    adj_r2: float = np.nan
    durbin_watson: float = np.nan
    fitted: pd.DataFrame | None = None
    spec_comparison: pd.DataFrame | None = None
    driver_range: pd.DataFrame | None = None
    z_range: tuple = (np.nan, np.nan)

    def fit(self, default_rates: pd.Series, macro: pd.DataFrame) -> "ZFactorModel":
        dr = default_rates.clip(1e-4, 0.5)
        self.pd_bar = float(dr.mean())
        v = float(np.var(norm.ppf(dr), ddof=1))
        self.rho = v / (1 + v)
        z = (norm.ppf(self.pd_bar) - np.sqrt(1 - self.rho) * norm.ppf(dr.to_numpy())) / np.sqrt(self.rho)
        hist = macro.loc[dr.index].fillna(0.0)

        rows, fits = [], {}
        for spec in CANDIDATE_SPECS:
            f = _ols(hist[spec], z)
            drv = f["coef"].iloc[1:]
            signs = bool(drv["sign_ok"].astype(bool).all())
            passes = signs and bool((drv["p_value"] < P_THRESHOLD).all())
            rows.append({"spec": " + ".join(spec), "n_drivers": len(spec), "adj_r2": f["adj_r2"], "r2": f["r2"],
                         "loocv_rmse": f["loocv_rmse"],
                         "durbin_watson": f["dw"], "signs_ok": signs,
                         "max_p_value": float(drv["p_value"].max()), "passes_rule": passes})
            fits[" + ".join(spec)] = (spec, f)
        comp = pd.DataFrame(rows)
        eligible = comp[comp["passes_rule"]].sort_values(["loocv_rmse", "n_drivers"])
        if eligible.empty:
            raise RuntimeError("No Z-factor specification satisfies the selection rule")
        chosen = eligible.iloc[0]["spec"]
        comp["selected"] = comp["spec"] == chosen
        self.spec_comparison = comp

        self.drivers, f = fits[chosen]
        self.coef, self.r2, self.adj_r2, self.durbin_watson = f["coef"], f["r2"], f["adj_r2"], f["dw"]
        self.fitted = pd.DataFrame({"observed_dr": dr.to_numpy(), "implied_z": z, "fitted_z": f["fitted"],
                                    "fitted_dr": [self.conditional_dr(x) for x in f["fitted"]]}, index=dr.index)
        self.driver_range = hist[self.drivers].agg(["min", "max"]).T
        self.z_range = (float(z.min()), float(z.max()))
        return self

    def predict_z(self, paths: pd.DataFrame) -> np.ndarray:
        X = paths[self.drivers].to_numpy(dtype=float)
        return self.coef["coef"].iloc[0] + X @ self.coef["coef"].iloc[1:].to_numpy()

    def out_of_range(self, paths: pd.DataFrame) -> list[str]:
        """Drivers whose scenario values fall outside the historical calibration range."""
        flags = []
        for d in self.drivers:
            lo, hi = self.driver_range.loc[d, "min"], self.driver_range.loc[d, "max"]
            if (paths[d] < lo).any() or (paths[d] > hi).any():
                flags.append(d)
        return flags

    def conditional_pd(self, pd_ttc: np.ndarray, z: float) -> np.ndarray:
        pd_ttc = np.clip(np.asarray(pd_ttc, float), 1e-6, 1 - 1e-6)
        return norm.cdf((norm.ppf(pd_ttc) - np.sqrt(self.rho) * z) / np.sqrt(1 - self.rho))

    def conditional_dr(self, z: float) -> float:
        return float(self.conditional_pd(np.array([self.pd_bar]), z)[0])
