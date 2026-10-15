"""Execute the UAT / UVT catalogue, raise defects for failures and produce a sign-off report.

    python uat/run_uat.py                                # full UAT on the production configuration
    python uat/run_uat.py --inject-defect sicr_and_rule  # demonstrate that UAT catches a seeded defect

Outputs (uat/results/ or uat/results_defect_demo/):
    uat_results.csv     one row per test case with expected vs actual and PASS/FAIL
    defect_log.csv      one defect per failed case (severity, detection, status, owner, retest)
    r_verification.csv  full comparison table from the independent R implementation
    uat_signoff.md      summary for the UAT sign-off forum
"""
from __future__ import annotations

import argparse
import contextlib
import json
import platform
import shutil
import subprocess
import sys
import traceback
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cibst.engine as engine_mod  # noqa: E402
from cibst.config import load_config  # noqa: E402
from cibst.dq.engine import ONE_NOTCH_PD_MULTIPLIER  # noqa: E402
from cibst.metrics.ecl import ECLInputs, annual_pd_curve, compute_ecl  # noqa: E402
from cibst.metrics.rwa import irb_correlation, irb_risk_weight, maturity_adjustment  # noqa: E402
from cibst.pipeline import run_pipeline  # noqa: E402

BCBS_CORPORATE_RW = {  # BCBS illustrative IRB risk weights, corporate exposures, LGD 45%, M 2.5 (%)
    0.0003: 14.44, 0.0005: 19.65, 0.001: 29.65, 0.0025: 49.47, 0.004: 62.72, 0.005: 69.61, 0.0075: 82.78,
    0.01: 92.32, 0.013: 100.95, 0.015: 105.59, 0.02: 114.86, 0.025: 122.16, 0.03: 128.44, 0.04: 139.58,
    0.05: 149.86, 0.06: 159.61, 0.10: 193.09, 0.15: 221.54, 0.20: 238.23,
}

# ----------------------------------------------------------------------------------- seeded defects
DEFECTS = {
    "maturity_unclipped": "IRB effective maturity not bounded to [1, 5] years",
    "sicr_and_rule": "SICR absolute-threshold condition dropped (relative test applied alone)",
    "ccf_not_applied": "CCF not applied to undrawn RCF commitments (EAD = drawn)",
}


@contextlib.contextmanager
def inject(defect: str | None):
    if defect is None:
        yield
        return
    if defect == "maturity_unclipped":
        orig = engine_mod.build_rwa_static

        def patched(fac, obl, cfg):
            st = orig(fac, obl, cfg)
            st.m_eff = np.maximum(fac["maturity_years"].to_numpy(dtype=float), 0.25)
            return st
        engine_mod.build_rwa_static = patched
        try:
            yield
        finally:
            engine_mod.build_rwa_static = orig
    elif defect == "sicr_and_rule":
        orig = engine_mod.compute_ecl

        def patched(inp, cfg):
            cfg = json.loads(json.dumps(cfg, default=str))
            cfg["ifrs9"]["sicr_absolute_threshold"] = -1.0
            return orig(inp, cfg)
        engine_mod.compute_ecl = patched
        try:
            yield
        finally:
            engine_mod.compute_ecl = orig
    elif defect == "ccf_not_applied":
        orig = engine_mod.ead_path

        def patched(fac, cfg, name, horizon):
            out = orig(fac, cfg, name, horizon)
            rcf = (fac["product"] == "rcf").to_numpy()
            out[rcf, :] = fac.loc[rcf, "drawn"].to_numpy()[:, None]
            return out
        engine_mod.ead_path = patched
        try:
            yield
        finally:
            engine_mod.ead_path = orig
    else:
        raise ValueError(f"unknown defect {defect}; choose from {list(DEFECTS)}")


# ----------------------------------------------------------------------------------- helpers
def _single(cfg, pd_path, lgd=0.40, ead=100.0, maturity=3.0, eir=0.05, orig_pd=None, grade=8, dpd=0, defaulted=False):
    pd_path = np.atleast_2d(pd_path)
    h1 = pd_path.shape[1]
    inp = ECLInputs(pd_path=pd_path, lgd=np.full((1, h1), lgd), ead=np.full((1, h1), ead),
                    maturity=np.array([maturity]), eir=np.array([eir]),
                    origination_pd=np.array([pd_path[0, 0] if orig_pd is None else orig_pd]),
                    grade_path=np.full((1, h1), grade), dpd=np.array([dpd]), defaulted=np.array([defaulted]))
    return compute_ecl(inp, cfg)


class UAT:
    def __init__(self, out_dir: Path, defect: str | None):
        self.out = out_dir
        self.defect = defect
        self.cfg = load_config()
        self.runs: dict = {}

    # ---------------- pipeline runs shared by end-to-end tests
    def prepare(self):
        root = self.out / "runs"
        with inject(self.defect):
            self.runs["main"] = run_pipeline(out_root=str(root), run_id="uat_main", sensitivities=False)
            self.runs["repeat"] = run_pipeline(out_root=str(root), run_id="uat_repeat", sensitivities=False,
                                               monitoring=False, reports=False)
            self.runs["seed"] = run_pipeline(overrides={"run": {"seed": 7}}, out_root=str(root), run_id="uat_seed7",
                                             sensitivities=False, monitoring=False, reports=False)

    # ---------------- RWA
    def UAT_RWA_001(self):
        pds = np.array(list(BCBS_CORPORATE_RW))
        rw = irb_risk_weight(pds, 0.45, 2.5) * 100
        diff = np.abs(rw - np.array(list(BCBS_CORPORATE_RW.values())))
        return diff.max() <= 0.01, f"max abs diff {diff.max():.4f} pp over {len(pds)} PDs"

    def UAT_RWA_002(self):
        base = irb_correlation(np.array([0.01]))[0]
        r5 = irb_correlation(np.array([0.01]), np.array([5.0]))[0]
        r27 = irb_correlation(np.array([0.01]), np.array([27.5]))[0]
        r60 = irb_correlation(np.array([0.01]), np.array([60.0]))[0]
        ok = abs(r5 - (base - 0.04)) < 1e-12 and abs(r27 - (base - 0.02)) < 1e-12 and abs(r60 - base) < 1e-12
        return ok, f"R base {base:.6f}, S=5 {r5:.6f}, S=27.5 {r27:.6f}, S=60 {r60:.6f}"

    def UAT_RWA_003(self):
        a = irb_correlation(np.array([0.02]), large_fi=np.array([True]))[0]
        b = irb_correlation(np.array([0.02]), large_fi=np.array([False]))[0]
        return abs(a / b - 1.25) < 1e-12, f"ratio {a / b:.12f}"

    def UAT_RWA_004(self):
        m = self.runs["main"].engine.rwa_static.m_eff
        ma = maturity_adjustment(np.array([0.01]), np.array([1.0]))[0]
        ok = m.min() >= 1 and m.max() <= 5 and abs(ma - 1) < 1e-12
        return ok, f"M range [{m.min():.2f}, {m.max():.2f}]; MA(M=1) = {ma:.6f}"

    def UAT_RWA_005(self):
        mn = min(r.facility["pd_reg"].min() for r in self.runs["main"].results.values())
        return mn >= self.cfg["rwa"]["pd_floor"] - 1e-15, f"min regulatory PD {mn:.6f}"

    def UAT_RWA_006(self):
        worst, n = 0.0, 0
        for r in self.runs["main"].results.values():
            dflt = r.facility[r.facility["defaulted_t0"]]
            lgd0 = dflt[dflt["t"] == 0].set_index("facility_id")["lgd"]
            for t in dflt["t"].unique():
                f = dflt[dflt["t"] == t]
                firb = f["approach"].to_numpy() == "F-IRB"
                lgd_dt = np.minimum(1.0, lgd0.loc[f["facility_id"]].to_numpy() + self.cfg["lgd"]["downturn_addon"])
                k = np.where(firb, 0.0, np.maximum(lgd_dt - f["lgd"].to_numpy(), 0.0))
                expected = k * 12.5 * self.cfg["rwa"]["scaling_factor"] * f["ead_reg"].to_numpy()
                worst = max(worst, float(np.abs(expected - f["rwa"].to_numpy()).max(initial=0.0)))
                n += len(f)
        return worst < 1e-9 and n > 0, f"max abs diff {worst:.2e} over {n} defaulted facility-dates"

    # ---------------- ECL
    def UAT_ECL_001(self):
        res = _single(self.cfg, [[0.02, 0.02]], maturity=3.0)
        exp = 0.02 * 0.40 * 100 * 1.05 ** -0.5
        got = res["ecl"][0, 0]
        return abs(got - exp) < 1e-9 and not res["stage2"][0, 0], f"ECL {got:.6f} vs {exp:.6f}"

    def UAT_ECL_002(self):
        res = _single(self.cfg, [[0.02, 0.02]], maturity=3.0, grade=self.cfg["ifrs9"]["watchlist_grade"])
        # horizon H=1 with reversion to PD_0 = 0.02 -> constant 2% curve
        exp = sum(0.98 ** (k - 1) * 0.02 * 40 * 1.05 ** -(k - 0.5) for k in (1, 2, 3))
        got = res["ecl"][0, 0]
        return abs(got - exp) < 1e-9 and bool(res["stage2"][0, 0]), f"ECL {got:.6f} vs {exp:.6f}"

    def UAT_ECL_003(self):
        res = _single(self.cfg, [[0.02, 0.02]], maturity=0.5)
        exp = (1 - 0.98 ** 0.5) * 40 * 1.05 ** -0.25
        got = res["ecl"][0, 0]
        return abs(got - exp) < 1e-9, f"ECL {got:.6f} vs {exp:.6f}"

    def UAT_ECL_004(self):
        from scipy.special import expit, logit
        p = np.array([[0.01, 0.03, 0.05, 0.08]])
        q = annual_pd_curve(p, 6, 2)
        e1 = expit(0.5 * logit(0.08) + 0.5 * logit(0.01))
        ok = abs(q[0, 3] - e1) < 1e-12 and abs(q[0, 4] - 0.01) < 1e-12 and abs(q[0, 2] - 0.08) < 1e-12
        return ok, f"PD(H+1) {q[0, 3]:.6f} vs {e1:.6f}; PD(H+2) {q[0, 4]:.6f}"

    def UAT_ECL_005(self):
        arts = self.runs["main"]
        w = arts.cfg["ifrs9"]["scenario_weights"]
        exp = sum(w[n] * arts.results[n].summary.loc[0, "ecl"] for n in w) / sum(w.values())
        return abs(exp - arts.weighted_ecl0) < 1e-6, f"weighted ECL {arts.weighted_ecl0:,.3f} vs {exp:,.3f}"

    # ---------------- staging
    def UAT_STG_001(self):
        a = _single(self.cfg, [[0.006, 0.006]], orig_pd=0.002)["stage2"][0, 0]
        b = _single(self.cfg, [[0.03, 0.03]], orig_pd=0.01)["stage2"][0, 0]
        return (not a) and bool(b), f"stage flags [{2 if a else 1}, {2 if b else 1}]"

    def UAT_STG_002(self):
        s = _single(self.cfg, [[0.10, 0.10]], orig_pd=0.10, grade=self.cfg["ifrs9"]["watchlist_grade"])["stage2"][0, 0]
        return bool(s), f"stage {2 if s else 1}"

    def UAT_STG_003(self):
        s = _single(self.cfg, [[0.01, 0.01]], orig_pd=0.01, dpd=35)["stage2"][0, 0]
        return bool(s), f"stage {2 if s else 1}"

    def UAT_STG_004(self):
        r = _single(self.cfg, [[1.0, 1.0]], lgd=0.45, ead=100, defaulted=True)
        ok = abs(r["ecl"][0, 1] - 45.0) < 1e-9 and r["survival"][0, 1] == 0 and not r["stage2"][0, 1]
        return ok, f"ECL {r['ecl'][0, 1]:.4f}, survival {r['survival'][0, 1]:.0f}, stage2 {bool(r['stage2'][0, 1])}"

    # ---------------- DQ
    def UAT_DQ_001(self):
        arts = self.runs["main"]
        inj, iss = arts.data.injected_issues, arts.dq.issues
        recalls = {k: len(set(v) & set(iss.loc[iss["rule_id"] == k, "record_id"])) / len(v) for k, v in inj.items()}
        worst = min(recalls.values())
        return worst == 1.0 and len(recalls) == 10, f"{len(recalls)} rules seeded; min recall {worst:.0%}"

    def UAT_DQ_002(self):
        arts = self.runs["main"]
        stale = set(arts.data.injected_issues["DQ-004"])
        o = arts.dq.obligors
        flagged = set(o.loc[o["pd_overlay_mult"] > 1, "obligor_id"])
        ok = flagged == stale and np.allclose(o.loc[o["pd_overlay_mult"] > 1, "pd_overlay_mult"], ONE_NOTCH_PD_MULTIPLIER)
        return ok, f"{len(flagged)} obligors with overlay x{ONE_NOTCH_PD_MULTIPLIER:.3f}; {len(stale)} stale"

    # ---------------- E2E
    def UAT_E2E_001(self):
        c = self.runs["main"].controls
        bad = c[c["status"] != "PASS"]
        return bad.empty, f"{len(c)} controls, {len(bad)} failed" + (f": {', '.join(bad['control'])}" if len(bad) else "")

    def UAT_E2E_002(self):
        p = self.runs["main"].plausibility
        n_fail = int((p["status"] == "FAIL").sum())
        return n_fail == 0, f"{len(p)} checks: {p['status'].value_counts().to_dict()}"

    def UAT_E2E_003(self):
        a, b = self.runs["main"].manifest["results_sha256"], self.runs["repeat"].manifest["results_sha256"]
        return a == b, f"{a[:12]} vs {b[:12]}"

    def UAT_E2E_004(self):
        a, b = self.runs["main"].manifest["results_sha256"], self.runs["seed"].manifest["results_sha256"]
        return a != b, f"{a[:12]} vs {b[:12]}"

    def UAT_E2E_005(self):
        m = self.runs["main"].manifest
        need = ["run_id", "created_utc", "input_hashes", "git_commit", "package_version", "results_sha256", "steps"]
        missing = [k for k in need if k not in m]
        steps_ok = all(s["status"] == "OK" for s in m["steps"])
        return not missing and steps_ok, f"missing {missing}; {len(m['steps'])} steps OK={steps_ok}"

    # ---------------- independent R verification
    def _r(self):
        if hasattr(self, "_rres"):
            return self._rres
        rscript = shutil.which("Rscript")
        if rscript is None:
            self._rres = None
            return None
        out = self.out / "r_verification.csv"
        vdir = self.runs["main"].out_dir / "verification"
        subprocess.run([rscript, str(ROOT / "uat" / "r_verification" / "verify_rwa_ecl.R"), str(vdir), str(out)],
                       capture_output=True, text=True)
        self._rres = pd.read_csv(out)
        return self._rres

    def _rcheck(self, metrics):
        r = self._r()
        if r is None:
            return False, "Rscript not available"
        sub = r[r["metric"].isin(metrics)]
        fails = sub[sub["status"] != "PASS"]
        return fails.empty, (f"{len(sub)} comparisons, {len(fails)} failed; max rel diff "
                             f"{sub['rel_diff_of_total'].max():.1e}")

    def UAT_RVER_001(self):
        return self._rcheck(["rwa", "el_reg"])

    def UAT_RVER_002(self):
        return self._rcheck(["survival", "stage2_flag", "ecl"])

    # ---------------- reporting
    def UAT_RPT_001(self):
        rep = self.runs["main"].out_dir / "reports"
        files = [rep / "dashboard.html", rep / "committee_pack.md", rep / "mst_results.xlsx"]
        if not all(f.exists() and f.stat().st_size > 1000 for f in files):
            return False, "missing report files"
        pack = files[1].read_text()
        sections = sum(f"## {i}." in pack for i in range(1, 12))
        sheets = set(pd.ExcelFile(files[2]).sheet_names)
        need = {"Scenario_KPIs", "Capital_walk", "Plausibility_checks", "Run_controls"}
        return sections == 11 and need <= sheets, f"{sections}/11 sections; sheets ok={need <= sheets}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inject-defect", choices=list(DEFECTS), default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out) if a.out else ROOT / "uat" / ("results_defect_demo" if a.inject_defect else "results")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    cases = yaml.safe_load((ROOT / "uat" / "test_cases.yaml").read_text())["cases"]

    u = UAT(out, a.inject_defect)
    u.prepare()
    rows = []
    for c in cases:
        fn = getattr(u, c["id"].replace("-", "_"))
        try:
            ok, actual = fn()
        except Exception as e:  # noqa: BLE001
            ok, actual = False, f"ERROR: {e!r}"
            traceback.print_exc()
        rows.append({"test_id": c["id"], "area": c["area"], "requirement": c["requirement"],
                     "description": c["description"], "expected": c["expected"], "actual": actual,
                     "result": "PASS" if ok else "FAIL", "severity_if_failed": c["severity"]})
        print(f"{c['id']:<14} {'PASS' if ok else 'FAIL'}  {actual}")
    res = pd.DataFrame(rows)
    res.to_csv(out / "uat_results.csv", index=False)

    today = date.today().isoformat()
    defects = []
    for i, r in enumerate(res[res["result"] == "FAIL"].itertuples(), 1):
        defects.append({
            "defect_id": f"DEF-{i:03d}", "test_id": r.test_id, "severity": r.severity_if_failed,
            "summary": f"{r.requirement}: expected {r.expected}; actual {r.actual}",
            "root_cause": (f"Seeded defect for UAT demonstration: {DEFECTS[a.inject_defect]}" if a.inject_defect
                           else "Under investigation"),
            "detected_by": r.test_id, "raised": today, "owner": "Model Implementation (Technology)",
            "status": "Open", "retest": "Pending fix",
        })
    dl = pd.DataFrame(defects, columns=["defect_id", "test_id", "severity", "summary", "root_cause", "detected_by",
                                        "raised", "owner", "status", "retest"])
    dl.to_csv(out / "defect_log.csv", index=False)
    _signoff(out, res, dl, u, a.inject_defect)
    shutil.rmtree(out / "runs", ignore_errors=True)
    blocking = dl[dl["severity"].isin(["S1", "S2"])]
    print(f"\n{(res['result'] == 'PASS').sum()}/{len(res)} passed; {len(dl)} defects ({len(blocking)} blocking)")
    return 0 if blocking.empty else 1


def _signoff(out: Path, res: pd.DataFrame, dl: pd.DataFrame, u: UAT, defect: str | None) -> None:
    r_ver = subprocess.run(["Rscript", "--version"], capture_output=True, text=True).stderr.strip() \
        if shutil.which("Rscript") else "not available"
    m = u.runs["main"].manifest
    by_area = res.groupby("area")["result"].agg(lambda s: f"{(s == 'PASS').sum()}/{len(s)}").reset_index()
    blocking = dl[dl["severity"].isin(["S1", "S2"])]
    met = blocking.empty
    lines = [
        "# UAT / UVT sign-off report — CIB Management Stress Testing engine\n",
        f"- **Date:** {date.today().isoformat()}",
        f"- **Build:** package {m['package_version']}, git `{m['git_commit']}`",
        f"- **Environment:** Python {platform.python_version()}; {r_ver.splitlines()[0] if r_ver else ''}",
        f"- **Run under test:** `{m['run_id']}` (results SHA-256 `{m['results_sha256'][:16]}…`)",
        f"- **Seeded defect:** {DEFECTS[defect] if defect else 'none (production configuration)'}\n",
        "## Summary\n",
        f"**{(res['result'] == 'PASS').sum()} of {len(res)} test cases passed.** "
        f"{len(dl)} defect(s) raised, {len(blocking)} blocking (S1/S2).\n",
        "| Area | Passed |", "|---|---|", *[f"| {a} | {p} |" for a, p in by_area.itertuples(index=False)], "",
        "## Exit criteria\n",
        f"- All S1 and S2 test cases passed: **{'Yes' if met else 'No'}**",
        f"- No open S1/S2 defects: **{'Yes' if met else 'No'}**",
        "- Independent R verification within 1e-8: **" + (
            "Yes" if (res.loc[res['test_id'].str.startswith('UAT-RVER'), 'result'] == 'PASS').all() else "No") + "**\n",
        f"**Recommendation:** {'UAT exit criteria met — recommend sign-off and promotion to BAU.' if met else 'Exit criteria NOT met — do not promote; remediate and re-test the defects below.'}\n",
    ]
    if not dl.empty:
        lines += ["## Defects\n", "| ID | Test | Severity | Summary | Status |", "|---|---|---|---|---|"]
        lines += [f"| {d.defect_id} | {d.test_id} | {d.severity} | {d.summary} | {d.status} |" for d in dl.itertuples()]
        lines.append("")
    lines += ["## Test results\n", "| Test | Area | Result | Actual |", "|---|---|---|---|"]
    lines += [f"| {r.test_id} | {r.area} | {r.result} | {r.actual} |" for r in res.itertuples()]
    (out / "uat_signoff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
