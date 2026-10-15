import numpy as np
import pytest
from scipy.special import expit, logit

from cibst.metrics.ecl import ECLInputs, annual_pd_curve, compute_ecl


def single(cfg, pd_path, **kw):
    pd_path = np.atleast_2d(pd_path)
    h1 = pd_path.shape[1]
    d = dict(lgd=0.4, ead=100.0, maturity=3.0, eir=0.05, orig_pd=pd_path[0, 0], grade=8, dpd=0, defaulted=False)
    d.update(kw)
    return compute_ecl(ECLInputs(
        pd_path=pd_path, lgd=np.full((1, h1), d["lgd"]), ead=np.full((1, h1), d["ead"]),
        maturity=np.array([d["maturity"]]), eir=np.array([d["eir"]]), origination_pd=np.array([d["orig_pd"]]),
        grade_path=np.full((1, h1), d["grade"]), dpd=np.array([d["dpd"]]), defaulted=np.array([d["defaulted"]])), cfg)


def test_stage1_twelve_month_ecl(cfg):
    r = single(cfg, [[0.02, 0.02]])
    assert r["ecl"][0, 0] == pytest.approx(0.02 * 0.4 * 100 * 1.05 ** -0.5)


def test_stage2_lifetime_ecl(cfg):
    r = single(cfg, [[0.02, 0.02]], grade=cfg["ifrs9"]["watchlist_grade"])
    exp = sum(0.98 ** (k - 1) * 0.02 * 40 * 1.05 ** -(k - 0.5) for k in (1, 2, 3))
    assert r["ecl"][0, 0] == pytest.approx(exp)


def test_lifetime_exceeds_twelve_month(cfg):
    r = single(cfg, [[0.03, 0.03, 0.03, 0.03]], maturity=5.0)
    assert r["ellife"][0, 0] > r["el12"][0, 0]


def test_sicr_requires_relative_and_absolute(cfg):
    assert not single(cfg, [[0.006, 0.006]], orig_pd=0.002)["stage2"][0, 0]
    assert single(cfg, [[0.03, 0.03]], orig_pd=0.01)["stage2"][0, 0]
    assert not single(cfg, [[0.03, 0.03]], orig_pd=0.02)["stage2"][0, 0]


def test_dpd_backstop(cfg):
    assert single(cfg, [[0.01, 0.01]], dpd=30)["stage2"][0, 0]
    assert not single(cfg, [[0.01, 0.01]], dpd=29)["stage2"][0, 0]


def test_survival_and_stage3(cfg):
    r = single(cfg, [[0.02, 0.10, 0.20]])
    assert r["survival"][0, 1] == pytest.approx(0.90)
    assert r["survival"][0, 2] == pytest.approx(0.90 * 0.80)
    assert r["ecl_s3"][0, 2] == pytest.approx((1 - 0.72) * 0.4 * 100)


def test_defaulted_facility(cfg):
    r = single(cfg, [[1.0, 1.0]], lgd=0.45, defaulted=True)
    assert r["ecl"][0, 1] == pytest.approx(45.0) and not r["stage2"][0, 1]


def test_reversion_curve():
    q = annual_pd_curve(np.array([[0.01, 0.05, 0.08]]), 6, 2)
    assert q[0, 1] == pytest.approx(0.08)
    assert q[0, 2] == pytest.approx(expit(0.5 * logit(0.08) + 0.5 * logit(0.01)))
    assert q[0, 3:] == pytest.approx([0.01] * 3)


def test_short_maturity_partial_period(cfg):
    r = single(cfg, [[0.02, 0.02]], maturity=0.5)
    assert r["ecl"][0, 0] == pytest.approx((1 - 0.98 ** 0.5) * 40 * 1.05 ** -0.25)
