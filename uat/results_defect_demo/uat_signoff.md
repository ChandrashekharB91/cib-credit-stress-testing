# UAT / UVT sign-off report — CIB Management Stress Testing engine

- **Date:** 2026-10-15
- **Build:** package 1.0.0, git `caafa34`
- **Environment:** Python 3.13.16; 
- **Run under test:** `uat_main` (results SHA-256 `4ea85f40217c9ae7…`)
- **Seeded defect:** SICR absolute-threshold condition dropped (relative test applied alone)

## Summary

**24 of 25 test cases passed.** 1 defect(s) raised, 1 blocking (S1/S2).

| Area | Passed |
|---|---|
| Data quality | 2/2 |
| ECL | 5/5 |
| End to end | 5/5 |
| Independent verification | 1/2 |
| RWA | 6/6 |
| Reporting | 1/1 |
| Staging | 4/4 |

## Exit criteria

- All S1 and S2 test cases passed: **No**
- No open S1/S2 defects: **No**
- Independent R verification within 1e-8: **No**

**Recommendation:** Exit criteria NOT met — do not promote; remediate and re-test the defects below.

## Defects

| ID | Test | Severity | Summary | Status |
|---|---|---|---|---|
| DEF-001 | UAT-RVER-002 | S1 | REQ-UVT-02 Independent recomputation of survival, staging and ECL: expected Differences <= 1e-8 relative; actual 36 comparisons, 24 failed; max rel diff 5.2e-03 | Open |

## Test results

| Test | Area | Result | Actual |
|---|---|---|---|
| UAT-RWA-001 | RWA | PASS | max abs diff 0.0066 pp over 19 PDs |
| UAT-RWA-002 | RWA | PASS | R base 0.192784, S=5 0.152784, S=27.5 0.172784, S=60 0.192784 |
| UAT-RWA-003 | RWA | PASS | ratio 1.250000000000 |
| UAT-RWA-004 | RWA | PASS | M range [1.00, 5.00]; MA(M=1) = 1.000000 |
| UAT-RWA-005 | RWA | PASS | min regulatory PD 0.000500 |
| UAT-RWA-006 | RWA | PASS | max abs diff 0.00e+00 over 468 defaulted facility-dates |
| UAT-ECL-001 | ECL | PASS | ECL 0.780720 vs 0.780720 |
| UAT-ECL-002 | ECL | PASS | ECL 2.189486 vs 2.189486 |
| UAT-ECL-003 | ECL | PASS | ECL 0.397146 vs 0.397146 |
| UAT-ECL-004 | ECL | PASS | PD(H+1) 0.028784 vs 0.028784; PD(H+2) 0.010000 |
| UAT-ECL-005 | ECL | PASS | weighted ECL 3,556.371 vs 3,556.371 |
| UAT-STG-001 | Staging | PASS | stage flags [1, 2] |
| UAT-STG-002 | Staging | PASS | stage 2 |
| UAT-STG-003 | Staging | PASS | stage 2 |
| UAT-STG-004 | Staging | PASS | ECL 45.0000, survival 0, stage2 False |
| UAT-DQ-001 | Data quality | PASS | 10 rules seeded; min recall 100% |
| UAT-DQ-002 | Data quality | PASS | 59 obligors with overlay x1.641; 59 stale |
| UAT-E2E-001 | End to end | PASS | 11 controls, 0 failed |
| UAT-E2E-002 | End to end | PASS | 17 checks: {'PASS': 16, 'AMBER': 1} |
| UAT-E2E-003 | End to end | PASS | 4ea85f40217c vs 4ea85f40217c |
| UAT-E2E-004 | End to end | PASS | 4ea85f40217c vs ae518c317f0e |
| UAT-E2E-005 | End to end | PASS | missing []; 11 steps OK=True |
| UAT-RVER-001 | Independent verification | PASS | 24 comparisons, 0 failed; max rel diff 2.1e-17 |
| UAT-RVER-002 | Independent verification | FAIL | 36 comparisons, 24 failed; max rel diff 5.2e-03 |
| UAT-RPT-001 | Reporting | PASS | 11/11 sections; sheets ok=True |
