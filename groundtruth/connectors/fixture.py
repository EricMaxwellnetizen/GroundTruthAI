from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector
from groundtruth.connectors.git_local import GitLocalConnector
from groundtruth.demo_repo import (
    AUTHOR_EMAIL,
    AUTHOR_NAME,
    FILE_PATH,
    FUNCTION_NAME,
    REPOSITORY_URL,
    RESOURCE_ADDRESS,
    ensure_demo_repo,
)
from groundtruth.models.connector import ConnectorResult
from groundtruth.models.enums import (
    ConfidenceLabel,
    ConnectorStatus,
    LineageStatus,
    MatchType,
    RecommendationCode,
)
from groundtruth.models.lineage import (
    CloudTrailEventEvidence,
    CloudWatchActivity,
    GitCommitEvidence,
    GitFileEvidence,
    OmniContext,
    RepositoryLineage,
    ResourceUsageRecord,
    RunEvidence,
    ScalrDataset,
    WorkspaceRef,
)
from groundtruth.models.resource import CloudResource

PLACEHOLDER_HEAD = "$DEMO_HEAD_SHA"
PLACEHOLDER_HISTORICAL = "$DEMO_HISTORICAL_SHA"
PLACEHOLDER_REPO = "$DEMO_REPO_PATH"

ProgressCallback = Callable[[str, str, str | None], None]


@dataclass
class FixtureCase:
    case_id: str
    label: str
    summary: str
    resource: CloudResource
    expected_status: LineageStatus
    expected_confidence: ConfidenceLabel
    expected_recommendation: RecommendationCode
    expected_blocked: bool
    raw: dict[str, Any]
    aws_result: ConnectorResult
    scalr_result: ConnectorResult
    git_lineage: RepositoryLineage | None
    git_result: ConnectorResult | None
    cloudtrail_result: ConnectorResult
    cloudwatch_result: ConnectorResult
    omni_result: ConnectorResult
    manifest: dict[str, Any] = field(default_factory=dict)

    @property
    def fixture(self) -> bool:
        return True


def _status(value: str | None, default: ConnectorStatus = ConnectorStatus.SUCCESS) -> ConnectorStatus:
    if not value:
        return default
    try:
        return ConnectorStatus(value)
    except ValueError:
        return default


def _replace_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for placeholder, replacement in replacements.items():
            result = result.replace(placeholder, replacement)
        return result
    if isinstance(value, list):
        return [_replace_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _replace_placeholders(item, replacements) for key, item in value.items()}
    return value


def _fixture_payload(item: dict[str, Any]) -> dict[str, Any]:
    payload = dict(item)
    payload["fixture"] = True
    return payload


def _coverage(result: ConnectorResult, *, required: bool) -> dict[str, Any]:
    return result.as_coverage(required=required, notes=result.warnings)


class FixtureCaseLoader(BaseConnector):
    name = "fixture"
    source = "fixture"

    def __init__(self, settings: Settings, fixtures_dir: Path | None = None) -> None:
        super().__init__(settings)
        self.fixtures_dir = Path(fixtures_dir or settings.fixtures_dir)
        self.cases_dir = self.fixtures_dir / "cases"

    def is_configured(self) -> bool:
        return self.cases_dir.exists()

    def test_connection(self):
        from groundtruth.models.connector import ConnectionTest

        if not self.is_configured():
            return ConnectionTest(
                name="Fixture mode",
                status=ConnectorStatus.NOT_CONFIGURED,
                message=f"No fixture cases directory found at {self.cases_dir}.",
            )
        count = len(self.list_cases())
        return ConnectionTest(
            name="Fixture mode",
            status=ConnectorStatus.SUCCESS if count else ConnectorStatus.NOT_CONFIGURED,
            message=f"{count} synthetic fixture case(s) available offline.",
            details={"fixtures_dir": str(self.fixtures_dir), "cases": count},
            fixture=True,
        )

    def _case_path(self, case_id: str) -> Path:
        safe = "".join(char for char in case_id if char.isalnum() or char in {"_", "-"})
        if not safe or safe != case_id:
            raise ValueError("Invalid fixture case identifier.")
        path = self.cases_dir / f"{safe}.json"
        if not path.exists():
            raise FileNotFoundError(f"Fixture case '{case_id}' was not found.")
        return path

    def list_cases(self) -> list[dict[str, Any]]:
        if not self.cases_dir.exists():
            return []
        cases: list[dict[str, Any]] = []
        for path in sorted(self.cases_dir.glob("*.json")):
            if path.name.startswith("expected_") or path.name == "schema.json":
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            expected = payload.get("expected") or {}
            cases.append(
                {
                    "case_id": payload.get("case_id") or path.stem,
                    "label": payload.get("label") or path.stem,
                    "summary": payload.get("summary") or "",
                    "expected_status": expected.get("status"),
                    "expected_confidence": expected.get("confidence"),
                    "fixture": True,
                }
            )
        return cases

    def _demo_context(self) -> tuple[dict[str, Any], dict[str, str]]:
        manifest = ensure_demo_repo(Path(self.settings.demo_repo_path))
        replacements = {
            PLACEHOLDER_HEAD: str(manifest.get("head_sha") or ""),
            PLACEHOLDER_HISTORICAL: str(manifest.get("historical_sha") or ""),
            PLACEHOLDER_REPO: str(manifest.get("repo_path") or ""),
        }
        return manifest, replacements

    def _git_result_from_manifest(self, payload: dict[str, Any], manifest: dict[str, Any]) -> RepositoryLineage:
        sha = str(payload.get("sha") or manifest.get("head_sha") or "")
        commit = GitCommitEvidence(
            repository=str(payload.get("repository") or manifest.get("repository_url") or "northgate/data-pipelines"),
            repository_url=str(payload.get("repository_url") or manifest.get("repository_url") or REPOSITORY_URL),
            sha=sha,
            author_name=str(manifest.get("author_name") or AUTHOR_NAME),
            author_email=str(manifest.get("author_email") or AUTHOR_EMAIL),
            committed_at=datetime.fromisoformat(str(manifest.get("committed_at") or "2026-09-08T10:15:00+00:00")),
            committer_name=str(manifest.get("author_name") or AUTHOR_NAME),
            committer_email=str(manifest.get("author_email") or AUTHOR_EMAIL),
            message="Add orders transformer Lambda module",
            fixture=True,
        )
        file_matches = [
            GitFileEvidence(
                path=str(payload.get("resource_address") and FILE_PATH or manifest.get("file_path") or FILE_PATH),
                matched_string=str(payload.get("resource_address") or RESOURCE_ADDRESS),
                match_type=MatchType.EXACT_ADDRESS,
                snippet='resource "aws_lambda_function" "transformer" { ... }',
                line=4,
                commit_sha=sha,
                fixture=True,
            )
        ]
        return RepositoryLineage(
            repository=str(payload.get("repository") or "northgate/data-pipelines"),
            repository_url=str(payload.get("repository_url") or REPOSITORY_URL),
            working_directory=payload.get("working_directory"),
            branch=payload.get("branch") or "main",
            vcs_revision=sha,
            run_id=payload.get("run_id"),
            workspace_id=payload.get("workspace_id"),
            commit_verified=bool(manifest.get("git_available")),
            commit=commit,
            file_matches=file_matches,
            history_matches=[],
            candidate_only=not bool(manifest.get("git_available")),
            limitations=["Synthetic fixture commit generated from the deterministic demo manifest."],
        )

    def _git_result(
        self, payload: dict[str, Any] | None, usages: list[ResourceUsageRecord], manifest: dict[str, Any]
    ) -> tuple[RepositoryLineage | None, ConnectorResult | None]:
        if not payload:
            return None, None
        mode = str(payload.get("mode") or "inline")
        if mode == "demo_repo":
            workspace_id = payload.get("workspace_id")
            run_id = payload.get("run_id")
            workspace = None
            run = None
            for usage in usages:
                if usage.workspace and (not workspace_id or usage.workspace.id == workspace_id):
                    workspace = usage.workspace
                    run = usage.run
                    break
            if workspace is None:
                workspace = WorkspaceRef(
                    id=str(workspace_id or "ws-demo"),
                    name="orders-prod",
                    environment="prod",
                    active=True,
                    vcs_repo_identifier=str(payload.get("repository") or "northgate/data-pipelines"),
                    working_directory=payload.get("working_directory"),
                    branch=payload.get("branch") or "main",
                    fixture=True,
                )
            if run is None:
                run = RunEvidence(
                    id=str(run_id or "run-demo"),
                    workspace_id=workspace.id,
                    status="applied",
                    source="vcs",
                    vcs_revision=payload.get("sha"),
                    fixture=True,
                )
            connector = GitLocalConnector(self.settings, repo_path=manifest.get("repo_path"))
            if connector.is_configured():
                result = connector.build_repository_lineage(
                    workspace=workspace,
                    run=run,
                    function_name=str(payload.get("function_name") or FUNCTION_NAME),
                    resource_address=payload.get("resource_address") or RESOURCE_ADDRESS,
                )
                if result.status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL} and isinstance(
                    result.data, RepositoryLineage
                ):
                    if result.data.commit:
                        result.data.commit.fixture = True
                    for match in result.data.file_matches + result.data.history_matches:
                        match.fixture = True
                    return result.data, result
            lineage = self._git_result_from_manifest(payload, manifest)
            result = self.result(
                ConnectorStatus.PARTIAL,
                data=lineage,
                coverage={"mode": "manifest_fallback", "commit_verified": lineage.commit_verified},
                warnings=["Git CLI was unavailable; the fixture used the deterministic demo manifest."],
                fixture=True,
                source="git_local",
            )
            return lineage, result
        lineage = RepositoryLineage(
            repository=str(payload.get("repository") or "northgate/data-pipelines"),
            repository_url=payload.get("repository_url"),
            working_directory=payload.get("working_directory"),
            branch=payload.get("branch"),
            vcs_revision=payload.get("sha"),
            run_id=payload.get("run_id"),
            workspace_id=payload.get("workspace_id"),
            commit_verified=bool(payload.get("commit_verified")),
            commit=GitCommitEvidence(**_fixture_payload(payload["commit"])) if payload.get("commit") else None,
            file_matches=[GitFileEvidence(**_fixture_payload(item)) for item in payload.get("file_matches", [])],
            history_matches=[GitFileEvidence(**_fixture_payload(item)) for item in payload.get("history_matches", [])],
            candidate_only=bool(payload.get("candidate_only", True)),
            limitations=list(payload.get("limitations") or []),
        )
        result = self.result(
            ConnectorStatus.SUCCESS if lineage.commit_verified else ConnectorStatus.PARTIAL,
            data=lineage,
            coverage={"mode": "inline", "commit_verified": lineage.commit_verified},
            warnings=lineage.limitations,
            fixture=True,
            source="git_local",
        )
        return lineage, result

    def load(self, case_id: str, progress: ProgressCallback | None = None) -> FixtureCase:
        path = self._case_path(case_id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest, replacements = self._demo_context()
        raw = _replace_placeholders(raw, replacements)
        expected = raw.get("expected") or {}
        try:
            expected_status = LineageStatus(expected.get("status"))
            expected_confidence = ConfidenceLabel(expected.get("confidence"))
            expected_recommendation = RecommendationCode(expected.get("recommendation"))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Fixture case {case_id} has an invalid expected result: {exc}") from exc
        resource_data = dict(raw.get("resource") or {})
        resource_data.setdefault("fixture", True)
        resource = CloudResource(**resource_data)
        aws_raw = raw.get("aws") or {}
        aws_result = self.result(
            _status(aws_raw.get("status"), ConnectorStatus.SUCCESS),
            data={"function": resource.model_dump(mode="json")},
            coverage={"account_id": resource.account_id, "region": resource.region, "source": "synthetic fixture"},
            warnings=list(aws_raw.get("warnings") or []),
            fixture=True,
            source="aws_lambda",
        )
        self._notify(progress, "aws_lambda", "done", "Synthetic Lambda identity loaded.")
        scalr_raw = raw.get("scalr") or {}
        scalr_status = _status(scalr_raw.get("status"), ConnectorStatus.SUCCESS)
        usages: list[ResourceUsageRecord] = []
        if scalr_status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL}:
            for item in scalr_raw.get("resource_usages") or []:
                payload = dict(item)
                payload["fixture"] = True
                usages.append(ResourceUsageRecord(**payload))
        dataset = ScalrDataset(
            resource_usages=usages,
            queried_filter=scalr_raw.get("queried_filter") or "fixture-filter",
        )
        scalr_result = self.result(
            scalr_status,
            data=dataset,
            coverage={
                "endpoint": "/reports/resource-usage",
                "filter_configured": scalr_status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL},
                "synthetic": True,
            },
            warnings=list(scalr_raw.get("warnings") or []),
            error=scalr_raw.get("error"),
            records=len(usages),
            fixture=True,
            source="scalr",
        )
        self._notify(progress, "scalr", "done", "Synthetic Scalr resource usage loaded.")
        git_payload = raw.get("git")
        self._notify(progress, "git", "running", "Checking fixture Git lineage.")
        git_lineage, git_result = self._git_result(git_payload, usages, manifest)
        self._notify(progress, "git", "done" if git_lineage is not None else "skipped", "Fixture Git lineage checked.")
        cloudtrail_raw = raw.get("cloudtrail") or {}
        events = []
        for item in cloudtrail_raw.get("events") or []:
            payload = dict(item)
            payload["fixture"] = True
            events.append(CloudTrailEventEvidence(**payload))
        cloudtrail_result = self.result(
            _status(cloudtrail_raw.get("status"), ConnectorStatus.SUCCESS),
            data=events,
            coverage={
                "region": resource.region,
                "window_days": self.settings.cloudtrail_lookback_days,
                "event_history_limited": True,
                "synthetic": True,
            },
            warnings=list(cloudtrail_raw.get("warnings") or []),
            records=len(events),
            fixture=True,
            source="cloudtrail",
        )
        self._notify(progress, "cloudtrail", "done", "Synthetic CloudTrail events loaded.")
        cloudwatch_raw = raw.get("cloudwatch") or {}
        activity = None
        if cloudwatch_raw.get("activity"):
            activity_payload = dict(cloudwatch_raw["activity"])
            activity_payload["fixture"] = True
            activity = CloudWatchActivity(**activity_payload)
        cloudwatch_result = self.result(
            _status(cloudwatch_raw.get("status"), ConnectorStatus.SUCCESS),
            data=activity,
            coverage={
                "region": resource.region,
                "window_start": activity.window_start if activity else None,
                "window_end": activity.window_end if activity else None,
                "metric_namespace": "AWS/Lambda",
                "synthetic": True,
            },
            warnings=list(cloudwatch_raw.get("warnings") or []),
            records=activity.invocation_datapoints if activity else 0,
            fixture=True,
            source="cloudwatch",
        )
        self._notify(progress, "cloudwatch", "done", "Synthetic CloudWatch metrics loaded.")
        omni_raw = raw.get("omni") or {}
        omni_context = OmniContext(
            configured=bool(omni_raw.get("configured")),
            url=omni_raw.get("url"),
            space=omni_raw.get("space"),
            limitations=list(omni_raw.get("limitations") or []),
        )
        omni_result = self.result(
            ConnectorStatus.PARTIAL if omni_context.configured else ConnectorStatus.NOT_CONFIGURED,
            data=omni_context,
            warnings=omni_context.limitations,
            fixture=True,
            source="cloudwatch_omni",
        )
        self._notify(progress, "cloudwatch_omni", "done", "Synthetic Omni context loaded.")
        return FixtureCase(
            case_id=str(raw.get("case_id") or case_id),
            label=str(raw.get("label") or case_id),
            summary=str(raw.get("summary") or ""),
            resource=resource,
            expected_status=expected_status,
            expected_confidence=expected_confidence,
            expected_recommendation=expected_recommendation,
            expected_blocked=bool(expected.get("blocked_adoption", False)),
            raw=raw,
            aws_result=aws_result,
            scalr_result=scalr_result,
            git_lineage=git_lineage,
            git_result=git_result,
            cloudtrail_result=cloudtrail_result,
            cloudwatch_result=cloudwatch_result,
            omni_result=omni_result,
            manifest=manifest,
        )

    @staticmethod
    def _notify(progress: ProgressCallback | None, stage: str, status: str, detail: str | None = None) -> None:
        if progress is None:
            return
        try:
            progress(stage, status, detail)
        except Exception:
            return

    def inventory(self) -> list[CloudResource]:
        resources: list[CloudResource] = []
        seen: set[str] = set()
        for item in self.list_cases():
            try:
                case = self.load(item["case_id"])
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if case.resource.identity not in seen:
                seen.add(case.resource.identity)
                resources.append(case.resource)
        return resources
