# UAT cycle history

## Cycle 1 — 23 / 25 passed, 2 defects raised

| Defect | Test | Severity | Finding | Root cause | Resolution | Re-test |
|---|---|---|---|---|---|---|
| DEF-001 | UAT-RWA-004 | S2 | Test expected the maturity adjustment to equal 1 at M = 2.5; engine returned 1.2598 | **Test-specification error.** Per CRE31 the adjustment (1 + (M − 2.5)b) / (1 − 1.5b) equals 1 at **M = 1**, not 2.5. The engine was correct | Expected result corrected and agreed with the model owner; added a unit test that the adjustment is 1 at M = 1 and increasing in M | Pass (cycle 2) |
| DEF-002 | UAT-RPT-001 | S2 | Committee pack had 10 of 11 numbered sections when sensitivities were not run | **Engine defect.** Optional sections were omitted rather than stated as not run, breaking section numbering and cross-references | Pack now always renders sections 7 and 8 with a "not run in this execution" note | Pass (cycle 2) |

A third issue was corrected in the catalogue during cycle 1 review: the hand-calculated expected value for UAT-ECL-002 was stated as 2.216935; recomputing the closed form (0.780720 + 0.728672 + 0.680094) gives **2.189486**, which the engine matched.

## Cycle 2 — 25 / 25 passed, 0 open defects
Exit criteria met; R verification 60 / 60 comparisons within 1e-8. Sign-off report: `uat/results/uat_signoff.md`.

## Negative testing — seeded defects
| Seeded defect | Caught by |
|---|---|
| IRB effective maturity not bounded to [1, 5] | UAT-RWA-004 (unit) and UAT-RVER-001 (independent R) |
| SICR absolute-threshold condition dropped | UAT-RVER-002 (independent R) — unit tests call the correct function directly, so only end-to-end independent recomputation exposes it |
| CCF not applied to undrawn RCF commitments | UAT-E2E-001 (control C-02: EAD recomputed from input files) |

Lesson recorded: unit tests alone would have missed the SICR defect; independent end-to-end recomputation and reconciliation controls are both necessary.
