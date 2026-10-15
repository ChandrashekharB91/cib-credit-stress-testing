"""Rating master scale: 13 performing credit grades (CG01-CG13) plus default (D)."""
from __future__ import annotations

import numpy as np
import pandas as pd

CENTRAL_PD = np.array([0.0005, 0.0008, 0.0013, 0.0021, 0.0035, 0.0058, 0.0095,
                       0.0157, 0.0259, 0.0427, 0.0705, 0.1163, 0.2500])
GRADES = [f"CG{i:02d}" for i in range(1, len(CENTRAL_PD) + 1)]
# grade boundaries are geometric means of adjacent central PDs
UPPER_BOUND = np.append(np.sqrt(CENTRAL_PD[:-1] * CENTRAL_PD[1:]), 1.0)
DEFAULT_GRADE = len(GRADES) + 1  # numeric code for D


def master_scale_table() -> pd.DataFrame:
    lower = np.insert(UPPER_BOUND[:-1], 0, 0.0)
    return pd.DataFrame(
        {"grade": GRADES, "grade_num": range(1, len(GRADES) + 1),
         "pd_lower": lower, "pd_central": CENTRAL_PD, "pd_upper": UPPER_BOUND,
         "band": ["Investment grade"] * 5 + ["Sub-investment grade"] * 5 + ["Watch / high risk"] * 3}
    )


def pd_to_grade_num(pd_: np.ndarray, defaulted: np.ndarray | None = None) -> np.ndarray:
    """Map continuous PDs to numeric grades 1..13; defaulted obligors map to 14 (D)."""
    g = np.searchsorted(UPPER_BOUND, np.asarray(pd_, float), side="left") + 1
    g = np.clip(g, 1, len(GRADES))
    if defaulted is not None:
        g = np.where(np.asarray(defaulted, bool), DEFAULT_GRADE, g)
    return g


def grade_label(grade_num: np.ndarray) -> np.ndarray:
    labels = np.array(GRADES + ["D"])
    return labels[np.asarray(grade_num, int) - 1]


def grade_central_pd(grade_num: np.ndarray) -> np.ndarray:
    g = np.asarray(grade_num, int)
    out = np.ones(len(g))
    perf = g <= len(GRADES)
    out[perf] = CENTRAL_PD[g[perf] - 1]
    return out
