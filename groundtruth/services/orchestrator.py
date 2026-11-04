from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from groundtruth.config import Settings
from groundtruth.connectors import (
    AwsLambdaConnector,
    CloudTrailConnector,
    CloudWatchMetricsConnector,
    CloudWatchOmniConnector,
    FixtureCaseLoader,
    GitLabConnector,
    GitLocalConnector,
    ScalrConnector,
)
from groundtruth.models.connector import ConnectorResult
from groundtruth.models.enums import ConnectorStatus
from groundtruth.models.lineage import LineageResult, RunEvidence, ScalrDataset, WorkspaceRef
from groundtruth.models.resource import CloudResource
from groundtruth.models.state_backup import StateBackupEvidence
from groundtruth.services.identity import IdentityError, is_lambda_arn, normalize_lambda_identity, parse_lambda_arn
from groundtruth.services.lineage_engine import LineageEngine

ProgressCallback = Callable[[str, str, str | None], None]


class InvestigationError(ValueError):
    pass


class InvestigationOrchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_env()
        self.engine = LineageEngine(self.settings)

    def list_fixture_cases(self) -> list[dict[str, Any]]:
        return FixtureCaseLoader(self.settings).list_cases()

    def fixture_inventory(self) -> list[CloudResource]:
        return FixtureCaseLoader(self.settings).inventory()

    def run_fixture(self, case_id: str, progress: ProgressCallback | None = None) -> LineageResult:
        self._safe_progress(progress, "fixture", "running", "Loading synthetic fixture sources.")
        case = FixtureCaseLoader(self.settings).load(case_id, progress=progress)
        self._safe_progress(progress, "fixture", "done", "Synthetic sources loaded.")
        self._safe_progress(progress, "correlation", "running", "Correlating deterministic lineage.")
        result = self.engine.investigate(
            case.resource,
            aws_result=case.aws_result,
            scalr_result=case.scalr_result,
            git_lineage=case.git_lineage,
            git_result=case.git_result,
            cloudtrail_result=case.cloudtrail_result,
            cloudwatch_result=case.cloudwatch_result,
            omni_result=case.omni_result,
            mode="fixture",
        )
        self._safe_progress(progress, "correlation", "done", "Lineage correlated.")
        return result

    def run_live(
        self,
        identifier: str,
        *,
        region: str | None = None,
        account_id: str | None = None,
        progress: ProgressCallback | None = None,
        sources: set[str] | None = None,
        cloudtrail_lookback_days: int | None = None,
        cloudwatch_lookback_days: int | None = None,
        state_backup: StateBackupEvidence | None = None,
    ) -> LineageResult:
        enabled_sources = sources or {"aws", "scalr", "git", "cloudtrail", "cloudwatch", "omni"}
        text = (identifier or "").strip()
        if not text:
            raise InvestigationError("Enter a Lambda ARN or function name.")
        selected_region = (region or self.settings.aws_region or self.settings.aws_default_region).strip()
        parsed_account = account_id
        parsed_name = text
        parsed_arn: str | None = None
        if is_lambda_arn(text):
            try:
                parsed = parse_lambda_arn(text)
            except IdentityError as exc:
                raise InvestigationError(str(exc)) from exc
            parsed_account = parsed.account_id
            selected_region = parsed.region
            parsed_name = parsed.function_name
            parsed_arn = text

        self._safe_progress(progress, "aws_lambda", "running", "Reading Lambda configuration.")
        aws = AwsLambdaConnector(self.settings, region=selected_region)
        aws_result = aws.get_function(parsed_name)
        self._safe_progress(
            progress,
            "aws_lambda",
            "done" if aws_result.succeeded else "error",
            aws_result.error or "Lambda configuration read.",
        )
        if aws_result.status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL} and isinstance(
            aws_result.data, dict
        ):
            function_payload = dict(aws_result.data.get("function") or {})
            if aws_result.data.get("tags"):
                function_payload["tags"] = aws_result.data["tags"]
            try:
                resource = normalize_lambda_identity(
                    function_payload,
                    region=selected_region,
                    account_id=parsed_account or "",
                    fixture=False,
                )
            except IdentityError as exc:
                raise InvestigationError(str(exc)) from exc
            if not resource.arn and parsed_arn:
                resource.arn = parsed_arn
        else:
            resource = CloudResource(
                account_id=parsed_account or "unknown",
                region=selected_region or "unknown",
                name=parsed_name,
                arn=parsed_arn,
                provider_id=parsed_name,
                observed_at=datetime.now(timezone.utc),
                fixture=False,
            )

        self._safe_progress(progress, "scalr", "running", "Searching Scalr resource usage.")
        scalr = ScalrConnector(self.settings)
        scalr_result = self._safe_call(
            "scalr",
            lambda: scalr.fetch_dataset(function_name=resource.name, resource_arn=resource.arn),
        )

        self._safe_progress(
            progress,
            "scalr",
            "done" if scalr_result.succeeded else "error",
            scalr_result.error or "Scalr search complete.",
        )
        if "cloudtrail" in enabled_sources:
            self._safe_progress(progress, "cloudtrail", "running", "Looking up CloudTrail management events.")
            cloudtrail = CloudTrailConnector(self.settings, region=resource.region)
            cloudtrail_result = self._safe_call(
                "cloudtrail",
                lambda: cloudtrail.lookup_management_events(
                    function_name=resource.name,
                    resource_arn=resource.arn,
                    lookback_days=cloudtrail_lookback_days or self.settings.cloudtrail_lookback_days,
                ),
            )
        else:
            cloudtrail_result = self._skipped_result("cloudtrail", "CloudTrail was disabled for this investigation.")
            self._safe_progress(progress, "cloudtrail", "skipped", "CloudTrail disabled by user.")
        if "cloudtrail" in enabled_sources:
            self._safe_progress(
                progress,
                "cloudtrail",
                "done" if cloudtrail_result.succeeded else "error",
                cloudtrail_result.error or "CloudTrail lookup complete.",
            )
        if "cloudwatch" in enabled_sources:
            self._safe_progress(progress, "cloudwatch", "running", "Reading CloudWatch activity metrics.")
            cloudwatch = CloudWatchMetricsConnector(self.settings, region=resource.region)
            cloudwatch_result = self._safe_call(
                "cloudwatch",
                lambda: cloudwatch.get_activity(
                    function_name=resource.name,
                    lookback_days=cloudwatch_lookback_days or self.settings.cloudwatch_lookback_days,
                ),
            )
        else:
            cloudwatch_result = self._skipped_result("cloudwatch", "CloudWatch was disabled for this investigation.")
            self._safe_progress(progress, "cloudwatch", "skipped", "CloudWatch disabled by user.")
        if "cloudwatch" in enabled_sources:
            self._safe_progress(
                progress,
                "cloudwatch",
                "done" if cloudwatch_result.succeeded else "error",
                cloudwatch_result.error or "CloudWatch metrics read.",
            )
        if "omni" in enabled_sources:
            self._safe_progress(progress, "cloudwatch_omni", "running", "Checking optional CloudWatch Omni context.")
            omni_result = self._safe_call(
                "cloudwatch_omni",
                lambda: CloudWatchOmniConnector(self.settings).get_context(),
            )
        else:
            omni_result = self._skipped_result(
                "cloudwatch_omni", "CloudWatch Omni was disabled for this investigation."
            )
            self._safe_progress(progress, "cloudwatch_omni", "skipped", "Omni disabled by user.")
        self._safe_progress(
            progress,
            "cloudwatch_omni",
            "done" if omni_result.succeeded else "error",
            omni_result.error or "Omni context checked.",
        )
        if "git" in enabled_sources:
            self._safe_progress(progress, "git", "running", "Correlating repository lineage.")
            git_lineage, git_result = self._repository_lineage(resource, scalr_result)
            self._safe_progress(
                progress, "git", "done" if git_lineage is not None else "skipped", "Repository lineage checked."
            )
        else:
            git_lineage, git_result = (
                None,
                self._skipped_result("git_local", "Git correlation was disabled for this investigation."),
            )
            self._safe_progress(progress, "git", "skipped", "Git disabled by user.")
        self._safe_progress(progress, "correlation", "running", "Correlating deterministic lineage.")
        result = self.engine.investigate(
            resource,
            aws_result=aws_result,
            scalr_result=scalr_result,
            git_lineage=git_lineage,
            git_result=git_result,
            cloudtrail_result=cloudtrail_result,
            cloudwatch_result=cloudwatch_result,
            omni_result=omni_result,
            mode="live",
            state_backup=state_backup,
        )
        self._safe_progress(progress, "correlation", "done", "Lineage correlated.")
        return result

    def _repository_lineage(
        self,
        resource: CloudResource,
        scalr_result: ConnectorResult,
    ) -> tuple[Any | None, ConnectorResult | None]:
        if not isinstance(scalr_result.data, ScalrDataset):
            return None, None
        workspace, run, address = self._select_context(scalr_result.data)
        if workspace is None:
            return None, None
        try:
            if self.settings.git_configured:
                connector = GitLocalConnector(self.settings)
                if not connector.is_configured():
                    return None, None
                result = connector.build_repository_lineage(
                    workspace=workspace,
                    run=run,
                    function_name=resource.name,
                    resource_address=address,
                )
                return (result.data if result.succeeded else None), result
            if self.settings.gitlab_configured:
                connector = GitLabConnector(self.settings)
                result = connector.build_repository_lineage(
                    workspace=workspace,
                    run=run,
                    function_name=resource.name,
                    resource_address=address,
                )
                return (result.data if result.succeeded else None), result
        except Exception as exc:
            return None, self._failed_result("git_local" if self.settings.git_configured else "gitlab", exc)
        return None, None

    @staticmethod
    def _select_context(dataset: ScalrDataset) -> tuple[WorkspaceRef | None, RunEvidence | None, str | None]:
        if not dataset.resource_usages:
            return None, None, None
        ordered = sorted(
            dataset.resource_usages,
            key=lambda usage: (
                0 if usage.is_active and (usage.workspace is None or usage.workspace.active is not False) else 1
            ),
        )
        for usage in ordered:
            if usage.workspace is not None:
                return usage.workspace, usage.run, usage.address
        return None, None, None

    def _safe_call(self, source: str, callable_: Callable[[], ConnectorResult]) -> ConnectorResult:
        try:
            return callable_()
        except Exception as exc:
            return self._failed_result(source, exc)

    @staticmethod
    def _safe_progress(
        progress: ProgressCallback | None,
        stage: str,
        status: str,
        detail: str | None = None,
    ) -> None:
        if progress is None:
            return
        try:
            progress(stage, status, detail)
        except Exception:
            return

    @staticmethod
    def _skipped_result(source: str, warning: str) -> ConnectorResult:
        return ConnectorResult(
            status=ConnectorStatus.NOT_CONFIGURED,
            source=source,
            queried_at=datetime.now(timezone.utc),
            warnings=[warning],
        )

    @staticmethod
    def _failed_result(source: str, exc: BaseException) -> ConnectorResult:
        message = str(exc).strip()[:500] or exc.__class__.__name__
        return ConnectorResult(
            status=ConnectorStatus.FAILED,
            source=source,
            queried_at=datetime.now(timezone.utc),
            error=message,
            warnings=[f"{source} raised an unexpected connector error."],
        )
