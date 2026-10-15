"""Command-line entry point:  python -m cibst.run --config config/run_config.yaml"""
from __future__ import annotations

import argparse
import json
import sys

from cibst.pipeline import run_pipeline


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the CIB credit Management Stress Test")
    p.add_argument("--config", default="config/run_config.yaml")
    p.add_argument("--out", default=None, help="output root (defaults to run.output_dir in the config)")
    p.add_argument("--run-id", default=None)
    p.add_argument("--scenarios", nargs="*", default=None, help="subset of scenarios to run")
    p.add_argument("--seed", type=int, default=None, help="override the random seed")
    p.add_argument("--skip-sensitivities", action="store_true")
    p.add_argument("--skip-monitoring", action="store_true")
    p.add_argument("--no-reports", action="store_true")
    a = p.parse_args(argv)
    overrides = {"run": {"seed": a.seed}} if a.seed is not None else None
    arts = run_pipeline(a.config, overrides=overrides, out_root=a.out, run_id=a.run_id,
                        sensitivities=not a.skip_sensitivities, monitoring=not a.skip_monitoring,
                        reports=not a.no_reports, scenarios=a.scenarios)
    print(json.dumps({"run_id": arts.run_id, "output_dir": str(arts.out_dir),
                      "plausibility": arts.manifest.get("plausibility"),
                      "controls_failed": arts.manifest.get("controls_failed")}, indent=2))
    return 0 if arts.manifest.get("controls_failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
