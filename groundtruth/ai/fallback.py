from __future__ import annotations

from groundtruth.models.ai import AIExplanation, AIFact, AINextStep
from groundtruth.models.enums import LineageStatus, SourceType
from groundtruth.models.lineage import LineageResult
from groundtruth.utils.redaction import safe_text


def _evidence_id(result: LineageResult, source: SourceType) -> str | None:
    for item in result.evidence:
        if item.source == source:
            return item.evidence_id
    return None


def build_fallback_explanation(
    result: LineageResult,
    *,
    reason: str | None = None,
    model: str | None = None,
) -> AIExplanation:
    facts: list[AIFact] = []
    aws_evidence = _evidence_id(result, SourceType.AWS_LAMBDA)
    if aws_evidence:
        facts.append(
            AIFact(
                statement=(
                    f"The deterministic result is {result.status.value}: {safe_text(result.status_reason, limit=500)}"
                ),
                evidence_ids=[aws_evidence],
            )
        )
    for owner in result.current_owners[:3]:
        if owner.evidence_ids:
            facts.append(
                AIFact(
                    statement=(
                        f"Current owner workspace {owner.workspace.name} contains the exact address "
                        f"{owner.resource_address}."
                    ),
                    evidence_ids=owner.evidence_ids[:3],
                )
            )
    for owner in result.historical_managers[:3]:
        if owner.evidence_ids:
            facts.append(
                AIFact(
                    statement=(
                        f"Historical manager workspace {owner.workspace.name} contains the exact address "
                        f"{owner.resource_address}; it is not an active binding."
                    ),
                    evidence_ids=owner.evidence_ids[:3],
                )
            )
    if result.repository_lineage:
        commit_evidence = _evidence_id(result, SourceType.GIT_COMMIT)
        if commit_evidence:
            lineage = result.repository_lineage
            facts.append(
                AIFact(
                    statement=(
                        f"Repository context is available for {lineage.repository}"
                        f"{f' at commit {lineage.vcs_revision[:12]}' if lineage.vcs_revision else ''}; "
                        "Git evidence does not by itself prove current state ownership."
                    ),
                    evidence_ids=[commit_evidence],
                )
            )
    if result.cloudtrail_events:
        event_evidence = _evidence_id(result, SourceType.CLOUDTRAIL)
        if event_evidence:
            facts.append(
                AIFact(
                    statement=(
                        f"CloudTrail returned {len(result.cloudtrail_events)} matching management event(s); "
                        "these are not invocation records."
                    ),
                    evidence_ids=[event_evidence],
                )
            )
    if result.activity:
        activity_evidence = _evidence_id(result, SourceType.CLOUDWATCH_METRIC)
        if activity_evidence:
            facts.append(
                AIFact(
                    statement=(
                        f"CloudWatch returned {result.activity.invocation_datapoints} invocation datapoint(s) "
                        f"for the {result.activity.window_start.date()} to {result.activity.window_end.date()} window."
                    ),
                    evidence_ids=[activity_evidence],
                )
            )
    facts = [fact for fact in facts if fact.evidence_ids]
    next_steps = [
        AINextStep(
            step=safe_text(result.recommendation.title, limit=300),
            reason=safe_text(result.recommendation.explanation, limit=700),
            evidence_ids=result.recommendation.evidence_ids[:5],
        )
    ]
    warnings = []
    if reason:
        warnings.append(safe_text(reason, limit=500))
    warnings.append("Muse Spark explanation was unavailable or invalid; this is the deterministic fallback.")
    warnings.extend(safe_text(item, limit=300) for item in result.limitations[:4])
    summary = (
        f"{result.status.value} with {result.confidence.value} confidence. "
        f"{safe_text(result.status_reason, limit=700)} "
        f"Confidence rule: {safe_text(result.confidence_rule, limit=400)}"
    )
    if result.status in {LineageStatus.INSUFFICIENT_ACCESS, LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES}:
        summary += " This result is not proof that no owner exists."
    return AIExplanation(
        generated_by="deterministic_fallback",
        model=model,
        summary=safe_text(summary, limit=1600),
        established_facts=facts,
        unresolved_questions=[safe_text(item, limit=400) for item in result.unresolved_questions[:8]],
        next_steps=next_steps,
        warnings=warnings,
        tool_calls_used=0,
    )
