from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from groundtruth.models.enums import LineageStatus
from groundtruth.models.lineage import LineageResult
from groundtruth.services.actions import ActionExecutor, ActionKind, plan_action

ATTENTION_STATUSES = {
    LineageStatus.MULTIPLE_ACTIVE_OWNERS,
    LineageStatus.HISTORICAL_OWNER_FOUND,
    LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES,
    LineageStatus.CANDIDATE_LINEAGE,
}


class AttentionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function_name: str
    status: str
    suggested_action: str
    auto_eligible: bool
    reason: str


class AutomationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    simulated_only: bool = True
    allow_delete: bool = False


def attention_for(result: LineageResult) -> AttentionItem | None:
    if result.status not in ATTENTION_STATUSES:
        return None
    if result.status == LineageStatus.MULTIPLE_ACTIVE_OWNERS:
        return AttentionItem(
            function_name=result.resource.name,
            status=result.status.value,
            suggested_action="reattribute",
            auto_eligible=False,
            reason="Duplicate ownership needs a human decision on the authoritative workspace.",
        )
    if result.status == LineageStatus.HISTORICAL_OWNER_FOUND:
        return AttentionItem(
            function_name=result.resource.name,
            status=result.status.value,
            suggested_action="reattribute",
            auto_eligible=True,
            reason="Historical manager known; adoption preview can be prepared automatically.",
        )
    if result.status == LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES:
        return AttentionItem(
            function_name=result.resource.name,
            status=result.status.value,
            suggested_action="review_then_delete_or_adopt",
            auto_eligible=False,
            reason="No owner found in checked sources; a human must choose adoption vs retirement.",
        )
    return AttentionItem(
        function_name=result.resource.name,
        status=result.status.value,
        suggested_action="review_candidate",
        auto_eligible=False,
        reason="Candidate evidence only; manual verification required.",
    )


def scan_attention(results: list[LineageResult]) -> list[AttentionItem]:
    items = [item for result in results if (item := attention_for(result)) is not None]
    return sorted(items, key=lambda item: item.function_name)


def run_automation(
    results: list[LineageResult],
    policy: AutomationPolicy,
    executor: ActionExecutor,
) -> list[dict[str, str]]:
    """Executes only policy-eligible, non-destructive preparations.

    Automation never deletes and never resolves ownership disputes on its own:
    it prepares reattribution runbooks for historical owners in the simulated
    environment and records everything else as queued for a human. Live mode
    is plan-only regardless of policy.
    """
    outcomes: list[dict[str, str]] = []
    for result in results:
        item = attention_for(result)
        if item is None:
            continue
        if not policy.enabled:
            outcomes.append(
                {"function": item.function_name, "outcome": "queued", "detail": "Automation policy is disabled."}
            )
            continue
        if result.mode == "live":
            outcomes.append(
                {
                    "function": item.function_name,
                    "outcome": "plan_only",
                    "detail": "Live automation prepares plans only; execution stays approval-gated.",
                }
            )
            continue
        if not item.auto_eligible:
            outcomes.append({"function": item.function_name, "outcome": "queued", "detail": item.reason})
            continue
        target = result.historical_managers[0].workspace.name if result.historical_managers else ""
        plan = plan_action(result, ActionKind.REATTRIBUTE, target_workspace=target)
        entry = executor.execute(plan, mode=result.mode, confirmation=result.resource.name)
        outcomes.append({"function": item.function_name, "outcome": entry.outcome, "detail": entry.detail})
    return outcomes
