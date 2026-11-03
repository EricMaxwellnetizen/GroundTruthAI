from __future__ import annotations

import json
import re
from typing import Any

from groundtruth.config import Settings
from groundtruth.ai.fallback import build_fallback_explanation
from groundtruth.ai.prompt_builder import build_ai_bundle, explanation_tool_schema, system_prompt, user_prompt
from groundtruth.ai.validation import AIValidationError, validate_explanation
from groundtruth.models.ai import AIExplanation
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import safe_text
from groundtruth.utils.retry import retry_with_backoff

JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AIUnavailable(RuntimeError):
    pass


def _retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status <= 599):
        return True
    return isinstance(exc, (TimeoutError, ConnectionError, OSError))


class AIExplainService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.last_error: str | None = None

    @property
    def configured(self) -> bool:
        return bool(self.settings.ai_enabled and self.settings.model_api_key)

    def explain(self, result: LineageResult) -> AIExplanation:
        if not self.configured:
            return build_fallback_explanation(
                result,
                reason="Meta Muse Spark is not configured; set AI_ENABLED=true and MODEL_API_KEY to enable it.",
                model=self.settings.meta_model,
            )
        try:
            return self._explain_remote(result)
        except (AIUnavailable, AIValidationError) as exc:
            self.last_error = safe_text(str(exc), limit=500)
            return build_fallback_explanation(
                result,
                reason=f"Muse Spark explanation unavailable: {self.last_error}",
                model=self.settings.meta_model,
            )
        except Exception as exc:
            self.last_error = f"{exc.__class__.__name__}: {safe_text(str(exc), limit=400)}"
            return build_fallback_explanation(
                result,
                reason=f"Muse Spark explanation unavailable: {self.last_error}",
                model=self.settings.meta_model,
            )

    def _explain_remote(self, result: LineageResult) -> AIExplanation:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AIUnavailable("The OpenAI-compatible client package is not installed.") from exc

        client = OpenAI(
            api_key=self.settings.model_api_key,
            base_url=self.settings.meta_api_base_url,
            timeout=float(self.settings.request_timeout_seconds),
        )
        bundle = build_ai_bundle(result)
        tool = explanation_tool_schema(result.status)
        try:
            response = retry_with_backoff(
                lambda: client.chat.completions.create(
                    model=self.settings.meta_model,
                    messages=[
                        {"role": "system", "content": system_prompt()},
                        {"role": "user", "content": user_prompt(result, bundle)},
                    ],
                    tools=[tool],
                    tool_choice="auto",
                    temperature=0.1,
                    max_tokens=1800,
                ),
                max_attempts=2,
                base_delay=0.6,
                max_delay=3.0,
                should_retry=_retryable,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status in {401, 403}:
                raise AIUnavailable("Meta Model API rejected the API key or model access.") from exc
            if status == 429:
                raise AIUnavailable("Meta Model API rate-limited the explanation request.") from exc
            raise AIUnavailable(f"Meta Model API request failed: {exc.__class__.__name__}.") from exc

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise AIUnavailable("Meta Model API returned no choices.")
        message = choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []
        tool_calls_used = len(tool_calls)
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
            text = JSON_FENCE.sub("", str(content).strip())
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise AIValidationError("Muse Spark returned text that was not valid JSON.") from exc
        assert payload is not None
        return validate_explanation(
            payload,
            result,
            model=self.settings.meta_model,
            tool_calls_used=tool_calls_used,
        )


def attach_ai_explanation(result: LineageResult, explanation: AIExplanation) -> LineageResult:
    return result.model_copy(update={"ai_explanation": explanation})
