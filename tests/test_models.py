import numpy as np
import pandas as pd
import pytest

from cibst.engine import Shocks
from cibst.models.master_scale import CENTRAL_PD, UPPER_BOUND, grade_central_pd, pd_to_grade_num
from cibst.models.z_factor import ZFactorModel


def test_master_scale_monotone_and_consistent():
    assert np.all(np.diff(CENTRAL_PD) > 0)
    g = pd_to_grade_num(CENTRAL_PD)
    assert list(g) == list(range(1, len(CENTRAL_PD) + 1))
    assert np.all(CENTRAL_PD <= UPPER_BOUND)
    assert pd_to_grade_num(np.array([0.5]), np.array([True]))[0] == len(CENTRAL_PD) + 1
    assert grade_central_pd(np.array([len(CENTRAL_PD) + 1]))[0] == 1.0


def test_scorecard_signs_and_discrimination(small_run):
    coef = small_run.scorecard.fit_info.coefficients
    ratio_terms = coef[coef["expected_sign"].notna()]
    core = ratio_terms[ratio_terms["term"].isin(["ln_leverage", "margin_rel", "ln_current_ratio"])]
    assert core["sign_ok"].astype(bool).all()
    disc = small_run.monitoring["discrimination"].set_index("sample")
    assert disc.loc["development", "gini"] > 0.4


def test_scorecard_calibrated_to_long_run_default_rate(small_run):
    fit = small_run.scorecard.fit_info
    assert 0.005 < fit.long_run_default_rate < 0.05


def test_zfactor_recovers_known_relationship():
    rng = np.random.default_rng(0)
    years = np.arange(2000, 2030)
    macro = pd.DataFrame({"global_gdp_growth": rng.normal(3, 2, len(years)),
                          "unemployment_change": rng.normal(0, 0.5, len(years)),
                          "equity_return": rng.normal(8, 15, len(years))}, index=years)
    z = 0.5 * (macro["global_gdp_growth"] - 3) + 0.05 * rng.standard_normal(len(years))
    rho, pdbar = 0.10, 0.02
    from scipy.stats import norm
    dr = pd.Series(norm.cdf((norm.ppf(pdbar) - np.sqrt(rho) * z) / np.sqrt(1 - rho)), index=years)
    m = ZFactorModel().fit(dr, macro)
    assert "global_gdp_growth" in m.drivers
    assert m.coef.set_index("term").loc["global_gdp_growth", "coef"] > 0
    assert m.r2 > 0.8


def test_stress_increases_pd(small_run):
    r = small_run.results
    base = r["baseline"].summary["pd_wavg"].iloc[1]
    sev = r["severe"].summary["pd_wavg"].iloc[1]
    assert sev > 1.5 * base


def test_sensitivity_shocks_directional(small_run):
    eng = small_run.engine
    base = eng.run_scenario("adverse").summary["ecl"].iloc[-1]
    up = eng.run_scenario("adverse", Shocks(pd_mult=1.2)).summary["ecl"].iloc[-1]
    dn = eng.run_scenario("adverse", Shocks(gdp_add=1.0)).summary["ecl"].iloc[-1]
    assert up > base > dn
