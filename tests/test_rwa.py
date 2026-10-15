import numpy as np
import pytest

from cibst.metrics.rwa import irb_correlation, irb_risk_weight, maturity_adjustment

BCBS = {0.0003: 14.44, 0.001: 29.65, 0.005: 69.61, 0.01: 92.32, 0.02: 114.86, 0.05: 149.86, 0.10: 193.09, 0.20: 238.23}


@pytest.mark.parametrize("pd_, rw", list(BCBS.items()))
def test_bcbs_illustrative_risk_weights(pd_, rw):
    assert irb_risk_weight(np.array([pd_]), 0.45, 2.5)[0] * 100 == pytest.approx(rw, abs=0.01)


def test_correlation_bounds():
    r = irb_correlation(np.array([1e-6, 0.999]))
    assert r[0] == pytest.approx(0.24, abs=1e-4) and r[1] == pytest.approx(0.12, abs=1e-4)


def test_sme_adjustment_linear_in_turnover():
    base = irb_correlation(np.array([0.01]))[0]
    for s, cut in [(5, 0.04), (27.5, 0.02), (50, 0.0), (100, 0.0), (1, 0.04)]:
        assert irb_correlation(np.array([0.01]), np.array([float(s)]))[0] == pytest.approx(base - cut)


def test_maturity_adjustment_is_one_at_one_year_and_increasing():
    assert maturity_adjustment(np.array([0.02]), np.array([1.0]))[0] == pytest.approx(1.0)
    m = maturity_adjustment(np.full(5, 0.02), np.array([1, 2, 3, 4, 5.0]))
    assert np.all(np.diff(m) > 0)


def test_risk_weight_monotone_in_pd_and_lgd():
    pds = np.geomspace(0.0005, 0.3, 30)
    rw = irb_risk_weight(pds, 0.45, 2.5)
    assert np.all(np.diff(rw[:25]) > 0)
    assert irb_risk_weight(np.array([0.01]), 0.6, 2.5)[0] > irb_risk_weight(np.array([0.01]), 0.45, 2.5)[0]
