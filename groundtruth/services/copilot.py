from __future__ import annotations

import json
import re

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.config import Settings
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import safe_text

SUGGESTED_QUESTIONS = [
    "Who owns this function?",
    "Who last changed it?",
    "Is it safe to delete?",
    "What evidence supports the verdict?",
    "What should I do next?",
]


class CopilotAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    evidence_ids: list[str] = Field(default_factory=list)
    generated_by: str = "deterministic"
    model: str | None = None


def _owner_text(result: LineageResult) -> tuple[str, list[str]]:
    if result.current_owners:
        owners = "; ".join(
            f"{o.workspace.name} ({o.resource_address}, last seen {o.last_seen_at})" for o in result.current_owners
        )
        ids = [i for o in result.current_owners for i in o.evidence_ids]
        return f"Current owner: {owners}. Verdict {result.status.value} ({result.confidence.value} confidence).", ids
    if result.historical_managers:
        owners = "; ".join(f"{o.workspace.name} ({o.resource_address})" for o in result.historical_managers)
        ids = [i for o in result.historical_managers for i in o.evidence_ids]
        return (
            f"No current owner in the checked sources. Historical manager: {owners}. Verdict {result.status.value}.",
            ids,
        )
    return (
        f"No owner found in the checked sources. Verdict {result.status.value} — this is not proof the function is unowned.",
        list(result.recommendation.evidence_ids),
    )


def answer_deterministic(result: LineageResult, question: str) -> CopilotAnswer:
    q = question.lower()
    evidence_by_text = " ".join(f"{e.source_label}: {e.facts.get('title', '')}" for e in result.evidence)
    if any(k in q for k in ("delete", "remove", "retire", "safe to")):
        rec = result.recommendation
        ids = list(rec.evidence_ids) or [e.evidence_id for e in result.evidence[:3]]
        extra = " Adoption is blocked for this verdict." if rec.blocked_adoption else ""
        return CopilotAnswer(
            answer=f"Deterministic verdict: {result.status.value}. Recommended action: {rec.title}. {rec.explanation}{extra} Use the Action Center for the governed plan; deletion always needs typed confirmation and an audit entry.",
            evidence_ids=ids,
        )
    if any(k in q for k in ("who changed", "last change", "actor", "who ran", "changed it")):
        if result.actors:
            lines = "; ".join(
                f"{a.identity_type} {a.identifier} ({a.source.value}, {a.timestamp})" for a in result.actors[:5]
            )
            return CopilotAnswer(
                answer=f"Recorded actors (kept separate by source, never merged into one 'creator'): {lines}.",
                evidence_ids=[a.evidence_id for a in result.actors[:5]],
            )
        return CopilotAnswer(
            answer="No actor evidence was recorded in the checked sources. That is a coverage gap, not proof nobody changed it.",
            evidence_ids=[],
        )
    if any(k in q for k in ("evidence", "prove", "support", "why", "verdict")):
        ids = result.evidence_ids[:6]
        facts = "; ".join(str(e.facts.get("title", e.source_label)) for e in result.evidence[:4])
        return CopilotAnswer(
            answer=f"{result.status_reason} Confidence rule: {result.confidence_rule}. Key records: {facts}.",
            evidence_ids=ids,
        )
    if any(k in q for k in ("next", "do now", "should i", "action")):
        rec = result.recommendation
        steps = " Unresolved: " + "; ".join(result.unresolved_questions[:3]) if result.unresolved_questions else ""
        return CopilotAnswer(answer=f"Next: {rec.title}. {rec.explanation}{steps}", evidence_ids=list(rec.evidence_ids))
    if any(k in q for k in ("active", "used", "invok", "traffic", "cost", "idle")):
        act = result.activity
        if act is None:
            return CopilotAnswer(answer="No CloudWatch activity was collected for this investigation.", evidence_ids=[])
        return CopilotAnswer(
            answer=f"CloudWatch window {act.window_start.date()} to {act.window_end.date()}: {act.total_invocations:,.0f} invocations, {act.total_errors:,.0f} errors, latest non-zero bucket {act.latest_nonzero_invocations_at}. A metric bucket is an interval, not an exact invocation time.",
            evidence_ids=[act.evidence_id] if act.evidence_id else result.evidence_ids[:2],
        )
    text, ids = _owner_text(result)
    return CopilotAnswer(
        answer=text + f" ({len(result.evidence)} evidence records checked: {evidence_by_text[:180]}…)",
        evidence_ids=ids or result.evidence_ids[:3],
    )


class CopilotService:
    """Ask GroundTruth. With a model configured, Muse Spark / Llama answers
    from the same minimized evidence bundle and must cite known evidence IDs;
    anything uncited or unparseable falls back to the deterministic answer."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()

    def ask(self, result: LineageResult, question: str) -> CopilotAnswer:
        fallback = answer_deterministic(result, question)
        if not self.settings.ai_configured:
            return fallback
        try:
            return self._ask_remote(result, question, fallback)
        except Exception:
            return fallback

    def _ask_remote(self, result: LineageResult, question: str, fallback: CopilotAnswer) -> CopilotAnswer:
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.active_api_key, base_url=self.settings.active_base_url, timeout=60)
        bundle = {
            "status": result.status.value,
            "confidence": result.confidence.value,
            "status_reason": result.status_reason,
            "evidence": [
                {
                    "evidence_id": e.evidence_id,
                    "source": e.source_label,
                    "title": e.facts.get("title", ""),
                    "detail": safe_text(str(e.facts.get("detail", "")), limit=240),
                }
                for e in result.evidence[:24]
            ],
            "recommendation": result.recommendation.title,
        }
        response = client.chat.completions.create(
            model=self.settings.active_model,
            temperature=0.1,
            max_tokens=900,
            messages=[
                {
                    "role": "system",
                    "content": 'You are GroundTruth\'s copilot. Answer only from the supplied evidence JSON. Cite evidence_id values inline like [ev_...]. Never invent owners, people, or events. If evidence is insufficient, say what is missing. Reply with JSON: {"answer": string, "evidence_ids": [string]}.',
                },
                {
                    "role": "user",
                    "content": f"Evidence: {json.dumps(bundle)}\nQuestion: {safe_text(question, limit=400)}",
                },
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.MULTILINE).strip()
        payload = json.loads(raw)
        known = set(result.evidence_ids)
        cited = [i for i in payload.get("evidence_ids", []) if i in known]
        cited += [i for i in re.findall(r"\[(ev_[A-Za-z0-9_]+)\]", str(payload.get("answer", ""))) if i in known]
        answer = safe_text(str(payload.get("answer", "")), limit=1200)
        if not answer or not cited:
            return fallback
        provider = "llama" if self.settings.ai_provider == "llama_open_weights" else "muse-spark"
        return CopilotAnswer(
            answer=answer, evidence_ids=sorted(set(cited))[:8], generated_by=provider, model=self.settings.active_model
        )
