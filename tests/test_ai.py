from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from groundtruth.ai import AIExplainService, AIValidationError, attach_ai_explanation, validate_explanation
from groundtruth.services.orchestrator import InvestigationOrchestrator


class _FakeCompletions:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    def create(self, **kwargs):
        function = SimpleNamespace(name="submit_explanation", arguments=self.payload)
        message = SimpleNamespace(tool_calls=[SimpleNamespace(function=function)], content=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeOpenAI:
    payload = "{}"

    def __init__(self, **kwargs) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(self.payload))


@pytest.fixture()
def result(settings):
    return InvestigationOrchestrator(settings).run_fixture("E_current_owner")


def test_fallback_when_not_configured(settings, result) -> None:
    explanation = AIExplainService(settings).explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert explanation.established_facts
    assert any("not configured" in warning.lower() for warning in explanation.warnings)
    known = set(result.evidence_ids)
    for fact in explanation.established_facts:
        assert set(fact.evidence_ids) <= known


def test_validation_rejects_unknown_evidence(result) -> None:
    payload = {
        "summary": "The engine found a current owner.",
        "established_facts": [{"statement": "Ownership is exact.", "evidence_ids": ["ev_missing"]}],
    }
    with pytest.raises(AIValidationError):
        validate_explanation(payload, result)


def test_validation_rejects_alternative_status(result) -> None:
    payload = {
        "summary": "This could be CANDIDATE_LINEAGE instead.",
        "established_facts": [{"statement": "The workspace is exact.", "evidence_ids": [result.evidence_ids[0]]}],
    }
    with pytest.raises(AIValidationError):
        validate_explanation(payload, result)


def test_validation_rejects_autonomous_write_step(result) -> None:
    payload = {
        "summary": "A current owner was found.",
        "established_facts": [{"statement": "Ownership is exact.", "evidence_ids": [result.evidence_ids[0]]}],
        "next_steps": [{"step": "Run terraform apply to adopt it.", "reason": "Faster.", "evidence_ids": []}],
    }
    with pytest.raises(AIValidationError):
        validate_explanation(payload, result)


def test_remote_success_path(settings, result, monkeypatch) -> None:
    import openai

    payload = (
        '{"summary":"The deterministic engine found one current owner.","established_facts":'
        '[{"statement":"The workspace matches the Lambda ARN exactly.","evidence_ids":["'
        + result.evidence_ids[0]
        + '"]}],"unresolved_questions":[],"next_steps":[],"warnings":[]}'
    )
    _FakeOpenAI.payload = payload
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    configured = replace(settings, ai_enabled=True, model_api_key="test-key")
    explanation = AIExplainService(configured).explain(result)
    assert explanation.generated_by == "muse-spark"
    assert explanation.model == configured.meta_model
    assert explanation.tool_calls_used == 1


def test_remote_invalid_payload_falls_back(settings, result, monkeypatch) -> None:
    import openai

    _FakeOpenAI.payload = '{"summary":"CANDIDATE_LINEAGE"}'
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    configured = replace(settings, ai_enabled=True, model_api_key="test-key")
    service = AIExplainService(configured)
    explanation = service.explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert service.last_error


def test_attach_returns_copy(settings, result) -> None:
    explanation = AIExplainService(settings).explain(result)
    attached = attach_ai_explanation(result, explanation)
    assert attached.ai_explanation is explanation
    assert result.ai_explanation is None
