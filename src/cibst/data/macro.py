"""Macro history and stress scenario loading."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

GDP_REFERENCE = 3.0  # trend real GDP growth (%) at which sector revenue grows at its trend rate


@dataclass
class Scenario:
    name: str
    narrative: str
    paths: pd.DataFrame          # index: projection year 1..H
    regional_gdp: pd.DataFrame   # index: projection year 1..H, columns: regions


@dataclass
class ScenarioSet:
    jump_off: dict
    calendar_years: list[int]
    scenarios: dict[str, Scenario] = field(default_factory=dict)

    @property
    def names(self) -> list[str]:
        return list(self.scenarios)

    @property
    def horizon(self) -> int:
        return len(self.calendar_years)


def load_history(path) -> pd.DataFrame:
    hist = pd.read_csv(path).set_index("year")
    hist["unemployment_change"] = hist["unemployment"].diff()
    hist["oil_price_change"] = hist["oil_price"].pct_change()
    return hist


def build_scenarios(raw: dict) -> ScenarioSet:
    jump = raw["jump_off"]
    years = raw["horizon_years"]
    out = ScenarioSet(jump_off=jump, calendar_years=years)
    for name, s in raw["scenarios"].items():
        idx = pd.Index(range(1, len(years) + 1), name="t")
        paths = pd.DataFrame(
            {
                "calendar_year": years,
                "global_gdp_growth": s["global_gdp_growth"],
                "unemployment": s["unemployment"],
                "policy_rate": s["policy_rate"],
                "oil_price": s["oil_price"],
                "equity_return": s["equity_return"],
                "property_price_growth": s["property_price_growth"],
            },
            index=idx,
        )
        prev_oil = [jump["oil_price"]] + list(paths["oil_price"].iloc[:-1])
        paths["oil_price_change"] = paths["oil_price"] / prev_oil - 1.0
        prev_u = [jump["unemployment"]] + list(paths["unemployment"].iloc[:-1])
        paths["unemployment_change"] = paths["unemployment"] - prev_u
        regional = pd.DataFrame(s["gdp_growth"], index=idx)
        _validate(name, paths, regional, len(years))
        out.scenarios[name] = Scenario(name, " ".join(s["narrative"].split()), paths, regional)
    return out


def _validate(name: str, paths: pd.DataFrame, regional: pd.DataFrame, h: int) -> None:
    if len(paths) != h or len(regional) != h:
        raise ValueError(f"Scenario {name}: every path must have {h} annual points")
    if (paths["oil_price"] <= 0).any():
        raise ValueError(f"Scenario {name}: oil price must be positive")
    if paths.isna().any().any() or regional.isna().any().any():
        raise ValueError(f"Scenario {name}: missing values")
