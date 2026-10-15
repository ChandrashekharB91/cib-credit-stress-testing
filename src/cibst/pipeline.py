"""End-to-end orchestration of a Management Stress Test run with controls and an audit trail.

Steps (each timed and logged; every run gets its own folder and manifest):
  01 configuration & input hashing     07 IFRS 9 probability-weighted ECL
  02 macro history & scenarios          08 reconciliation controls
  03 data ingestion (synthetic)         09 plausibility checks
  04 data-quality rules & remediation   10 sensitivity analysis
  05 PD scorecard development           11 model monitoring
  06 Z-factor challenger + scenario runs 12 outputs, verification extracts, reports, manifest
"""
from __future__ import annotations

import hashlib
import json
import logging
import platform
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import cibst
from cibst.analysis.plausibility import run_plausibility
from cibst.analysis.sensitivity import run_sensitivities
from cibst.config import REPO_ROOT, input_hashes, load_config, resolve
from cibst.data.macro import build_scenarios, load_history
from cibst.data.portfolio import generate_all
from cibst.dq.engine import DQEngine
from cibst.engine import StressTestEngine
from cibst.models.features import credit_ratios
from cibst.models.master_scale import master_scale_table
from cibst.models.pd_scorecard import PDScorecard
from cibst.models.z_factor import ZFactorModel
from cibst.monitoring.monitor import run_monitoring

log = logging.getLogger("cibst")


@dataclass
class RunArtifacts:
    run_id: str
    out_dir: Path
    cfg: dict
    scenarios: object = None
    data: object = None
    dq: object = None
    scorecard: object = None
    zmodel: object = None
    engine: object = None
    results: dict = field(default_factory=dict)
    weighted_ecl0: float = np.nan
    controls: pd.DataFrame | None = None
    plausibility: pd.DataFrame | None = None
    sensitivity: pd.DataFrame | None = None
    monitoring: dict | None = None
    step_log: list = field(default_factory=list)
    manifest: dict = field(default_factory=dict)


class _Step:
    def __init__(self, arts: RunArtifacts, code: str, name: str):
        self.arts, self.code, self.name = arts, code, name

    def __enter__(self):
        self.t0 = time.perf_counter()
        log.info("[%s] %s ...", self.code, self.name)
        return self

    def __exit__(self, exc_type, exc, tb):
        dt = time.perf_counter() - self.t0
        status = "FAILED" if exc_type else "OK"
        self.arts.step_log.append({"step": self.code, "name": self.name, "status": status, "seconds": round(dt, 3)})
        log.info("[%s] %s %s (%.2fs)", self.code, self.name, status, dt)
        return False


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "uncommitted"


def _setup_logging(out_dir: Path) -> None:
    log.setLevel(logging.INFO)
    for h in list(log.handlers):
        log.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(out_dir / "run_log.txt", mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(fh)
    log.addHandler(sh)


def run_pipeline(config_path: str = "config/run_config.yaml", overrides: dict | None = None,
                 out_root: str | None = None, run_id: str | None = None, sensitivities: bool = True,
                 monitoring: bool = True, reports: bool = True, scenarios: list[str] | None = None) -> RunArtifacts:
    cfg = load_config(config_path, overrides)
    hashes = input_hashes(cfg)
    cfg_hash = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:8]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = run_id or f"{cfg['run']['name']}_{stamp}_{cfg_hash}"
    out_dir = resolve(out_root or cfg["run"]["output_dir"]) / run_id
    for sub in ["inputs", "dq", "models", "results", "checks", "monitoring", "verification", "reports"]:
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    _setup_logging(out_dir)
    arts = RunArtifacts(run_id=run_id, out_dir=out_dir, cfg=cfg)
    log.info("Run %s started; outputs -> %s", run_id, out_dir)

    with _Step(arts, "01", "configuration & input hashing"):
        arts.manifest["input_hashes"] = hashes

    with _Step(arts, "02", "macro history & scenarios"):
        macro = load_history(resolve(cfg["files"]["macro_history"]))
        sc = build_scenarios(cfg["_scenarios"])
        if scenarios:
            sc.scenarios = {k: v for k, v in sc.scenarios.items() if k in scenarios}
        arts.scenarios = sc

    with _Step(arts, "03", "data ingestion (synthetic CIB portfolio and default history)"):
        data = generate_all(cfg, macro, sc.jump_off)
        arts.data = data
        data.obligors.to_csv(out_dir / "inputs" / "obligors_raw.csv", index=False)
        data.facilities.to_csv(out_dir / "inputs" / "facilities_raw.csv", index=False)
        data.ledger.to_csv(out_dir / "inputs" / "finance_ledger_controls.csv", index=False)
        data.history.to_csv(out_dir / "inputs" / "default_history.csv.gz", index=False, compression="gzip")

    with _Step(arts, "04", "data-quality rules & remediation"):
        dq = DQEngine(cfg["_dq_rules"], cfg["run"]["as_of_date"], cfg["_sectors"]).run(
            data.obligors, data.facilities, data.ledger)
        arts.dq = dq
        dq.report.to_csv(out_dir / "dq" / "dq_report.csv", index=False)
        dq.issues.to_csv(out_dir / "dq" / "dq_issue_log.csv", index=False)
        if dq.blocked:
            raise RuntimeError("Critical data-quality failure unresolved - run blocked")
        log.info("DQ: %d rules failing, %d issues logged, %d escalations open",
                 int((dq.report["status"] == "FAIL").sum()), len(dq.issues), len(dq.open_escalations))

    with _Step(arts, "05", "PD scorecard development & master scale"):
        hist = data.history
        hratios = credit_ratios(hist["revenue"], hist["ebitda"], hist["debt"], hist["interest_expense"],
                                hist["current_ratio"], hist["sector_margin"])
        dev = (hist["year"] <= cfg["portfolio"]["dev_end_year"]).to_numpy()
        sectors = list(cfg["_sectors"]["sectors"])
        sc_model = PDScorecard(sectors)
        fit = sc_model.fit(hratios[dev], hist["sector"].to_numpy()[dev], hist["default"].to_numpy()[dev],
                           hist["year"].to_numpy()[dev], cfg["pd_model"].get("long_run_default_rate"))
        arts.scorecard = sc_model
        fit.coefficients.to_csv(out_dir / "models" / "pd_scorecard_coefficients.csv", index=False)
        master_scale_table().to_csv(out_dir / "models" / "master_scale.csv", index=False)
        log.info("Scorecard: %d obs, %d defaults, LRDR %.3f%%", fit.n_dev, fit.n_defaults_dev,
                 100 * fit.long_run_default_rate)

    with _Step(arts, "06", "Z-factor challenger & scenario runs"):
        dr = hist.groupby("year")["default"].mean()
        zm = ZFactorModel().fit(dr.loc[: cfg["portfolio"]["dev_end_year"]], macro)
        arts.zmodel = zm
        zm.spec_comparison.to_csv(out_dir / "models" / "zfactor_spec_selection.csv", index=False)
        zm.coef.to_csv(out_dir / "models" / "zfactor_coefficients.csv", index=False)
        zm.fitted.to_csv(out_dir / "models" / "zfactor_fit.csv")
        eng = StressTestEngine(cfg, dq.obligors, dq.facilities, sc_model, zm, sc)
        arts.engine = eng
        for name in sc.names:
            arts.results[name] = eng.run_scenario(name)
            s = arts.results[name].summary
            log.info("%-8s ECL t0 %.0f -> t%d %.0f | peak RWA %.0f | CET1 trough %.2f%%", name, s["ecl"].iloc[0],
                     sc.horizon, s["ecl"].iloc[-1], s["rwa"].max(), 100 * s["cet1_ratio"].min())

    with _Step(arts, "07", "IFRS 9 probability-weighted ECL"):
        w = cfg["ifrs9"]["scenario_weights"]
        avail = {k: v for k, v in w.items() if k in arts.results}
        tot = sum(avail.values())
        arts.weighted_ecl0 = sum(v / tot * arts.results[k].summary.loc[0, "ecl"] for k, v in avail.items())
        log.info("Probability-weighted ECL at reporting date: %.0f", arts.weighted_ecl0)

    with _Step(arts, "08", "reconciliation controls"):
        arts.controls = _controls(arts)
        arts.controls.to_csv(out_dir / "checks" / "controls.csv", index=False)

    with _Step(arts, "09", "plausibility checks"):
        arts.plausibility = run_plausibility(arts.results, arts.weighted_ecl0, zm, sc, cfg)
        arts.plausibility.to_csv(out_dir / "checks" / "plausibility.csv", index=False)

    if sensitivities and "severe" in arts.results:
        with _Step(arts, "10", "sensitivity analysis (severe)"):
            arts.sensitivity = run_sensitivities(eng, "severe")
            arts.sensitivity.to_csv(out_dir / "checks" / "sensitivity_severe.csv", index=False)

    if monitoring:
        with _Step(arts, "11", "model monitoring"):
            obl = dq.obligors
            cur = credit_ratios(obl["revenue"], obl["ebitda"], obl["debt"], obl["interest_expense"],
                                obl["current_ratio"], obl["sector"].map(lambda s: cfg["_sectors"]["sectors"][s]["margin_mean"]))
            arts.monitoring = run_monitoring(sc_model, hist, hratios, obl, cur, zm, macro,
                                             cfg["portfolio"]["dev_end_year"], cfg)
            for k, v in arts.monitoring.items():
                if isinstance(v, pd.DataFrame):
                    v.to_csv(out_dir / "monitoring" / f"{k}.csv", index=False)

    with _Step(arts, "12", "outputs, verification extracts, reports & manifest"):
        _write_results(arts)
        _write_verification_extracts(arts)
        if reports:
            from cibst.reporting import committee_pack, dashboard, excel
            dashboard.write_dashboard(arts, out_dir / "reports" / "dashboard.html")
            committee_pack.write_committee_pack(arts, out_dir / "reports" / "committee_pack.md")
            excel.write_workbook(arts, out_dir / "reports" / "mst_results.xlsx")
        _write_manifest(arts)
    log.info("Run %s complete", run_id)
    return arts


def _controls(arts: RunArtifacts) -> pd.DataFrame:
    dq, eng = arts.dq, arts.engine
    rows = []
    n_fac = len(dq.facilities)
    for name, r in arts.results.items():
        f0 = r.facility[r.facility["t"] == 0]
        rows.append({"control": "C-01", "scenario": name, "description": "Facility count: post-DQ input vs engine output",
                     "expected": n_fac, "actual": f0["facility_id"].nunique(),
                     "status": "PASS" if f0["facility_id"].nunique() == n_fac else "FAIL"})
        fi = dq.facilities
        ccf = fi["product"].map(arts.cfg["ead"]["ccf_model"])
        ead_in = float((fi["drawn"] + ccf * (fi["limit"] - fi["drawn"]).clip(lower=0)).sum())
        ead_out = float(r.summary.loc[0, "ead"])
        rows.append({"control": "C-02", "scenario": name,
                     "description": "Reporting-date EAD: recomputed from post-DQ input file vs engine output",
                     "expected": round(ead_in, 4), "actual": round(ead_out, 4),
                     "status": "PASS" if abs(ead_in - ead_out) < 1e-6 * ead_in else "FAIL"})
    base_ead = {n: r.summary.loc[0, "ead"] for n, r in arts.results.items()}
    spread = max(base_ead.values()) - min(base_ead.values())
    rows.append({"control": "C-03", "scenario": "all", "description": "Reporting-date EAD identical across scenarios",
                 "expected": 0.0, "actual": spread, "status": "PASS" if spread < 1e-6 else "FAIL"})
    rwa0 = {n: r.summary.loc[0, "rwa"] for n, r in arts.results.items()}
    spread = max(rwa0.values()) - min(rwa0.values())
    rows.append({"control": "C-04", "scenario": "all", "description": "Reporting-date RWA identical across scenarios",
                 "expected": 0.0, "actual": spread, "status": "PASS" if spread < 1e-6 else "FAIL"})
    for name, r in arts.results.items():
        tot = r.by_sector.groupby("t")["ecl"].sum().to_numpy()
        diff = float(np.max(np.abs(tot - r.summary["ecl"].to_numpy())))
        rows.append({"control": "C-05", "scenario": name, "description": "Sector ECL sums to portfolio ECL",
                     "expected": 0.0, "actual": diff, "status": "PASS" if diff < 1e-6 else "FAIL"})
    return pd.DataFrame(rows)


def _write_results(arts: RunArtifacts) -> None:
    d = arts.out_dir / "results"
    cat = lambda attr: pd.concat([getattr(r, attr).assign(scenario=n) for n, r in arts.results.items()],  # noqa: E731
                                 ignore_index=True)
    cat("summary").to_csv(d / "summary.csv", index=False)
    cat("capital").to_csv(d / "capital.csv", index=False)
    cat("by_sector").to_csv(d / "by_sector.csv", index=False)
    cat("by_region").to_csv(d / "by_region.csv", index=False)
    cat("topdown").to_csv(d / "topdown_benchmark.csv", index=False)
    pd.concat([r.facility for r in arts.results.values()]).to_csv(d / "facility_results.csv.gz", index=False,
                                                                   compression="gzip")
    pd.DataFrame([{"scenario": k, "weight": v} for k, v in arts.cfg["ifrs9"]["scenario_weights"].items()]).assign(
        weighted_ecl_t0=arts.weighted_ecl0).to_csv(d / "ifrs9_weighted_ecl.csv", index=False)


def _write_verification_extracts(arts: RunArtifacts) -> None:
    """Facility-level inputs and outputs for the independent R re-implementation (uat/r_verification)."""
    d = arts.out_dir / "verification"
    eng = arts.engine
    H = arts.scenarios.horizon
    st = eng.rwa_static
    for name, r in arts.results.items():
        f = r.facility
        wide = f.pivot(index="facility_id", columns="t")
        base = pd.DataFrame({"facility_id": eng.fac["facility_id"]}).set_index("facility_id")
        out = base.copy()
        out["maturity"] = eng.fac["maturity_years"].to_numpy()
        out["eir"] = eng.fac["eir"].to_numpy()
        out["origination_pd"] = eng.fac["origination_pd"].to_numpy()
        out["dpd"] = eng.dpd_fac
        out["defaulted"] = eng.defaulted_fac.astype(int)
        out["approach"] = st.approach
        out["sales"] = st.sales
        out["large_fi"] = st.large_fi.astype(int)
        out["m_eff"] = st.m_eff
        out["lgd_downturn"] = np.minimum(1.0, wide["lgd"][0].reindex(out.index).to_numpy() + arts.cfg["lgd"]["downturn_addon"])
        for t in range(H + 1):
            for col in ["pd", "grade", "lgd", "ead", "survival", "ecl", "stage2", "pd_reg", "lgd_reg", "ead_reg",
                        "rwa", "el_reg"]:
                v = wide[col][t].reindex(out.index).to_numpy()
                out[f"{col}_{t}"] = v.astype(int) if col == "stage2" else v
        out.reset_index().to_csv(d / f"facility_{name}.csv", index=False)
    i, rw = arts.cfg["ifrs9"], arts.cfg["rwa"]
    params = {"horizon": H, "sicr_relative_threshold": i["sicr_relative_threshold"],
              "sicr_absolute_threshold": i["sicr_absolute_threshold"], "watchlist_grade": i["watchlist_grade"],
              "dpd_backstop": i["dpd_backstop"], "reversion_years": i["reversion_years"],
              "max_lifetime_years": i["max_lifetime_years"], "scaling_factor": rw["scaling_factor"],
              "sme_threshold": rw["sme_turnover_threshold_musd"], "pd_floor": rw["pd_floor"],
              "maturity_floor": rw["maturity_floor"], "maturity_cap": rw["maturity_cap"]}
    pd.DataFrame([params]).to_csv(d / "parameters.csv", index=False)


def _write_manifest(arts: RunArtifacts) -> None:
    res = arts.out_dir / "results" / "summary.csv"
    m = {
        "run_id": arts.run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of_date": arts.cfg["run"]["as_of_date"],
        "seed": arts.cfg["run"]["seed"],
        "package_version": cibst.__version__,
        "git_commit": _git_commit(),
        "python": platform.python_version(),
        "scenarios": list(arts.results),
        "input_hashes": arts.manifest.get("input_hashes", {}),
        "results_sha256": hashlib.sha256(res.read_bytes()).hexdigest(),
        "steps": arts.step_log,
        "dq": {"rules_failing": int((arts.dq.report["status"] == "FAIL").sum()),
               "issues_logged": len(arts.dq.issues), "open_escalations": len(arts.dq.open_escalations)},
        "controls_failed": int((arts.controls["status"] != "PASS").sum()) if arts.controls is not None else None,
        "plausibility": arts.plausibility["status"].value_counts().to_dict() if arts.plausibility is not None else {},
    }
    arts.manifest.update(m)
    (arts.out_dir / "manifest.json").write_text(json.dumps(m, indent=2, default=str))
