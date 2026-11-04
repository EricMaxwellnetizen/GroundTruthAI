from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from groundtruth.ai import AIExplainService
from groundtruth.ai.tool_schema import SchemaValidationError, validate_json_schema
from groundtruth.ai.tools import InternalToolRegistry, ToolArgumentError, ToolExecutionError, ToolPermissionError
from groundtruth.mcp import McpServerConfig, McpToolRegistry
from groundtruth.services.orchestrator import InvestigationOrchestrator


def _call(name: str, arguments: dict, call_id: str = "call_1"):
    return SimpleNamespace(
        id=call_id,
        function=SimpleNamespace(name=name, arguments=json.dumps(arguments)),
    )


def _response(*calls, content: str | None = None):
    message = SimpleNamespace(tool_calls=list(calls), content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _payload(result, extra: dict | None = None) -> dict:
    payload = {
        "summary": "The deterministic engine found the recorded owner.",
        "established_facts": [
            {
                "statement": "The evidence bundle contains the workspace match.",
                "evidence_ids": [result.evidence_ids[0]],
            }
        ],
        "unresolved_questions": [],
        "next_steps": [],
        "warnings": [],
    }
    payload.update(extra or {})
    return payload


class _Completions:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.script: list = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if not self.script:
            raise AssertionError("Fake OpenAI ran out of scripted responses.")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _FakeOpenAI:
    completions = _Completions()

    def __init__(self, **kwargs) -> None:
        self.chat = SimpleNamespace(completions=self.completions)


@pytest.fixture()
def result(settings):
    return InvestigationOrchestrator(settings).run_fixture("A_historical_owner")


@pytest.fixture()
def fake_openai(monkeypatch):
    import openai

    fake = _FakeOpenAI()
    fake.completions.requests = []
    fake.completions.script = []
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    return fake.completions


def _configured(settings):
    return replace(settings, ai_enabled=True, model_api_key="test-key", ai_tool_loop_enabled=True)


def test_tool_loop_calls_read_tool_then_submits(settings, result, fake_openai) -> None:
    fake_openai.script = [
        _response(_call("lookup_resource_lineage", {"function_name": result.resource.name})),
        _response(_call("submit_explanation", _payload(result), call_id="call_2")),
    ]
    service = AIExplainService(_configured(settings))
    explanation = service.explain(result)
    assert explanation.generated_by == "muse-spark"
    assert explanation.tool_calls_used == 2
    assert [record.tool for record in service.last_tool_calls] == ["lookup_resource_lineage"]
    assert service.last_tool_calls[0].status == "ok"
    assert result.status.value == "HISTORICAL_OWNER_FOUND"
    first_request = fake_openai.requests[0]
    assert {tool["function"]["name"] for tool in first_request["tools"]} >= {
        "submit_explanation",
        "lookup_resource_lineage",
        "get_workspace_runs",
    }
    replay = fake_openai.requests[1]["messages"]
    assert replay[-1]["role"] == "tool"
    assert "HISTORICAL_OWNER_FOUND" in replay[-1]["content"]


def test_tool_loop_aborts_on_repeated_call(settings, result, fake_openai) -> None:
    repeated = {"function_name": result.resource.name}
    fake_openai.script = [
        _response(_call("lookup_resource_lineage", repeated, call_id="call_1")),
        _response(_call("lookup_resource_lineage", repeated, call_id="call_2")),
    ]
    service = AIExplainService(_configured(settings))
    explanation = service.explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert service.last_error and "repeated" in service.last_error.lower()


def test_tool_loop_enforces_call_budget(settings, result, fake_openai) -> None:
    fake_openai.script = [
        _response(_call("lookup_resource_lineage", {"function_name": result.resource.name})),
        _response(_call("submit_explanation", _payload(result))),
    ]
    service = AIExplainService(
        replace(_configured(settings), ai_max_tool_calls=1),
    )
    explanation = service.explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert service.last_error and "budget" in service.last_error.lower()


def test_tool_loop_refuses_write_tool_name(settings, result, fake_openai) -> None:
    fake_openai.script = [
        _response(_call("delete_workspace", {"workspace_id": "ws-orders-prod"})),
        _response(_call("submit_explanation", _payload(result))),
    ]
    service = AIExplainService(_configured(settings))
    explanation = service.explain(result)
    assert explanation.generated_by == "muse-spark"
    assert explanation.tool_calls_used == 2
    assert service.last_tool_calls == []
    refusal = fake_openai.requests[1]["messages"][-1]
    assert refusal["role"] == "tool"
    assert "not registered" in refusal["content"]


def test_tool_loop_disabled_uses_single_shot(settings, result, fake_openai) -> None:
    fake_openai.script = [_response(_call("submit_explanation", _payload(result)))]
    service = AIExplainService(
        replace(_configured(settings), ai_tool_loop_enabled=False),
    )
    explanation = service.explain(result)
    assert explanation.generated_by == "muse-spark"
    assert [tool["function"]["name"] for tool in fake_openai.requests[0]["tools"]] == ["submit_explanation"]


def test_tool_loop_failure_falls_back_without_changing_result(settings, result, fake_openai) -> None:
    fake_openai.script = [RuntimeError("boom")]
    service = AIExplainService(_configured(settings))
    explanation = service.explain(result)
    assert explanation.generated_by == "deterministic_fallback"
    assert service.last_error
    assert result.status.value == "HISTORICAL_OWNER_FOUND"
    assert result.historical_managers


def test_registry_rejects_other_resources(result) -> None:
    registry = InternalToolRegistry(result)
    with pytest.raises(ToolArgumentError):
        registry.execute("lookup_resource_lineage", {"function_name": "some-other-function"})
    with pytest.raises(ToolPermissionError):
        registry.execute("delete_workspace", {"workspace_id": "ws-orders-prod"})


def test_registry_rejects_invalid_arguments(result) -> None:
    registry = InternalToolRegistry(result)
    with pytest.raises(ToolArgumentError):
        registry.execute("get_workspace_runs", {"limit": 500})
    with pytest.raises(ToolArgumentError):
        registry.execute("get_cloudwatch_metrics", {"metric": "Cost"})


def test_mcp_wrapper_rechecks_allowlist_before_call(result) -> None:
    registry = McpToolRegistry(["fake:get_workspace"])
    registry.register_server(McpServerConfig(name="fake", url="https://mcp.example.test/mcp"))
    registry.add_discovered(
        "fake",
        {
            "name": "get_workspace",
            "description": "Read one workspace",
            "inputSchema": {"type": "object", "properties": {"workspace_id": {"type": "string"}}},
            "annotations": {"readOnlyHint": True},
        },
    )
    manager = SimpleNamespace(
        enabled=True,
        registry=registry,
        call=lambda name, arguments: SimpleNamespace(
            text='{"workspace": "orders"}',
            is_error=False,
        ),
    )
    tools = InternalToolRegistry(result, mcp_manager=manager)
    name = next(item.name for item in tools.tools if item.name.startswith("mcp__fake__"))
    payload = tools.execute(name, {"workspace_id": "ws-orders-prod"})
    assert payload["source"] == "mcp"
    assert payload["evidence_ids"] == []

    registry.allowlist.clear()
    with pytest.raises(ToolExecutionError):
        tools.execute(name, {"workspace_id": "ws-orders-prod"})


def test_schema_validator_is_fail_closed() -> None:
    schema = {
        "type": "object",
        "required": ["name"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "minLength": 2, "maxLength": 4},
            "mode": {"anyOf": [{"type": "string", "enum": ["read"]}, {"type": "null"}]},
        },
    }
    validate_json_schema({"name": "ok", "mode": "read"}, schema)
    with pytest.raises(SchemaValidationError):
        validate_json_schema({"name": "too-long"}, schema)
    with pytest.raises(SchemaValidationError):
        validate_json_schema({"name": "ok", "extra": True}, schema)
    with pytest.raises(SchemaValidationError):
        validate_json_schema({"mode": None}, schema)
