import json

import pandas as pd


def test_controls_pass(small_run):
    assert (small_run.controls["status"] == "PASS").all()


def test_no_plausibility_failures(small_run):
    assert not (small_run.plausibility["status"] == "FAIL").any()


def test_scenario_ordering(small_run):
    s = {n: r.summary for n, r in small_run.results.items()}
    assert (s["baseline"]["ecl"] <= s["adverse"]["ecl"]).all()
    assert (s["adverse"]["ecl"] <= s["severe"]["ecl"]).all()
    assert s["severe"]["cet1_ratio"].min() < s["baseline"]["cet1_ratio"].min()


def test_dq_detects_all_seeded_issues(small_run):
    inj, iss = small_run.data.injected_issues, small_run.dq.issues
    for rule, ids in inj.items():
        found = set(iss.loc[iss["rule_id"] == rule, "record_id"])
        assert set(ids) <= found, rule


def test_outputs_and_manifest(small_run):
    d = small_run.out_dir
    for p in ["manifest.json", "results/summary.csv", "reports/dashboard.html", "reports/committee_pack.md",
              "reports/mst_results.xlsx", "verification/facility_severe.csv", "checks/plausibility.csv"]:
        assert (d / p).exists(), p
    m = json.loads((d / "manifest.json").read_text())
    assert all(s["status"] == "OK" for s in m["steps"])
    assert len(m["results_sha256"]) == 64


def test_probability_weighted_ecl(small_run):
    w = small_run.cfg["ifrs9"]["scenario_weights"]
    exp = sum(w[n] * small_run.results[n].summary.loc[0, "ecl"] for n in w) / sum(w.values())
    assert abs(exp - small_run.weighted_ecl0) < 1e-6


def test_stage_shares_sum_to_one(small_run):
    for r in small_run.results.values():
        s = r.summary
        total = (s["ead_s1"] + s["ead_s2"] + s["ead_s3"]) / s["ead"]
        assert ((total - 1).abs() < 1e-9).all()


def test_results_csv_schema(small_run):
    df = pd.read_csv(small_run.out_dir / "results" / "summary.csv")
    for c in ["scenario", "t", "ead", "ecl", "rwa", "cet1_ratio", "stage2_share"]:
        assert c in df.columns
