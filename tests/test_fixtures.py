from __future__ import annotations

import pytest

from groundtruth.ai import AIExplainService, validate_explanation
from groundtruth.connectors import FixtureCaseLoader
from groundtruth.models.enums import ConfidenceLabel, LineageStatus
from groundtruth.services.orchestrator import InvestigationOrchestrator

EXPECTED = {
    "E_current_owner": (LineageStatus.CURRENT_OWNER_FOUND, ConfidenceLabel.HIGH),
    "A_historical_owner": (LineageStatus.HISTORICAL_OWNER_FOUND, ConfidenceLabel.HIGH),
    "B_multiple_active_owners": (LineageStatus.MULTIPLE_ACTIVE_OWNERS, ConfidenceLabel.HIGH),
    "C_candidate_lineage": (LineageStatus.CANDIDATE_LINEAGE, ConfidenceLabel.LOW),
    "D_insufficient_access": (LineageStatus.INSUFFICIENT_ACCESS, ConfidenceLabel.UNKNOWN),
}


@pytest.mark.parametrize("case_id", sorted(EXPECTED))
def test_fixture_status_and_confidence(settings, case_id: str) -> None:
    result = InvestigationOrchestrator(settings).run_fixture(case_id)
    expected_status, expected_confidence = EXPECTED[case_id]
    assert result.fixture is True
    assert result.mode == "fixture"
    assert result.status == expected_status
    assert result.confidence == expected_confidence
    assert result.investigation_id.startswith("inv_")
    assert result.evidence
    assert result.graph.nodes
    assert result.status_reason


@pytest.mark.parametrize("case_id", sorted(EXPECTED))
def test_fixture_evidence_integrity(settings, case_id: str) -> None:
    result = InvestigationOrchestrator(settings).run_fixture(case_id)
    evidence_ids = [item.evidence_id for item in result.evidence]
    assert len(evidence_ids) == len(set(evidence_ids))
    known = set(evidence_ids)
    for node in result.graph.nodes:
        if node.source_evidence_id:
            assert node.source_evidence_id in known
    for edge in result.graph.edges:
        assert edge.source_evidence_id in known
    for owner in [*result.current_owners, *result.historical_managers]:
        assert set(owner.evidence_ids) <= known
    assert set(result.recommendation.evidence_ids) <= known


def test_fixture_case_specific_shapes(settings) -> None:
    loader = FixtureCaseLoader(settings)
    current = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    historical = InvestigationOrchestrator(settings).run_fixture("A_historical_owner")
    multiple = InvestigationOrchestrator(settings).run_fixture("B_multiple_active_owners")
    candidate = InvestigationOrchestrator(settings).run_fixture("C_candidate_lineage")
    insufficient = InvestigationOrchestrator(settings).run_fixture("D_insufficient_access")

    assert len(current.current_owners) == 1
    assert current.recommendation.code.value == "INSPECT_CURRENT_WORKSPACE"
    assert current.recommendation.blocked_adoption is False

    assert not historical.current_owners
    assert historical.historical_managers
    assert historical.recommendation.code.value == "INSPECT_LAST_KNOWN_STATE_AND_RUN"

    assert len(multiple.current_owners) >= 2
    assert multiple.recommendation.code.value == "RESOLVE_DUPLICATE_STATE_OWNERSHIP"
    assert multiple.recommendation.blocked_adoption is True

    assert candidate.repository_lineage is not None
    assert candidate.repository_lineage.commit_verified is False
    assert not candidate.current_owners
    assert candidate.recommendation.code.value == "REVIEW_CANDIDATE_MATCH_MANUALLY"

    assert insufficient.recommendation.code.value == "REQUEST_MISSING_READ_PERMISSION"

    assert len([gap for gap in insufficient.coverage if gap.required]) >= 2

    cases = loader.list_cases()
    assert len(cases) == 5
    assert {case["case_id"] for case in cases} == set(EXPECTED)


def test_fixture_is_deterministic_without_ai(settings) -> None:
    first = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    second = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    assert first.status == second.status
    assert first.confidence == second.confidence
    assert first.confidence_rule == second.confidence_rule
    first_records = [(item.source, item.source_label, item.source_record_id) for item in first.evidence]
    second_records = [(item.source, item.source_label, item.source_record_id) for item in second.evidence]
    assert first_records == second_records


def test_fixture_progress_reports_real_stages(settings) -> None:
    events: list[tuple[str, str, str | None]] = []
    InvestigationOrchestrator(settings).run_fixture(
        "E_current_owner",
        progress=lambda stage, status, detail=None: events.append((stage, status, detail)),
    )
    stage_status = {(stage, status) for stage, status, _ in events}
    assert ("fixture", "running") in stage_status
    assert ("fixture", "done") in stage_status
    assert ("aws_lambda", "done") in stage_status
    assert ("scalr", "done") in stage_status
    assert ("git", "done") in stage_status
    assert ("correlation", "done") in stage_status


def test_ai_fallback_is_grounded(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    explanation = AIExplainService(settings).explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert explanation.summary
    assert explanation.established_facts
    known = set(result.evidence_ids)
    for fact in explanation.established_facts:
        assert fact.evidence_ids
        assert set(fact.evidence_ids) <= known
    payload = {
        "summary": explanation.summary,
        "established_facts": [fact.model_dump() for fact in explanation.established_facts],
        "unresolved_questions": explanation.unresolved_questions,
        "next_steps": [step.model_dump() for step in explanation.next_steps],
        "warnings": explanation.warnings,
    }
    validated = validate_explanation(
        payload,
        result,
        model=explanation.model,
        tool_calls_used=explanation.tool_calls_used,
    )
    assert validated.summary == explanation.summary


def test_live_sources_can_skip_optional_connectors(settings, monkeypatch) -> None:
    from groundtruth.services import orchestrator as module

    case = FixtureCaseLoader(settings).load("E_current_owner")

    class AwsStub:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_function(self, name: str):
            return case.aws_result.model_copy(update={"fixture": False})

    class ScalrStub:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def fetch_dataset(self, *, function_name: str, resource_arn: str | None = None):
            return case.scalr_result.model_copy(update={"fixture": False})

    def forbidden(*args, **kwargs):
        raise AssertionError("Optional connector should not be constructed when disabled.")

    monkeypatch.setattr(module, "AwsLambdaConnector", AwsStub)
    monkeypatch.setattr(module, "ScalrConnector", ScalrStub)
    monkeypatch.setattr(module, "GitLocalConnector", forbidden)
    monkeypatch.setattr(module, "CloudTrailConnector", forbidden)
    monkeypatch.setattr(module, "CloudWatchMetricsConnector", forbidden)
    monkeypatch.setattr(module, "CloudWatchOmniConnector", forbidden)

    progress: list[tuple[str, str, str | None]] = []
    result = InvestigationOrchestrator(settings).run_live(
        case.resource.arn,
        sources={"aws", "scalr"},
        progress=lambda stage, status, detail=None: progress.append((stage, status, detail)),
    )
    assert result.mode == "live"
    assert result.fixture is False
    assert result.status == LineageStatus.CURRENT_OWNER_FOUND
    assert any(stage == "cloudtrail" and status == "skipped" for stage, status, _ in progress)
    assert not any(stage == "cloudtrail" and status == "error" for stage, status, _ in progress)
    assert any(stage == "cloudwatch" and status == "skipped" for stage, status, _ in progress)
    assert any(stage == "cloudwatch_omni" and status == "skipped" for stage, status, _ in progress)
    assert any(stage == "git" and status == "skipped" for stage, status, _ in progress)
