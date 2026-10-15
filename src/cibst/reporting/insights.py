"""Headline metrics and analytical views shared by the dashboard, committee pack and Excel workbook."""
from __future__ import annotations

import numpy as np
import pandas as pd

from cibst.models.master_scale import DEFAULT_GRADE

BANDS = ["Investment grade (CG01-05)", "Sub-IG (CG06-10)", "Watch (CG11-13)", "Default"]


def band_of(grade: np.ndarray) -> np.ndarray:
    g = np.asarray(grade, int)
    return np.select([g <= 5, g <= 10, g < DEFAULT_GRADE], BANDS[:3], BANDS[3])


def scenario_kpis(arts) -> pd.DataFrame:
    hurdle = arts.cfg["capital"]["hurdle_cet1_ratio"]
    rows = []
    for name, r in arts.results.items():
        s = r.summary
        rows.append({
            "scenario": name,
            "ecl_t0": s["ecl"].iloc[0],
            "ecl_peak": s["ecl"].max(),
            "cum_impairment": s["cum_impairment"].iloc[-1],
            "cum_loss_rate": s["cum_loss_rate"].iloc[-1],
            "stage2_peak": s["stage2_share"].max(),
            "rwa_t0": s["rwa"].iloc[0],
            "rwa_peak": s["rwa"].max(),
            "rwa_uplift": s["rwa"].max() / s["rwa"].iloc[0] - 1,
            "cet1_start": s["cet1_ratio"].iloc[0],
            "cet1_trough": s["cet1_ratio"].min(),
            "cet1_drawdown_bps": (s["cet1_ratio"].min() - s["cet1_ratio"].iloc[0]) * 1e4,
            "trough_year": int(s.loc[s["cet1_ratio"].idxmin(), "t"]),
            "headroom_bps": (s["cet1_ratio"].min() - hurdle) * 1e4,
        })
    return pd.DataFrame(rows)


def portfolio_snapshot(arts) -> dict:
    r0 = next(iter(arts.results.values()))
    s = r0.summary.iloc[0]
    eng = arts.engine
    return {
        "as_of": arts.cfg["run"]["as_of_date"],
        "obligors": int(eng.obl.shape[0]),
        "facilities": int(eng.fac.shape[0]),
        "limits": float(eng.fac["limit"].sum()),
        "drawn": float(eng.fac["drawn"].sum()),
        "ead": float(s["ead"]),
        "rwa": float(s["rwa"]),
        "rw_density": float(s["rw_density"]),
        "weighted_ecl": float(arts.weighted_ecl0),
        "weighted_coverage": float(arts.weighted_ecl0 / s["ead"]),
        "stage2_share": float(s["stage2_share"]),
        "stage3_share": float(s["stage3_share"]),
        "pd_wavg": float(s["pd_wavg"]),
        "firb_share": float(eng.fac.assign(a=eng.rwa_static.approach)
                            .pipe(lambda d: d.loc[d["a"] == "F-IRB", "limit"].sum() / d["limit"].sum())),
    }


def sector_contribution(arts, scenario: str = "severe") -> pd.DataFrame:
    g = arts.results[scenario].by_sector
    t_last = g["t"].max()
    e0 = g[g["t"] == 0].set_index("sector")
    eL = g[g["t"] == t_last].set_index("sector")
    out = pd.DataFrame({
        "ead_t0": e0["ead"],
        "cum_impairment": eL["impairment_cum"],
        "impairment_rate": eL["impairment_cum"] / e0["ead"],
        "rwa_t0": e0["rwa"],
        "rwa_peak": g.groupby("sector")["rwa"].max(),
        "stage2_share_peak": g.groupby("sector")["stage2_share"].max(),
    })
    out["share_of_impairment"] = out["cum_impairment"] / out["cum_impairment"].sum()
    out["rwa_uplift"] = out["rwa_peak"] / out["rwa_t0"] - 1
    return out.sort_values("cum_impairment", ascending=False).reset_index()


def region_contribution(arts, scenario: str = "severe") -> pd.DataFrame:
    g = arts.results[scenario].by_region
    t_last = g["t"].max()
    e0 = g[g["t"] == 0].set_index("region")
    eL = g[g["t"] == t_last].set_index("region")
    out = pd.DataFrame({"ead_t0": e0["ead"], "cum_impairment": eL["impairment_cum"],
                        "impairment_rate": eL["impairment_cum"] / e0["ead"]})
    names = {k: v["name"] for k, v in arts.cfg["_sectors"]["regions"].items()}
    out.index = [names.get(i, i) for i in out.index]
    return out.sort_values("cum_impairment", ascending=False).reset_index(names="region")


def top_obligors(arts, scenario: str = "severe", n: int = 10) -> pd.DataFrame:
    f = arts.results[scenario].facility
    t_last = f["t"].max()
    a = f[f["t"] == 0].groupby("obligor_id").agg(sector=("sector", "first"), region=("region", "first"),
                                                 ead_t0=("ead", "sum"), ecl_t0=("ecl", "sum"))
    b = f[f["t"] == t_last].groupby("obligor_id")["ecl"].sum().rename("ecl_end")
    out = a.join(b)
    out["impairment"] = out["ecl_end"] - out["ecl_t0"]
    r = arts.results[scenario]
    pos = pd.Series(range(len(arts.engine.obl)), index=arts.engine.obl["obligor_id"])
    out["pd_t0"] = r.obligor_pd[pos.loc[out.index].to_numpy(), 0]
    out["pd_peak"] = r.obligor_pd[pos.loc[out.index].to_numpy(), 1:].max(axis=1)
    return out.sort_values("impairment", ascending=False).head(n).reset_index()


def migration_matrix(arts, scenario: str = "severe") -> pd.DataFrame:
    r = arts.results[scenario]
    eng = arts.engine
    ead0 = r.facility[r.facility["t"] == 0].groupby("obligor_id")["ead"].sum().reindex(eng.obl["obligor_id"]).fillna(0)
    b0 = band_of(r.obligor_grade[:, 0])
    bH = band_of(r.obligor_grade[:, -1])
    m = pd.crosstab(pd.Categorical(b0, BANDS), pd.Categorical(bH, BANDS), values=ead0.to_numpy(), aggfunc="sum",
                    dropna=False).fillna(0.0)
    m = m.div(m.sum(axis=1).replace(0, np.nan), axis=0)
    m.index.name, m.columns.name = "rating at reporting date", f"rating at year {r.obligor_grade.shape[1] - 1}"
    return m


def fmt_bn(x: float) -> str:
    return f"${x / 1000:,.1f}bn"


def fmt_m(x: float) -> str:
    return f"${x:,.0f}m"
