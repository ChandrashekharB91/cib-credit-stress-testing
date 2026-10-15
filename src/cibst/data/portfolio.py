"""Synthetic Corporate & Institutional Banking (CIB) portfolio and default-history generator.

All data are synthetic and seeded. The generator embeds a known "true" credit model so that
the PD scorecard, satellite models and monitoring tests can be checked against ground truth:

* obligor financials are drawn by sector (revenue, EBITDA margin, leverage, liquidity, rates);
* the true through-the-cycle log-odds of default is a function of transformed ratios plus an
  unobserved idiosyncratic term (management quality, governance) that no model can see;
* in the 20-year default history, margins co-move with GDP and an additional systematic
  factor Z_t drives defaults through a one-factor Vasicek mechanism.

The generator also seeds realistic data-quality defects so that the DQ engine has work to do.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.special import expit
from scipy.stats import norm

from cibst.data.macro import GDP_REFERENCE
from cibst.models.features import FEATURES, credit_ratios, interest_expense

TRUE_COEF = {
    "ln_leverage": 1.00,
    "ln_icr": -0.80,
    "margin_rel": -1.20,
    "ln_current_ratio": -0.60,
    "ln_revenue": -0.12,
}
REVENUE_CENTRE = 6.0
UNOBSERVED_SD = 0.50
TARGET_TTC_PD = 0.02
CYCLE_MARGIN_SENSITIVITY = 0.06
GDP_SCALE = 2.0

INDUSTRY_CODES = {
    "oil_gas": "B06", "metals_mining": "B07", "commercial_real_estate": "L68",
    "manufacturing": "C25", "consumer_retail": "G47", "tmt": "J61",
    "utilities_infra": "D35", "financial_institutions": "K64",
    "shipping_transport": "H50", "commodity_traders": "G46",
}

PRODUCT_MIX = {
    "commodity_traders": {"trade_finance": 0.50, "rcf": 0.30, "term_loan": 0.15, "guarantee": 0.05},
    "financial_institutions": {"trade_finance": 0.30, "rcf": 0.30, "term_loan": 0.30, "guarantee": 0.10},
    "_default": {"term_loan": 0.45, "rcf": 0.30, "trade_finance": 0.15, "guarantee": 0.10},
}
SECURED_PROB = {"commercial_real_estate": 0.90, "tmt": 0.20, "utilities_infra": 0.20, "_default": 0.45}
MATURITY_RANGE = {"term_loan": (1.0, 7.0), "rcf": (0.5, 5.0), "trade_finance": (0.1, 1.0), "guarantee": (0.5, 3.0)}
UTILISATION = {"term_loan": (1.0, 1.0), "rcf": (0.10, 0.70), "trade_finance": (0.30, 0.90), "guarantee": (0.0, 0.0)}


@dataclass
class GeneratedData:
    obligors: pd.DataFrame
    facilities: pd.DataFrame
    ledger: pd.DataFrame
    history: pd.DataFrame
    systematic_factor: pd.Series
    injected_issues: dict = field(default_factory=dict)


class PortfolioGenerator:
    def __init__(self, cfg: dict, macro_history: pd.DataFrame, jump_off: dict):
        self.cfg = cfg
        self.pcfg = cfg["portfolio"]
        self.sectors = pd.DataFrame(cfg["_sectors"]["sectors"]).T
        self.sectors["share"] = self.sectors["share"].astype(float)
        self.sectors["share"] /= self.sectors["share"].sum()
        self.regions = pd.DataFrame(cfg["_sectors"]["regions"]).T
        self.regions["share"] = self.regions["share"].astype(float)
        self.regions["share"] /= self.regions["share"].sum()
        self.hist = macro_history
        self.jump_off = jump_off
        self.rho = float(cfg["pd_model"]["asset_correlation_generator"])
        self.rng = np.random.default_rng(int(cfg["run"]["seed"]))
        self.intercept = self._calibrate_intercept()

    # ------------------------------------------------------------------ financials
    def _draw_financials(self, n: int, rng: np.random.Generator, policy_rate: float, gdp: float) -> pd.DataFrame:
        sec = rng.choice(self.sectors.index.to_numpy(), size=n, p=self.sectors["share"].to_numpy())
        reg = rng.choice(self.regions.index.to_numpy(), size=n, p=self.regions["share"].to_numpy())
        p = self.sectors.loc[sec]
        f = lambda c: p[c].to_numpy(dtype=float)  # noqa: E731

        revenue = f("rev_median_musd") * np.exp(f("rev_sigma") * rng.standard_normal(n))
        base_margin = np.clip(f("margin_mean") + f("margin_sd") * rng.standard_normal(n), 0.005, 0.85)
        leverage0 = f("leverage_median") * np.exp(0.45 * rng.standard_normal(n))
        debt = leverage0 * revenue * base_margin
        d = (gdp - GDP_REFERENCE) / GDP_SCALE
        margin = base_margin * (1.0 + CYCLE_MARGIN_SENSITIVITY * f("cyclicality") * d)
        ebitda = revenue * margin

        floating_share = np.clip(f("floating_share") + rng.uniform(-0.1, 0.1, n), 0.0, 1.0)
        fixed_coupon = rng.uniform(0.040, 0.065, n)
        floating_spread = rng.uniform(0.015, 0.035, n)
        interest = interest_expense(debt, floating_share, fixed_coupon, floating_spread, policy_rate)
        is_fi = sec == "financial_institutions"
        total_assets = np.where(is_fi, revenue * rng.uniform(15, 40, n), debt / rng.uniform(0.25, 0.55, n))

        return pd.DataFrame(
            {
                "sector": sec,
                "region": reg,
                "revenue": revenue,
                "ebitda": ebitda,
                "debt": debt,
                "cash": debt * rng.uniform(0.05, 0.30, n),
                "current_ratio": np.exp(np.log(1.35) + 0.30 * rng.standard_normal(n)),
                "total_assets": total_assets,
                "floating_share": floating_share,
                "fixed_coupon": fixed_coupon,
                "floating_spread": floating_spread,
                "interest_expense": interest,
                "sector_margin": f("margin_mean"),
                "unobserved": UNOBSERVED_SD * rng.standard_normal(n),
            }
        )

    def ratios(self, df: pd.DataFrame) -> pd.DataFrame:
        return credit_ratios(df["revenue"], df["ebitda"], df["debt"], df["interest_expense"],
                             df["current_ratio"], df["sector_margin"])

    def _structural_logit(self, df: pd.DataFrame) -> np.ndarray:
        r = self.ratios(df)
        x = sum(TRUE_COEF[k] * (r[k].to_numpy() - (REVENUE_CENTRE if k == "ln_revenue" else 0.0)) for k in FEATURES)
        prem = self.sectors.loc[df["sector"], "risk_premium"].to_numpy(dtype=float)
        return x + prem + df["unobserved"].to_numpy()

    def true_pd(self, df: pd.DataFrame) -> np.ndarray:
        return expit(self.intercept + self._structural_logit(df))

    def _calibrate_intercept(self) -> float:
        ref_rng = np.random.default_rng(12345)
        ref = self._draw_financials(60_000, ref_rng, policy_rate=2.5, gdp=GDP_REFERENCE)
        s = self._structural_logit(ref)
        return brentq(lambda c: expit(c + s).mean() - TARGET_TTC_PD, -15, 5)

    # ------------------------------------------------------------------ history
    def generate_history(self) -> tuple[pd.DataFrame, pd.Series]:
        start, end = self.pcfg["history_start"], self.pcfg["history_end"]
        h = self.hist.loc[start:end]
        g = (h["global_gdp_growth"] - h["global_gdp_growth"].mean()) / h["global_gdp_growth"].std()
        du = h["unemployment_change"].fillna(0.0)
        u = (du - du.mean()) / du.std()
        # systematic credit-cycle factor: macro-driven component plus an unexplained shock,
        # clipped to +/-2.5 sd so that a single extreme year cannot dominate the history
        z_raw = 0.70 * g - 0.30 * u + 0.35 * self.rng.standard_normal(len(h))
        z = (z_raw - z_raw.mean()).clip(-2.5, 2.5)
        frames = []
        n = int(self.pcfg["history_obligors_per_year"])
        for year in h.index:
            df = self._draw_financials(n, self.rng, h.at[year, "policy_rate"], h.at[year, "global_gdp_growth"])
            pd_ttc = self.true_pd(df)
            p_cond = norm.cdf((norm.ppf(pd_ttc) - np.sqrt(self.rho) * z[year]) / np.sqrt(1 - self.rho))
            df["default"] = (self.rng.uniform(size=n) < p_cond).astype(int)
            df["true_pd"] = pd_ttc
            df["year"] = year
            frames.append(df)
        hist = pd.concat(frames, ignore_index=True)
        return hist, z.rename("Z")

    # ------------------------------------------------------------------ portfolio
    def generate_portfolio(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        rng = self.rng
        n = int(self.pcfg["n_obligors"])
        obl = self._draw_financials(n, rng, self.jump_off["policy_rate"], self.hist["global_gdp_growth"].iloc[-1])
        obl.insert(0, "obligor_id", [f"OBL{i:05d}" for i in range(1, n + 1)])
        obl["industry_code"] = obl["sector"].map(INDUSTRY_CODES)
        obl["true_pd_ttc"] = self.true_pd(obl)
        # PD the bank's rating system can observe (excludes the unobserved idiosyncratic term)
        obl["_observable_pd"] = expit(self.intercept + self._structural_logit(obl) - obl["unobserved"].to_numpy())

        k = int(round(self.pcfg["initial_default_rate"] * n))
        w = obl["true_pd_ttc"].to_numpy() / obl["true_pd_ttc"].sum()
        defaulted = rng.choice(n, size=k, replace=False, p=w)
        obl["default_flag"] = 0
        obl.loc[defaulted, "default_flag"] = 1

        u = rng.uniform(size=n)
        pdv = obl["true_pd_ttc"].to_numpy()
        dpd = np.where(u < 0.6 * pdv, rng.integers(30, 90, n), np.where(u < 0.6 * pdv + 0.03, rng.integers(1, 30, n), 0))
        dpd[defaulted] = rng.integers(90, 400, k)
        obl["days_past_due"] = dpd

        as_of = pd.Timestamp(self.cfg["run"]["as_of_date"])
        months = rng.uniform(2, 15, n)
        obl["financials_date"] = [(as_of - pd.DateOffset(days=int(m * 30.4))).date().isoformat() for m in months]
        obl = obl.drop(columns=["unobserved"])
        fac = self._generate_facilities(obl, rng)
        obl = obl.drop(columns=["_observable_pd"])

        ledger = (
            fac.merge(obl[["obligor_id", "region"]], on="obligor_id")
            .groupby("region", as_index=False)["drawn"].sum()
            .rename(columns={"drawn": "ledger_drawn"})
        )
        ledger["ledger_drawn"] *= 1 + rng.uniform(-0.001, 0.001, len(ledger))
        return obl, fac, ledger

    def _generate_facilities(self, obl: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
        n = len(obl)
        n_fac = 1 + np.minimum(rng.poisson(1.2, n), 3)
        idx = np.repeat(np.arange(n), n_fac)
        m = len(idx)
        sec = obl["sector"].to_numpy()[idx]

        product = np.empty(m, dtype=object)
        for s in np.unique(sec):
            mix = PRODUCT_MIX.get(s, PRODUCT_MIX["_default"])
            sel = sec == s
            product[sel] = rng.choice(list(mix), size=sel.sum(), p=list(mix.values()))

        share = rng.uniform(*self.pcfg["bank_share_of_debt"], n)
        bank_total = (obl["debt"].to_numpy() * share)[idx]
        wts = rng.gamma(1.0, 1.0, m)
        wsum = np.bincount(idx, weights=wts)[idx]
        limit = bank_total * wts / wsum

        util = np.array([rng.uniform(*UTILISATION[p]) for p in product])
        drawn = limit * util

        p_sec = np.array([SECURED_PROB.get(s, SECURED_PROB["_default"]) for s in sec])
        secured = rng.uniform(size=m) < p_sec
        sub = (~secured) & (rng.uniform(size=m) < 0.05)
        seniority = np.where(secured, "senior_secured", np.where(sub, "subordinated", "senior_unsecured"))
        coll_type_sector = self.sectors.loc[sec, "collateral"].to_numpy()
        coll_type = np.where(secured & (coll_type_sector != "none"), coll_type_sector,
                             np.where(secured, "receivables", "none"))
        coll_mult = np.where(coll_type == "cash", rng.uniform(0.2, 0.8, m), rng.uniform(0.6, 1.5, m))
        coll_value = np.where(coll_type != "none", limit * coll_mult, 0.0)

        mat = np.array([rng.uniform(*MATURITY_RANGE[p]) for p in product])
        # origination PD = observable PD at the reporting date adjusted for rating drift since origination
        pd0 = obl["_observable_pd"].to_numpy()[idx]
        orig_pd = np.clip(pd0 * np.exp(rng.normal(-0.10, 0.45, m)), 0.0003, 0.50)

        return pd.DataFrame(
            {
                "facility_id": [f"FAC{i:06d}" for i in range(1, m + 1)],
                "obligor_id": obl["obligor_id"].to_numpy()[idx],
                "product": product,
                "seniority": seniority,
                "collateral_type": coll_type,
                "collateral_value": coll_value,
                "limit": limit,
                "drawn": drawn,
                "maturity_years": mat,
                "eir": 0.045 + rng.uniform(0.005, 0.030, m),
                "origination_pd": orig_pd,
            }
        )

    # ------------------------------------------------------------------ DQ seeding
    def inject_dq_issues(self, obl: pd.DataFrame, fac: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        rng = np.random.default_rng(int(self.cfg["run"]["seed"]) + 7)
        obl, fac = obl.copy(), fac.copy()
        inj: dict[str, list] = {}
        perf = obl.index[obl["default_flag"] == 0].to_numpy()
        as_of = pd.Timestamp(self.cfg["run"]["as_of_date"])

        def pick(pool, frac=None, k=None):
            k = k if k is not None else max(1, int(round(frac * len(pool))))
            return rng.choice(pool, size=k, replace=False)

        i = pick(perf, 0.004); obl.loc[i, "sector"] = None; inj["DQ-001"] = obl.loc[i, "obligor_id"].tolist()
        i = pick(perf, k=2); obl.loc[i, "revenue"] = 0.0; inj["DQ-002"] = obl.loc[i, "obligor_id"].tolist()
        rest = np.setdiff1d(perf, i)
        i = pick(rest, 0.003); obl.loc[i, "ebitda"] *= 100; inj["DQ-003"] = obl.loc[i, "obligor_id"].tolist()
        i = pick(perf, 0.04)
        obl.loc[i, "financials_date"] = [
            (as_of - pd.DateOffset(days=int(mm * 30.4))).date().isoformat() for mm in rng.uniform(19, 30, len(i))
        ]
        inj["DQ-004"] = obl.loc[i, "obligor_id"].tolist()

        funded = fac.index[fac["product"] != "guarantee"].to_numpy()
        j = pick(funded, 0.006); fac.loc[j, "drawn"] = fac.loc[j, "limit"] * rng.uniform(1.05, 1.30, len(j))
        inj["DQ-005"] = fac.loc[j, "facility_id"].tolist()
        j = pick(fac.index.to_numpy(), 0.003); fac.loc[j, "maturity_years"] = rng.choice([0.0, -0.1], len(j))
        inj["DQ-006"] = fac.loc[j, "facility_id"].tolist()
        sec_idx = fac.index[fac["collateral_value"] > 0].to_numpy()
        j = pick(sec_idx, 0.003); fac.loc[j, "collateral_value"] *= -1
        inj["DQ-009"] = fac.loc[j, "facility_id"].tolist()

        orphans = fac.sample(2, random_state=int(rng.integers(1e6))).copy()
        orphans["facility_id"] = ["FAC900001", "FAC900002"]
        orphans["obligor_id"] = ["OBL99998", "OBL99999"]
        dups = fac.sample(3, random_state=int(rng.integers(1e6))).copy()
        fac = pd.concat([fac, orphans, dups], ignore_index=True)
        inj["DQ-007"] = orphans["facility_id"].tolist()
        inj["DQ-008"] = dups["facility_id"].tolist()
        return obl, fac, inj


def generate_all(cfg: dict, macro_history: pd.DataFrame, jump_off: dict) -> GeneratedData:
    gen = PortfolioGenerator(cfg, macro_history, jump_off)
    history, z = gen.generate_history()
    obl, fac, ledger = gen.generate_portfolio()
    injected: dict = {}
    if cfg["portfolio"].get("inject_dq_issues", False):
        # seed a material ledger break in one region to exercise the reconciliation control
        ledger.loc[ledger["region"] == "AME", "ledger_drawn"] *= 1.008
        obl, fac, injected = gen.inject_dq_issues(obl, fac)
        injected["DQ-010"] = ["AME"]
    return GeneratedData(obl, fac, ledger, history, z, injected)
