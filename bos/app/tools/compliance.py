"""
Compliance tool - rule-based KYC / AML / policy checks (Phase 1).

Stands in for OFAC / AML screening services, sanctions lists, and a real
policy engine (Phase 2 integrations). The rules here are deliberately
deterministic so unit tests are reproducible.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .base import ToolResult

log = logging.getLogger("bos.tools.compliance")


# A tiny synthetic sanctions list - enough for demo / tests.
_SANCTIONS = {"bad actor", "sanctioned entity", "evil corp", "terror funding ltd"}
_HIGH_RISK_COUNTRIES = {"XX", "YY"}  # fictional ISO codes
_PEP_KEYWORDS = {"politically exposed", "pep", "government official"}


def _score(kyc_data: Dict[str, Any]) -> float:
    """Risk score 0..1 (higher = riskier)."""
    score = 0.0
    name = (kyc_data.get("full_name") or "").lower()
    country = (kyc_data.get("country") or "").upper()
    notes = (kyc_data.get("notes") or "").lower()

    for s in _SANCTIONS:
        if s in name or s in notes:
            score += 0.8
    if country in _HIGH_RISK_COUNTRIES:
        score += 0.3
    for kw in _PEP_KEYWORDS:
        if kw in notes:
            score += 0.4
    if not kyc_data.get("gov_id"):
        score += 0.1
    if not kyc_data.get("address_proof"):
        score += 0.1
    return min(score, 1.0)


class ComplianceTool:
    def run_kyc(self, kyc_data: Dict[str, Any]) -> ToolResult:
        required = ["full_name", "gov_id", "address_proof", "dob"]
        missing = [r for r in required if not kyc_data.get(r)]
        passed = not missing
        return ToolResult(
            ok=True,
            data={
                "kyc_passed": passed,
                "missing_fields": missing,
                "checked": required,
            },
            tools_used=["compliance.run_kyc"],
        )

    def run_aml(self, kyc_data: Dict[str, Any]) -> ToolResult:
        risk = _score(kyc_data)
        cleared = risk < 0.5
        return ToolResult(
            ok=True,
            data={
                "aml_cleared": cleared,
                "risk_score": round(risk, 2),
                "risk_band": ("low" if risk < 0.25 else "medium" if risk < 0.5 else "high"),
                "checks": {
                    "sanctions_screening": "passed" if risk < 0.8 else "flagged",
                    "pep_screening": "passed" if risk < 0.4 else "flagged",
                    "country_risk": "low" if (kyc_data.get("country") or "").upper() not in _HIGH_RISK_COUNTRIES else "high",
                },
            },
            tools_used=["compliance.run_aml"],
        )

    def validate_policy(self, intent: str, payload: Dict[str, Any]) -> ToolResult:
        """Check if an action is allowed by organizational policy.

        Returns:
          - allowed: True/False
          - reasons: list[str]
          - requires_human_approval: bool
        """
        reasons: List[str] = []
        requires_approval = False

        # Account opening requires KYC pass
        if intent in ("account_opening", "account_transfer"):
            if not payload.get("kyc_passed"):
                reasons.append("KYC not yet passed - account action blocked")
                requires_approval = False  # blocked outright, not approvable
                return ToolResult(
                    ok=True,
                    data={
                        "allowed": False,
                        "reasons": reasons,
                        "requires_human_approval": False,
                    },
                    tools_used=["compliance.validate_policy"],
                )
            requires_approval = True
            reasons.append("Account actions always require human approval")

        # Trade execution requires client to be active & KYC verified
        if intent == "trade_execution":
            client = payload.get("client", {})
            if client.get("status") != "active":
                reasons.append("client not active")
                return ToolResult(
                    ok=True,
                    data={"allowed": False, "reasons": reasons, "requires_human_approval": False},
                    tools_used=["compliance.validate_policy"],
                )
            if float(payload.get("amount", 0)) > 1000:
                requires_approval = True
                reasons.append("Trade > $1000 requires human approval")
            else:
                requires_approval = False
                reasons.append("Trade within auto-approval threshold")

        # High-risk ops always need approval
        if intent == "high_risk_operation":
            requires_approval = True
            reasons.append("High-risk operation flagged for review")

        return ToolResult(
            ok=True,
            data={
                "allowed": True,
                "reasons": reasons or ["No policy violations"],
                "requires_human_approval": requires_approval,
            },
            tools_used=["compliance.validate_policy"],
        )


_singleton: Optional[ComplianceTool] = None


def _inst() -> ComplianceTool:
    global _singleton
    if _singleton is None:
        _singleton = ComplianceTool()
    return _singleton


def comp_run_kyc(kyc_data: Dict[str, Any]) -> ToolResult:
    return _inst().run_kyc(kyc_data)


def comp_run_aml(kyc_data: Dict[str, Any]) -> ToolResult:
    return _inst().run_aml(kyc_data)


def comp_validate_policy(intent: str, payload: Dict[str, Any]) -> ToolResult:
    return _inst().validate_policy(intent, payload)
