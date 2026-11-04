from __future__ import annotations

import json
from typing import Any

from groundtruth.config import Settings
from groundtruth.ai.fallback import build_fallback_explanation
from groundtruth.ai.prompt_builder import build_ai_bundle, explanation_tool_schema, system_prompt, user_prompt
from groundtruth.ai.tool_loop import ToolLoopError, run_tool_loop
from groundtruth.ai.tools import InternalToolRegistry, ToolCallRecord
from groundtruth.ai.validation import AIValidationError, validate_explanation
from groundtruth.mcp.manager import McpManager
from groundtruth.models.ai import AIExplanation
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import safe_text
from groundtruth.utils.retry import retry_with_backoff

JSON_FENCE_MARKER = "```"


class AIUnavailable(RuntimeError):
    pass


def _retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status <= 599):
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


class AIExplainService:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        mcp_manager: McpManager | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.mcp_manager = mcp_manager
        self.last_error: str | None = None
        self.last_tool_calls: list[ToolCallRecord] = []

    @property
    def configured(self) -> bool:
        return self.settings.ai_configured

    def explain(self, result: LineageResult) -> AIExplanation:
        self.last_error = None
        self.last_tool_calls = []
        if not self.configured:
            provider = (
                "Llama open-weights endpoint"
                if self.settings.ai_provider == "llama_open_weights"
                else "Meta Muse Spark"
            )
            return build_fallback_explanation(
                result,
                reason=f"{provider} is not configured; enable AI and add credentials in Settings to use it.",
                model=self.settings.active_model,
            )
        try:
            return self._explain_remote(result)
        except (AIUnavailable, AIValidationError, ToolLoopError) as exc:
            self.last_error = safe_text(str(exc), limit=500)
            return build_fallback_explanation(
                result,
                reason=f"Muse Spark explanation unavailable: {self.last_error}",
                model=self.settings.active_model,
            )
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {safe_text(str(exc), limit=400)}"
            return build_fallback_explanation(
                result,
                reason=f"Muse Spark explanation unavailable: {self.last_error}",
                model=self.settings.active_model,
            )

    def _client(self):
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIUnavailable("The OpenAI-compatible client package is not installed.") from exc

        return OpenAI(
            api_key=self.settings.active_api_key,
            base_url=self.settings.active_base_url,
            # Muse Spark is a reasoning model. A 20s connector timeout is too
            # short once the model spends tokens on reasoning before emitting
            # the structured tool call, so give AI calls a separate floor.
            timeout=max(90.0, float(self.settings.request_timeout_seconds)),
        )

    def _explain_remote(self, result: LineageResult) -> AIExplanation:
        client = self._client()
        bundle = build_ai_bundle(result)
        tool = explanation_tool_schema(result.status)
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_prompt(result, bundle)},
        ]
        if self.settings.ai_tool_loop_enabled:
            registry = InternalToolRegistry(result, mcp_manager=self.mcp_manager)
            try:
                outcome = run_tool_loop(
                    client,
                    model=self.settings.active_model,
                    messages=messages,
                    submit_tool=tool,
                    registry=registry,
                    max_turns=self.settings.ai_max_tool_turns,
                    max_calls=self.settings.ai_max_tool_calls,
                    timeout_seconds=self.settings.ai_tool_timeout_seconds,
                )
            finally:
                self.last_tool_calls = list(registry.calls)
            return validate_explanation(
                outcome.payload,
                result,
                model=self.settings.active_model,
                tool_calls_used=outcome.tool_calls_used,
            )

        response = self._single_request(client, messages, tool)
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        payload, used = self._extract_payload(message, tool_calls)
        return validate_explanation(
            payload,
            result,
            model=self.settings.active_model,
            tool_calls_used=used,
        )

    def _single_request(self, client, messages: list[dict[str, Any]], tool: dict[str, Any]):
        try:
            return retry_with_backoff(
                lambda: client.chat.completions.create(
                    model=self.settings.active_model,
                    messages=messages,
                    tools=[tool],
                    tool_choice="auto",
                    temperature=0.1,
                    # The evidence bundle is large and Muse Spark reasons
                    # before calling the tool. 1,800 tokens truncates the
                    # response before submit_explanation is emitted.
                    max_tokens=6000,
                ),
                max_attempts=2,
                base_delay=0.6,
                max_delay=3.0,
                should_retry=_retryable,
            )
        except Exception as exc:
            self._raise_api_error(exc)

    @staticmethod
    def _raise_api_error(exc: BaseException) -> None:
        status = getattr(exc, "status_code", None)
        if status in {401, 403}:
            raise AIUnavailable("Meta Model API rejected the API key or model access.") from exc
        if status == 429:
            raise AIUnavailable("Meta Model API rate-limited the explanation request.") from exc
        raise AIUnavailable(f"Meta Model API request failed: {exc.__class__.__name__}.") from exc

    @staticmethod
    def _extract_payload(message: Any, tool_calls: list[Any]) -> tuple[dict[str, Any], int]:
        payload: dict[str, Any] | None = None
        for call in tool_calls:
            function = getattr(call, "function", None)
            if function and getattr(function, "name", None) == "submit_explanation":
                raw_arguments = getattr(function, "arguments", "") or "{}"
                try:
                    payload = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise AIValidationError("The submit_explanation arguments were not valid JSON.") from exc
                break
        if payload is None:
            content = getattr(message, "content", None)
            if not content:
                raise AIUnavailable("Meta Model API returned neither a tool call nor text content.")
            text = str(content).strip()
            if text.startswith(JSON_FENCE_MARKER):
                first_newline = text.find("\n")
                if first_newline != -1:
                    text = text[first_newline + 1 :]
                if text.endswith(JSON_FENCE_MARKER):
                    text = text[: -len(JSON_FENCE_MARKER)]
            try:
                payload = json.loads(text.strip())
            except json.JSONDecodeError as exc:
                raise AIValidationError("Muse Spark returned text that was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise AIValidationError("Muse Spark returned JSON that was not an object.")
        return payload, len(tool_calls)


def attach_ai_explanation(result: LineageResult, explanation: AIExplanation) -> LineageResult:
    return result.model_copy(update={"ai_explanation": explanation})
