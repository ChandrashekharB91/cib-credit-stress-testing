"""Model monitoring for the PD scorecard and the top-down satellite model.

Stability       PSI on the score distribution (development vs current portfolio) and CSI per characteristic
Discrimination  Gini (= 2 AUC - 1) with bootstrap confidence intervals and KS, development vs out-of-time
Calibration     per-grade one-sided binomial and Jeffreys tests (ECB TRIM style), Hosmer-Lemeshow,
                portfolio default rate vs mean PD by year
Satellite       out-of-sample default-rate prediction error of the Z-factor model
Each metric is mapped to a RAG status using thresholds in run_config.yaml.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import beta, binom, chi2
from sklearn.metrics import roc_auc_score, roc_curve

from cibst.models.features import FEATURES
from cibst.models.master_scale import GRADES, pd_to_grade_num


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> tuple[float, pd.DataFrame]:
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    contrib = (a - e) * np.log(a / e)
    tab = pd.DataFrame({"bin": range(1, len(e) + 1), "expected_pct": e, "actual_pct": a, "psi_contribution": contrib})
    return float(contrib.sum()), tab


def gini(y: np.ndarray, score: np.ndarray) -> float:
    return 2 * roc_auc_score(y, score) - 1


def gini_ci(y, score, n_boot: int, seed: int = 0) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    y, score = np.asarray(y), np.asarray(score)
    vals = []
    for _ in range(n_boot):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        vals.append(gini(y[i], score[i]))
    return gini(y, score), float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def ks_stat(y, score) -> float:
    fpr, tpr, _ = roc_curve(y, score)
    return float(np.max(tpr - fpr))


def calibration_by_grade(pd_: np.ndarray, y: np.ndarray, alpha: float) -> pd.DataFrame:
    g = pd_to_grade_num(pd_)
    df = pd.DataFrame({"grade_num": g, "pd": pd_, "default": y})
    tab = df.groupby("grade_num").agg(n=("default", "size"), defaults=("default", "sum"), avg_pd=("pd", "mean"))
    tab["observed_dr"] = tab["defaults"] / tab["n"]
    # H0: PD is not underestimated. Small p-value -> realised defaults too high for the PD.
    tab["binomial_p"] = binom.sf(tab["defaults"] - 1, tab["n"], tab["avg_pd"])
    tab["jeffreys_p"] = beta.cdf(tab["avg_pd"], tab["defaults"] + 0.5, tab["n"] - tab["defaults"] + 0.5)
    tab["status"] = np.where(tab["jeffreys_p"] < alpha / 5, "RED", np.where(tab["jeffreys_p"] < alpha, "AMBER", "GREEN"))
    tab.index = [GRADES[i - 1] for i in tab.index]
    return tab.reset_index(names="grade")


def hosmer_lemeshow(pd_: np.ndarray, y: np.ndarray, groups: int = 10) -> tuple[float, float]:
    df = pd.DataFrame({"pd": pd_, "y": y})
    df["bucket"] = pd.qcut(df["pd"].rank(method="first"), groups, labels=False)
    g = df.groupby("bucket").agg(n=("y", "size"), d=("y", "sum"), p=("pd", "mean"))
    stat = (((g["d"] - g["n"] * g["p"]) ** 2) / (g["n"] * g["p"] * (1 - g["p"]))).sum()
    return float(stat), float(chi2.sf(stat, groups - 2))


def _rag(value: float, amber: float, red: float, higher_is_worse: bool = True) -> str:
    if not higher_is_worse:
        value, amber, red = -value, -amber, -red
    return "RED" if value >= red else ("AMBER" if value >= amber else "GREEN")


def run_monitoring(scorecard, history: pd.DataFrame, hist_ratios: pd.DataFrame, current_obl: pd.DataFrame,
                   current_ratios: pd.DataFrame, zmodel, macro_hist: pd.DataFrame, dev_end: int, cfg: dict) -> dict:
    m = cfg["monitoring"]
    dev = (history["year"] <= dev_end).to_numpy()
    oot = ~dev
    pd_hist = scorecard.predict_pd(hist_ratios, history["sector"].to_numpy())
    y = history["default"].to_numpy()

    score_dev = scorecard.score(hist_ratios[dev], history["sector"].to_numpy()[dev])
    perf = current_obl["default_flag"].to_numpy() == 0
    score_cur = scorecard.score(current_ratios[perf], current_obl["sector"].to_numpy()[perf])
    psi_val, psi_tab = psi(score_dev, score_cur)
    csi = pd.DataFrame([{"characteristic": f, "csi": psi(hist_ratios[f].to_numpy()[dev],
                                                         current_ratios[f].to_numpy()[perf])[0]} for f in FEATURES])
    csi["status"] = [_rag(v, m["psi_amber"], m["psi_red"]) for v in csi["csi"]]

    g_dev = gini_ci(y[dev], pd_hist[dev], m["bootstrap_samples"], seed=1)
    g_oot = gini_ci(y[oot], pd_hist[oot], m["bootstrap_samples"], seed=2)
    rel_drop = (g_dev[0] - g_oot[0]) / g_dev[0]
    disc = pd.DataFrame([
        {"sample": "development", "gini": g_dev[0], "ci_low": g_dev[1], "ci_high": g_dev[2], "ks": ks_stat(y[dev], pd_hist[dev]),
         "n": int(dev.sum()), "defaults": int(y[dev].sum())},
        {"sample": "out_of_time", "gini": g_oot[0], "ci_low": g_oot[1], "ci_high": g_oot[2], "ks": ks_stat(y[oot], pd_hist[oot]),
         "n": int(oot.sum()), "defaults": int(y[oot].sum())},
    ])

    calib = calibration_by_grade(pd_hist[oot], y[oot], m["calibration_alpha"])
    hl_stat, hl_p = hosmer_lemeshow(pd_hist[oot], y[oot])
    yearly = pd.DataFrame({"year": history["year"], "pd": pd_hist, "default": y}).groupby("year").agg(
        mean_pd=("pd", "mean"), observed_dr=("default", "mean"), n=("default", "size"))
    yearly["sample"] = np.where(yearly.index <= dev_end, "development", "out_of_time")
    yearly["jeffreys_p"] = beta.cdf(yearly["mean_pd"], yearly["observed_dr"] * yearly["n"] + 0.5,
                                    yearly["n"] * (1 - yearly["observed_dr"]) + 0.5)
    yearly = yearly.reset_index()

    dr_all = history.groupby("year")["default"].mean()
    z_pred = zmodel.predict_z(macro_hist.loc[dr_all.index].fillna(0.0))
    sat = pd.DataFrame({"year": dr_all.index, "observed_dr": dr_all.to_numpy(),
                        "predicted_dr": [zmodel.conditional_dr(z) for z in z_pred]})
    sat["sample"] = np.where(sat["year"] <= dev_end, "in_sample", "out_of_sample")
    sat["error"] = sat["predicted_dr"] - sat["observed_dr"]
    rmse_oos = float(np.sqrt((sat.loc[sat["sample"] == "out_of_sample", "error"] ** 2).mean()))
    rmse_is = float(np.sqrt((sat.loc[sat["sample"] == "in_sample", "error"] ** 2).mean()))

    n_red_grades = int((calib["status"] == "RED").sum())
    n_amber_grades = int((calib["status"] == "AMBER").sum())
    rag = pd.DataFrame([
        {"area": "Stability", "metric": "Score PSI (dev vs current)", "value": psi_val,
         "threshold": f"amber {m['psi_amber']} / red {m['psi_red']}", "status": _rag(psi_val, m["psi_amber"], m["psi_red"])},
        {"area": "Stability", "metric": "Max characteristic CSI", "value": float(csi["csi"].max()),
         "threshold": f"amber {m['psi_amber']} / red {m['psi_red']}",
         "status": _rag(float(csi["csi"].max()), m["psi_amber"], m["psi_red"])},
        {"area": "Discrimination", "metric": "Gini relative drop (OOT vs dev)", "value": rel_drop,
         "threshold": f"amber {m['gini_relative_drop_amber']:.0%} / red {m['gini_relative_drop_red']:.0%}",
         "status": _rag(rel_drop, m["gini_relative_drop_amber"], m["gini_relative_drop_red"])},
        {"area": "Calibration", "metric": "Grades failing Jeffreys test (OOT)", "value": n_red_grades + n_amber_grades,
         "threshold": "any red grade -> RED; any amber -> AMBER",
         "status": "RED" if n_red_grades else ("AMBER" if n_amber_grades else "GREEN")},
        {"area": "Calibration", "metric": "Hosmer-Lemeshow p-value (OOT)", "value": hl_p, "threshold": "amber < 0.05 / red < 0.01",
         "status": "RED" if hl_p < 0.01 else ("AMBER" if hl_p < 0.05 else "GREEN")},
        {"area": "Satellite", "metric": "Z-factor OOS RMSE / in-sample RMSE", "value": rmse_oos / rmse_is,
         "threshold": "amber > 1.5 / red > 2.5", "status": _rag(rmse_oos / rmse_is, 1.5, 2.5)},
    ])
    return {"rag": rag, "psi_bins": psi_tab, "csi": csi, "discrimination": disc, "calibration": calib,
            "calibration_yearly": yearly, "hosmer_lemeshow": {"stat": hl_stat, "p_value": hl_p},
            "satellite_backtest": sat}
