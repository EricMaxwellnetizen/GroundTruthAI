from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector, classify_http_error, safe_error_message
from groundtruth.models.connector import ConnectionTest, ConnectorResult
from groundtruth.models.enums import ConnectorStatus, MatchType
from groundtruth.models.lineage import (
    GitCommitEvidence,
    GitFileEvidence,
    RepositoryLineage,
    RunEvidence,
    WorkspaceRef,
)
from groundtruth.utils.redaction import safe_text
from groundtruth.utils.retry import RateLimiter
from groundtruth.utils.urls import build_gitlab_url, safe_url

SHA_PATTERN = __import__("re").compile(r"^[0-9a-fA-F]{7,40}$")
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


class GitLabConnector(BaseConnector):
    name = "gitlab"
    source = "gitlab"

    def __init__(self, settings: Settings, session: Any | None = None) -> None:
        super().__init__(settings)
        self._session = session
        self._rate_limiter = RateLimiter(0.2)

    def _http(self) -> Any:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _base(self) -> str:
        return (self.settings.gitlab_base_url or "https://gitlab.com").rstrip("/")

    def _project(self) -> str:
        return quote(str(self.settings.gitlab_project_id), safe="")

    def _headers(self) -> dict[str, str]:
        return {
            "PRIVATE-TOKEN": self.settings.gitlab_token,
            "Accept": "application/json",
            "User-Agent": "GroundTruth/1.0",
        }

    def is_configured(self) -> bool:
        return bool(safe_url(self._base()) and self.settings.gitlab_project_id and self.settings.gitlab_token)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> tuple[Any | None, ConnectorResult | None]:
        url = f"{self._base()}/api/v4{path}"
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
                return None, self.result(
                    classify_http_error(response.status_code),
                    error=self._response_error(response),
                    coverage={"endpoint": path, "http_status": response.status_code},
                )
            try:
                return response.json(), None
            except ValueError:
                return None, self.result(
                    ConnectorStatus.FAILED,
                    error="GitLab returned a non-JSON response.",
                    coverage={"endpoint": path, "http_status": response.status_code},
                )
        return None, self.result(
            ConnectorStatus.FAILED,
            error=f"GitLab request failed after {self.settings.max_retries} attempts: {safe_error_message(last_error or RuntimeError('unknown error'))}",
            coverage={"endpoint": path},
        )

    @staticmethod
    def _response_error(response: Any) -> str:
        detail = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                detail = str(payload.get("message") or payload.get("error") or "")
        except ValueError:
            detail = ""
        prefix = f"GitLab API returned HTTP {response.status_code}."
        if response.status_code in {401, 403}:
            return (
                f"{prefix} The token is invalid, expired, or lacks read_api/read_repository scope for this project. "
                "Use a read-only token, or use the local Git clone fallback."
            )[:500]
        if response.status_code == 404:
            return f"{prefix} The project, commit, or file was not found, or the token cannot see it."[:500]
        if response.status_code == 429:
            return f"{prefix} GitLab rate limit reached. Retry shortly."[:500]
        return f"{prefix} {detail}".strip()[:500]

    def test_connection(self) -> ConnectionTest:
        if not self.is_configured():
            return ConnectionTest(
                name="GitLab",
                status=ConnectorStatus.NOT_CONFIGURED,
                message="Set GITLAB_BASE_URL, GITLAB_PROJECT_ID (ID or namespace/project), and a read-only GITLAB_TOKEN.",
            )
        payload, failure = self._request(f"/projects/{self._project()}")
        if failure:
            return ConnectionTest(
                name="GitLab",
                status=failure.status,
                message=failure.error or "GitLab connection failed.",
                details=failure.coverage,
            )
        name = payload.get("path_with_namespace") if isinstance(payload, dict) else None
        return ConnectionTest(
            name="GitLab",
            status=ConnectorStatus.SUCCESS,
            message=f"Connected to GitLab project {name or self.settings.gitlab_project_id} with a read-only token.",
            details={"base_url": self._base(), "project_id": self.settings.gitlab_project_id},
        )

    def verify_commit(self, sha: str) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("GitLab is not configured.")
        text = (sha or "").strip()
        if not SHA_PATTERN.match(text):
            return self.result(ConnectorStatus.FAILED, error="A valid Git commit SHA is required.")
        payload, failure = self._request(f"/projects/{self._project()}/repository/commits/{quote(text, safe='')}")
        if failure:
            return failure
        if not isinstance(payload, dict):
            return self.result(ConnectorStatus.FAILED, error="GitLab returned an unexpected commit shape.")
        commit = GitCommitEvidence(
            repository=str(self.settings.gitlab_project_id),
            repository_url=build_gitlab_url(self._base(), self.settings.gitlab_project_id),
            sha=str(payload.get("id") or text),
            author_name=safe_text(str(payload.get("author_name") or ""), limit=120) or None,
            author_email=safe_text(str(payload.get("author_email") or ""), limit=200) or None,
            committed_at=_parse_datetime(payload.get("committed_date") or payload.get("created_at")),
            committer_name=safe_text(str(payload.get("committer_name") or ""), limit=120) or None,
            committer_email=safe_text(str(payload.get("committer_email") or ""), limit=200) or None,
            message=safe_text(str(payload.get("message") or ""), limit=1000),
            source_url=build_gitlab_url(
                self._base(), self.settings.gitlab_project_id, commit_sha=str(payload.get("id") or text)
            ),
        )
        return self.result(
            ConnectorStatus.SUCCESS,
            data=commit,
            coverage={"project_id": self.settings.gitlab_project_id, "commit_sha": commit.sha},
            records=1,
        )

    def search_blobs(self, *, term: str, ref: str) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("GitLab is not configured.")
        if not term or len(term) > 300:
            return self.result(ConnectorStatus.FAILED, error="A search term of 1-300 characters is required.")
        params = {"scope": "blobs", "search": term, "ref": ref, "per_page": "20"}
        payload, failure = self._request(f"/projects/{self._project()}/search", params)
        if failure:
            if failure.status in {ConnectorStatus.NOT_FOUND, ConnectorStatus.FAILED}:
                failure.warnings.append(
                    "GitLab project blob search may be disabled or unavailable on this tier/configuration. Use the local Git clone for reliable search."
                )
                failure.status = ConnectorStatus.PARTIAL
            return failure
        if not isinstance(payload, list):
            return self.result(ConnectorStatus.PARTIAL, error="GitLab search returned an unexpected shape.")
        matches: list[GitFileEvidence] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "")
            if not path.endswith(".tf"):
                continue
            data = safe_text(str(item.get("data") or ""), limit=400)
            line = item.get("startline") if isinstance(item.get("startline"), int) else None
            matches.append(
                GitFileEvidence(
                    path=path,
                    matched_string=term,
                    match_type=MatchType.EXACT_NAME_CONTEXT,
                    snippet=data,
                    line=line,
                    commit_sha=ref if SHA_PATTERN.match(ref) else None,
                    source_url=build_gitlab_url(
                        self._base(), self.settings.gitlab_project_id, commit_sha=ref, path=path
                    ),
                )
            )
            if len(matches) >= 20:
                break
        warnings = []
        if not matches:
            warnings.append("No Terraform blob matched this term. GitLab search scope and indexing can affect results.")
        return self.result(
            ConnectorStatus.SUCCESS if matches else ConnectorStatus.PARTIAL,
            data=matches,
            coverage={"project_id": self.settings.gitlab_project_id, "ref": ref, "search_scope": "blobs"},
            warnings=warnings,
            records=len(matches),
        )

    def build_repository_lineage(
        self,
        *,
        workspace: WorkspaceRef,
        run: RunEvidence | None,
        function_name: str,
        resource_address: str | None = None,
    ) -> ConnectorResult:
        if not self.is_configured():
            return self.not_configured("GitLab is not configured.")
        repository = workspace.vcs_repo_identifier or str(self.settings.gitlab_project_id)
        limitations = [
            "GitLab REST blob search searches the selected revision; use a local clone for reliable history search."
        ]
        commit_sha = run.vcs_revision if run else None
        commit = None
        commit_verified = False
        if not commit_sha:
            limitations.append("No exact Scalr run VCS revision was available; GitLab matches are candidate-only.")
        else:
            commit_result = self.verify_commit(commit_sha)
            if commit_result.status == ConnectorStatus.SUCCESS and isinstance(commit_result.data, GitCommitEvidence):
                commit = commit_result.data
                commit_verified = True
            else:
                limitations.append(commit_result.error or "The GitLab commit could not be verified.")
        matches: list[GitFileEvidence] = []
        if commit_sha:
            for term in [resource_address, function_name]:
                if not term:
                    continue
                result = self.search_blobs(term=term, ref=commit_sha)
                if result.status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL} and isinstance(
                    result.data, list
                ):
                    for match in result.data:
                        if all(
                            not (
                                existing.path == match.path
                                and existing.line == match.line
                                and existing.matched_string == match.matched_string
                            )
                            for existing in matches
                        ):
                            matches.append(match)
                for warning in result.warnings:
                    if warning not in limitations:
                        limitations.append(warning)
        lineage = RepositoryLineage(
            repository=repository,
            repository_url=build_gitlab_url(self._base(), self.settings.gitlab_project_id),
            working_directory=workspace.working_directory,
            branch=workspace.branch,
            vcs_revision=commit_sha,
            run_id=run.id if run else None,
            workspace_id=workspace.id,
            commit_verified=commit_verified,
            commit=commit,
            file_matches=matches,
            history_matches=[],
            candidate_only=not commit_verified,
            limitations=limitations,
        )
        return self.result(
            ConnectorStatus.SUCCESS if commit_verified else ConnectorStatus.PARTIAL,
            data=lineage,
            coverage={
                "project_id": self.settings.gitlab_project_id,
                "commit_verified": commit_verified,
                "file_matches": len(matches),
            },
            warnings=limitations,
            records=len(matches),
        )
