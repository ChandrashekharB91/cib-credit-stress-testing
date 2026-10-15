"""Interactive HTML dashboard (Plotly) for stress-test results, drivers, checks and monitoring."""
from __future__ import annotations

import html
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs_version
from plotly.subplots import make_subplots

from cibst.reporting.insights import (migration_matrix, portfolio_snapshot, scenario_kpis, sector_contribution,
                                      fmt_bn, fmt_m)

# Scenario severity is ordinal -> one-hue ramp, light (baseline) to dark (severe); validated ordinal ramp.
SCEN_COLOR = {"baseline": "#86b6ef", "adverse": "#2a78d6", "severe": "#104281"}
# Categorical slots in fixed order (validated all-pairs for three series).
CAT = ["#2a78d6", "#eb6834", "#1baf7a"]
STATUS = {"PASS": ("#0ca30c", "&#10003;"), "GREEN": ("#0ca30c", "&#10003;"), "AMBER": ("#fab219", "&#9650;"),
          "RED": ("#d03b3b", "&#10005;"), "FAIL": ("#d03b3b", "&#10005;")}
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"


def _layout(fig: go.Figure, title: str, height: int = 340, ytitle: str = "", yfmt: str | None = None) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=14, color=INK)),
        height=height, margin=dict(l=56, r=16, t=48, b=40), paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", size=12, color=INK2),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=1, xanchor="right", font=dict(color=INK2)),
        hoverlabel=dict(bgcolor="white", font=dict(color=INK)), hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS, tickfont=dict(color=MUTED))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=AXIS, tickfont=dict(color=MUTED),
                     title=dict(text=ytitle, font=dict(color=MUTED)))
    if yfmt:
        fig.update_yaxes(tickformat=yfmt)
    return fig


def _years(arts) -> list[str]:
    return [str(arts.scenarios.jump_off["year"])] + [str(y) for y in arts.scenarios.calendar_years]


def fig_metric(arts, col: str, title: str, ytitle: str, yfmt: str | None = None, hurdle: float | None = None):
    fig = go.Figure()
    x = _years(arts)
    for n, r in arts.results.items():
        fig.add_trace(go.Scatter(x=x, y=r.summary[col], name=n, mode="lines+markers",
                                 line=dict(color=SCEN_COLOR.get(n), width=2), marker=dict(size=8)))
    if hurdle is not None:
        fig.add_hline(y=hurdle, line=dict(color=MUTED, width=1, dash="dash"),
                      annotation_text=f"hurdle {hurdle:.1%}", annotation_font_color=MUTED)
    return _layout(fig, title, ytitle=ytitle, yfmt=yfmt)


def fig_macro(arts):
    vars_ = [("global_gdp_growth", "Global GDP growth (%)", False), ("unemployment", "Unemployment (%)", True),
             ("policy_rate", "Policy rate (%)", True), ("oil_price", "Oil (USD/bbl)", True)]
    fig = make_subplots(rows=2, cols=2, subplot_titles=[v[1] for v in vars_], vertical_spacing=0.18)
    jump = arts.scenarios.jump_off
    for i, (col, _, has_jump) in enumerate(vars_):
        r, c = i // 2 + 1, i % 2 + 1
        for n, sc in arts.scenarios.scenarios.items():
            ys = list(sc.paths[col])
            x = [str(y) for y in arts.scenarios.calendar_years]
            if has_jump:
                ys, x = [jump[col]] + ys, _years(arts)
            fig.add_trace(go.Scatter(x=x, y=ys, name=n, legendgroup=n, showlegend=i == 0, mode="lines+markers",
                                     line=dict(color=SCEN_COLOR.get(n), width=2), marker=dict(size=7)), row=r, col=c)
    fig.update_annotations(font=dict(size=12, color=INK2))
    f = _layout(fig, "Macro scenario paths", height=480)
    f.update_layout(margin=dict(t=90), legend=dict(y=1.13, x=0, xanchor="left"))
    return f


def fig_stage(arts, scen: str):
    s = arts.results[scen].summary
    fig = go.Figure()
    for i, (col, name) in enumerate([("ead_s1", "Stage 1"), ("ead_s2", "Stage 2"), ("ead_s3", "Stage 3")]):
        fig.add_trace(go.Bar(x=_years(arts), y=s[col] / s["ead"], name=name, marker=dict(color=CAT[i], line=dict(width=0)),
                             hovertemplate="%{y:.1%}"))
    fig.update_layout(barmode="stack", bargap=0.35, legend=dict(traceorder="normal"))
    return _layout(fig, f"IFRS 9 stage mix of EAD — {scen}", yfmt=".0%")


def fig_sector(arts):
    fig = go.Figure()
    order = sector_contribution(arts, "severe" if "severe" in arts.results else list(arts.results)[-1])["sector"]
    for n in [x for x in ("adverse", "severe") if x in arts.results]:
        sc = sector_contribution(arts, n).set_index("sector").reindex(order[::-1])
        fig.add_trace(go.Bar(y=[s.replace("_", " ") for s in sc.index], x=sc["impairment_rate"], name=n,
                             orientation="h", marker=dict(color=SCEN_COLOR[n], line=dict(width=0)),
                             hovertemplate="%{x:.2%}"))
    fig.update_layout(barmode="group", bargap=0.25, bargroupgap=0.08, hovermode="y unified")
    f = _layout(fig, "Cumulative impairment rate by sector (% of starting EAD)", height=420)
    f.update_xaxes(tickformat=".0%", showgrid=True, gridcolor=GRID)
    f.update_yaxes(showgrid=False)
    return f


def fig_migration(arts, scen: str):
    m = migration_matrix(arts, scen)
    short = ["IG", "Sub-IG", "Watch", "Default"]
    fig = go.Figure(go.Heatmap(z=m.values, x=short, y=short, colorscale=[[0, "#f0efec"], [0.25, "#b7d3f6"],
                                                                          [0.5, "#5598e7"], [1, "#0d366b"]],
                               zmin=0, zmax=1, text=[[f"{v:.0%}" if v > 0 else "" for v in row] for row in m.values],
                               texttemplate="%{text}", hovertemplate="from %{y} to %{x}: %{z:.1%}<extra></extra>",
                               showscale=False, xgap=2, ygap=2))
    f = _layout(fig, f"Rating migration, EAD-weighted — {scen} (reporting date → year {arts.scenarios.horizon})")
    f.update_yaxes(autorange="reversed", showgrid=False, title="from")
    f.update_xaxes(title="to")
    f.update_layout(hovermode="closest")
    return f


def fig_topdown(arts):
    fig = go.Figure()
    names = list(arts.results)
    bu = [arts.results[n].topdown["cum_pd_bottom_up"].iloc[-1] for n in names]
    td = [arts.results[n].topdown["cum_pd_top_down_capped"].iloc[-1] for n in names]
    fig.add_trace(go.Bar(x=names, y=bu, name="Bottom-up (stressed financials)", marker=dict(color=CAT[0]),
                         hovertemplate="%{y:.2%}"))
    fig.add_trace(go.Bar(x=names, y=td, name="Top-down (Z-factor, capped)", marker=dict(color=CAT[1]),
                         hovertemplate="%{y:.2%}"))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    return _layout(fig, f"Cumulative {arts.scenarios.horizon}-year PD: bottom-up vs top-down challenger", yfmt=".0%")


def fig_tornado(arts):
    sv = arts.sensitivity
    order = sv.groupby("driver")["d_cet1_trough_bps"].apply(lambda s: s.abs().max()).sort_values().index
    fig = go.Figure()
    for i, (direction, label) in enumerate([("adverse", "Adverse shock"), ("favourable", "Favourable shock")]):
        d = sv[sv["direction"] == direction].set_index("driver").reindex(order)
        fig.add_trace(go.Bar(y=list(order), x=d["d_cet1_trough_bps"], name=label, orientation="h",
                             marker=dict(color=CAT[1] if direction == "adverse" else CAT[0]),
                             customdata=d["shock"], hovertemplate="%{customdata}: %{x:+.0f} bps<extra></extra>"))
    fig.update_layout(barmode="overlay", bargap=0.35, hovermode="closest")
    f = _layout(fig, f"Sensitivity of severe CET1 trough (bps)", height=360)
    f.update_xaxes(showgrid=True, gridcolor=GRID, zeroline=True, zerolinecolor=AXIS)
    f.update_yaxes(showgrid=False)
    return f


def _badge(status: str) -> str:
    color, icon = STATUS.get(status, (MUTED, "&#8226;"))
    return f'<span class="badge"><span class="dot" style="background:{color}">{icon}</span>{html.escape(status)}</span>'


def _table(df: pd.DataFrame, fmt: dict | None = None, status_col: str | None = None) -> str:
    fmt = fmt or {}
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in df.columns:
            v = r[c]
            if c == status_col:
                cells.append(f"<td>{_badge(str(v))}</td>")
            else:
                txt = fmt[c](v) if c in fmt and pd.notna(v) else ("" if pd.isna(v) else str(v))
                num = isinstance(v, (int, float)) and not isinstance(v, bool)
                cells.append(f'<td class="{"num" if num else ""}">{html.escape(txt)}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def write_dashboard(arts, path: Path) -> None:
    snap = portfolio_snapshot(arts)
    k = scenario_kpis(arts).set_index("scenario")
    sev = "severe" if "severe" in arts.results else list(arts.results)[-1]
    s = k.loc[sev]
    cfg = {"displayModeBar": False, "responsive": True}
    div = lambda f: f.to_html(full_html=False, include_plotlyjs=False, config=cfg)  # noqa: E731

    tiles = [
        ("Probability-weighted ECL", fmt_m(snap["weighted_ecl"]), f"{snap['weighted_coverage']:.2%} coverage of {fmt_bn(snap['ead'])} EAD"),
        (f"Cumulative impairment — {sev}", fmt_m(s["cum_impairment"]), f"{s['cum_loss_rate']:.2%} of starting EAD over {arts.scenarios.horizon} years"),
        (f"CET1 trough — {sev}", f"{s['cet1_trough']:.2%}", f"{s['cet1_drawdown_bps']:+.0f} bps; {s['headroom_bps']:+.0f} bps vs hurdle"),
        (f"Peak RWA uplift — {sev}", f"{s['rwa_uplift']:+.1%}", f"{fmt_bn(s['rwa_peak'])} at peak vs {fmt_bn(s['rwa_t0'])}"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="tl">{html.escape(a)}</div><div class="tv">{html.escape(b)}</div>'
                         f'<div class="ts">{html.escape(c)}</div></div>' for a, b, c in tiles)

    kt = k.reset_index()[["scenario", "cum_impairment", "cum_loss_rate", "stage2_peak", "rwa_uplift", "cet1_trough",
                          "cet1_drawdown_bps", "headroom_bps"]]
    kt.columns = ["Scenario", "Cum. impairment ($m)", "Loss rate", "Stage 2 peak", "RWA uplift", "CET1 trough",
                  "CET1 drawdown (bps)", "Headroom (bps)"]
    kpi_table = _table(kt, {"Cum. impairment ($m)": lambda x: f"{x:,.0f}", "Loss rate": lambda x: f"{x:.2%}",
                            "Stage 2 peak": lambda x: f"{x:.1%}", "RWA uplift": lambda x: f"{x:+.1%}",
                            "CET1 trough": lambda x: f"{x:.2%}", "CET1 drawdown (bps)": lambda x: f"{x:+.0f}",
                            "Headroom (bps)": lambda x: f"{x:+.0f}"})
    pl = arts.plausibility[["check_id", "description", "value", "status"]]
    pl.columns = ["Check", "Description", "Value", "Status"]
    mon_html = ""
    if arts.monitoring:
        mt = arts.monitoring["rag"][["area", "metric", "value", "threshold", "status"]].copy()
        mt.columns = ["Area", "Metric", "Value", "Threshold", "Status"]
        mon_html = _table(mt, {"Value": lambda x: f"{x:.3f}"}, "Status")
    dq = arts.dq.report[["rule_id", "dimension", "description", "severity", "records_failing", "exposure_impacted", "status",
                         "resolution"]].copy()
    dq["resolution"] = dq["resolution"].str.split(":").str[0]
    dq.columns = ["Rule", "Dimension", "Description", "Severity", "Records", "Exposure ($m)", "Status", "Resolution"]

    sections = [
        ("Scenarios", div(fig_macro(arts)), True),
        ("Losses", div(fig_metric(arts, "ecl", "ECL stock by scenario ($m)", "USD m", ",.0f")), False),
        ("Capital", div(fig_metric(arts, "cet1_ratio", "CET1 ratio path", "", ".1%",
                                   arts.cfg["capital"]["hurdle_cet1_ratio"])), False),
        ("RWA", div(fig_metric(arts, "rwa", "Credit RWA by scenario ($m)", "USD m", ",.0f")), False),
        ("Staging", div(fig_stage(arts, sev)), False),
        ("Sectors", div(fig_sector(arts)), False),
        ("Migration", div(fig_migration(arts, sev)), False),
        ("Benchmark", div(fig_topdown(arts)), False),
    ]
    if arts.sensitivity is not None:
        sections.append(("Sensitivities", div(fig_tornado(arts)), False))
    charts = "".join(f'<section class="card{" wide" if wide else ""}" aria-label="{t}">{h}</section>'
                     for t, h, wide in sections)

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CIB Stress Test Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@{get_plotlyjs_version()}/plotly.min.js"></script>
<style>
:root {{ color-scheme: light; --surface:{SURFACE}; --page:#f9f9f7; --ink:{INK}; --ink2:{INK2}; --muted:{MUTED};
  --grid:{GRID}; --border:rgba(11,11,11,.10); }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }}
header {{ padding:24px 16px 8px; max-width:1280px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h2 {{ font-size:16px; margin:28px 0 10px; }}
.sub {{ color:var(--ink2); font-size:13px; }}
main {{ max-width:1280px; margin:0 auto; padding:0 16px 40px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:12px; margin:16px 0; }}
.tile {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }}
.tl {{ color:var(--ink2); font-size:12px; }} .tv {{ font-size:28px; font-weight:600; margin:4px 0; }}
.ts {{ color:var(--muted); font-size:12px; }}
.grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }}
.card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:8px; min-width:0; }}
.card.wide {{ grid-column:1/-1; }}
.tbl {{ overflow-x:auto; background:var(--surface); border:1px solid var(--border); border-radius:10px; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th {{ text-align:left; color:var(--ink2); font-weight:600; border-bottom:1px solid var(--grid); padding:8px 10px; white-space:nowrap; }}
td {{ border-bottom:1px solid var(--grid); padding:7px 10px; vertical-align:top; }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.badge {{ display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }}
.dot {{ display:inline-flex; width:16px; height:16px; border-radius:50%; color:#fff; font-size:10px; align-items:center; justify-content:center; }}
footer {{ color:var(--muted); font-size:12px; margin-top:24px; }}
@media (max-width: 760px) {{ .grid {{ grid-template-columns:1fr; }} }}
</style></head><body>
<header><h1>CIB Credit Management Stress Test</h1>
<div class="sub">Run <code>{html.escape(arts.run_id)}</code> · reporting date {snap['as_of']} · {snap['obligors']:,} obligors · {snap['facilities']:,} facilities · {fmt_bn(snap['ead'])} EAD · synthetic data</div></header>
<main>
<div class="tiles">{tiles_html}</div>
<h2>Scenario results</h2>{kpi_table}
<h2>Charts</h2><div class="grid">{charts}</div>
<h2>Plausibility and benchmarking checks</h2>{_table(pl, status_col="Status")}
<h2>Model monitoring</h2>{mon_html}
<h2>Data quality</h2>{_table(dq, {"Exposure ($m)": lambda x: f"{x:,.0f}"}, "Status")}
<footer>Generated by cibst · all figures in USD m unless stated · static balance sheet, no management actions · synthetic, illustrative data.</footer>
</main></body></html>"""
    Path(path).write_text(page, encoding="utf-8")
