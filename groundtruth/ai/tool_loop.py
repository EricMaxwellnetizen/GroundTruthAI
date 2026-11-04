from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from groundtruth.ai.tools import InternalToolRegistry, ToolCallRecord, ToolError
from groundtruth.utils.redaction import safe_text
from groundtruth.utils.retry import retry_with_backoff

LOGGER = logging.getLogger("groundtruth.ai.tool_loop")

MAX_TOOL_RESULT_MESSAGE_CHARS = 8000
MAX_ASSISTANT_CONTENT_CHARS = 4000


class ToolLoopError(RuntimeError):
    pass


@dataclass
class ToolLoopOutcome:
    payload: dict[str, Any]
    tool_calls_used: int
    calls: list[ToolCallRecord] = field(default_factory=list)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status <= 599):
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


def _normalize_arguments(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if raw is None:
        return "{}"
    try:
        return json.dumps(raw, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _assistant_message(message: Any, tool_calls: list[Any]) -> dict[str, Any]:
    serialized: list[dict[str, Any]] = []
    for index, call in enumerate(tool_calls):
        function = _get(call, "function", {}) or {}
        call_id = str(_get(call, "id", "") or f"call_{index}")
        serialized.append(
            {
                "id": safe_text(call_id, limit=120),
                "type": "function",
                "function": {
                    "name": safe_text(str(_get(function, "name", "") or ""), limit=120),
                    "arguments": _normalize_arguments(_get(function, "arguments")),
                },
            }
        )
    content = _get(message, "content")
    return {
        "role": "assistant",
        "content": safe_text(str(content or ""), limit=MAX_ASSISTANT_CONTENT_CHARS),
        "tool_calls": serialized,
    }


def _parse_submit(arguments: str) -> dict[str, Any]:
    try:
        payload = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ToolLoopError("The submit_explanation arguments were not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ToolLoopError("The submit_explanation arguments were not a JSON object.")
    return payload


def _parse_text_payload(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    try:
        payload = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        raise ToolLoopError("Muse Spark returned text that was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise ToolLoopError("Muse Spark returned text that was not a JSON object.")
    return payload


def run_tool_loop(
    client: Any,
    *,
    model: str,
    messages: list[dict[str, Any]],
    submit_tool: dict[str, Any],
    registry: InternalToolRegistry,
    max_turns: int,
    max_calls: int,
    timeout_seconds: float,
    max_tokens: int = 6000,
    clock: Callable[[], float] = time.monotonic,
    logger: logging.Logger | None = None,
) -> ToolLoopOutcome:
    """Run a bounded, read-only tool-calling loop against an OpenAI-compatible client.

    The loop is deliberately fail-closed:

    - the model may only call tools that the registry exposed for this investigation;
    - write/execute names are refused before any handler runs;
    - every tool counts against a hard call budget;
    - a repeated call with identical arguments aborts the loop;
    - the whole loop has a wall-clock deadline;
    - only ``submit_explanation`` produces the final payload.
    """

    log = logger or LOGGER
    if max_turns < 1 or max_calls < 1:
        raise ToolLoopError("Tool loop budgets must be at least one turn and one call.")
    deadline = clock() + max(1.0, float(timeout_seconds))
    call_budget = max(1, int(max_calls))
    calls_used = 0
    seen: set[tuple[str, str]] = set()
    conversation = list(messages)
    tools = [submit_tool, *registry.definitions()]
    allowed = registry.allowed_names()

    for turn in range(1, max(1, int(max_turns)) + 1):
        if clock() >= deadline:
            raise ToolLoopError(f"Tool loop exceeded its {int(timeout_seconds)}s deadline.")
        response = retry_with_backoff(
            lambda: client.chat.completions.create(
                model=model,
                messages=list(conversation),
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
                max_tokens=max_tokens,
            ),
            max_attempts=2,
            base_delay=0.6,
            max_delay=3.0,
            should_retry=_retryable,
        )
        choices = _get(response, "choices", []) or []
        if not choices:
            raise ToolLoopError("Meta Model API returned no choices.")
        message = _get(choices[0], "message")
        if message is None:
            raise ToolLoopError("Meta Model API returned a choice without a message.")
        tool_calls = _get(message, "tool_calls", []) or []
        if not tool_calls:
            content = str(_get(message, "content", "") or "").strip()
            if not content:
                raise ToolLoopError("Meta Model API returned neither a tool call nor text content.")
            log.info("tool_loop.final_text turn=%s tool_calls=%s", turn, calls_used)
            return ToolLoopOutcome(
                payload=_parse_text_payload(content), tool_calls_used=calls_used, calls=registry.calls
            )

        conversation.append(_assistant_message(message, list(tool_calls)))

        for call in tool_calls:
            function = _get(call, "function", {}) or {}
            name = str(_get(function, "name", "") or "").strip()
            raw_arguments = _normalize_arguments(_get(function, "arguments"))
            call_id = str(_get(call, "id", "") or f"call_{turn}_{calls_used}")
            calls_used += 1
            if calls_used > call_budget:
                raise ToolLoopError(f"Tool call budget of {call_budget} was exceeded.")

            if name == "submit_explanation":
                payload = _parse_submit(raw_arguments)
                log.info("tool_loop.submit turn=%s tool_calls=%s", turn, calls_used)
                return ToolLoopOutcome(payload=payload, tool_calls_used=calls_used, calls=registry.calls)

            signature = (name, raw_arguments)
            if signature in seen:
                raise ToolLoopError(f"The model repeated an identical tool call: {name or '[unnamed]'}.")
            seen.add(signature)
            if name not in allowed:
                result: dict[str, Any] = {
                    "error": "Tool is not registered for this investigation.",
                    "tool": safe_text(name, limit=120),
                }
                log.warning("tool_loop.refused turn=%s name=%s", turn, safe_text(name, limit=120) or "[unnamed]")
            else:
                try:
                    arguments = json.loads(raw_arguments or "{}")
                except json.JSONDecodeError:
                    result = {"error": "Tool arguments were not valid JSON."}
                else:
                    if not isinstance(arguments, dict):
                        result = {"error": "Tool arguments must be a JSON object."}
                    else:
                        try:
                            result = registry.execute(name, arguments)
                            log.info("tool_loop.call turn=%s name=%s status=ok", turn, name)
                        except ToolError as exc:
                            result = {"error": safe_text(str(exc), limit=500), "tool": name}
                            log.warning(
                                "tool_loop.call turn=%s name=%s status=error error=%s",
                                turn,
                                name,
                                safe_text(str(exc), limit=200),
                            )
            serialized = json.dumps(result, ensure_ascii=True, sort_keys=True)
            if len(serialized) > MAX_TOOL_RESULT_MESSAGE_CHARS:
                serialized = json.dumps(
                    {
                        "truncated": True,
                        "note": "Tool result exceeded the message cap.",
                        "keys": sorted(str(key) for key in result)[:20],
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                )
            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": safe_text(call_id, limit=120),
                    "content": serialized,
                }
            )

    raise ToolLoopError(f"Tool loop used all {max_turns} turns without submitting an explanation.")
