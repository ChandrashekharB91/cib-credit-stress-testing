"""Corporate PD scorecard: logistic regression on transformed financial ratios with sector effects,
calibrated to the long-run default rate (through-the-cycle central tendency)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit
from scipy.stats import norm
from sklearn.linear_model import LogisticRegression

from cibst.models.features import FEATURES

EXPECTED_SIGNS = {"ln_leverage": 1, "ln_icr": -1, "margin_rel": -1, "ln_current_ratio": -1, "ln_revenue": -1}


@dataclass
class ScorecardFit:
    coefficients: pd.DataFrame
    calibration_offset: float
    long_run_default_rate: float
    dev_years: tuple[int, int]
    n_dev: int
    n_defaults_dev: int


class PDScorecard:
    def __init__(self, sectors: list[str]):
        self.sectors = sorted(sectors)
        self.base_sector = self.sectors[0]
        self.model: LogisticRegression | None = None
        self.offset = 0.0
        self.fit_info: ScorecardFit | None = None

    # design matrix: ratio features + sector dummies (base sector dropped)
    def design(self, ratios: pd.DataFrame, sector: pd.Series | np.ndarray) -> pd.DataFrame:
        X = ratios[FEATURES].reset_index(drop=True).copy()
        sec = pd.Series(np.asarray(sector)).reset_index(drop=True)
        for s in self.sectors[1:]:
            X[f"sector_{s}"] = (sec == s).astype(float)
        return X

    def fit(self, ratios: pd.DataFrame, sector, default, years, lrdr: float | None = None) -> ScorecardFit:
        X = self.design(ratios, sector)
        y = np.asarray(default, int)
        self.model = LogisticRegression(C=1e6, max_iter=5000, solver="lbfgs")
        self.model.fit(X, y)
        coefs = self._coefficient_table(X, y)
        target = float(y.mean()) if lrdr is None else float(lrdr)
        raw_logit = self.model.decision_function(X)
        self.offset = brentq(lambda c: expit(raw_logit + c).mean() - target, -5, 5)
        self.fit_info = ScorecardFit(coefs, self.offset, target, (int(np.min(years)), int(np.max(years))),
                                     len(y), int(y.sum()))
        return self.fit_info

    def _coefficient_table(self, X: pd.DataFrame, y: np.ndarray) -> pd.DataFrame:
        Xc = np.column_stack([np.ones(len(X)), X.to_numpy()])
        beta = np.concatenate([self.model.intercept_, self.model.coef_.ravel()])
        p = expit(Xc @ beta)
        W = p * (1 - p)
        cov = np.linalg.inv((Xc * W[:, None]).T @ Xc)
        se = np.sqrt(np.diag(cov))
        names = ["intercept"] + list(X.columns)
        tab = pd.DataFrame({"term": names, "coef": beta, "std_err": se})
        tab["z"] = tab["coef"] / tab["std_err"]
        tab["p_value"] = 2 * norm.sf(np.abs(tab["z"]))
        tab["expected_sign"] = tab["term"].map(EXPECTED_SIGNS)
        tab["sign_ok"] = np.where(tab["expected_sign"].isna(), np.nan,
                                  np.sign(tab["coef"]) == tab["expected_sign"])
        return tab

    def logit(self, ratios: pd.DataFrame, sector) -> np.ndarray:
        return self.model.decision_function(self.design(ratios, sector)) + self.offset

    def predict_pd(self, ratios: pd.DataFrame, sector) -> np.ndarray:
        return np.clip(expit(self.logit(ratios, sector)), 1e-5, 0.9999)

    def score(self, ratios: pd.DataFrame, sector) -> np.ndarray:
        """Points-based score (higher = safer): 600 points at 50:1 good/bad odds, 20 points to double odds."""
        return 600 - 20 / np.log(2) * (self.logit(ratios, sector) - np.log(1 / 50))
