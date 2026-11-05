from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import LineageStatus
from groundtruth.models.lineage import LineageResult


class ActionKind(str, Enum):
    REATTRIBUTE = "reattribute"
    DELETE = "delete"


class ActionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ActionKind
    function_name: str
    arn: str | None = None
    eligible: bool
    blocked_reason: str | None = None
    requires_confirmation: str
    steps: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    kind: str
    function_name: str
    mode: str
    outcome: str
    detail: str


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def plan_action(result: LineageResult, kind: ActionKind, *, target_workspace: str | None = None) -> ActionPlan:
    resource = result.resource
    confirm = resource.name
    evidence = list(result.recommendation.evidence_ids)
    if kind == ActionKind.DELETE:
        if result.status == LineageStatus.CURRENT_OWNER_FOUND:
            return ActionPlan(
                kind=kind,
                function_name=resource.name,
                arn=resource.arn,
                eligible=False,
                blocked_reason="Function is actively managed. Remove it from its workspace state through a reviewed Terraform change first; direct deletion would orphan the state binding.",
                requires_confirmation=confirm,
                evidence_ids=evidence,
            )
        if result.status in {LineageStatus.MULTIPLE_ACTIVE_OWNERS, LineageStatus.IDENTITY_AMBIGUOUS}:
            return ActionPlan(
                kind=kind,
                function_name=resource.name,
                arn=resource.arn,
                eligible=False,
                blocked_reason="Ownership is contested or ambiguous. Resolve ownership first — deleting under dispute risks removing a function another workspace manages.",
                requires_confirmation=confirm,
                evidence_ids=evidence,
            )
        if result.status == LineageStatus.INSUFFICIENT_ACCESS:
            return ActionPlan(
                kind=kind,
                function_name=resource.name,
                arn=resource.arn,
                eligible=False,
                blocked_reason="Ownership could not be checked. Grant read access and re-investigate before considering deletion.",
                requires_confirmation=confirm,
                evidence_ids=evidence,
            )
        steps = [
            "Capture this evidence bundle and attach it to the change ticket.",
            "Confirm no invocations in the last 14 days (CloudWatch) and no event sources depend on the function.",
            f"Delete Lambda function {resource.name} in {resource.region} (DeleteFunction).",
            "Re-run the investigation and confirm the function no longer resolves.",
        ]
        if result.activity and not result.activity.no_datapoints and (result.activity.total_invocations or 0) > 0:
            steps.insert(
                1,
                f"WARNING: {result.activity.total_invocations:,.0f} invocations observed in the checked window — obtain service-owner sign-off before deleting.",
            )
        return ActionPlan(
            kind=kind,
            function_name=resource.name,
            arn=resource.arn,
            eligible=True,
            requires_confirmation=confirm,
            steps=steps,
            evidence_ids=evidence,
        )
    # REATTRIBUTE
    target = (target_workspace or "").strip()
    if result.status == LineageStatus.MULTIPLE_ACTIVE_OWNERS:
        names = ", ".join(o.workspace.name for o in result.current_owners)
        return ActionPlan(
            kind=kind,
            function_name=resource.name,
            arn=resource.arn,
            eligible=True,
            requires_confirmation=confirm,
            evidence_ids=evidence,
            steps=[
                f"Active owners today: {names}. Pick the single authoritative workspace with both owning teams.",
                "In each non-authoritative workspace: `terraform state rm <address>` on a branch (never edit state by hand).",
                "Plan in sandbox; verify zero destroys; merge and apply through the normal pipeline.",
                "Re-run this investigation and confirm exactly one active owner remains.",
            ],
        )
    if not target:
        return ActionPlan(
            kind=kind,
            function_name=resource.name,
            arn=resource.arn,
            eligible=False,
            blocked_reason="Choose the target workspace that should own this function.",
            requires_confirmation=confirm,
            evidence_ids=evidence,
        )
    return ActionPlan(
        kind=kind,
        function_name=resource.name,
        arn=resource.arn,
        eligible=True,
        requires_confirmation=confirm,
        evidence_ids=evidence,
        steps=[
            f"Generate the adoption preview for workspace {target} (Lineage → Adoption proposal).",
            "Commit the resource + import block on a branch in that workspace's repository root.",
            "Run plan in an isolated sandbox; verify the plan shows only the expected import.",
            "Apply through the workspace pipeline after second-reviewer approval.",
            "Re-run this investigation and confirm the function reports exactly one active owner.",
        ],
    )


class ActionExecutor:
    """Executes governed actions. Simulated mode mutates only the audit-backed
    simulation record. Live deletion additionally requires the explicit
    ALLOW_LIVE_ACTIONS gate plus typed confirmation; reattribution in live
    mode always produces a runbook (state surgery belongs in the pipeline,
    not in an API call from this console)."""

    def __init__(self, audit_path: Path, *, allow_live: bool = False) -> None:
        self.audit_path = Path(audit_path)
        self.allow_live = allow_live

    def audit(self) -> list[AuditEntry]:
        if not self.audit_path.exists():
            return []
        entries: list[AuditEntry] = []
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(AuditEntry(**json.loads(line)))
        return entries

    def _log(self, entry: AuditEntry) -> None:
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def execute(self, plan: ActionPlan, *, mode: str, confirmation: str) -> AuditEntry:
        if not plan.eligible:
            entry = AuditEntry(
                at=_utcnow(),
                kind=plan.kind.value,
                function_name=plan.function_name,
                mode=mode,
                outcome="blocked",
                detail=plan.blocked_reason or "Not eligible.",
            )
            self._log(entry)
            return entry
        if confirmation.strip() != plan.requires_confirmation:
            entry = AuditEntry(
                at=_utcnow(),
                kind=plan.kind.value,
                function_name=plan.function_name,
                mode=mode,
                outcome="rejected",
                detail="Typed confirmation did not match the function name.",
            )
            self._log(entry)
            return entry
        if mode == "live":
            if plan.kind == ActionKind.REATTRIBUTE:
                entry = AuditEntry(
                    at=_utcnow(),
                    kind=plan.kind.value,
                    function_name=plan.function_name,
                    mode=mode,
                    outcome="runbook_issued",
                    detail="Live reattribution is performed via the workspace pipeline; runbook steps recorded, no API mutation made.",
                )
                self._log(entry)
                return entry
            if not self.allow_live:
                entry = AuditEntry(
                    at=_utcnow(),
                    kind=plan.kind.value,
                    function_name=plan.function_name,
                    mode=mode,
                    outcome="blocked",
                    detail="Live actions are disabled. Enable GROUNDTRUTH_ALLOW_LIVE_ACTIONS in Settings to permit live deletion.",
                )
                self._log(entry)
                return entry
            self._delete_live(plan)
            entry = AuditEntry(
                at=_utcnow(),
                kind=plan.kind.value,
                function_name=plan.function_name,
                mode=mode,
                outcome="executed",
                detail=f"DeleteFunction issued for {plan.function_name}.",
            )
            self._log(entry)
            return entry
        entry = AuditEntry(
            at=_utcnow(),
            kind=plan.kind.value,
            function_name=plan.function_name,
            mode=mode,
            outcome="executed",
            detail=f"Simulated {plan.kind.value} applied to {plan.function_name}; recorded in audit log.",
        )
        self._log(entry)
        return entry

    @staticmethod
    def _delete_live(plan: ActionPlan) -> None:
        import boto3

        client = boto3.client("lambda")
        client.delete_function(FunctionName=plan.arn or plan.function_name)
