from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import requests

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector, classify_http_error, safe_error_message
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus
from groundtruth.models.lineage import (
    ResourceUsageRecord,
    RunEvidence,
    ScalrDataset,
    StateVersionEvidence,
    WorkspaceRef,
)
from groundtruth.utils.retry import RateLimiter
from groundtruth.utils.urls import build_scalr_url

SCALR_RETENTION_NOTE = (
    "Scalr public documentation checked 2026-11-02: apply runs are retained for three years, "
    "plan-only runs for 30 days, and the last 100 state files per workspace, subject to documented exceptions. "
    "A missing historical record is not proof that the history does not exist."
)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return default


def _api_root(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/api/iacp/v3"):
        return base
    return f"{base}/api/iacp/v3"


def _sha(value: Any) -> str | None:
    text = _string(value)
    if not text:
        return None
    text = text.lower()
    if 7 <= len(text) <= 40 and all(char in "0123456789abcdef" for char in text):
        return text
    return None


def _resolve_relationship(
    relationships: dict[str, Any],
    included_index: dict[tuple[str, str], dict[str, Any]],
    name: str,
) -> tuple[dict[str, Any] | None, str | None]:
    relation = relationships.get(name) or {}
    data = relation.get("data") if isinstance(relation, dict) else None
    if not isinstance(data, dict):
        return None, None
    rel_id = _string(data.get("id"))
    rel_type = _string(data.get("type"))
    if not rel_id or not rel_type:
        return None, None
    return included_index.get((rel_type, rel_id)), rel_id


def _included_index(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    included = payload.get("included") or []
    if not isinstance(included, list):
        return index
    for item in included:
        if not isinstance(item, dict):
            continue
        item_type = _string(item.get("type"))
        item_id = _string(item.get("id"))
        if item_type and item_id:
            index[(item_type, item_id)] = item
    return index


def _workspace_from_pair(
    workspace_obj: dict[str, Any] | None,
    workspace_id: str | None,
    *,
    base_url: str,
    environment_name: str | None,
    fallback_active: bool | None = None,
) -> WorkspaceRef | None:
    if not workspace_id and not workspace_obj:
        return None
    attrs = (workspace_obj or {}).get("attributes") or {}
    vcs_repo = attrs.get("vcs-repo") if isinstance(attrs.get("vcs-repo"), dict) else {}
    workspace_id = workspace_id or _string((workspace_obj or {}).get("id")) or "unknown-workspace"
    name = _string(attrs.get("name")) or workspace_id
    return WorkspaceRef(
        id=workspace_id,
        name=name,
        environment=environment_name or _string(attrs.get("environment-type")),
        active=fallback_active,
        vcs_repo_identifier=_string(vcs_repo.get("identifier")),
        working_directory=_string(attrs.get("working-directory")),
        branch=_string(vcs_repo.get("branch")),
        source_url=build_scalr_url(base_url, workspace_id=workspace_id),
        attributes={
            "execution_mode": attrs.get("execution-mode"),
            "iac_platform": attrs.get("iac-platform"),
            "environment_type": attrs.get("environment-type"),
            "has_resources": attrs.get("has-resources"),
            "vcs_repo_inaccessible": attrs.get("vcs-repo-inaccessible"),
            "deletion_protection_enabled": attrs.get("deletion-protection-enabled"),
        },
    )


def _run_from_pair(
    run_obj: dict[str, Any] | None,
    run_id: str | None,
    *,
    included_index: dict[tuple[str, str], dict[str, Any]],
    base_url: str,
) -> RunEvidence | None:
    if not run_id and not run_obj:
        return None
    attrs = (run_obj or {}).get("attributes") or {}
    relationships = (run_obj or {}).get("relationships") or {}
    revision_obj, revision_id = _resolve_relationship(relationships, included_index, "vcs-revision")
    revision_attrs = (revision_obj or {}).get("attributes") or {}
    created_by_obj, created_by_id = _resolve_relationship(relationships, included_index, "created-by")
    created_by_attrs = (created_by_obj or {}).get("attributes") or {}
    revision = None
    for key in ("commit-sha", "commit_sha", "sha", "revision", "commit"):
        revision = _sha(revision_attrs.get(key))
        if revision:
            break
    actor_email = _string(created_by_attrs.get("email")) or _string(attrs.get("updated-by-email"))
    actor_category = _string(attrs.get("actor"))
    actor_text = actor_email or actor_category
    if actor_email and actor_category:
        actor_text = f"{actor_category}:{actor_email}"
    return RunEvidence(
        id=run_id or _string((run_obj or {}).get("id")) or "unknown-run",
        workspace_id=_string(((relationships.get("workspace") or {}).get("data") or {}).get("id")),
        status=_string(attrs.get("status")),
        created_at=_parse_datetime(attrs.get("created-at")),
        source=_string(attrs.get("source")),
        actor=actor_text,
        vcs_revision=revision,
        source_url=build_scalr_url(base_url, run_id=run_id),
        attributes={
            "actor_category": actor_category,
            "created_by_id": created_by_id,
            "created_by_email": actor_email,
            "vcs_revision_id": revision_id,
            "has_changes": attrs.get("has-changes"),
            "is_destroy": attrs.get("is-destroy"),
            "is_dry": attrs.get("is-dry"),
            "message": attrs.get("message"),
            "error_message": attrs.get("error-message"),
            "iac_platform": attrs.get("iac-platform"),
        },
    )


def _usage_from_item(
    item: dict[str, Any],
    *,
    included_index: dict[tuple[str, str], dict[str, Any]],
    base_url: str,
) -> ResourceUsageRecord:
    attrs = item.get("attributes") or {}
    relationships = item.get("relationships") or {}
    workspace_obj, workspace_id = _resolve_relationship(relationships, included_index, "workspace")
    run_obj, run_id = _resolve_relationship(relationships, included_index, "run")
    state_obj, state_id = _resolve_relationship(relationships, included_index, "state-version")
    environment_obj, environment_id = _resolve_relationship(relationships, included_index, "environment")
    environment_attrs = (environment_obj or {}).get("attributes") or {}
    environment_name = _string(environment_attrs.get("name")) or _string(environment_id)
    state_attrs = (state_obj or {}).get("attributes") or {}
    usage_id = _string(item.get("id")) or "unknown-usage"
    workspace_ref = _workspace_from_pair(
        workspace_obj,
        workspace_id,
        base_url=base_url,
        environment_name=environment_name,
        fallback_active=_bool(attrs.get("is-active")),
    )
    run_ref = _run_from_pair(run_obj, run_id, included_index=included_index, base_url=base_url)
    if run_ref and workspace_ref and not run_ref.workspace_id:
        run_ref.workspace_id = workspace_ref.id
    state_ref = None
    if state_id or state_obj:
        state_ref = StateVersionEvidence(
            id=state_id or _string((state_obj or {}).get("id")) or "unknown-state-version",
            created_at=_parse_datetime(state_attrs.get("created-at")),
            source_url=None,
        )
    limitations: list[str] = []
    if run_ref and not run_ref.vcs_revision:
        limitations.append(
            "Scalr did not return a VCS commit SHA for this run in the selected response; the exact commit join is unavailable."
        )
    if not workspace_ref:
        limitations.append("The Scalr resource usage did not include workspace detail in the response.")
    return ResourceUsageRecord(
        id=usage_id,
        external_id=_string(attrs.get("external-id")) or "",
        address=_string(attrs.get("address")) or "",
        name=_string(attrs.get("name")) or "",
        is_active=_bool(attrs.get("is-active"), default=True),
        is_duplicate=_bool(attrs.get("is-duplicate"), default=False),
        updated_at=_parse_datetime(attrs.get("updated-at")),
        updated_by_email=_string(attrs.get("updated-by-email")),
        workspace=workspace_ref,
        run=run_ref,
        state_version=state_ref,
        environment=environment_name,
        account_id=_string(attrs.get("account-id")),
        region=_string(attrs.get("region")),
        source_url=build_scalr_url(base_url, workspace_id=workspace_id) if workspace_id else None,
        limitations=limitations,
        fixture=False,
    )


class ScalrConnector(BaseConnector):
    name = "scalr"
    source = "scalr_resource_usage"

    def __init__(self, settings: Settings, session: Any | None = None) -> None:
        super().__init__(settings)
        self._session = session
        self._rate_limiter = RateLimiter(0.25)

    def _http(self) -> Any:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.scalr_api_token}",
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json",
            "User-Agent": "GroundTruth/1.0",
        }

    def is_configured(self) -> bool:
        return self.settings.scalr_credentials_configured

    def _configuration_error(self) -> ConnectorResult | None:
        if not self.settings.scalr_base_url or not self.settings.scalr_api_token:
            return self.not_configured(
                "Scalr is not configured. Set SCALR_BASE_URL (https://<account>.scalr.io) and a read-only SCALR_API_TOKEN."
            )
        if not self.settings.scalr_tf_resource_usage_filter:
            return self.not_configured(
                "SCALR_TF_RESOURCE_USAGE_FILTER is required by the Scalr resource-usage endpoint. "
                "The current Scalr OpenAPI specification publishes it as a free-form value with no enum, so GroundTruth will not guess it. "
                "Set the value required by your Scalr account, or continue with Scalr disabled and only supplementary sources."
            )
        return None

    def _request(
        self, path: str, params: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, ConnectorResult | None]:
        url = f"{_api_root(self.settings.scalr_base_url)}{path}"
        last_error: BaseException | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            self._rate_limiter.wait()
            try:
                response = self._http().get(
                    url,
                    headers=self._headers(),
                    params=params or {},
                    timeout=self.settings.request_timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(min(5.0, 0.4 * (2 ** (attempt - 1))))
                continue
            if response.status_code in RETRYABLE_STATUS and attempt < self.settings.max_retries:
                time.sleep(min(5.0, 0.5 * (2 ** (attempt - 1))))
                continue
            if response.status_code >= 400:
                status = classify_http_error(response.status_code)
                message = self._response_error(response)
                return None, self.result(
                    status,
                    error=message,
                    coverage={
                        "endpoint": path,
                        "http_status": response.status_code,
                        "request_id": response.headers.get("x-request-id")
                        or response.headers.get("x-scalr-request-id"),
                    },
                )
            try:
                payload = response.json()
            except ValueError:
                return None, self.result(
                    ConnectorStatus.FAILED,
                    error="Scalr returned a non-JSON response for a JSON:API endpoint.",
                    coverage={"endpoint": path, "http_status": response.status_code},
                )
            if not isinstance(payload, dict):
                return None, self.result(
                    ConnectorStatus.FAILED,
                    error="Scalr returned an unexpected JSON document shape.",
                    coverage={"endpoint": path},
                )
            return payload, None
        return None, self.result(
            ConnectorStatus.FAILED,
            error=f"Scalr request failed after {self.settings.max_retries} attempts: {safe_error_message(last_error or RuntimeError('unknown error'))}",
            coverage={"endpoint": path},
        )

    @staticmethod
    def _response_error(response: Any) -> str:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                errors = payload.get("errors")
                if isinstance(errors, list) and errors:
                    first = errors[0]
                    if isinstance(first, dict):
                        detail = _string(first.get("detail")) or _string(first.get("title")) or ""
                detail = detail or _string(payload.get("message")) or _string(payload.get("error")) or ""
        except ValueError:
            detail = ""
        prefix = f"Scalr API returned HTTP {response.status_code}."
        if response.status_code == 401:
            return f"{prefix} The API token is invalid or expired. Create a read-only token and update SCALR_API_TOKEN."
        if response.status_code == 403:
            return f"{prefix} The token is valid but lacks permission for this endpoint."
        if response.status_code == 429:
            return f"{prefix} Scalr rate limit reached. Retry shortly or reduce the lookback scope."
        return f"{prefix} {detail}".strip()[:500]

    def test_connection(self) -> ConnectionTest:
        error = self._configuration_error()
        if error:
            return ConnectionTest(
                name="Scalr",
                status=error.status,
                message=error.error or "Scalr is not configured.",
                details={
                    "base_url_configured": bool(self.settings.scalr_base_url),
                    "filter_configured": bool(self.settings.scalr_tf_resource_usage_filter),
                },
            )
        payload, failure = self._request("/workspaces", {"page[size]": "1"})
        if failure:
            return ConnectionTest(
                name="Scalr",
                status=failure.status,
                message=failure.error or "Scalr connection test failed.",
                details=failure.coverage,
            )
        return ConnectionTest(
            name="Scalr",
            status=ConnectorStatus.SUCCESS,
            message="Connected with read-only Scalr credentials; the resource-usage filter is configured.",
            details={"api": _api_root(self.settings.scalr_base_url), "filter_configured": True},
        )

    def fetch_resource_usages(
        self,
        *,
        function_name: str,
        resource_arn: str | None = None,
        filter_value: str | None = None,
        max_pages: int | None = None,
    ) -> ConnectorResult:
        error = self._configuration_error()
        if error:
            return error
        filter_text = (filter_value or self.settings.scalr_tf_resource_usage_filter).strip()
        if not filter_text:
            return self.not_configured("SCALR_TF_RESOURCE_USAGE_FILTER is required and was empty.")
        page_size = max(1, min(self.settings.scalr_page_size, 100))
        page_cap = max(1, min(max_pages or self.settings.max_pages, self.settings.max_pages))
        queries = [resource_arn or function_name, function_name]
        ordered_queries: list[str] = []
        for query in queries:
            if query and query not in ordered_queries:
                ordered_queries.append(query)
        included_index: dict[tuple[str, str], dict[str, Any]] = {}
        usages: dict[str, ResourceUsageRecord] = {}
        pages = 0
        warnings: list[str] = []
        total_records = 0
        for query in ordered_queries:
            page_number = 1
            while pages < page_cap:
                params = {
                    "query": query,
                    "filter[tf-resource-usage]": filter_text,
                    "include": "environment,run,state-version,workspace",
                    "page[size]": str(page_size),
                    "page[number]": str(page_number),
                }
                payload, failure = self._request("/reports/resource-usage", params)
                if failure:
                    if usages and pages:
                        failure.status = ConnectorStatus.PARTIAL
                        failure.data = ScalrDataset(
                            resource_usages=sorted(usages.values(), key=lambda item: item.id),
                            queried_filter=filter_text,
                            retention_note=SCALR_RETENTION_NOTE,
                        )
                        failure.records = len(usages)
                        failure.warnings = warnings + ["The resource-usage query stopped after a partial page."]
                    return failure
                pages += 1
                for key, value in _included_index(payload).items():
                    included_index[key] = value
                data = payload.get("data") or []
                if not isinstance(data, list):
                    warnings.append("Scalr returned an unexpected resource-usage data shape; this page was skipped.")
                    break
                total_records += len(data)
                for item in data:
                    if not isinstance(item, dict):
                        warnings.append("One Scalr resource-usage record was malformed and was skipped.")
                        continue
                    try:
                        usage = _usage_from_item(
                            item, included_index=included_index, base_url=self.settings.scalr_base_url
                        )
                    except (TypeError, ValueError):
                        warnings.append("One Scalr resource-usage record could not be normalized and was skipped.")
                        continue
                    if usage.id not in usages:
                        usages[usage.id] = usage
                meta = payload.get("meta") or {}
                pagination = meta.get("pagination") if isinstance(meta, dict) else {}
                next_page = pagination.get("next-page") if isinstance(pagination, dict) else None
                total_pages = pagination.get("total-pages") if isinstance(pagination, dict) else None
                if not next_page and total_pages is not None:
                    try:
                        if page_number >= int(total_pages):
                            break
                    except (TypeError, ValueError):
                        pass
                if not next_page and not total_pages:
                    break
                page_number = int(next_page) if str(next_page).isdigit() else page_number + 1
                if page_number > page_cap:
                    break
            if pages >= page_cap:
                warnings.append(f"Scalr pagination was capped at {page_cap} pages; results may be incomplete.")
                break
        dataset = ScalrDataset(
            resource_usages=sorted(usages.values(), key=lambda item: item.id),
            queried_filter=filter_text,
            retention_note=SCALR_RETENTION_NOTE,
        )
        status = ConnectorStatus.PARTIAL if warnings else ConnectorStatus.SUCCESS
        return self.result(
            status,
            data=dataset,
            coverage={
                "endpoint": "/reports/resource-usage",
                "filter_configured": True,
                "page_size": page_size,
                "pagination_capped": any("capped" in warning for warning in warnings),
                "retention_note": SCALR_RETENTION_NOTE,
            },
            warnings=warnings,
            pages=pages,
            records=len(usages),
        )

    def list_workspaces(self, *, vcs_identifier: str | None = None) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("Scalr is not configured.")
        params: dict[str, Any] = {
            "page[size]": str(max(1, min(self.settings.scalr_page_size, 100))),
            "page[number]": "1",
        }
        if vcs_identifier:
            params["filter[vcs-repo][identifier]"] = vcs_identifier
        payload, failure = self._request("/workspaces", params)
        if failure:
            return failure
        workspaces: list[WorkspaceRef] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            workspace = _workspace_from_pair(
                item,
                _string(item.get("id")),
                base_url=self.settings.scalr_base_url,
                environment_name=None,
            )
            if workspace:
                workspaces.append(workspace)
        return self.result(
            ConnectorStatus.SUCCESS,
            data=workspaces,
            coverage={"endpoint": "/workspaces", "vcs_identifier_filter": bool(vcs_identifier)},
            pages=1,
            records=len(workspaces),
        )

    def list_runs(self, *, workspace_id: str, vcs_revision: str | None = None, page_size: int = 20) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("Scalr is not configured.")
        if not workspace_id:
            return self.not_configured("A Scalr workspace ID is required to list runs.")
        params: dict[str, Any] = {
            "filter[workspace]": workspace_id,
            "include": "vcs-revision,created-by,workspace",
            "page[size]": str(max(1, min(page_size, 100))),
            "page[number]": "1",
        }
        if vcs_revision:
            params["filter[vcs-revision]"] = vcs_revision
        payload, failure = self._request("/runs", params)
        if failure:
            return failure
        included_index = _included_index(payload)
        runs: list[RunEvidence] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            run = _run_from_pair(
                item, _string(item.get("id")), included_index=included_index, base_url=self.settings.scalr_base_url
            )
            if run:
                if not run.workspace_id:
                    run.workspace_id = workspace_id
                runs.append(run)
        return self.result(
            ConnectorStatus.SUCCESS,
            data=runs,
            coverage={"endpoint": "/runs", "workspace_id": workspace_id, "vcs_revision_filter": bool(vcs_revision)},
            pages=1,
            records=len(runs),
        )

    def fetch_dataset(self, *, function_name: str, resource_arn: str | None = None) -> ConnectorResult:
        usage_result = self.fetch_resource_usages(function_name=function_name, resource_arn=resource_arn)
        if usage_result.status in {
            ConnectorStatus.NOT_CONFIGURED,
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.RATE_LIMITED,
        }:
            return usage_result
        if not isinstance(usage_result.data, ScalrDataset):
            return usage_result
        dataset = usage_result.data
        warnings = list(usage_result.warnings)
        enriched_workspaces: dict[str, WorkspaceRef] = {ws.id: ws for ws in dataset.workspaces}
        enriched_runs: dict[str, RunEvidence] = {run.id: run for run in dataset.runs}
        for usage in dataset.resource_usages:
            if usage.workspace:
                enriched_workspaces.setdefault(usage.workspace.id, usage.workspace)
            if usage.run:
                enriched_runs.setdefault(usage.run.id, usage.run)
        missing_sha_workspaces = []
        for usage in dataset.resource_usages:
            if usage.run and not usage.run.vcs_revision and usage.workspace:
                if usage.workspace.id not in missing_sha_workspaces:
                    missing_sha_workspaces.append(usage.workspace.id)
        for workspace_id in missing_sha_workspaces[:3]:
            run_result = self.list_runs(workspace_id=workspace_id, page_size=20)
            if run_result.status != ConnectorStatus.SUCCESS or not isinstance(run_result.data, list):
                warnings.append(
                    f"Scalr run detail lookup for workspace {workspace_id} failed; VCS commit join may be incomplete."
                )
                continue
            for run in run_result.data:
                if run.id in enriched_runs and not enriched_runs[run.id].vcs_revision:
                    enriched_runs[run.id] = run
        for usage in dataset.resource_usages:
            if usage.run and usage.run.id in enriched_runs:
                replacement = enriched_runs[usage.run.id]
                if replacement.vcs_revision and not usage.run.vcs_revision:
                    usage.run = replacement
        dataset.workspaces = sorted(enriched_workspaces.values(), key=lambda item: item.id)
        dataset.runs = sorted(enriched_runs.values(), key=lambda item: item.id)
        usage_result.data = dataset
        usage_result.warnings = warnings
        if warnings and usage_result.status == ConnectorStatus.SUCCESS:
            usage_result.status = ConnectorStatus.PARTIAL
        return usage_result
