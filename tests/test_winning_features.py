from __future__ import annotations

from groundtruth.services.copilot import CopilotService, answer_deterministic
from groundtruth.services.orchestrator import InvestigationOrchestrator
from groundtruth.services.risk import assess_risk, rank_fleet


def test_risk_ranks_conflict_above_managed(settings) -> None:
    orchestrator = InvestigationOrchestrator(settings)
    results = [orchestrator.run_fixture(c["case_id"]) for c in orchestrator.list_fixture_cases()]
    ranked = rank_fleet(results)
    assert ranked[0].score >= 90
    assert ranked[-1].band == "Low"
    by_status = {a.status: a for a in ranked}
    assert by_status["MULTIPLE_ACTIVE_OWNERS"].band == "Critical"
    assert by_status["CURRENT_OWNER_FOUND"].score < by_status["HISTORICAL_OWNER_FOUND"].score


def test_risk_is_deterministic(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("A_historical_owner")
    first, second = assess_risk(result), assess_risk(result)
    assert first == second
    assert first.factors and first.next_action


def test_copilot_answers_are_grounded(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("E_current_owner")
    known = set(result.evidence_ids)
    for question in (
        "Who owns this function?",
        "Is it safe to delete?",
        "What should I do next?",
        "Who last changed it?",
    ):
        answer = answer_deterministic(result, question)
        assert answer.answer
        assert set(answer.evidence_ids) <= known


def test_copilot_service_falls_back_without_model(settings) -> None:
    result = InvestigationOrchestrator(settings).run_fixture("B_multiple_active_owners")
    answer = CopilotService(settings).ask(result, "Who owns this function?")
    assert answer.generated_by == "deterministic"
    assert "prod-orders" in answer.answer
