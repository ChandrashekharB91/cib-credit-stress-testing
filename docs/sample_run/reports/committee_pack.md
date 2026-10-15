# Management Stress Test — CIB Credit Portfolio

**Run:** `sample_MST_2026Q4`  
**Reporting date:** 2026-09-30  
**Horizon:** 3 years (2027–2029)  
**Prepared by:** Risk Portfolio Analytics (illustrative — synthetic data)  
**For:** Credit Risk Committee / Stress Testing Working Group

## 1. Executive summary

- **Severe scenario drives $9.5bn of cumulative impairments over 3 years (4.61% of starting EAD)**, with CET1 falling 202 bps to a trough of 11.98% in year 1 — above the 10.0% hurdle by 198 bps.
- **Credit RWA inflate by 26.0% at peak** in the severe scenario as obligors migrate down the rating scale, adding to the capital pressure from losses.
- **Losses are concentrated:** financial institutions, commodity traders, commercial real estate account for 53.0% of severe impairments; the top 10 obligors account for 19.0%.
- **IFRS 9:** probability-weighted ECL at the reporting date is $3,555m (1.73% coverage); Stage 2 peaks at 48.2% of EAD under severe stress vs 9.3% today.
- **Adverse scenario is manageable:** $5.2bn cumulative impairments, CET1 trough 13.40% (-60 bps).
- **Model risk:** 1 plausibility check(s) need attention and monitoring shows 3 red / 0 amber metric(s) — see sections 6 and 8.

## 2. Portfolio at the reporting date

| Metric | Value |
|---|---|
| Obligors / facilities | 1,498 / 3,203 |
| Committed limits / drawn | $249.3bn / $164.5bn |
| EAD (IFRS 9) | $205.4bn |
| Credit RWA (RW density) | $168.7bn (85.5%) |
| EAD-weighted PD (performing) | 2.26% |
| Stage 2 / Stage 3 share of EAD | 9.3% / 1.8% |
| Probability-weighted ECL (coverage) | $3,555m (1.73%) |
| Share of limits on F-IRB (large corporates) | 85.3% |

## 3. Scenarios

| Scenario | Global GDP (y1/y2/y3) | Unemployment peak | Policy rate peak | Oil trough | Equity y1 | Property cum. | IFRS 9 weight |
|---|---|---|---|---|---|---|---|
| baseline | +3.1% / +3.2% / +3.2% | 5.0% | 3.75% | $72 | +6% | +8% | 60.0% |
| adverse | +0.8% / +1.6% / +2.6% | 6.6% | 4.50% | $58 | -18% | -11% | 30.0% |
| severe | -2.2% / +0.0% / +2.2% | 8.4% | 6.00% | $40 | -38% | -31% | 10.0% |

- **Baseline:** Central case: global growth near trend, gradual policy easing, stable commodity prices.
- **Adverse:** Trade fragmentation: tariff escalation hits export-oriented Asian supply chains, sticky inflation delays easing, commodity prices soften and CRE values correct.
- **Severe:** Synchronised Asia-led downturn: China property and credit stress spills over to regional trade, a USD funding shock forces a rate spike, commodities collapse and global equities fall sharply before a slow recovery in year 3.

## 4. Results

| Scenario | ECL t0 | ECL peak | Cum. impairment | Loss rate | Stage 2 peak | Peak RWA | RWA uplift | CET1 trough | CET1 drawdown | Headroom vs hurdle |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline | 2,983 | 6,234 | 3,251 | 1.58% | 9.3% | 168,716 | 0.0% | 14.00% | +0 bps | +400 bps |
| adverse | 3,752 | 8,922 | 5,170 | 2.52% | 21.6% | 183,755 | 8.9% | 13.40% | -60 bps | +340 bps |
| severe | 6,400 | 15,869 | 9,469 | 4.61% | 48.2% | 212,629 | 26.0% | 11.98% | -202 bps | +198 bps |

*Amounts in USD m. Static balance sheet; no management actions or distributions.*

**Capital walk — severe scenario**

| Year | PPNR | Impairment | After-tax profit | IRB EL shortfall | Total RWA | CET1 | CET1 ratio |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 0 | 379,611 | 53,145 | 14.00% |
| 1 | 1,643 | 4,849 | -2,404 | 0 | 423,523 | 50,741 | 11.98% |
| 2 | 1,643 | 3,033 | -1,042 | 0 | 413,941 | 49,699 | 12.01% |
| 3 | 1,643 | 1,588 | 42 | 205 | 394,111 | 49,535 | 12.57% |

## 5. Key drivers (severe scenario)

**By sector**

| Sector | EAD t0 | Cum. impairment | Impairment rate | Share of losses | RWA uplift | Stage 2 peak |
|---|---|---|---|---|---|---|
| financial_institutions | 60,273 | 2,049 | 3.40% | 21.6% | 18.2% | 48.0% |
| commodity_traders | 22,295 | 1,675 | 7.51% | 17.7% | 82.0% | 82.5% |
| commercial_real_estate | 21,471 | 1,293 | 6.02% | 13.7% | 27.3% | 69.7% |
| oil_gas | 19,711 | 1,061 | 5.38% | 11.2% | 87.6% | 75.8% |
| utilities_infra | 34,943 | 871 | 2.49% | 9.2% | 0.0% | 7.8% |
| metals_mining | 12,669 | 738 | 5.82% | 7.8% | 50.5% | 86.7% |
| shipping_transport | 6,997 | 601 | 8.59% | 6.3% | 20.9% | 65.1% |
| tmt | 15,468 | 493 | 3.19% | 5.2% | 3.2% | 11.1% |
| manufacturing | 6,792 | 471 | 6.94% | 5.0% | 34.2% | 74.7% |
| consumer_retail | 4,766 | 217 | 4.55% | 2.3% | 19.7% | 53.3% |

**By region**

| Region | EAD t0 | Cum. impairment | Impairment rate |
|---|---|---|---|
| Greater China & North Asia | 66,959 | 3,324 | 4.96% |
| ASEAN & South Asia | 59,908 | 2,638 | 4.40% |
| Africa & Middle East | 51,611 | 2,512 | 4.87% |
| Europe & Americas | 26,907 | 995 | 3.70% |

**Top 10 obligor contributors**

| Obligor | Sector | Region | EAD t0 | PD t0 | PD peak | Impairment |
|---|---|---|---|---|---|---|
| OBL00262 | commodity_traders | GCNA | 1,700 | 3.46% | 29.49% | 329 |
| OBL01209 | financial_institutions | GCNA | 2,800 | 3.37% | 7.45% | 246 |
| OBL00735 | commodity_traders | GCNA | 2,504 | 1.23% | 18.58% | 195 |
| OBL01367 | metals_mining | AME | 2,851 | 6.03% | 30.70% | 180 |
| OBL01092 | financial_institutions | AME | 1,858 | 3.92% | 9.07% | 155 |
| OBL01284 | utilities_infra | GCNA | 3,000 | 3.87% | 4.16% | 152 |
| OBL00768 | financial_institutions | EA | 2,143 | 3.18% | 5.55% | 147 |
| OBL00974 | commodity_traders | EA | 1,260 | 2.30% | 15.32% | 144 |
| OBL00193 | commercial_real_estate | AME | 918 | 6.36% | 23.15% | 136 |
| OBL00119 | oil_gas | ASA | 1,302 | 2.32% | 29.30% | 121 |

**Rating migration (EAD-weighted, reporting date → year 3)**

| From \ To | Investment grade (CG01-05) | Sub-IG (CG06-10) | Watch (CG11-13) | Default |
|---|---|---|---|---|
| Investment grade (CG01-05) | 30.1% | 69.9% | 0.0% | 0.0% |
| Sub-IG (CG06-10) | 0.0% | 59.1% | 40.9% | 0.0% |
| Watch (CG11-13) | 0.0% | 0.0% | 100.0% | 0.0% |
| Default | 0.0% | 0.0% | 0.0% | 100.0% |

## 6. Benchmarking and plausibility

| Scenario | Bottom-up cum. PD | Top-down cum. PD (capped Z) | Top-down cum. PD (uncapped) | BU / TD |
|---|---|---|---|---|
| baseline | 6.18% | 5.15% | 5.15% | 1.20x |
| adverse | 9.68% | 11.60% | 11.60% | 0.83x |
| severe | 19.36% | 17.86% | 28.34% | 1.08x |

Top-down challenger: Vasicek Z-factor, drivers = unemployment_change, rho = 0.099, adj. R² = 0.86, Durbin-Watson = 2.45. Projections are capped at the historical Z range [-2.74, 1.55] to prevent extrapolation.

| Check | Description | Value | Status |
|---|---|---|---|
| PL-01 | ECL ordered baseline <= adverse <= severe at every date | ordered | PASS |
| PL-02 | Peak RWA ordered across scenarios | baseline 168,716, adverse 183,755, severe 212,629 | PASS |
| PL-03 | CET1 trough ordered across scenarios | baseline 14.00%, adverse 13.40%, severe 11.98% | PASS |
| PL-04 | All PDs finite and within [0, 1] | ok | PASS |
| PL-05 | Year-1 Stage 2 share rises with scenario severity | baseline 8.4%, adverse 21.6%, severe 41.1% | PASS |
| PL-06 | ECL coverage within [0, 100%] | max 7.43% | PASS |
| PL-07 | Severe cumulative impairment / starting EAD below plausibility ceiling | 4.61% | PASS |
| PL-08-BAS | Bottom-up vs top-down cumulative 3y PD (baseline) | BU 6.18% / TD 5.15% = 1.20x | PASS |
| PL-09-BAS | Satellite drivers inside calibration range (baseline) | all inside | PASS |
| PL-08-ADV | Bottom-up vs top-down cumulative 3y PD (adverse) | BU 9.68% / TD 11.60% = 0.83x | PASS |
| PL-09-ADV | Satellite drivers inside calibration range (adverse) | all inside | PASS |
| PL-08-SEV | Bottom-up vs top-down cumulative 3y PD (severe) | BU 19.36% / TD 17.86% = 1.08x | PASS |
| PL-09-SEV | Satellite drivers inside calibration range (severe) | unemployment_change | AMBER |
| PL-10 | Commodity collapse: commodity sectors' severe/baseline loss multiple above portfolio | oil_gas 4.7x, metals_mining 4.8x, commodity_traders 4.8x vs portfolio 2.9x | PASS |
| PL-11 | Probability-weighted ECL lies between scenario ECLs | 3,555 in [2,983, 6,400] | PASS |
| PL-12 | Stage allocation conserves exposure (S1 + S2 + S3 = EAD) | max rel diff 1.4e-16 | PASS |
| PL-13 | Baseline CET1 change is moderate (baseline is not a stress) | +115 bps | PASS |

## 7. Sensitivities (severe scenario)

| Shock | Δ cum. impairment | Δ peak RWA | Δ CET1 trough |
|---|---|---|---|
| PD x1.20 | +1,183 | +6,794 | -37 bps |
| PD x0.80 | -1,333 | -11,539 | +42 bps |
| LGD +5pp | +1,589 | +4,562 | -18 bps |
| LGD -5pp | -1,589 | -3,563 | -3 bps |
| CCF +10pp | +510 | +1,212 | -8 bps |
| CCF -10pp | -496 | -1,017 | +7 bps |
| GDP -1pp | +1,447 | +1,929 | -35 bps |
| GDP +1pp | -1,224 | -3,990 | +24 bps |
| Oil x0.80 | +1,209 | +532 | -18 bps |
| Oil x1.20 | -991 | -4,290 | +23 bps |
| Rates +100bp | +148 | +568 | -3 bps |
| Rates -100bp | -142 | -1,338 | +6 bps |

Largest single sensitivity: **PD x1.20** (-37 bps on the CET1 trough).

## 8. Model monitoring

| Area | Metric | Value | Threshold | Status |
|---|---|---|---|---|
| Stability | Score PSI (dev vs current) | 0.021 | amber 0.1 / red 0.25 | GREEN |
| Stability | Max characteristic CSI | 0.358 | amber 0.1 / red 0.25 | RED |
| Discrimination | Gini relative drop (OOT vs dev) | 0.099 | amber 10% / red 20% | GREEN |
| Calibration | Grades failing Jeffreys test (OOT) | 2.000 | any red grade -> RED; any amber -> AMBER | RED |
| Calibration | Hosmer-Lemeshow p-value (OOT) | 0.135 | amber < 0.05 / red < 0.01 | GREEN |
| Satellite | Z-factor OOS RMSE / in-sample RMSE | 3.754 | amber > 1.5 / red > 2.5 | RED |

- Largest characteristic shift: **ln_icr** (CSI 0.36) — consistent with the higher policy-rate environment compressing interest cover relative to the development sample.
- Latest year (2025) observed default rate 3.93% vs mean PD 1.99% (Jeffreys p = 0.000).

## 9. Data quality

| Rule | Description | Severity | Records | Exposure impacted | Resolution |
|---|---|---|---|---|---|
| DQ-001 | Sector must be populated | critical | 6 | 498 | REMEDIATED: sector derived from industry code |
| DQ-002 | Revenue must be strictly positive | critical | 2 | 531 | ESCALATED: excluded from run, raised with data owner |
| DQ-003 | EBITDA cannot exceed revenue | major | 4 | 728 | REMEDIATED: EBITDA restated at sector-norm margin; credit officer review requested |
| DQ-004 | Financial statements no older than 18 months at the reporting date | major | 59 | 6,506 | REMEDIATED: one-notch conservative PD overlay (post-model adjustment) |
| DQ-005 | Drawn balance cannot exceed approved limit | major | 17 | 2,345 | REMEDIATED: drawn capped at limit; limit breach referred to credit admin |
| DQ-006 | Remaining maturity must be positive | major | 10 | 635 | REMEDIATED: remaining maturity set to 1 year (conservative IRB M floor) |
| DQ-007 | Every facility must reference an existing obligor | critical | 2 | 43 | ESCALATED: excluded from run, raised with data owner |
| DQ-008 | Facility identifiers must be unique | critical | 3 | 8 | REMEDIATED: duplicate rows removed (first occurrence kept) |
| DQ-009 | Collateral value cannot be negative | minor | 4 | 1,364 | REMEDIATED: collateral value set to zero (no credit risk mitigation) |
| DQ-010 | Drawn balances reconcile to finance ledger control totals by region (0.5% tolerance) | major | 2 | 358 | ESCALATED: ledger break referred to Group Finance; results flagged |

## 10. Key assumptions and limitations

- Static balance sheet: maturing facilities are replaced like-for-like; defaulted exposures are not replaced and are not written off within the horizon.
- No management actions, dividends or AT1 coupons; pre-provision net revenue held flat at 80 bps of starting EAD; non-modelled RWA held flat.
- Stressed PDs come from re-rating projected financial statements with the corporate scorecard (TTC-calibrated); no separate PIT overlay — the top-down Z-factor model is used as a challenger only.
- Financial institutions are scored with the corporate scorecard as a simplification; a dedicated FI model (capital, liquidity, asset quality) would be used in production.
- LGD reflects collateral revaluation along the scenario; downturn LGD is a fixed add-on; CCF stress is a scenario-level utilisation uplift on undrawn commitments.
- SICR test uses the rating PD at each reporting date against origination PD; watchlist and 30 dpd backstops apply.
- All data are synthetic; results illustrate the methodology and are not representative of any institution.

## 11. Proposed actions for the committee

1. Note the severe-scenario CET1 trough of 11.98% and headroom of 198 bps to the 10.0% hurdle.
2. Review risk appetite and concentration limits for financial institutions, the largest loss contributor.
3. Commission a model-monitoring deep dive (calibration and characteristic stability) with the model owner; consider a temporary post-model adjustment pending review.
4. Track open data-quality escalations (excluded records and ledger break) to closure with Data Owners and Group Finance before the next run.

## Appendix — run controls

| control | scenario | description | status |
|---|---|---|---|
| C-01 | baseline | Facility count: post-DQ input vs engine output | PASS |
| C-02 | baseline | Reporting-date EAD: recomputed from post-DQ input file vs engine output | PASS |
| C-01 | adverse | Facility count: post-DQ input vs engine output | PASS |
| C-02 | adverse | Reporting-date EAD: recomputed from post-DQ input file vs engine output | PASS |
| C-01 | severe | Facility count: post-DQ input vs engine output | PASS |
| C-02 | severe | Reporting-date EAD: recomputed from post-DQ input file vs engine output | PASS |
| C-03 | all | Reporting-date EAD identical across scenarios | PASS |
| C-04 | all | Reporting-date RWA identical across scenarios | PASS |
| C-05 | baseline | Sector ECL sums to portfolio ECL | PASS |
| C-05 | adverse | Sector ECL sums to portfolio ECL | PASS |
| C-05 | severe | Sector ECL sums to portfolio ECL | PASS |
