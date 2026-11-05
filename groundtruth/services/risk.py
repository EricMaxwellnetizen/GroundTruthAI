from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import LineageStatus
from groundtruth.models.lineage import LineageResult

BASE_SCORES = {
    LineageStatus.MULTIPLE_ACTIVE_OWNERS: 95,
    LineageStatus.IDENTITY_AMBIGUOUS: 90,
    LineageStatus.INSUFFICIENT_ACCESS: 70,
    LineageStatus.HISTORICAL_OWNER_FOUND: 65,
    LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES: 60,
    LineageStatus.CANDIDATE_LINEAGE: 45,
    LineageStatus.CURRENT_OWNER_FOUND: 10,
}


class RiskAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str
    status: str
    score: int
    band: str
    factors: list[str] = Field(default_factory=list)
    next_action: str


def _band(score: int) -> str:
    if score >= 85:
        return "Critical"
    if score >= 60:
        return "High"
    if score >= 35:
        return "Medium"
    return "Low"


def assess_risk(result: LineageResult) -> RiskAssessment:
    score = BASE_SCORES[result.status]
    factors = [f"Status {result.status.value} (base {score})"]
    activity = result.activity
    if activity is not None and not activity.no_datapoints and (activity.total_invocations or 0) > 0:
        if result.status in {LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES, LineageStatus.HISTORICAL_OWNER_FOUND}:
            score = min(100, score + 10)
            factors.append(
                f"Actively invoked ({activity.total_invocations:,.0f} in window) with no confirmed current owner (+10)"
            )
        if (activity.total_errors or 0) > 0:
            score = min(100, score + 5)
            factors.append(f"Errors observed ({activity.total_errors:,.0f}) (+5)")
    if result.coverage_gaps():
        score = min(100, score + 5)
        factors.append(f"{len(result.coverage_gaps())} coverage gap(s) (+5)")
    if result.status == LineageStatus.CURRENT_OWNER_FOUND and len(result.current_owners) == 1:
        score = max(0, score - 5)
        factors.append("Exactly one verified active owner (-5)")
    action = {
        LineageStatus.MULTIPLE_ACTIVE_OWNERS: "Resolve duplicate ownership (Action Center)",
        LineageStatus.IDENTITY_AMBIGUOUS: "Verify exact ARN/account/region",
        LineageStatus.INSUFFICIENT_ACCESS: "Grant read access, then re-investigate",
        LineageStatus.HISTORICAL_OWNER_FOUND: "Reattribute to the historical workspace or adopt deliberately",
        LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES: "Assign an owner: adopt or retire with sign-off",
        LineageStatus.CANDIDATE_LINEAGE: "Manually verify the candidate match",
        LineageStatus.CURRENT_OWNER_FOUND: "No action — monitor",
    }[result.status]
    return RiskAssessment(
        function_name=result.resource.name,
        status=result.status.value,
        score=score,
        band=_band(score),
        factors=factors,
        next_action=action,
    )


def rank_fleet(results: list[LineageResult]) -> list[RiskAssessment]:
    return sorted((assess_risk(r) for r in results), key=lambda a: (-a.score, a.function_name))


_FUNCTION_BY_CASE = {
    "A_historical_owner": "orders-transformer",
    "B_multiple_active_owners": "orders-transformer",
    "C_candidate_lineage": "analytics-normalizer",
    "D_insufficient_access": "payments-settler",
    "E_current_owner": "orders-transformer",
    "F_unattributed": "invoice-pdf-renderer",
    "G_identity_ambiguous": "checkout-pricing",
    "H_current_owner_fraud": "fraud-scorer",
}


def queue_from_cases(cases: list[dict]) -> list[RiskAssessment]:
    """Lightweight queue from scenario metadata (no investigation runs), so
    Overview paints instantly. Full assessments replace these after a sweep."""
    rows: dict[str, RiskAssessment] = {}
    for case in cases:
        try:
            status = LineageStatus(str(case.get("expected_status") or ""))
        except ValueError:
            continue
        name = _FUNCTION_BY_CASE.get(str(case.get("case_id") or ""), str(case.get("label") or "function"))
        score = BASE_SCORES[status]
        action = {
            LineageStatus.MULTIPLE_ACTIVE_OWNERS: "Resolve duplicate ownership (Action Center)",
            LineageStatus.IDENTITY_AMBIGUOUS: "Verify exact ARN/account/region",
            LineageStatus.INSUFFICIENT_ACCESS: "Grant read access, then re-investigate",
            LineageStatus.HISTORICAL_OWNER_FOUND: "Reattribute to the historical workspace or adopt deliberately",
            LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES: "Assign an owner: adopt or retire with sign-off",
            LineageStatus.CANDIDATE_LINEAGE: "Manually verify the candidate match",
            LineageStatus.CURRENT_OWNER_FOUND: "No action — monitor",
        }[status]
        row = RiskAssessment(
            function_name=name,
            status=status.value,
            score=score,
            band=_band(score),
            factors=[f"Status {status.value} (base {score})"],
            next_action=action,
        )
        existing = rows.get(name)
        if existing is None or row.score > existing.score:
            rows[name] = row
    return sorted(rows.values(), key=lambda a: (-a.score, a.function_name))
