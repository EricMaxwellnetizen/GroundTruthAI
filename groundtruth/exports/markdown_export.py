from __future__ import annotations

from typing import Any

from groundtruth.exports.common import build_evidence_bundle
from groundtruth.models.lineage import LineageResult
from groundtruth.models.report import EvidenceBundle
from groundtruth.utils.redaction import safe_text


def _cell(value: Any, limit: int = 240) -> str:
    text = safe_text(str(value if value is not None else ""), limit=limit)
    return text.replace("|", "\\|").replace("\n", " ").replace("`", "'")


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return lines


def _owner_table(owners: list[dict[str, Any]]) -> list[str]:
    if not owners:
        return ["_None found._"]
    rows = []
    for owner in owners:
        workspace = owner.get("workspace") or {}
        run = owner.get("run") or {}
        rows.append(
            [
                workspace.get("name") or workspace.get("id") or "",
                owner.get("resource_address") or "",
                owner.get("match_type") or "",
                owner.get("last_seen_at") or "",
                run.get("id") or "",
                ", ".join(owner.get("evidence_ids") or []),
            ]
        )
    return _table(["Workspace", "Address", "Match", "Last seen", "Run", "Evidence"], rows)


def export_markdown(
    result: LineageResult,
    *,
    redact: bool = True,
) -> tuple[str, EvidenceBundle]:
    bundle = build_evidence_bundle(result, redact=redact)
    resource = bundle.resource
    lines: list[str] = ["# GroundTruth Evidence Report", ""]
    if bundle.fixture:
        lines.extend(
            [
                "> **Simulated environment (Northgate Production mirror).** This report was produced from simulated records",
                "> that mirror live AWS, Scalr and GitLab payloads. It does not describe a live customer account.",
                "",
            ]
        )
    lines.extend(
        [
            f"**Investigation:** `{safe_text(bundle.investigation_id, 120)}`  ",
            f"**Exported:** {bundle.exported_at.isoformat()}  ",
            f"**Mode:** {bundle.mode}  ",
            f"**Status:** `{safe_text(bundle.status, 80)}`  ",
            f"**Confidence:** `{safe_text(bundle.confidence, 40)}`  ",
            f"**Checksum:** `sha256:{bundle.integrity.checksum if bundle.integrity else 'unavailable'}`",
            "",
            f"**Why this status:** {safe_text(bundle.status_reason, 600)}",
            "",
            f"**Confidence rule:** {safe_text(bundle.confidence_rule, 600)}",
            "",
            f"**Confidence reason:** {safe_text(bundle.confidence_reason, 600)}",
            "",
            "## Resource",
            "",
        ]
    )
    lines.extend(
        _table(
            ["Field", "Value"],
            [
                ["Name", resource.name],
                ["Type", resource.resource_type],
                ["ARN", resource.arn or ""],
                ["Account", resource.account_id or ""],
                ["Region", resource.region or ""],
                ["Status", resource.status or ""],
                ["Last modified", resource.last_modified_at.isoformat() if resource.last_modified_at else ""],
                ["Tags", ", ".join(f"{key}={value}" for key, value in sorted(resource.tags.items()))],
            ],
        )
    )
    lines.extend(["", "## Ownership", "", "### Current owners", ""])
    lines.extend(_owner_table(bundle.current_owners))
    lines.extend(["", "### Historical managers", ""])
    lines.extend(_owner_table(bundle.historical_managers))

    lineage = bundle.repository_lineage
    lines.extend(["", "## Repository lineage", ""])
    if not lineage:
        lines.append("_No repository lineage was collected._")
    else:
        lines.extend(
            [
                f"- Repository: {safe_text(str(lineage.get('repository') or ''), 300)}",
                f"- Branch: {safe_text(str(lineage.get('branch') or ''), 200)}",
                f"- VCS revision: {safe_text(str(lineage.get('vcs_revision') or ''), 100)}",
                f"- Commit verified: {lineage.get('commit_verified')}",
                f"- Working directory: {safe_text(str(lineage.get('working_directory') or ''), 300)}",
            ]
        )
        commit = lineage.get("commit")
        if isinstance(commit, dict):
            lines.extend(
                [
                    "",
                    f"**Commit `{safe_text(str(commit.get('sha') or ''), 60)}`**",
                    "",
                    f"- Author: {safe_text(str(commit.get('author_name') or ''), 200)}",
                    f"- Committed at: {commit.get('committed_at') or ''}",
                    f"- Message: {safe_text(str(commit.get('message') or ''), 600)}",
                ]
            )
        for label, key in (("File matches", "file_matches"), ("History matches", "history_matches")):
            matches = lineage.get(key) or []
            if matches:
                lines.extend(["", f"**{label}**", ""])
                lines.extend(
                    _table(
                        ["Path", "Line", "Matched", "Commit", "Evidence"],
                        [
                            [
                                item.get("path") or "",
                                item.get("line") or "",
                                item.get("matched_string") or "",
                                item.get("commit_sha") or "",
                                item.get("evidence_id") or "",
                            ]
                            for item in matches
                        ],
                    )
                )

    lines.extend(["", "## Actors", ""])
    if bundle.actors:
        lines.extend(
            _table(
                ["Source", "Type", "Identifier", "Display name", "Observed", "Evidence"],
                [
                    [
                        actor.get("source") or "",
                        actor.get("identity_type") or "",
                        actor.get("identifier") or "",
                        actor.get("display_name") or "",
                        actor.get("timestamp") or "",
                        actor.get("evidence_id") or "",
                    ]
                    for actor in bundle.actors
                ],
            )
        )
    else:
        lines.append("_No actor evidence was collected._")

    lines.extend(["", "## CloudTrail management events", ""])
    if bundle.cloudtrail_events:
        lines.extend(
            _table(
                ["Time", "Event", "Principal", "Principal ARN", "Match", "Evidence"],
                [
                    [
                        event.get("event_time") or "",
                        event.get("event_name") or "",
                        event.get("principal_type") or "",
                        event.get("principal_arn") or "",
                        event.get("match_type") or "",
                        event.get("evidence_id") or "",
                    ]
                    for event in bundle.cloudtrail_events
                ],
            )
        )
    else:
        lines.append("_No matching CloudTrail events were collected._")

    lines.extend(["", "## Activity", ""])
    if bundle.activity:
        activity = bundle.activity
        lines.extend(
            [
                f"- Window: {activity.get('window_start')} to {activity.get('window_end')}",
                f"- Period: {activity.get('period_seconds')} seconds",
                f"- Latest non-zero invocations: {activity.get('latest_nonzero_invocations_at') or 'none'}",
                f"- Total invocations: {activity.get('total_invocations')}",
                f"- Total errors: {activity.get('total_errors')}",
                f"- Total throttles: {activity.get('total_throttles')}",
                f"- No datapoints: {activity.get('no_datapoints')}",
            ]
        )
    else:
        lines.append("_No CloudWatch activity was collected._")

    lines.extend(["", "## Dependencies", ""])
    if bundle.dependencies:
        lines.extend(
            _table(
                ["Kind", "Name", "Relationship", "Direction", "Match", "Evidence"],
                [
                    [
                        item.get("kind") or "",
                        item.get("name") or "",
                        item.get("relationship") or "",
                        item.get("direction") or "",
                        item.get("match_type") or "",
                        item.get("evidence_id") or "",
                    ]
                    for item in bundle.dependencies
                ],
            )
        )
    else:
        lines.append("_No dependency context was collected._")

    lines.extend(["", "## Evidence", ""])
    lines.extend(
        _table(
            ["ID", "Source", "Observed", "Match", "Confidence", "Title"],
            [
                [
                    item.get("evidence_id") or "",
                    item.get("source_label") or item.get("source") or "",
                    item.get("observed_at") or "",
                    item.get("match_type") or "",
                    item.get("match_confidence") or "",
                    (item.get("facts") or {}).get("title") or "",
                ]
                for item in bundle.evidence
            ],
        )
    )

    lines.extend(["", "## Coverage", ""])
    lines.extend(
        _table(
            ["Source", "Status", "Required", "Records", "Pages", "Notes"],
            [
                [
                    item.get("source") or "",
                    item.get("status") or "",
                    item.get("required"),
                    item.get("records"),
                    item.get("pages"),
                    "; ".join(item.get("notes") or []),
                ]
                for item in bundle.coverage
            ],
        )
    )

    lines.extend(["", "## Limitations", ""])
    lines.extend([f"- {safe_text(item, 500)}" for item in bundle.limitations] or ["_None recorded._"])

    lines.extend(["", "## Unresolved questions", ""])
    lines.extend([f"- {safe_text(item, 500)}" for item in bundle.unresolved_questions] or ["_None._"])

    recommendation = bundle.recommendation or {}
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"**{safe_text(str(recommendation.get('title') or ''), 300)}**",
            "",
            safe_text(str(recommendation.get("explanation") or ""), 1000),
            "",
            f"Adoption blocked: {recommendation.get('blocked_adoption')}",
        ]
    )

    explanation = bundle.ai_explanation
    lines.extend(["", "## AI explanation", ""])
    if not explanation:
        lines.append("_No AI explanation was attached. Use deterministic evidence only._")
    else:
        lines.extend(
            [
                f"- Generated by: `{safe_text(str(explanation.get('generated_by') or ''), 80)}`",
                f"- Model: `{safe_text(str(explanation.get('model') or ''), 120)}`",
                f"- Tool calls used: {explanation.get('tool_calls_used')}",
                "",
                safe_text(str(explanation.get("summary") or ""), 1500),
                "",
                "### Established facts",
                "",
            ]
        )
        facts = explanation.get("established_facts") or []
        lines.extend(
            [
                f"- {safe_text(str(fact.get('statement') or ''), 600)} ({', '.join(fact.get('evidence_ids') or [])})"
                for fact in facts
            ]
            or ["_None._"]
        )
        lines.extend(["", "### Next steps", ""])
        steps = explanation.get("next_steps") or []
        lines.extend(
            [
                f"- **{safe_text(str(step.get('step') or ''), 300)}** — "
                f"{safe_text(str(step.get('reason') or ''), 500)} "
                f"({', '.join(step.get('evidence_ids') or [])})"
                for step in steps
            ]
            or ["_None._"]
        )
        warnings = explanation.get("warnings") or []
        if warnings:
            lines.extend(["", "### Warnings", ""])
            lines.extend([f"- {safe_text(str(item), 500)}" for item in warnings])

    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Algorithm: {bundle.integrity.algorithm if bundle.integrity else 'sha256'}",
            f"- Checksum: `{bundle.integrity.checksum if bundle.integrity else 'unavailable'}`",
            f"- Redaction applied: {bundle.redaction_applied}",
            "",
            "_GroundTruth is read-only. This report is evidence for human review, not authorization to change infrastructure._",
            "",
        ]
    )
    return "\n".join(lines), bundle
