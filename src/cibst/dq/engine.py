"""Data-quality rules engine: detect, quantify (record count and exposure impacted), remediate and log.

Rules are declared in config/dq_rules.yaml. Every failing record is written to an issue log with the action
taken, so that each remediation is traceable for audit and for follow-up with the upstream data owner.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cibst.data.portfolio import INDUSTRY_CODES
from cibst.models.master_scale import CENTRAL_PD

ONE_NOTCH_PD_MULTIPLIER = float(np.exp(np.mean(np.diff(np.log(CENTRAL_PD[:-1])))))


@dataclass
class DQResult:
    report: pd.DataFrame
    issues: pd.DataFrame
    obligors: pd.DataFrame
    facilities: pd.DataFrame
    blocked: bool

    @property
    def open_escalations(self) -> pd.DataFrame:
        return self.issues[self.issues["action"].str.startswith("ESCALATED")]


class DQEngine:
    def __init__(self, rules: list[dict], as_of: str, sectors_cfg: dict):
        self.rules = rules
        self.as_of = pd.Timestamp(as_of)
        self.sector_margin = {k: v["margin_mean"] for k, v in sectors_cfg["sectors"].items()}
        self.code_to_sector = {v: k for k, v in INDUSTRY_CODES.items()}

    # ---------------------------------------------------------------- detection
    def _failing(self, rule: dict, obl: pd.DataFrame, fac: pd.DataFrame, ledger: pd.DataFrame) -> pd.Index:
        df = obl if rule["table"] == "obligors" else fac
        col, chk = rule["column"], rule["check"]
        if chk == "not_null":
            mask = df[col].isna()
        elif chk == "positive":
            mask = ~(pd.to_numeric(df[col], errors="coerce") > 0)
        elif chk == "non_negative":
            mask = pd.to_numeric(df[col], errors="coerce") < 0
        elif chk == "le_column":
            mask = df[col] > df[rule["other"]] * (1 + 1e-9)
        elif chk == "max_age_months":
            age = (self.as_of - pd.to_datetime(df[col])).dt.days / 30.4
            mask = age > rule["limit"]
        elif chk == "foreign_key":
            mask = ~df[col].isin(obl["obligor_id"])
        elif chk == "unique":
            mask = df[col].duplicated(keep="first")
        elif chk == "reconcile_ledger":
            return self._recon_breaks(rule, obl, fac, ledger)
        else:
            raise ValueError(f"Unknown check {chk}")
        return df.index[mask.fillna(False).astype(bool)]

    def _recon(self, obl, fac, ledger) -> pd.DataFrame:
        sys = fac.merge(obl[["obligor_id", "region"]], on="obligor_id").groupby("region")["drawn"].sum()
        out = ledger.set_index("region").join(sys.rename("system_drawn"), how="outer").fillna(0.0)
        out["difference"] = out["system_drawn"] - out["ledger_drawn"]
        out["difference_pct"] = out["difference"] / out["ledger_drawn"]
        return out

    def _recon_breaks(self, rule, obl, fac, ledger) -> pd.Index:
        rec = self._recon(obl, fac, ledger)
        return rec.index[rec["difference_pct"].abs() > rule["tolerance"]]

    # ---------------------------------------------------------------- run
    def run(self, obligors: pd.DataFrame, facilities: pd.DataFrame, ledger: pd.DataFrame) -> DQResult:
        obl, fac = obligors.copy(), facilities.copy()
        obl["pd_overlay_mult"] = 1.0
        obl["dq_flags"] = ""
        report, issues = [], []
        exposure = lambda f: f["limit"].clip(lower=0) + 0.0  # noqa: E731

        # structural facility rules first, then obligor rules, then the remaining facility rules
        order = sorted(self.rules, key=lambda r: (r["check"] not in ("unique", "foreign_key"), r["table"] != "obligors"))
        for rule in order:
            bad = self._failing(rule, obl, fac, ledger)
            n_bad = len(bad)
            if rule["table"] == "obligors":
                ids = obl.loc[bad, "obligor_id"]
                ead_imp = exposure(fac[fac["obligor_id"].isin(ids)]).sum()
            elif rule["check"] == "reconcile_ledger":
                ids = pd.Series(bad, dtype=object)
                rec = self._recon(obl, fac, ledger)
                ead_imp = rec.loc[bad, "difference"].abs().sum()
            else:
                ids = fac.loc[bad, "facility_id"]
                ead_imp = exposure(fac.loc[bad]).sum()
            action = rule["remediation"]
            obl, fac, note = self._remediate(rule, bad, obl, fac, ledger)
            for rid in ids:
                issues.append({"rule_id": rule["id"], "table": rule["table"], "record_id": rid,
                               "severity": rule["severity"], "action": note})
            report.append({
                "rule_id": rule["id"], "table": rule["table"], "dimension": rule["dimension"],
                "description": rule["description"], "severity": rule["severity"], "records_failing": n_bad,
                "exposure_impacted": ead_imp, "status": "PASS" if n_bad == 0 else "FAIL",
                "remediation": action if n_bad else "", "resolution": note if n_bad else "",
            })
        rep = pd.DataFrame(report).sort_values("rule_id").reset_index(drop=True)
        iss = pd.DataFrame(issues, columns=["rule_id", "table", "record_id", "severity", "action"])
        blocked = bool(((rep["severity"] == "critical") & (rep["status"] == "FAIL") &
                        (rep["resolution"].str.startswith("UNRESOLVED"))).any())
        return DQResult(rep, iss, obl.reset_index(drop=True), fac.reset_index(drop=True), blocked)

    # ---------------------------------------------------------------- remediation
    def _remediate(self, rule, bad, obl, fac, ledger):
        if len(bad) == 0:
            return obl, fac, ""
        r = rule["remediation"]
        if r == "map_sector_from_industry_code":
            mapped = obl.loc[bad, "industry_code"].map(self.code_to_sector)
            obl.loc[bad, "sector"] = mapped
            unresolved = mapped.isna().sum()
            return obl, fac, ("UNRESOLVED: industry code unmapped" if unresolved else
                              "REMEDIATED: sector derived from industry code")
        if r == "exclude_and_escalate":
            if rule["table"] == "obligors":
                ids = obl.loc[bad, "obligor_id"]
                obl = obl.drop(index=bad)
                fac = fac[~fac["obligor_id"].isin(ids)]
            else:
                fac = fac.drop(index=bad)
            return obl, fac, "ESCALATED: excluded from run, raised with data owner"
        if r == "cap_ebitda_at_margin_p99":
            obl.loc[bad, "ebitda"] = obl.loc[bad, "revenue"] * obl.loc[bad, "sector"].map(self.sector_margin)
            obl.loc[bad, "dq_flags"] += "ebitda_restated;"
            return obl, fac, "REMEDIATED: EBITDA restated at sector-norm margin; credit officer review requested"
        if r == "one_notch_conservative_downgrade":
            obl.loc[bad, "pd_overlay_mult"] *= ONE_NOTCH_PD_MULTIPLIER
            obl.loc[bad, "dq_flags"] += "stale_financials;"
            return obl, fac, "REMEDIATED: one-notch conservative PD overlay (post-model adjustment)"
        if r == "cap_drawn_at_limit":
            fac.loc[bad, "drawn"] = fac.loc[bad, "limit"]
            return obl, fac, "REMEDIATED: drawn capped at limit; limit breach referred to credit admin"
        if r == "set_to_one_year":
            fac.loc[bad, "maturity_years"] = 1.0
            return obl, fac, "REMEDIATED: remaining maturity set to 1 year (conservative IRB M floor)"
        if r == "drop_duplicates_keep_first":
            fac = fac.drop(index=bad)
            return obl, fac, "REMEDIATED: duplicate rows removed (first occurrence kept)"
        if r == "set_to_zero":
            fac.loc[bad, "collateral_value"] = 0.0
            return obl, fac, "REMEDIATED: collateral value set to zero (no credit risk mitigation)"
        if r == "escalate_to_finance":
            return obl, fac, "ESCALATED: ledger break referred to Group Finance; results flagged"
        raise ValueError(f"Unknown remediation {r}")
