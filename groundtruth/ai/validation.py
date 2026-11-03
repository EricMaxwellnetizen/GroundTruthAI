from __future__ import annotations

import html
import re
from typing import Any

from pydantic import ValidationError

from groundtruth.models.ai import AIExplanation, AIFact, AINextStep
from groundtruth.models.enums import LineageStatus, RecommendationCode
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import safe_text

TAG_PATTERN = re.compile(r"<[^>]{1,300}>")
DANGEROUS_SCHEME = re.compile(r"(?i)\b(?:javascript|data|vbscript):")
UNSAFE_ACTION = re.compile(r"(?i)\b(delete|destroy|apply|terraform\s+apply|tofu\s+apply|import)\b")
MAX_FACTS = 20
MAX_QUESTIONS = 10
MAX_NEXT_STEPS = 10
MAX_WARNINGS = 12


class AIValidationError(ValueError):
    pass


def sanitize_text(value: str, *, limit: int = 1200) -> str:
    cleaned = TAG_PATTERN.sub("", value or "")
    cleaned = DANGEROUS_SCHEME.sub("[blocked]", cleaned)
    cleaned = html.unescape(cleaned)
    return safe_text(cleaned, limit=limit).strip()


def _check_status_consistency(text: str, result: LineageResult) -> None:
    for status in LineageStatus:
        if status == result.status:
            continue
        if re.search(rf"\b{re.escape(status.value)}\b", text):
            raise AIValidationError(f"Model output referenced a different deterministic status: {status.value}.")
    for code in RecommendationCode:
        if code == result.recommendation.code:
            continue
        if re.search(rf"\b{re.escape(code.value)}\b", text):
            raise AIValidationError(f"Model output referenced a different recommendation code: {code.value}.")


def _check_unsafe_steps(steps: list[AINextStep]) -> None:
    for step in steps:
        if UNSAFE_ACTION.search(step.step):
            raise AIValidationError("Model output suggested an autonomous apply, import, destroy, or delete action.")


def validate_explanation(
    payload: dict[str, Any],
    result: LineageResult,
    *,
    model: str | None = None,
    tool_calls_used: int = 0,
) -> AIExplanation:
    if not isinstance(payload, dict):
        raise AIValidationError("Model output was not a JSON object.")
    allowed_fields = {"summary", "established_facts", "unresolved_questions", "next_steps", "warnings"}
    unknown = set(payload) - allowed_fields
    if unknown:
        raise AIValidationError(f"Model output contained unsupported fields: {', '.join(sorted(unknown))}.")
    allowed_ids = set(result.evidence_ids)
    try:
        data = {
            "summary": sanitize_text(str(payload.get("summary") or ""), limit=2400),
            "established_facts": [
                AIFact(
                    statement=sanitize_text(str(item.get("statement") or ""), limit=900),
                    evidence_ids=[str(value) for value in item.get("evidence_ids") or []],
                )
                for item in payload.get("established_facts") or []
                if isinstance(item, dict)
            ][:MAX_FACTS],
            "unresolved_questions": [
                sanitize_text(str(item), limit=500) for item in payload.get("unresolved_questions") or []
            ][:MAX_QUESTIONS],
            "next_steps": [
                AINextStep(
                    step=sanitize_text(str(item.get("step") or ""), limit=600),
                    reason=sanitize_text(str(item.get("reason") or ""), limit=800),
                    evidence_ids=[str(value) for value in item.get("evidence_ids") or []],
                )
                for item in payload.get("next_steps") or []
                if isinstance(item, dict)
            ][:MAX_NEXT_STEPS],
            "warnings": [sanitize_text(str(item), limit=500) for item in payload.get("warnings") or []][:MAX_WARNINGS],
        }
        explanation = AIExplanation(
            generated_by="muse-spark",
            model=model,
            tool_calls_used=max(0, int(tool_calls_used)),
            **data,
        )
    except (ValidationError, ValueError) as exc:
        raise AIValidationError(f"Model output failed schema validation: {exc}") from exc

    if not explanation.summary:
        raise AIValidationError("Model output had an empty summary.")

    all_text = " ".join(
        [explanation.summary]
        + [fact.statement for fact in explanation.established_facts]
        + explanation.unresolved_questions
        + [step.step for step in explanation.next_steps]
        + explanation.warnings
    )
    _check_status_consistency(all_text, result)
    _check_unsafe_steps(explanation.next_steps)

    referenced: set[str] = set()
    for fact in explanation.established_facts:
        if not fact.evidence_ids:
            raise AIValidationError("An established fact had no evidence citation.")
        for evidence_id in fact.evidence_ids:
            if evidence_id not in allowed_ids:
                raise AIValidationError(f"Unknown evidence ID referenced: {evidence_id}.")
            referenced.add(evidence_id)
    for step in explanation.next_steps:
        for evidence_id in step.evidence_ids:
            if evidence_id not in allowed_ids:
                raise AIValidationError(f"Unknown evidence ID referenced: {evidence_id}.")
            referenced.add(evidence_id)
    return explanation
