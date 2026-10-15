"""Run the production configuration and copy the reviewable outputs into docs/sample_run/."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cibst.pipeline import run_pipeline  # noqa: E402

KEEP = [
    "manifest.json", "run_log.txt",
    "reports/dashboard.html", "reports/committee_pack.md", "reports/mst_results.xlsx",
    "results/summary.csv", "results/capital.csv", "results/by_sector.csv", "results/by_region.csv",
    "results/topdown_benchmark.csv", "results/ifrs9_weighted_ecl.csv",
    "checks/controls.csv", "checks/plausibility.csv", "checks/sensitivity_severe.csv",
    "dq/dq_report.csv", "dq/dq_issue_log.csv",
    "models/pd_scorecard_coefficients.csv", "models/master_scale.csv", "models/zfactor_spec_selection.csv",
    "models/zfactor_coefficients.csv", "models/zfactor_fit.csv",
    "monitoring/rag.csv", "monitoring/discrimination.csv", "monitoring/csi.csv", "monitoring/calibration.csv",
    "monitoring/calibration_yearly.csv", "monitoring/satellite_backtest.csv",
]


def main() -> None:
    arts = run_pipeline(out_root=str(ROOT / "outputs" / "runs"), run_id="sample_MST_2026Q4")
    dest = ROOT / "docs" / "sample_run"
    shutil.rmtree(dest, ignore_errors=True)
    for rel in KEEP:
        src = arts.out_dir / rel
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / rel)
    print(f"sample outputs refreshed in {dest}")


if __name__ == "__main__":
    main()
