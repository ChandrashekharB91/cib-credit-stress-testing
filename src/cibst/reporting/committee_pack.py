"""Auto-generated management committee pack (Markdown) — results, key drivers, assumptions and limitations."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from cibst.reporting.insights import (fmt_bn, fmt_m, migration_matrix, portfolio_snapshot, region_contribution,
                                      scenario_kpis, sector_contribution, top_obligors)

STATUS_ICON = {"PASS": "PASS", "GREEN": "GREEN", "AMBER": "AMBER", "RED": "RED", "FAIL": "FAIL"}


def md_table(df: pd.DataFrame, fmt: dict | None = None) -> str:
    fmt = fmt or {}
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            f = fmt.get(c)
            cells.append(f(v) if f and pd.notna(v) else ("" if pd.isna(v) else str(v)))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


pct = lambda x: f"{x:.2%}"  # noqa: E731
pct1 = lambda x: f"{x:.1%}"  # noqa: E731
bps = lambda x: f"{x:+.0f} bps"  # noqa: E731
mn = lambda x: f"{x:,.0f}"  # noqa: E731


def write_committee_pack(arts, path: Path) -> str:
    snap = portfolio_snapshot(arts)
    k = scenario_kpis(arts).set_index("scenario")
    names = list(arts.results)
    sev = "severe" if "severe" in names else names[-1]
    sectors = sector_contribution(arts, sev)
    regions = region_contribution(arts, sev)
    top = top_obligors(arts, sev, 10)
    mig = migration_matrix(arts, sev)
    hurdle = arts.cfg["capital"]["hurdle_cet1_ratio"]
    H = arts.scenarios.horizon
    years = arts.scenarios.calendar_years
    pl = arts.plausibility
    amber = pl[pl["status"] != "PASS"]
    mon = arts.monitoring["rag"] if arts.monitoring else None
    dq = arts.dq.report

    s = k.loc[sev]
    top3 = sectors.head(3)
    out = []
    out.append(f"# Management Stress Test — CIB Credit Portfolio\n")
    out.append(f"**Run:** `{arts.run_id}`  \n**Reporting date:** {snap['as_of']}  \n"
               f"**Horizon:** {H} years ({years[0]}–{years[-1]})  \n"
               f"**Prepared by:** Risk Portfolio Analytics (illustrative — synthetic data)  \n"
               f"**For:** Credit Risk Committee / Stress Testing Working Group\n")

    out.append("## 1. Executive summary\n")
    bullets = [
        f"**Severe scenario drives {fmt_bn(s['cum_impairment'])} of cumulative impairments over {H} years "
        f"({pct(s['cum_loss_rate'])} of starting EAD)**, with CET1 falling {abs(s['cet1_drawdown_bps']):.0f} bps to a trough "
        f"of {pct(s['cet1_trough'])} in year {int(s['trough_year'])} — "
        f"{'above' if s['headroom_bps'] >= 0 else 'BELOW'} the {pct1(hurdle)} hurdle by {abs(s['headroom_bps']):.0f} bps.",
        f"**Credit RWA inflate by {pct1(s['rwa_uplift'])} at peak** in the severe scenario as obligors migrate down the "
        f"rating scale, adding to the capital pressure from losses.",
        f"**Losses are concentrated:** {', '.join(top3['sector'].str.replace('_', ' '))} account for "
        f"{pct1(top3['share_of_impairment'].sum())} of severe impairments; the top 10 obligors account for "
        f"{pct1(top['impairment'].sum() / s['cum_impairment'])}.",
        f"**IFRS 9:** probability-weighted ECL at the reporting date is {fmt_m(snap['weighted_ecl'])} "
        f"({pct(snap['weighted_coverage'])} coverage); Stage 2 peaks at {pct1(s['stage2_peak'])} of EAD under severe stress "
        f"vs {pct1(snap['stage2_share'])} today.",
    ]
    if "adverse" in k.index:
        a = k.loc["adverse"]
        bullets.append(f"**Adverse scenario is manageable:** {fmt_bn(a['cum_impairment'])} cumulative impairments, "
                       f"CET1 trough {pct(a['cet1_trough'])} ({a['cet1_drawdown_bps']:+.0f} bps).")
    bullets.append(f"**Model risk:** {len(amber)} plausibility check(s) need attention"
                   + (f" and monitoring shows {int((mon['status'] == 'RED').sum())} red / "
                      f"{int((mon['status'] == 'AMBER').sum())} amber metric(s)" if mon is not None else "")
                   + " — see sections 6 and 8.")
    out.extend(f"- {b}" for b in bullets)
    out.append("")

    out.append("## 2. Portfolio at the reporting date\n")
    out.append(md_table(pd.DataFrame([
        ["Obligors / facilities", f"{snap['obligors']:,} / {snap['facilities']:,}"],
        ["Committed limits / drawn", f"{fmt_bn(snap['limits'])} / {fmt_bn(snap['drawn'])}"],
        ["EAD (IFRS 9)", fmt_bn(snap["ead"])],
        ["Credit RWA (RW density)", f"{fmt_bn(snap['rwa'])} ({pct1(snap['rw_density'])})"],
        ["EAD-weighted PD (performing)", pct(snap["pd_wavg"])],
        ["Stage 2 / Stage 3 share of EAD", f"{pct1(snap['stage2_share'])} / {pct1(snap['stage3_share'])}"],
        ["Probability-weighted ECL (coverage)", f"{fmt_m(snap['weighted_ecl'])} ({pct(snap['weighted_coverage'])})"],
        ["Share of limits on F-IRB (large corporates)", pct1(snap["firb_share"])],
    ], columns=["Metric", "Value"])))
    out.append("")

    out.append("## 3. Scenarios\n")
    rows = []
    for n, sc in arts.scenarios.scenarios.items():
        p = sc.paths
        rows.append({"Scenario": n, "Global GDP (y1/y2/y3)": " / ".join(f"{v:+.1f}%" for v in p["global_gdp_growth"]),
                     "Unemployment peak": f"{p['unemployment'].max():.1f}%",
                     "Policy rate peak": f"{p['policy_rate'].max():.2f}%",
                     "Oil trough": f"${p['oil_price'].min():.0f}",
                     "Equity y1": f"{p['equity_return'].iloc[0]:+.0f}%",
                     "Property cum.": f"{((1 + p['property_price_growth'] / 100).prod() - 1):+.0%}",
                     "IFRS 9 weight": pct1(arts.cfg["ifrs9"]["scenario_weights"].get(n, 0))})
    out.append(md_table(pd.DataFrame(rows)))
    out.append("")
    for n, sc in arts.scenarios.scenarios.items():
        out.append(f"- **{n.capitalize()}:** {sc.narrative}")
    out.append("")

    out.append("## 4. Results\n")
    t = k.reset_index()[["scenario", "ecl_t0", "ecl_peak", "cum_impairment", "cum_loss_rate", "stage2_peak",
                         "rwa_peak", "rwa_uplift", "cet1_trough", "cet1_drawdown_bps", "headroom_bps"]]
    t.columns = ["Scenario", "ECL t0", "ECL peak", "Cum. impairment", "Loss rate", "Stage 2 peak", "Peak RWA",
                 "RWA uplift", "CET1 trough", "CET1 drawdown", "Headroom vs hurdle"]
    out.append(md_table(t, {"ECL t0": mn, "ECL peak": mn, "Cum. impairment": mn, "Loss rate": pct,
                            "Stage 2 peak": pct1, "Peak RWA": mn, "RWA uplift": pct1, "CET1 trough": pct,
                            "CET1 drawdown": bps, "Headroom vs hurdle": bps}))
    out.append("\n*Amounts in USD m. Static balance sheet; no management actions or distributions.*\n")

    cap = arts.results[sev].capital
    cap_t = cap[["t", "ppnr", "impairment", "after_tax_profit", "el_shortfall", "total_rwa", "cet1_capital", "cet1_ratio"]].copy()
    cap_t.columns = ["Year", "PPNR", "Impairment", "After-tax profit", "IRB EL shortfall", "Total RWA", "CET1", "CET1 ratio"]
    out.append(f"**Capital walk — {sev} scenario**\n")
    out.append(md_table(cap_t, {c: mn for c in ["PPNR", "Impairment", "After-tax profit", "IRB EL shortfall",
                                                 "Total RWA", "CET1"]} | {"CET1 ratio": pct, "Year": lambda x: str(int(x))}))
    out.append("")

    out.append(f"## 5. Key drivers ({sev} scenario)\n")
    st = sectors[["sector", "ead_t0", "cum_impairment", "impairment_rate", "share_of_impairment", "rwa_uplift",
                  "stage2_share_peak"]].copy()
    st.columns = ["Sector", "EAD t0", "Cum. impairment", "Impairment rate", "Share of losses", "RWA uplift", "Stage 2 peak"]
    out.append("**By sector**\n")
    out.append(md_table(st, {"EAD t0": mn, "Cum. impairment": mn, "Impairment rate": pct, "Share of losses": pct1,
                             "RWA uplift": pct1, "Stage 2 peak": pct1}))
    out.append("\n**By region**\n")
    rg = regions.copy()
    rg.columns = ["Region", "EAD t0", "Cum. impairment", "Impairment rate"]
    out.append(md_table(rg, {"EAD t0": mn, "Cum. impairment": mn, "Impairment rate": pct}))
    out.append("\n**Top 10 obligor contributors**\n")
    tp = top[["obligor_id", "sector", "region", "ead_t0", "pd_t0", "pd_peak", "impairment"]].copy()
    tp.columns = ["Obligor", "Sector", "Region", "EAD t0", "PD t0", "PD peak", "Impairment"]
    out.append(md_table(tp, {"EAD t0": mn, "PD t0": pct, "PD peak": pct, "Impairment": mn}))
    out.append(f"\n**Rating migration (EAD-weighted, reporting date → year {H})**\n")
    mm = mig.reset_index()
    mm.columns = ["From \\ To"] + list(mig.columns)
    out.append(md_table(mm, {c: pct1 for c in mig.columns}))
    out.append("")

    out.append("## 6. Benchmarking and plausibility\n")
    td_rows = []
    for n, r in arts.results.items():
        td = r.topdown.iloc[-1]
        td_rows.append({"Scenario": n, "Bottom-up cum. PD": td["cum_pd_bottom_up"],
                        "Top-down cum. PD (capped Z)": td["cum_pd_top_down_capped"],
                        "Top-down cum. PD (uncapped)": td["cum_pd_top_down"], "BU / TD": td["cum_bu_td_ratio_capped"]})
    out.append(md_table(pd.DataFrame(td_rows), {"Bottom-up cum. PD": pct, "Top-down cum. PD (capped Z)": pct,
                                                "Top-down cum. PD (uncapped)": pct, "BU / TD": lambda x: f"{x:.2f}x"}))
    zm = arts.zmodel
    out.append(f"\nTop-down challenger: Vasicek Z-factor, drivers = {', '.join(zm.drivers)}, rho = {zm.rho:.3f}, "
               f"adj. R² = {zm.adj_r2:.2f}, Durbin-Watson = {zm.durbin_watson:.2f}. Projections are capped at the "
               f"historical Z range [{zm.z_range[0]:.2f}, {zm.z_range[1]:.2f}] to prevent extrapolation.\n")
    pl_t = pl[["check_id", "description", "value", "status"]].copy()
    pl_t.columns = ["Check", "Description", "Value", "Status"]
    out.append(md_table(pl_t, {"Status": lambda x: STATUS_ICON.get(x, x)}))
    out.append("")

    if arts.sensitivity is None:
        out.append("## 7. Sensitivities\n")
        out.append("*Not run in this execution (`--skip-sensitivities`).*\n")
    else:
        sv = arts.sensitivity
        out.append(f"## 7. Sensitivities ({arts.sensitivity.attrs.get('scenario', 'severe')} scenario)\n")
        sv_t = sv[["shock", "d_cum_impairment", "d_rwa_peak", "d_cet1_trough_bps"]].copy()
        sv_t.columns = ["Shock", "Δ cum. impairment", "Δ peak RWA", "Δ CET1 trough"]
        out.append(md_table(sv_t, {"Δ cum. impairment": lambda x: f"{x:+,.0f}", "Δ peak RWA": lambda x: f"{x:+,.0f}",
                                   "Δ CET1 trough": bps}))
        biggest = sv.loc[sv["d_cet1_trough_bps"].idxmin()]
        out.append(f"\nLargest single sensitivity: **{biggest['shock']}** ({biggest['d_cet1_trough_bps']:+.0f} bps on the "
                   f"CET1 trough).\n")

    if mon is None:
        out.append("## 8. Model monitoring\n")
        out.append("*Not run in this execution (`--skip-monitoring`).*\n")
    else:
        out.append("## 8. Model monitoring\n")
        mt = mon[["area", "metric", "value", "threshold", "status"]].copy()
        mt.columns = ["Area", "Metric", "Value", "Threshold", "Status"]
        out.append(md_table(mt, {"Value": lambda x: f"{x:.3f}"}))
        csi = arts.monitoring["csi"]
        worst = csi.loc[csi["csi"].idxmax()]
        out.append(f"\n- Largest characteristic shift: **{worst['characteristic']}** (CSI {worst['csi']:.2f}) — consistent "
                   f"with the higher policy-rate environment compressing interest cover relative to the development sample.")
        cal = arts.monitoring["calibration_yearly"]
        last = cal.iloc[-1]
        out.append(f"- Latest year ({int(last['year'])}) observed default rate {pct(last['observed_dr'])} vs mean PD "
                   f"{pct(last['mean_pd'])} (Jeffreys p = {last['jeffreys_p']:.3f}).")
        out.append("")

    out.append("## 9. Data quality\n")
    dq_t = dq[dq["status"] == "FAIL"][["rule_id", "description", "severity", "records_failing", "exposure_impacted",
                                         "resolution"]].copy()
    dq_t.columns = ["Rule", "Description", "Severity", "Records", "Exposure impacted", "Resolution"]
    out.append(md_table(dq_t, {"Exposure impacted": mn}))
    out.append("")

    out.append("## 10. Key assumptions and limitations\n")
    for line in [
        "Static balance sheet: maturing facilities are replaced like-for-like; defaulted exposures are not replaced "
        "and are not written off within the horizon.",
        "No management actions, dividends or AT1 coupons; pre-provision net revenue held flat at "
        f"{arts.cfg['capital']['ppnr_bps_of_ead']} bps of starting EAD; non-modelled RWA held flat.",
        "Stressed PDs come from re-rating projected financial statements with the corporate scorecard (TTC-calibrated); "
        "no separate PIT overlay — the top-down Z-factor model is used as a challenger only.",
        "Financial institutions are scored with the corporate scorecard as a simplification; a dedicated FI model "
        "(capital, liquidity, asset quality) would be used in production.",
        "LGD reflects collateral revaluation along the scenario; downturn LGD is a fixed add-on; CCF stress is a "
        "scenario-level utilisation uplift on undrawn commitments.",
        "SICR test uses the rating PD at each reporting date against origination PD; watchlist and 30 dpd backstops apply.",
        "All data are synthetic; results illustrate the methodology and are not representative of any institution.",
    ]:
        out.append(f"- {line}")
    out.append("")

    out.append("## 11. Proposed actions for the committee\n")
    actions = [f"Note the severe-scenario CET1 trough of {pct(s['cet1_trough'])} and headroom of "
               f"{s['headroom_bps']:.0f} bps to the {pct1(hurdle)} hurdle."]
    if not top3.empty:
        actions.append(f"Review risk appetite and concentration limits for {top3['sector'].iloc[0].replace('_', ' ')}, "
                       f"the largest loss contributor.")
    if mon is not None and (mon["status"] == "RED").any():
        actions.append("Commission a model-monitoring deep dive (calibration and characteristic stability) with the "
                       "model owner; consider a temporary post-model adjustment pending review.")
    if (dq["resolution"].str.startswith("ESCALATED")).any():
        actions.append("Track open data-quality escalations (excluded records and ledger break) to closure with "
                       "Data Owners and Group Finance before the next run.")
    out.extend(f"{i}. {a}" for i, a in enumerate(actions, 1))
    out.append("")

    out.append("## Appendix — run controls\n")
    c = arts.controls[["control", "scenario", "description", "status"]]
    out.append(md_table(c))
    text = "\n".join(out) + "\n"
    Path(path).write_text(text, encoding="utf-8")
    return text
