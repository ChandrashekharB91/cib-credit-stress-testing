PY ?= python

.PHONY: install run test uat uat-defect-demo verify-r sample clean

install:
	$(PY) -m pip install -e ".[dev]"

run:            ## full MST run -> outputs/runs/<run_id>/
	$(PY) -m cibst.run

test:           ## unit + integration tests
	$(PY) -m pytest

uat:            ## UAT/UVT catalogue incl. independent R verification -> uat/results/
	$(PY) uat/run_uat.py

uat-defect-demo: ## show UAT catching a seeded defect -> uat/results_defect_demo/
	$(PY) uat/run_uat.py --inject-defect sicr_and_rule

verify-r:       ## run only the R verification against the latest run
	Rscript uat/r_verification/verify_rwa_ecl.R $$(ls -d outputs/runs/*/ | tail -1)verification outputs/r_verification.csv

sample:         ## refresh the committed sample outputs in docs/sample_run/
	$(PY) scripts/refresh_sample.py

clean:
	rm -rf outputs .pytest_cache
