"""Stress-test engine: runs one scenario end to end (stressed financials -> PD/LGD/EAD -> ECL, RWA, capital)
and the top-down Z-factor challenger, returning portfolio, sector, region and facility-level results."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cibst.data.macro import Scenario, ScenarioSet
from cibst.metrics.capital import capital_projection
from cibst.metrics.ecl import ECLInputs, compute_ecl
from cibst.metrics.rwa import build_rwa_static, rwa_at_t
from cibst.models.lgd_ead import collateral_index, downturn_lgd, ead_path, lgd_path
from cibst.models.master_scale import grade_central_pd, pd_to_grade_num
from cibst.models.stressed_financials import stressed_pd_paths


@dataclass
class Shocks:
    """Sensitivity shocks layered on top of a scenario (applied to projection years only)."""
    pd_mult: float = 1.0
    lgd_add: float = 0.0
    ccf_add: float = 0.0
    gdp_add: float = 0.0       # percentage points, every region and year
    oil_mult: float = 1.0
    rate_add: float = 0.0      # percentage points

    def is_null(self) -> bool:
        return self == Shocks()


@dataclass
class ScenarioResult:
    name: str
    summary: pd.DataFrame
    capital: pd.DataFrame
    by_sector: pd.DataFrame
    by_region: pd.DataFrame
    facility: pd.DataFrame
    obligor_pd: np.ndarray
    obligor_grade: np.ndarray
    topdown: pd.DataFrame
    financials: list = field(default_factory=list)


def apply_macro_shocks(sc: Scenario, sh: Shocks) -> Scenario:
    out = copy.deepcopy(sc)
    out.regional_gdp = out.regional_gdp + sh.gdp_add
    out.paths["global_gdp_growth"] += sh.gdp_add
    out.paths["policy_rate"] += sh.rate_add
    if sh.oil_mult != 1.0:
        jump = sc.paths["oil_price"].iloc[0] / (1 + sc.paths["oil_price_change"].iloc[0])
        out.paths["oil_price"] = out.paths["oil_price"] * sh.oil_mult
        prev = np.concatenate([[jump], out.paths["oil_price"].to_numpy()[:-1]])
        out.paths["oil_price_change"] = out.paths["oil_price"].to_numpy() / prev - 1
    return out


class StressTestEngine:
    def __init__(self, cfg: dict, obligors: pd.DataFrame, facilities: pd.DataFrame, scorecard, zmodel,
                 scenarios: ScenarioSet):
        self.cfg = cfg
        self.obl = obligors.reset_index(drop=True)
        self.fac = facilities.reset_index(drop=True)
        self.scorecard = scorecard
        self.zmodel = zmodel
        self.scenarios = scenarios
        self.H = scenarios.horizon
        self.sectors = pd.DataFrame(cfg["_sectors"]["sectors"]).T
        self.region_trend = {k: v["trend_gdp"] for k, v in cfg["_sectors"]["regions"].items()}
        self.property_trend = float(cfg["_sectors"]["property_trend_growth"])
        pos = pd.Series(np.arange(len(self.obl)), index=self.obl["obligor_id"])
        self.pos = pos.loc[self.fac["obligor_id"]].to_numpy()
        self.fac_sector = self.obl["sector"].to_numpy()[self.pos]
        self.fac_region = self.obl["region"].to_numpy()[self.pos]
        self.defaulted_fac = self.obl["default_flag"].to_numpy(dtype=bool)[self.pos]
        self.dpd_fac = self.obl["days_past_due"].to_numpy(dtype=float)[self.pos]
        self.rwa_static = build_rwa_static(self.fac, self.obl, cfg)
        drawn = self.fac["drawn"].to_numpy(dtype=float)
        self.undrawn = np.maximum(self.fac["limit"].to_numpy(dtype=float) - drawn, 0.0)
        self._other_rwa: float | None = None

    # ------------------------------------------------------------------ main
    def run_scenario(self, name: str, shocks: Shocks | None = None) -> ScenarioResult:
        sh = shocks or Shocks()
        sc = self.scenarios.scenarios[name]
        if not sh.is_null():
            sc = apply_macro_shocks(sc, sh)
        H = self.H
        defaulted_obl = self.obl["default_flag"].to_numpy(dtype=bool)

        pd_obl, states = stressed_pd_paths(self.obl, self.sectors, sc, self.scorecard,
                                           self.region_trend, self.property_trend)
        if "pd_overlay_mult" in self.obl:   # post-model adjustments raised by the DQ engine
            mult = self.obl["pd_overlay_mult"].to_numpy(dtype=float)
            pd_obl[~defaulted_obl] = np.clip(pd_obl[~defaulted_obl] * mult[~defaulted_obl, None], 1e-5, 0.9999)
        if sh.pd_mult != 1.0:
            pd_obl[~defaulted_obl, 1:] = np.clip(pd_obl[~defaulted_obl, 1:] * sh.pd_mult, 1e-5, 0.9999)
        grade_obl = np.column_stack([pd_to_grade_num(pd_obl[:, t], defaulted_obl) for t in range(H + 1)])
        pd_fac, grade_fac = pd_obl[self.pos], grade_obl[self.pos]

        coll = collateral_index(self.fac, self.fac_region, sc, H, self.region_trend)
        ead = ead_path(self.fac, self.cfg, name, H)
        if sh.ccf_add:
            ead[:, 1:] += np.where(self.fac["product"].to_numpy() == "term_loan", 0.0, sh.ccf_add)[:, None] * \
                self.undrawn[:, None]
            ead = np.minimum(ead, (self.fac["drawn"].to_numpy() + self.undrawn)[:, None])
        lgd = lgd_path(self.fac, self.cfg, coll, ead)
        if sh.lgd_add:
            lgd[:, 1:] = np.clip(lgd[:, 1:] + sh.lgd_add, 0.0, 1.0)
        lgd_dt = np.clip(downturn_lgd(lgd[:, 0], self.cfg) + sh.lgd_add, 0.0, 1.0)

        ecl = compute_ecl(ECLInputs(
            pd_path=pd_fac, lgd=lgd, ead=ead, maturity=self.fac["maturity_years"].to_numpy(dtype=float),
            eir=self.fac["eir"].to_numpy(dtype=float), origination_pd=self.fac["origination_pd"].to_numpy(dtype=float),
            grade_path=grade_fac, dpd=self.dpd_fac, defaulted=self.defaulted_fac), self.cfg)

        rwa_parts = [rwa_at_t(self.rwa_static, grade_central_pd(grade_fac[:, t]), lgd[:, t], lgd_dt, ead[:, t],
                              coll[:, t], ecl["survival"][:, t], self.cfg) for t in range(H + 1)]
        rwa = np.column_stack([p["rwa"] for p in rwa_parts])
        el_reg = np.column_stack([p["el_reg"] for p in rwa_parts])
        ead_reg = np.column_stack([p["ead_reg"] for p in rwa_parts])

        facility = self._facility_frame(name, pd_fac, grade_fac, ead, lgd, ecl, rwa, ead_reg, el_reg, rwa_parts)
        summary = self._summary(facility)
        if self._other_rwa is None:
            self._other_rwa = self.cfg["capital"]["other_rwa_multiple"] * summary.loc[0, "rwa"]
        capital = capital_projection(summary["rwa"].to_numpy(), summary["ecl"].to_numpy(),
                                     summary["el_reg"].to_numpy(), summary.loc[0, "ead"], self._other_rwa, self.cfg)
        summary = summary.merge(capital[["t", "impairment", "cet1_ratio"]], on="t")
        summary["cum_impairment"] = summary["impairment"].cumsum()
        summary["cum_loss_rate"] = summary["cum_impairment"] / summary.loc[0, "ead"]

        return ScenarioResult(
            name=name, summary=summary, capital=capital,
            by_sector=self._group(facility, "sector"), by_region=self._group(facility, "region"),
            facility=facility, obligor_pd=pd_obl, obligor_grade=grade_obl,
            topdown=self._topdown(sc, pd_obl, summary, facility), financials=states,
        )

    # ------------------------------------------------------------------ helpers
    def _facility_frame(self, name, pd_fac, grade_fac, ead, lgd, ecl, rwa, ead_reg, el_reg, parts) -> pd.DataFrame:
        m, h1 = pd_fac.shape
        base = pd.DataFrame({
            "facility_id": self.fac["facility_id"], "obligor_id": self.fac["obligor_id"],
            "sector": self.fac_sector, "region": self.fac_region, "product": self.fac["product"],
            "approach": self.rwa_static.approach, "defaulted_t0": self.defaulted_fac,
        })
        frames = []
        for t in range(h1):
            f = base.copy()
            f["scenario"], f["t"] = name, t
            f["pd"], f["grade"] = pd_fac[:, t], grade_fac[:, t]
            f["pd12"] = ecl["pd12"][:, t]
            f["ead"], f["lgd"] = ead[:, t], lgd[:, t]
            f["survival"], f["stage2"] = ecl["survival"][:, t], ecl["stage2"][:, t].astype(bool)
            for k in ["ecl", "ecl_s1", "ecl_s2", "ecl_s3", "ead_s1", "ead_s2", "ead_s3", "el12", "ellife"]:
                f[k] = ecl[k][:, t]
            f["ead_reg"], f["lgd_reg"], f["pd_reg"] = ead_reg[:, t], parts[t]["lgd_reg"], parts[t]["pd_reg"]
            f["rwa"], f["el_reg"] = rwa[:, t], el_reg[:, t]
            frames.append(f)
        return pd.concat(frames, ignore_index=True)

    @staticmethod
    def _agg(df: pd.DataFrame) -> pd.Series:
        ead = df["ead_s1"] + df["ead_s2"] + df["ead_s3"]
        perf_w = df["ead"] * df["survival"]
        return pd.Series({
            "ead": ead.sum(), "ecl": df["ecl"].sum(),
            "ecl_s1": df["ecl_s1"].sum(), "ecl_s2": df["ecl_s2"].sum(), "ecl_s3": df["ecl_s3"].sum(),
            "ead_s1": df["ead_s1"].sum(), "ead_s2": df["ead_s2"].sum(), "ead_s3": df["ead_s3"].sum(),
            "pd_wavg": np.average(df["pd"], weights=perf_w) if perf_w.sum() > 0 else np.nan,
            "pd12_fwd_wavg": np.average(df["pd12"], weights=perf_w) if perf_w.sum() > 0 else np.nan,
            "lgd_wavg": np.average(df["lgd"], weights=df["ead"]) if df["ead"].sum() > 0 else np.nan,
            "rwa": df["rwa"].sum(), "ead_reg": df["ead_reg"].sum(), "el_reg": df["el_reg"].sum(),
        })

    def _summary(self, fac: pd.DataFrame) -> pd.DataFrame:
        s = fac.groupby("t").apply(self._agg, include_groups=False).reset_index()
        s["coverage"] = s["ecl"] / s["ead"]
        s["stage2_share"] = s["ead_s2"] / s["ead"]
        s["stage3_share"] = s["ead_s3"] / s["ead"]
        s["rw_density"] = s["rwa"] / s["ead_reg"]
        return s

    def _group(self, fac: pd.DataFrame, key: str) -> pd.DataFrame:
        g = fac.groupby([key, "t"]).apply(self._agg, include_groups=False).reset_index()
        g["coverage"] = g["ecl"] / g["ead"]
        g["stage2_share"] = g["ead_s2"] / g["ead"]
        base_ecl = g[g["t"] == 0].set_index(key)["ecl"]
        g["impairment_cum"] = g["ecl"] - g[key].map(base_ecl)
        return g

    def _topdown(self, sc: Scenario, pd_obl: np.ndarray, summary: pd.DataFrame, fac: pd.DataFrame) -> pd.DataFrame:
        perf = self.obl["default_flag"].to_numpy() == 0
        ead0 = fac[fac["t"] == 0].groupby("obligor_id")["ead"].sum().reindex(self.obl["obligor_id"]).fillna(0).to_numpy()
        w = ead0[perf]
        z = self.zmodel.predict_z(sc.paths)
        z_capped = np.clip(z, *self.zmodel.z_range)   # challenger not allowed beyond the worst/best observed year
        rows = []
        for t in range(1, self.H + 1):
            td = self.zmodel.conditional_pd(pd_obl[perf, 0], z[t - 1])
            tdc = self.zmodel.conditional_pd(pd_obl[perf, 0], z_capped[t - 1])
            rows.append({"t": t, "z": z[t - 1], "z_capped": z_capped[t - 1],
                         "pd_bottom_up": float(np.average(pd_obl[perf, t], weights=w)),
                         "pd_top_down": float(np.average(td, weights=w)),
                         "pd_top_down_capped": float(np.average(tdc, weights=w))})
        out = pd.DataFrame(rows)
        out["bu_td_ratio"] = out["pd_bottom_up"] / out["pd_top_down"]
        out["cum_pd_bottom_up"] = 1 - (1 - out["pd_bottom_up"]).cumprod()
        out["cum_pd_top_down"] = 1 - (1 - out["pd_top_down"]).cumprod()
        out["cum_bu_td_ratio"] = out["cum_pd_bottom_up"] / out["cum_pd_top_down"]
        out["cum_pd_top_down_capped"] = 1 - (1 - out["pd_top_down_capped"]).cumprod()
        out["cum_bu_td_ratio_capped"] = out["cum_pd_bottom_up"] / out["cum_pd_top_down_capped"]
        out["z_outside_history"] = (out["z"] < self.zmodel.z_range[0]) | (out["z"] > self.zmodel.z_range[1])
        return out
