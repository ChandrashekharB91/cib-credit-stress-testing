# BAU runbook — quarterly Management Stress Test run

## Timeline (working days relative to quarter-end data cut, D)
| Day | Activity | Owner | Output / control |
|---|---|---|---|
| D+3 | Receive facility, obligor and financial-statement extracts; Finance ledger control totals | Data owners, Group Finance | Source files hashed in the run manifest |
| D+4 | Scenario paths approved and loaded into `config/scenarios.yaml` | ERM Scenario Design | Scenario sign-off email filed |
| D+5 | Dry run: `python -m cibst.run --skip-sensitivities` | Risk Portfolio Analytics | DQ report, controls |
| D+5 | Triage DQ issues; agree remediations and escalations with data owners | RPA, data owners | `dq/dq_issue_log.csv` |
| D+7 | Production run: `python -m cibst.run` | RPA | Manifest, results, checks |
| D+7 | Independent verification: `make verify-r` | RPA | `r_verification.csv` all PASS |
| D+8 | Results review: plausibility AMBERs, top-down benchmark, sector/obligor drivers | RPA with Credit Officers | Commentary on every AMBER |
| D+9 | Committee pack finalised from `reports/committee_pack.md`; dashboard circulated | RPA | Pack v1 |
| D+10 | Stress Testing Working Group | RPA presents | Actions logged |
| D+12 | Credit Risk Committee | CRO delegate | Decisions recorded |

## Run checklist
- [ ] Configuration change log reviewed (git diff of `config/`)
- [ ] Input hashes recorded in `manifest.json`
- [ ] No critical DQ rule unresolved (otherwise the run is blocked)
- [ ] All controls `C-01`…`C-05` PASS
- [ ] No plausibility FAIL; each AMBER has commentary
- [ ] R verification within tolerance
- [ ] Monitoring RAG reviewed; RED items raised with the model owner
- [ ] Results reproduced from manifest (same seed and inputs → same results SHA-256)

## Escalation
| Situation | Escalate to | Within |
|---|---|---|
| Critical DQ failure blocking the run | Data owner and Head of RPA | Same day |
| Ledger reconciliation break above tolerance | Group Finance | 1 day |
| Control failure (C-01…C-05) | Technology / Model Implementation | Same day; run not released |
| Plausibility FAIL or unexplained AMBER | Model owner, Model Validation | Before working group |
| Monitoring RED | Model owner; consider PMA via the PMA forum | Before committee |

## Re-running and audit
Every run folder contains `manifest.json` (inputs, git commit, package version, timings, results hash) and `run_log.txt`. To reproduce: check out the recorded commit and re-run with the same configuration; `UAT-E2E-003` proves byte-identical results.
