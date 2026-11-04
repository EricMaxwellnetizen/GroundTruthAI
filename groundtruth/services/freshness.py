from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class EndpointContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector: str
    operation: str
    docs_url: str
    checked_on: str
    deterministic_surface: str


CONTRACTS: list[EndpointContract] = [
    EndpointContract(
        connector="aws_lambda",
        operation="GetFunction / ListFunctions / ListTags",
        docs_url="https://docs.aws.amazon.com/lambda/latest/api/API_GetFunction.html",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/connectors/aws_lambda.py",
    ),
    EndpointContract(
        connector="cloudtrail",
        operation="LookupEvents (90-day Event History)",
        docs_url="https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_LookupEvents.html",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/connectors/cloudtrail.py",
    ),
    EndpointContract(
        connector="cloudwatch",
        operation="GetMetricData (AWS/Lambda)",
        docs_url="https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/Lambda-Insights.html",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/connectors/cloudwatch.py",
    ),
    EndpointContract(
        connector="scalr",
        operation="GET /reports/resource-usage, /workspaces, /runs",
        docs_url="https://docs.scalr.io/reference/list_terraform_resource_instances_usage",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/connectors/scalr.py",
    ),
    EndpointContract(
        connector="gitlab",
        operation="Commits / tree / blob at ref",
        docs_url="https://docs.gitlab.com/api/commits/",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/connectors/gitlab.py",
    ),
    EndpointContract(
        connector="meta_model",
        operation="Chat completions (OpenAI-compatible)",
        docs_url="https://dev.meta.ai/docs/cookbook/tool-function-calling",
        checked_on="2026-11-02",
        deterministic_surface="groundtruth/ai/client.py",
    ),
]


class FreshnessItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connector: str
    operation: str
    docs_url: str
    checked_on: str
    age_days: int
    state: str
    recommendation: str


class FreshnessReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    interval_days: int
    items: list[FreshnessItem] = Field(default_factory=list)
    ai_review_prompt: str = ""
    note: str = (
        "Freshness checks flag contracts for review and draft the review brief. "
        "Deterministic connector code is only changed through a reviewed commit — "
        "the engine never rewrites itself unattended."
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def check_freshness(
    *, interval_days: int = 30, now: datetime | None = None, contracts: list[EndpointContract] | None = None
) -> FreshnessReport:
    moment = now or _utcnow()
    items: list[FreshnessItem] = []
    for contract in contracts or CONTRACTS:
        checked = datetime.fromisoformat(contract.checked_on).replace(tzinfo=timezone.utc)
        age = max(0, (moment - checked).days)
        if age <= interval_days:
            state, rec = "fresh", "No action needed."
        elif age <= interval_days * 2:
            state, rec = (
                "due",
                f"Re-verify {contract.operation} against the current docs and bump checked_on via a reviewed commit.",
            )
        else:
            state, rec = (
                "stale",
                f"Priority re-verification: confirm parameters/response shape for {contract.operation}; add connector tests before changing code.",
            )
        items.append(
            FreshnessItem(
                connector=contract.connector,
                operation=contract.operation,
                docs_url=contract.docs_url,
                checked_on=contract.checked_on,
                age_days=age,
                state=state,
                recommendation=rec,
            )
        )
    due = [i for i in items if i.state != "fresh"]
    brief = (
        "Review the following connector contracts against their current official documentation. "
        "For each, report: changed parameters, deprecated fields, new required filters, and the exact "
        "deterministic-code files to update. Do not invent endpoints.\n"
        + "\n".join(
            f"- {i.connector}: {i.operation} ({i.docs_url}) last checked {i.checked_on}, {i.age_days}d ago" for i in due
        )
        if due
        else "All connector contracts are within their freshness window."
    )
    return FreshnessReport(generated_at=moment, interval_days=interval_days, items=items, ai_review_prompt=brief)


class FreshnessStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def record(self, report: FreshnessReport) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def last(self) -> FreshnessReport | None:
        if not self.path.exists():
            return None
        try:
            return FreshnessReport(**json.loads(self.path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            return None
