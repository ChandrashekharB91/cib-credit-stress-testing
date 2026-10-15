"""Automated analytical validation and plausibility checks on stress-test outputs.

Each check returns PASS / AMBER / FAIL with the value tested and the threshold, so that the results can be
reviewed at the stress-testing working group and evidenced to model validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ORDER = ["baseline", "adverse", "severe"]


def _row(cid, desc, value, threshold, status):
    return {"check_id": cid, "description": desc, "value": value, "threshold": threshold, "status": status}


def run_plausibility(results: dict, weighted_ecl0: float, zmodel, scenarios, cfg: dict) -> pd.DataFrame:
    c = cfg["checks"]
    rows = []
    names = [n for n in ORDER if n in results]
    S = {n: results[n].summary.set_index("t") for n in names}

    ecl_ok = all((S[a]["ecl"] <= S[b]["ecl"] * (1 + 1e-9)).all() for a, b in zip(names, names[1:]))
    rows.append(_row("PL-01", "ECL ordered baseline <= adverse <= severe at every date",
                     "ordered" if ecl_ok else "not ordered", "monotone", "PASS" if ecl_ok else "FAIL"))
    rwa_peak = {n: S[n]["rwa"].max() for n in names}
    rwa_ok = all(rwa_peak[a] <= rwa_peak[b] for a, b in zip(names, names[1:]))
    rows.append(_row("PL-02", "Peak RWA ordered across scenarios",
                     ", ".join(f"{n} {rwa_peak[n]:,.0f}" for n in names), "monotone", "PASS" if rwa_ok else "FAIL"))
    trough = {n: S[n]["cet1_ratio"].min() for n in names}
    cet_ok = all(trough[a] >= trough[b] for a, b in zip(names, names[1:]))
    rows.append(_row("PL-03", "CET1 trough ordered across scenarios",
                     ", ".join(f"{n} {trough[n]:.2%}" for n in names), "monotone", "PASS" if cet_ok else "FAIL"))

    pd_ok = all(np.isfinite(r.obligor_pd).all() and (r.obligor_pd >= 0).all() and (r.obligor_pd <= 1).all()
                for r in results.values())
    rows.append(_row("PL-04", "All PDs finite and within [0, 1]", "ok" if pd_ok else "violations", "[0, 1]",
                     "PASS" if pd_ok else "FAIL"))

    s2 = {n: S[n].loc[1, "stage2_share"] for n in names}
    s2_ok = all(s2[a] <= s2[b] for a, b in zip(names, names[1:]))
    rows.append(_row("PL-05", "Year-1 Stage 2 share rises with scenario severity",
                     ", ".join(f"{n} {s2[n]:.1%}" for n in names), "monotone", "PASS" if s2_ok else "AMBER"))

    cov = pd.concat([S[n]["coverage"] for n in names])
    rows.append(_row("PL-06", "ECL coverage within [0, 100%]", f"max {cov.max():.2%}", "[0, 1]",
                     "PASS" if ((cov >= 0) & (cov <= 1)).all() else "FAIL"))

    if "severe" in S:
        loss = S["severe"]["cum_loss_rate"].iloc[-1]
        rows.append(_row("PL-07", "Severe cumulative impairment / starting EAD below plausibility ceiling",
                         f"{loss:.2%}", f"<= {c['max_loss_rate_severe']:.0%}",
                         "PASS" if loss <= c["max_loss_rate_severe"] else "AMBER"))

    for n in names:
        td = results[n].topdown
        ratio = td["cum_bu_td_ratio_capped"].iloc[-1]
        ok = abs(ratio - 1) <= c["topdown_benchmark_tolerance"]
        rows.append(_row(f"PL-08-{n[:3].upper()}", f"Bottom-up vs top-down cumulative 3y PD ({n})",
                         f"BU {td['cum_pd_bottom_up'].iloc[-1]:.2%} / TD {td['cum_pd_top_down_capped'].iloc[-1]:.2%} = {ratio:.2f}x",
                         f"within 1 +/- {c['topdown_benchmark_tolerance']:.2f}", "PASS" if ok else "AMBER"))
        oor = zmodel.out_of_range(scenarios.scenarios[n].paths)
        rows.append(_row(f"PL-09-{n[:3].upper()}", f"Satellite drivers inside calibration range ({n})",
                         ", ".join(oor) if oor else "all inside", "historical min/max",
                         "AMBER" if oor else "PASS"))

    if "severe" in results and "baseline" in results:
        def cum(name, by_sector=True):
            g = results[name].by_sector
            last = g[g["t"] == g["t"].max()].set_index("sector")["impairment_cum"]
            return last if by_sector else last.sum()
        sector_mult = cum("severe") / cum("baseline")
        port_mult = cum("severe", False) / cum("baseline", False)
        commodity = sector_mult.reindex(["oil_gas", "metals_mining", "commodity_traders"])
        ok = bool((commodity > port_mult).all())
        rows.append(_row("PL-10", "Commodity collapse: commodity sectors' severe/baseline loss multiple above portfolio",
                         ", ".join(f"{k} {v:.1f}x" for k, v in commodity.items()) + f" vs portfolio {port_mult:.1f}x",
                         "> portfolio multiple", "PASS" if ok else "AMBER"))

    e0 = [S[n].loc[0, "ecl"] for n in names]
    ok = min(e0) - 1e-6 <= weighted_ecl0 <= max(e0) + 1e-6
    rows.append(_row("PL-11", "Probability-weighted ECL lies between scenario ECLs",
                     f"{weighted_ecl0:,.0f} in [{min(e0):,.0f}, {max(e0):,.0f}]", "bounded", "PASS" if ok else "FAIL"))

    worst = 0.0
    for r in results.values():
        f = r.facility[~r.facility["defaulted_t0"]]
        tot = f.groupby("t")[["ead", "ead_s1", "ead_s2", "ead_s3"]].sum()
        staged = tot["ead_s1"] + tot["ead_s2"] + tot["ead_s3"]
        worst = max(worst, float((staged - tot["ead"]).abs().max() / tot["ead"].max()))
    rows.append(_row("PL-12", "Stage allocation conserves exposure (S1 + S2 + S3 = EAD)", f"max rel diff {worst:.1e}",
                     "< 1e-9", "PASS" if worst < 1e-9 else "FAIL"))

    if "baseline" in S:
        move = (S["baseline"]["cet1_ratio"].iloc[-1] - S["baseline"]["cet1_ratio"].iloc[0]) * 1e4
        rows.append(_row("PL-13", "Baseline CET1 change is moderate (baseline is not a stress)", f"{move:+.0f} bps",
                         "within +/- 250 bps", "PASS" if abs(move) <= 250 else "AMBER"))
    return pd.DataFrame(rows)
