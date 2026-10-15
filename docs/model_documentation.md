# Model documentation — CIB Credit Management Stress Testing (MST) engine

| Item | Detail |
|---|---|
| Model name | `cibst` — CIB credit MST engine (bottom-up stressed financials with top-down challenger) |
| Version | 1.0.0 |
| Purpose | Project credit losses (IFRS 9 ECL), credit RWA and CET1 impact of the Corporate & Institutional Banking loan book under management stress scenarios |
| Uses | Management stress testing, risk appetite calibration, ICAAP-style capital planning, portfolio insight for credit committees |
| Model type | Composite: satellite (macro → financials) + PD scorecard + LGD/EAD + IFRS 9 ECL + Basel IRB capital |
| Proposed MRM tier | Tier 1 (material, feeds capital planning) — components individually tiered below |
| Data | **Synthetic and seeded** — the repository demonstrates methodology, controls and delivery, not any institution's portfolio |

---

## 1. Scope and model inventory

| Component | Module | Role | Proposed tier |
|---|---|---|---|
| Macro scenarios | `config/scenarios.yaml`, `data/macro.py` | Baseline / adverse / severe 3-year annual paths, regional GDP | Input (owned by Scenario Design) |
| Stressed financials satellite | `models/stressed_financials.py` | Projects revenue, EBITDA, interest, cash and debt per obligor | Tier 1 |
| PD scorecard + master scale | `models/pd_scorecard.py`, `models/master_scale.py` | Re-rates obligors on projected financials; 13 performing grades + D | Tier 1 |
| LGD / EAD | `models/lgd_ead.py` | Collateral-sensitive LGD; CCF with scenario utilisation stress | Tier 2 |
| Top-down challenger | `models/z_factor.py` | Vasicek single-factor credit-cycle index linked to macro drivers | Tier 2 (benchmark only) |
| IFRS 9 ECL | `metrics/ecl.py` | Staging, 12-month and lifetime ECL, scenario weighting | Tier 1 |
| IRB RWA | `metrics/rwa.py` | Basel CRE31 / Basel 3.1 corporate and FI capital function | Tier 1 (regulatory formula) |
| Capital projection | `metrics/capital.py` | Impairment, PPNR, IRB EL shortfall, CET1 ratio | Tier 2 |
| Controls and checks | `dq/`, `analysis/`, `monitoring/`, `pipeline.py` | DQ, reconciliations, plausibility, sensitivity, monitoring | Non-model tools (EUC controls) |

## 2. Data

### 2.1 Synthetic generator (`data/portfolio.py`)
The generator embeds a known *true* credit model so every downstream component can be tested against ground truth:

* **Obligor financials** by sector: lognormal revenue, EBITDA margin around a sector norm, lognormal gross leverage, liquidity (current ratio), floating-rate share, fixed coupon and floating spread; interest expense is consistent with debt and the policy rate.
* **True TTC log-odds** = intercept + 1.00·ln(Debt/EBITDA) − 0.80·ln(EBITDA/interest) − 1.20·margin_rel − 0.60·ln(current ratio) − 0.12·(ln revenue − 6) + sector premium + **unobserved term** (σ = 0.5). The intercept is solved so that the reference-population mean PD is 2%.
* **Default history 2006–2025**: 1,500 obligor-years per year; margins co-move with GDP (cyclicality by sector), and an additional systematic factor Z_t (macro-driven plus shock, clipped at ±2.5σ) produces defaults through a one-factor Vasicek mechanism (ρ = 0.08).
* **Reporting-date portfolio**: 1,500 obligors across 10 CIB sectors and 4 regions, 1–4 facilities each (term loans, RCFs, trade finance, guarantees), seniority, collateral (property, commodity, receivables, cash), remaining maturity, EIR, origination PD, days past due, 1.2% already in default. Single-name limits are capped at USD 3bn.
* **Finance ledger** control totals by region, with a seeded break in one region.
* **Seeded data defects** across 10 rules (completeness, validity, consistency, timeliness, integrity, uniqueness, reconciliation) so the DQ engine is tested against known issues.

### 2.2 Data-quality framework (`dq/engine.py`, `config/dq_rules.yaml`)
Each rule has an ID, table, DQ dimension, severity (critical / major / minor) and a remediation action. Every failing record is logged with the action taken; exposure impacted is quantified for materiality. Remediations include deriving sector from industry code, capping drawn at limit, a **one-notch conservative PD overlay for stale financials** (a post-model adjustment), exclusion with escalation, and escalation of ledger breaks to Finance. A run is **blocked** if any critical rule remains unresolved.

## 3. Methodology

### 3.1 Scenarios
Three internally consistent 3-year annual scenarios (`config/scenarios.yaml`): baseline (trend growth), adverse (trade fragmentation) and severe (synchronised Asia-led downturn with commodity collapse and USD rate shock). Variables: regional real GDP growth (4 regions), global GDP, unemployment, policy rate, oil price, equity return, property price growth. IFRS 9 weights 60 / 30 / 10.

### 3.2 Stressed financials (bottom-up)
For each obligor *i* in sector *s*, region *r* and year *t*:

* Revenue growth: g = trend_s + β_gdp,s (GDP_r,t − trend_r) + β_oil,s ΔOil_t + β_prop,s (ΔProperty_t − 3%)
* EBITDA margin (operating leverage): m_t = m_{t−1} + (DOL_s − 1)(g − trend_s) m_0, bounded to [−0.5 m_0, max(1.5 m_0, m_0 + 5pp)]
* Interest: debt_{t−1} × [fixed share × coupon + floating share × (policy rate_t + spread)]
* Capex cut by up to 50% when revenue under-performs; tax at 25% of positive EBIT
* Free cash flow accrues to cash; excess over the target cash balance is distributed; any shortfall below 2% of revenue is funded by **drawing additional debt** — leverage therefore rises endogenously in stress
* Liquidity: current ratio moves with cash relative to target

Projected ratios are re-scored with the PD scorecard to obtain PD_i,t (t = 0..3). Defaulted obligors carry PD = 1. Stale-financials overlays from the DQ step are applied multiplicatively.

### 3.3 PD scorecard and master scale
Logistic regression on ln_leverage, ln_icr, margin_rel (margin relative to sector norm), ln_current_ratio, ln_revenue and sector effects, fitted on 2006–2021 (24,000 obligor-years, 440 defaults) with 2022–2025 out of time. The intercept is shifted so that the mean PD equals the long-run default rate of the development sample (1.83%) — a through-the-cycle central tendency.

| Term | Coef. | Std. err. | p-value | Expected sign |
|---|---|---|---|---|
| ln_leverage | +1.843 | 0.256 | <0.001 | + ✓ |
| ln_icr | −0.172 | 0.237 | 0.469 | − ✓ (not significant) |
| margin_rel | −1.626 | 0.169 | <0.001 | − ✓ |
| ln_current_ratio | −0.851 | 0.165 | <0.001 | − ✓ |
| ln_revenue | −0.049 | 0.043 | 0.260 | − ✓ (not significant) |

Discrimination: Gini 0.573 (95% bootstrap CI 0.528–0.619) development, 0.516 (0.441–0.592) out of time; the true data-generating PD achieves ≈0.60, so the scorecard captures most of the available signal. ln_icr is not significant because interest cover is close to collinear with leverage (ICR ≈ 1 / (leverage × rate)); it is retained on expert judgement because it is the only channel through which a **rate shock** reaches the PD — see enhancement backlog item E-01.

Master scale: 13 performing grades CG01–CG13 with geometric central PDs from 0.05% to 25% (boundaries at geometric means), plus D. CG01–05 ≈ investment grade; CG12+ is the watchlist used as an IFRS 9 backstop.

### 3.4 LGD
LGD = (1 − c) × base + c × workout cost, with c = min(1, collateral value × (1 − haircut) / EAD); base 45% senior, 75% subordinated, workout cost 5%, floor 5%. Collateral values move along the scenario: property with property prices, commodity with oil, receivables with GDP under-performance. Downturn LGD = LGD_0 + 8pp (A-IRB capital).

### 3.5 EAD
EAD = drawn + CCF × undrawn with modelled CCFs (RCF 60%, trade 20%, guarantees 50%); stressed CCF adds +5pp (adverse) / +10pp (severe) to non-term products from year 1 to reflect drawdowns in stress.

### 3.6 Top-down challenger (Vasicek Z-factor)
* ρ from the variance of probit default rates: v = Var(Φ⁻¹(DR_t)), ρ = v / (1 + v) → ρ̂ = 0.099
* Implied index Z_t = [Φ⁻¹(PD̄) − √(1−ρ) Φ⁻¹(DR_t)] / √ρ
* Driver selection rule (documented, automated): all coefficients with expected signs and p < 0.10, then **lowest leave-one-year-out CV RMSE** (robust to a single influential year such as 2020). Five specifications are tested; the selected model is Z_t = 0.07 − 1.92 ΔUnemployment_t (adj. R² 0.86, DW 2.45).
* PD_i | Z = Φ([Φ⁻¹(PD_i) − √ρ Z] / √(1−ρ)). Projections are **capped at the historical Z range** to prevent extrapolation; out-of-range drivers are flagged (the severe scenario's +2.3pp unemployment jump exceeds the historical maximum).

The challenger is used for **benchmarking only**: cumulative 3-year PDs from the bottom-up engine are compared with the top-down view (tolerance 1 ± 0.5x).

### 3.7 IFRS 9 ECL and staging
Expected-value (survival-weighted) mechanics per facility, scenario and reporting date t:

* Annual PD curve q_y: scenario PDs for y ≤ 3; afterwards logit-linear reversion to the reporting-date PD over 2 years
* Survival S_t = Π(1 − q_y); the defaulted fraction (1 − S_t) is Stage 3 with ECL = LGD_t × EAD_t
* Static balance sheet: facilities that mature are rolled over at the same tenor; remaining maturity drives the lifetime horizon (max 10 years); the final partial year uses q̃ = 1 − (1 − q)^f
* Discounting at the EIR, mid-period
* EL12 = first-period loss; ELlife = sum over remaining periods
* **SICR** (Stage 2) if rating PD at t > 2.5× origination PD **and** the increase exceeds 50 bps; backstops: watchlist grade (CG12+) and 30 days past due
* Reported reporting-date ECL is the **probability-weighted** average of scenario ECLs (60 / 30 / 10)

### 3.8 Basel IRB RWA
Corporate IRB function (BCBS CRE31): correlation R = 0.12w + 0.24(1 − w), w = (1 − e^{−50PD}) / (1 − e^{−50}); SME firm-size adjustment for turnover < 50m; ×1.25 for large regulated FIs (assets ≥ 100bn); maturity adjustment (1 + (M − 2.5)b) / (1 − 1.5b), b = (0.11852 − 0.05478 ln PD)², M bounded [1, 5]; K = [LGD·N((G(PD) + √R G(0.999)) / √(1 − R)) − PD·LGD] × MA; RWA = 12.5 K EAD.

* **Approach**: obligors with revenue > USD 500m are restricted to F-IRB (Basel 3.1 large-corporate rule): supervisory LGD 40% senior (45% FI, 75% subordinated) blended with secured LGDs for eligible collateral after supervisory haircuts; supervisory CCFs (commitments 40%, trade 20%, transaction-related 50%)
* A-IRB: max(downturn LGD, best-estimate LGD) subject to Basel 3.1 LGD floors (25% unsecured; 10–15% secured)
* PD from the **grade central PD** at each date (rating migration drives RWA), floored at 5 bps
* Defaulted fraction: F-IRB K = 0; A-IRB K = max(0, downturn LGD − best-estimate LGD)
* The formula reproduces the BCBS illustrative corporate risk-weight table to within 0.01pp for 19 PDs (UAT-RWA-001)

### 3.9 Capital projection
Impairment_t = ECL_t − ECL_{t−1}; after-tax profit = (PPNR − impairment) × (1 − 25%); IRB EL shortfall max(0, regulatory EL − ECL) deducted from CET1; CET1 ratio = CET1 / (portfolio RWA + other RWA). Starting CET1 ratio 14.0%, other RWA 1.25× portfolio RWA, PPNR 80 bps of starting EAD, hurdle 10%.

**Interaction worth noting:** because 85% of limits are on F-IRB, a lower best-estimate LGD reduces ECL but not regulatory EL, increasing the IRB shortfall deduction — so the "LGD −5pp" sensitivity lowers impairments by ~USD 1.6bn yet leaves the CET1 trough slightly lower (−3 bps).

## 4. Validation, testing and benchmarking

| Layer | What it does | Where |
|---|---|---|
| Unit and integration tests | 35 pytest cases: BCBS risk weights, SME/FI adjustments, ECL hand calculations, staging rules, reversion, Z-factor recovery of a known relationship, scenario ordering, controls | `tests/` |
| UAT / UVT catalogue | 25 cases with requirement IDs, expected results derived independently, defect log and sign-off report | `uat/` |
| Independent re-implementation | Base-R recomputation of RWA, regulatory EL, survival, staging and ECL for every facility × scenario × date (60 comparisons, ≤1e-8) | `uat/r_verification/` |
| Seeded-defect demonstrations | Three seeded defects, each caught by a different layer (unit test, R verification, reconciliation control) | `uat/run_uat.py --inject-defect` |
| Run controls | Facility counts, EAD recomputation from input files, cross-scenario consistency, sector-to-portfolio aggregation | `pipeline._controls` |
| Plausibility checks | 17 checks: scenario ordering of ECL/RWA/CET1, Stage 2 response, coverage bounds, loss-rate ceiling, top-down benchmark, driver range, commodity-sector response, weighted ECL bounds, exposure conservation, baseline stability | `analysis/plausibility.py` |
| Sensitivity analysis | One-at-a-time shocks to PD, LGD, CCF, GDP, oil, rates around the severe scenario | `analysis/sensitivity.py` |

## 5. Ongoing monitoring

| Area | Metric | Thresholds (amber / red) |
|---|---|---|
| Stability | Score PSI, development vs current portfolio | 0.10 / 0.25 |
| Stability | Characteristic CSI (max over drivers) | 0.10 / 0.25 |
| Discrimination | Relative Gini drop, out-of-time vs development | 10% / 20% |
| Calibration | Per-grade Jeffreys test (one-sided, α = 5%) | any amber / any red grade |
| Calibration | Hosmer–Lemeshow (out of time) | p < 0.05 / p < 0.01 |
| Satellite | Z-factor out-of-sample RMSE ÷ in-sample RMSE | 1.5 / 2.5 |

Findings in the sample run: score PSI 0.02 (green) but **ln_icr CSI 0.36 (red)** — interest cover has shifted because the policy rate (4%) is well above the development-sample average; **calibration red** — two grades fail the Jeffreys test (CG03 red on 2 defaults in 179, CG09 amber) and the latest year is under-predicted (2025 observed default rate 3.9% vs mean PD 2.0%); Hosmer–Lemeshow remains green (p = 0.14); and the **satellite model under-predicts 2025** (OOS/IS RMSE 3.8×). Recommended actions: deep-dive with the model owner, consider a temporary post-model adjustment, and schedule recalibration including the 2022–2025 period.

## 6. Assumptions and limitations register

| ID | Assumption / limitation | Impact | Mitigation |
|---|---|---|---|
| L-01 | Data are synthetic | Results are illustrative only | Generator embeds known truth so the methodology can be tested |
| L-02 | Static balance sheet, no write-offs within horizon | Stage 3 stock accumulates; RWA of defaulted fraction falls away | Documented; dynamic balance sheet is backlog item E-04 |
| L-03 | No management actions, distributions or PPNR stress | CET1 path ignores mitigants and revenue stress | PPNR held flat and conservative; sensitivity can be added |
| L-04 | Scorecard is TTC-calibrated; PIT effect comes only through financials | May under-state year-1 PD jumps not visible in financials | Top-down challenger benchmark; post-model adjustment if gap persists |
| L-05 | FIs scored with the corporate scorecard | FI PDs are a simplification | Dedicated FI model (capital, liquidity, asset quality) — E-03 |
| L-06 | Single-factor top-down challenger with 16 annual observations | Wide parameter uncertainty; extrapolation in severe | Z capped at historical range; out-of-range flag |
| L-07 | Downturn LGD as fixed add-on; CCF stress as scenario uplift | Simplified downturn and utilisation dynamics | Sensitivities on LGD and CCF |
| L-08 | SICR uses 12m rating PD vs origination 12m PD | Lifetime-PD comparison preferred under IFRS 9 | Acceptable proxy; E-02 |
| L-09 | ln_icr and ln_revenue not statistically significant | Model parsimony | Retained on expert judgement; E-01 |

## 7. Governance and MRM alignment

| Principle (SR 11-7 / PRA SS1/23) | How the repository evidences it |
|---|---|
| Model identification and inventory | Component inventory and proposed tiering (section 1) |
| Conceptual soundness | Documented methodology with formulas; expected-sign and significance tests; documented driver-selection rule |
| Data quality | Rules engine with severity, remediation, issue log and run blocking |
| Independent validation | Independent R re-implementation; BCBS benchmark; seeded-defect tests |
| Outcome analysis and monitoring | Back-testing, calibration tests, stability metrics with RAG thresholds |
| Use and limitations | Limitations register; committee pack states assumptions and limitations |
| Change control and reproducibility | Config-driven runs, input hashing, git commit and results SHA-256 in every manifest; reproducibility test |
| Post-model adjustments | PD overlay for stale financials logged per obligor; monitoring recommends PMA governance |

Roles: **model owner** (CCIB Modelling), **model user / application owner** (Risk Portfolio Analytics — this engine's runs, UAT and reporting), **independent validator** (Model Validation), **data owners** (Risk & CFCC Data), **scenario owner** (ERM Scenario Design).

## 8. Enhancement backlog

| ID | Enhancement |
|---|---|
| E-01 | Re-specify interest-cover channel (e.g. EBITDA / (interest + scheduled amortisation)) or replace with a rate-sensitivity overlay; re-test significance |
| E-02 | Lifetime-PD SICR test against origination lifetime PD |
| E-03 | Dedicated FI scorecard |
| E-04 | Dynamic balance sheet with new lending and write-offs |
| E-05 | Rating-migration matrices conditioned on Z (credit-cycle-adjusted transition matrices) as a second challenger |
| E-06 | Joint PPNR stress (margin compression, fee income) |
