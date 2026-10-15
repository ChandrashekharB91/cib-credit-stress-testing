# UAT / UVT test plan — CIB Management Stress Testing engine

## 1. Objective
Confirm, before promotion to BAU, that the implemented engine (a) computes IRB RWA, IFRS 9 ECL, staging and capital exactly as specified in `docs/model_documentation.md`, (b) handles data defects safely, (c) produces reproducible, reconciled and plausible results, and (d) delivers the management reporting the stress-testing forum needs.

## 2. Scope
| In scope | Out of scope |
|---|---|
| RWA function, PD floor, maturity bounds, SME/FI adjustments, defaulted exposures | Model development choices (owned by Modelling, reviewed by Validation) |
| ECL measurement, reversion, partial periods, probability weighting | Scenario design (owned by ERM Scenario Design) |
| SICR, watchlist and DPD staging, Stage 3 | Upstream source-system fixes |
| DQ detection and remediation | Performance / load testing |
| Run controls, plausibility, reproducibility, audit trail | |
| Independent recomputation (UVT) in R | |
| Reporting outputs | |

## 3. Approach
* **Test design** — each case maps to a requirement ID (`REQ-*`) with an expected result derived *independently* of the engine: published BCBS values, closed-form hand calculations, seeded ground truth, or the independent R implementation.
* **UVT** — `uat/r_verification/verify_rwa_ecl.R` re-implements RWA, regulatory EL, survival, staging and ECL in base R from the methodology document and compares every facility × scenario × date (tolerance 1e-8 relative).
* **Negative testing** — `--inject-defect` seeds known defects to prove the test suite detects them.
* **Execution** — `python uat/run_uat.py` (also run in CI on every push).

## 4. Severity and exit criteria
| Severity | Definition | Sign-off impact |
|---|---|---|
| S1 Critical | Wrong regulatory or financial number, control failure, irreproducible result | Blocks sign-off |
| S2 Major | Wrong behaviour in a material path or missing required output | Blocks sign-off |
| S3 Minor | Cosmetic or low-impact deviation | Sign-off with remediation plan |

**Exit criteria:** all S1/S2 cases pass, no open S1/S2 defects, R verification within tolerance, plausibility AMBER items have documented commentary.

## 5. Defect management
Failures automatically raise a defect (`defect_log.csv`) with severity, summary (expected vs actual), owner and retest status. Defects are triaged at the UAT stand-up, fixed by Technology / Model Implementation, re-tested by Risk Portfolio Analytics, and closed only on a passing re-test. History: `docs/uat_cycle_history.md`.

## 6. Roles
| Role | Responsibility |
|---|---|
| Risk Portfolio Analytics (UAT lead) | Test plan, execution, defect triage, sign-off recommendation |
| Model Implementation / Technology | Fix defects, release builds |
| CCIB Modelling (model owner) | Clarify methodology, approve specification interpretations |
| Model Validation | Review UVT evidence |
| Change | Release and BAU transition |

## 7. Deliverables
`uat/results/uat_results.csv`, `defect_log.csv`, `r_verification.csv`, `uat_signoff.md`; seeded-defect evidence in `uat/results_defect_demo/`.
