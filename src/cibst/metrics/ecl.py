"""IFRS 9 expected credit loss under a stress scenario, using expected-value (survival-weighted) mechanics.

Notation (per facility, scenario s, reporting date t = 0..H):
  q_y        annual PD for year y: scenario PD for y <= H; afterwards logit reversion from PD_H
             to the reporting-date PD over R years
  S_t        survival to t: prod_{y<=t} (1 - q_y); the defaulted fraction (1 - S_t) is Stage 3
  m_t        remaining maturity; static balance sheet -> matured facilities roll over at the same tenor
  q~_k       period PD with partial final year: 1 - (1 - q)^{f_k},  f_k = min(1, m_t - (k-1))
  u_k        unconditional default in forward period k: prod_{j<k}(1 - q~_j) q~_k
  DF_k       (1 + EIR)^-(k - 1 + f_k / 2)      (mid-period discounting at the effective interest rate)
  EL12_t     u_1 LGD_1 EAD_1 DF_1
  ELlife_t   sum_k u_k LGD_k EAD_k DF_k
Staging of the performing fraction at t (PD_t = 12m PD of the rating assigned at reporting date t):
  Stage 2 if [PD_t / PD_orig > relative threshold AND PD_t - PD_orig > absolute threshold]
           OR rating at t is on the watchlist OR the 30 days-past-due backstop is hit; else Stage 1.
ECL_t = S_t x (Stage 1 ? EL12 : ELlife) + (1 - S_t) x LGD_t x EAD_t.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.special import expit, logit


@dataclass
class ECLInputs:
    pd_path: np.ndarray        # (m, H+1) PD by reporting date (t=0 current, t>=1 scenario)
    lgd: np.ndarray            # (m, H+1)
    ead: np.ndarray            # (m, H+1)
    maturity: np.ndarray       # (m,) remaining maturity in years at t=0
    eir: np.ndarray            # (m,)
    origination_pd: np.ndarray # (m,)
    grade_path: np.ndarray     # (m, H+1) numeric rating grade at each reporting date
    dpd: np.ndarray            # (m,) days past due at the reporting date
    defaulted: np.ndarray      # (m,) bool, already in default at t=0


def annual_pd_curve(pd_path: np.ndarray, n_years: int, reversion_years: int) -> np.ndarray:
    """Annual PDs for years 1..n_years (column y-1 holds year y)."""
    m, h1 = pd_path.shape
    H = h1 - 1
    p = np.clip(pd_path, 1e-6, 1 - 1e-6)
    out = np.empty((m, n_years))
    for y in range(1, n_years + 1):
        if y <= H:
            out[:, y - 1] = p[:, y]
        else:
            w = min(1.0, (y - H) / max(reversion_years, 1))
            out[:, y - 1] = expit((1 - w) * logit(p[:, H]) + w * logit(p[:, 0]))
    return out


def compute_ecl(inp: ECLInputs, cfg: dict) -> dict[str, np.ndarray]:
    icfg = cfg["ifrs9"]
    m, h1 = inp.pd_path.shape
    H = h1 - 1
    max_life = int(icfg["max_lifetime_years"])
    q = annual_pd_curve(inp.pd_path, H + max_life + 1, int(icfg["reversion_years"]))
    defaulted = inp.defaulted.astype(bool)

    keys = ["survival", "stage2", "pd12", "el12", "ellife", "ecl", "ecl_s1", "ecl_s2", "ecl_s3",
            "ead_s1", "ead_s2", "ead_s3"]
    res = {k: np.zeros((m, h1)) for k in keys}

    survival = np.ones(m)
    survival[defaulted] = 0.0
    for t in range(h1):
        if t > 0:
            survival = survival * (1 - q[:, t - 1])
            survival[defaulted] = 0.0
        mt = np.where(inp.maturity - t > 0, inp.maturity - t, inp.maturity)
        K = int(min(np.ceil(mt.max()), max_life))
        alive = np.ones(m)
        el12 = np.zeros(m)
        ellife = np.zeros(m)
        for k in range(1, K + 1):
            f = np.clip(mt - (k - 1), 0.0, 1.0)
            qk = 1 - (1 - q[:, t + k - 1]) ** f
            u = alive * qk
            col = min(t + k, H)
            df = (1 + inp.eir) ** -(k - 1 + f / 2)
            loss = u * inp.lgd[:, col] * inp.ead[:, col] * df
            ellife += loss
            if k == 1:
                el12 = loss
            alive = alive * (1 - qk)
        pd12 = q[:, t]                       # forward 12m PD used to measure ECL
        pd_stage = inp.pd_path[:, t]          # rating PD at the reporting date used for the SICR test
        sicr = (pd_stage / np.maximum(inp.origination_pd, 1e-6) > icfg["sicr_relative_threshold"]) & \
               (pd_stage - inp.origination_pd > icfg["sicr_absolute_threshold"])
        watch = inp.grade_path[:, t] >= icfg["watchlist_grade"]
        backstop = inp.dpd >= icfg["dpd_backstop"]
        stage2 = (sicr | watch | backstop) & ~defaulted

        ead_t = np.where(defaulted, inp.ead[:, 0], inp.ead[:, t])
        perf_ecl = np.where(stage2, ellife, el12)
        res["survival"][:, t] = survival
        res["stage2"][:, t] = stage2
        res["pd12"][:, t] = pd12
        res["el12"][:, t] = el12
        res["ellife"][:, t] = ellife
        res["ecl_s1"][:, t] = survival * perf_ecl * ~stage2
        res["ecl_s2"][:, t] = survival * perf_ecl * stage2
        res["ecl_s3"][:, t] = (1 - survival) * inp.lgd[:, t] * ead_t
        res["ecl"][:, t] = res["ecl_s1"][:, t] + res["ecl_s2"][:, t] + res["ecl_s3"][:, t]
        res["ead_s1"][:, t] = survival * ead_t * ~stage2
        res["ead_s2"][:, t] = survival * ead_t * stage2
        res["ead_s3"][:, t] = (1 - survival) * ead_t
    return res
