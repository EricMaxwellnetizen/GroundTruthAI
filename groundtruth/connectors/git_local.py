from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from groundtruth.config import Settings
from groundtruth.connectors.base import BaseConnector
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

SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
SAFE_TERM = re.compile(r"^[A-Za-z0-9_.:/@+=,-]{1,300}$")
SAFE_PATH = re.compile(r"^[A-Za-z0-9_./@+=,-]{1,500}$")
MAX_GREP_LINES = 40
MAX_HISTORY_COMMITS = 10


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class GitLocalConnector(BaseConnector):
    name = "git_local"
    source = "git_local"

    def __init__(self, settings: Settings, repo_path: str | Path | None = None) -> None:
        super().__init__(settings)
        raw = Path(repo_path or settings.git_repo_path) if (repo_path or settings.git_repo_path) else None
        self.repo_path = raw.expanduser().resolve() if raw else None

    def _configured(self) -> bool:
        return bool(self.repo_path and self.repo_path.exists() and self.repo_path.is_dir())

    def is_configured(self) -> bool:
        return self._configured()

    def _git(self, args: list[str], *, timeout: int = 20) -> subprocess.CompletedProcess[str]:
        if not self.repo_path:
            raise RuntimeError("Git repository path is not configured.")
        env = os.environ.copy()
        env.update(
            {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_OPTIONAL_LOCKS": "0",
            }
        )
        return subprocess.run(
            ["git", *args],
            cwd=str(self.repo_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _run(self, args: list[str], *, timeout: int = 20) -> tuple[str | None, str | None]:
        try:
            completed = self._git(args, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, safe_text(str(exc), limit=300)
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout or "git command failed").strip()
            return None, safe_text(message, limit=400)
        return completed.stdout, None

    def test_connection(self) -> ConnectionTest:
        if not self._configured():
            return ConnectionTest(
                name="Local Git",
                status=ConnectorStatus.NOT_CONFIGURED,
                message="Set GIT_REPO_PATH to a local clone of the GitLab repository.",
            )
        inside, error = self._run(["rev-parse", "--is-inside-work-tree"])
        if error or (inside or "").strip() != "true":
            return ConnectionTest(
                name="Local Git",
                status=ConnectorStatus.FAILED,
                message="The configured path is not a readable Git working tree.",
                details={"error": error or "git rev-parse did not confirm a working tree"},
            )
        remote, _ = self._run(["remote", "get-url", "origin"])
        head, _ = self._run(["rev-parse", "HEAD"])
        return ConnectionTest(
            name="Local Git",
            status=ConnectorStatus.SUCCESS,
            message="Connected to a local read-only Git clone.",
            details={"repo_path": str(self.repo_path), "remote": (remote or "").strip(), "head": (head or "").strip()},
        )

    def _require_sha(self, sha: str) -> str:
        text = (sha or "").strip()
        if not SHA_PATTERN.match(text):
            raise ValueError("A valid Git commit SHA is required.")
        return text

    def verify_commit(self, sha: str) -> ConnectorResult:
        if not self._configured():
            return self.not_configured("Local Git is not configured. Set GIT_REPO_PATH to a clone of the repository.")
        try:
            commit_sha = self._require_sha(sha)
        except ValueError as exc:
            return self.result(ConnectorStatus.FAILED, error=str(exc))
        exists, error = self._run(["cat-file", "-e", f"{commit_sha}^{{commit}}"])
        if error:
            return self.result(
                ConnectorStatus.NOT_FOUND,
                error=f"The commit {commit_sha} is not present in the local clone. Fetch the repository history and retry.",
                coverage={"repo_path": str(self.repo_path), "commit_sha": commit_sha},
            )
        raw, error = self._run(
            [
                "show",
                "-s",
                "--no-show-signature",
                "--format=%H%x00%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%B",
                commit_sha,
            ]
        )
        if error or raw is None:
            return self.result(
                ConnectorStatus.FAILED,
                error=f"Could not read commit {commit_sha}: {error or 'no output'}",
                coverage={"repo_path": str(self.repo_path), "commit_sha": commit_sha},
            )
        parts = raw.split("\x00")
        if len(parts) < 7:
            return self.result(ConnectorStatus.FAILED, error="Git returned an unexpected commit metadata shape.")
        remote, _ = self._run(["remote", "get-url", "origin"])
        commit = GitCommitEvidence(
            repository=Path(str(self.repo_path)).name,
            repository_url=(remote or "").strip() or None,
            sha=parts[0].strip(),
            author_name=parts[1].strip() or None,
            author_email=parts[2].strip() or None,
            committed_at=_parse_datetime(parts[3]),
            committer_name=parts[4].strip() or None,
            committer_email=parts[5].strip() or None,
            message=safe_text("\x00".join(parts[7:]).strip(), limit=1000),
        )
        return self.result(
            ConnectorStatus.SUCCESS,
            data=commit,
            coverage={"repo_path": str(self.repo_path), "commit_sha": commit.sha},
            records=1,
        )

    def _grep(self, *, sha: str, term: str, match_type: MatchType) -> list[GitFileEvidence]:
        if not SAFE_TERM.match(term or ""):
            return []
        raw, error = self._run(["grep", "-n", "-F", "-e", term, sha, "--", "*.tf"])
        if error or not raw:
            return []
        matches: list[GitFileEvidence] = []
        for line in raw.splitlines():
            if len(matches) >= MAX_GREP_LINES:
                break
            parts = line.split(":", 3)
            if len(parts) < 3:
                continue
            if parts[0].lower().startswith(sha.lower()[:7]):
                if len(parts) < 4:
                    continue
                path, line_text, content = parts[1], parts[2], parts[3]
            else:
                path, line_text, content = parts[0], parts[1], ":".join(parts[2:])
            if not SAFE_PATH.match(path or ""):
                continue
            line_number = int(line_text) if line_text.isdigit() else None
            matches.append(
                GitFileEvidence(
                    path=path,
                    matched_string=term,
                    match_type=match_type,
                    snippet=safe_text(content.strip(), limit=400),
                    line=line_number,
                    commit_sha=sha,
                )
            )
        return matches

    def find_file_matches(
        self,
        *,
        sha: str,
        function_name: str,
        resource_address: str | None = None,
    ) -> ConnectorResult:
        if not self._configured():
            return self.not_configured("Local Git is not configured. Set GIT_REPO_PATH to a clone of the repository.")
        try:
            commit_sha = self._require_sha(sha)
        except ValueError as exc:
            return self.result(ConnectorStatus.FAILED, error=str(exc))
        matches: list[GitFileEvidence] = []
        seen: set[tuple[str, int | None, str]] = set()
        search_terms: list[tuple[str, MatchType]] = []
        if resource_address:
            search_terms.append((resource_address, MatchType.EXACT_ADDRESS))
        if function_name:
            search_terms.append((function_name, MatchType.EXACT_NAME_CONTEXT))
        for term, match_type in search_terms:
            for match in self._grep(sha=commit_sha, term=term, match_type=match_type):
                key = (match.path, match.line, match.matched_string)
                if key not in seen:
                    seen.add(key)
                    matches.append(match)
        return self.result(
            ConnectorStatus.SUCCESS,
            data=matches,
            coverage={
                "repo_path": str(self.repo_path),
                "commit_sha": commit_sha,
                "searched_terms": [term for term, _ in search_terms],
            },
            records=len(matches),
        )

    def history_matches(
        self,
        *,
        function_name: str,
        resource_address: str | None = None,
    ) -> ConnectorResult:
        if not self._configured():
            return self.not_configured("Local Git is not configured. Set GIT_REPO_PATH to a clone of the repository.")
        matches: list[GitFileEvidence] = []
        seen: set[tuple[str, str]] = set()
        search_terms: list[tuple[str, MatchType]] = []
        if resource_address:
            search_terms.append((resource_address, MatchType.EXACT_ADDRESS))
        if function_name:
            search_terms.append((function_name, MatchType.EXACT_NAME_CONTEXT))
        for term, match_type in search_terms:
            if not SAFE_TERM.match(term or ""):
                continue
            raw, error = self._run(
                ["log", "--all", f"-n{MAX_HISTORY_COMMITS}", "--format=%H", f"-S{term}", "--", "*.tf"]
            )
            if error or not raw:
                continue
            for sha in raw.splitlines():
                sha = sha.strip()
                if not SHA_PATTERN.match(sha) or (sha, term) in seen:
                    continue
                seen.add((sha, term))
                names, _ = self._run(["show", "--name-only", "--format=", sha, "--", "*.tf"])
                path = None
                for candidate in (names or "").splitlines():
                    candidate = candidate.strip()
                    if candidate and SAFE_PATH.match(candidate):
                        path = candidate
                        break
                matches.append(
                    GitFileEvidence(
                        path=path or "(path not resolved)",
                        matched_string=term,
                        match_type=match_type,
                        snippet="",
                        commit_sha=sha,
                    )
                )
        return self.result(
            ConnectorStatus.SUCCESS,
            data=matches,
            coverage={"repo_path": str(self.repo_path), "max_history_commits": MAX_HISTORY_COMMITS},
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
        if not self._configured():
            return self.not_configured("Local Git is not configured. Set GIT_REPO_PATH to a clone of the repository.")
        remote, _ = self._run(["remote", "get-url", "origin"])
        repository = workspace.vcs_repo_identifier or Path(str(self.repo_path)).name
        limitations: list[str] = []
        commit_sha = run.vcs_revision if run else None
        commit: GitCommitEvidence | None = None
        commit_verified = False
        if commit_sha:
            commit_result = self.verify_commit(commit_sha)
            if commit_result.status == ConnectorStatus.SUCCESS and isinstance(commit_result.data, GitCommitEvidence):
                commit = commit_result.data
                commit_verified = True
                if not commit.repository_url:
                    commit.repository_url = (remote or "").strip() or workspace.vcs_repo_identifier
            else:
                limitations.append(
                    commit_result.error
                    or f"Commit {commit_sha} could not be verified in the local clone; fetch the repository history and retry."
                )
        else:
            limitations.append("No exact Scalr run VCS revision was available; Git matches are candidate-only.")
            head, _ = self._run(["rev-parse", "HEAD"])
            commit_sha = (head or "").strip() or None
        file_matches: list[GitFileEvidence] = []
        history: list[GitFileEvidence] = []
        if commit_sha:
            file_result = self.find_file_matches(
                sha=commit_sha,
                function_name=function_name,
                resource_address=resource_address,
            )
            if file_result.status == ConnectorStatus.SUCCESS and isinstance(file_result.data, list):
                file_matches = file_result.data
            history_result = self.history_matches(function_name=function_name, resource_address=resource_address)
            if history_result.status == ConnectorStatus.SUCCESS and isinstance(history_result.data, list):
                history = history_result.data
        for match in file_matches:
            match.source_url = None
        if not commit_verified:
            limitations.append(
                "Repository file matches at the fallback revision are candidate evidence, not proof that the run used this code."
            )
        lineage = RepositoryLineage(
            repository=repository,
            repository_url=(remote or "").strip() or workspace.vcs_repo_identifier,
            working_directory=workspace.working_directory,
            branch=workspace.branch,
            vcs_revision=commit_sha,
            run_id=run.id if run else None,
            workspace_id=workspace.id,
            commit_verified=commit_verified,
            commit=commit,
            file_matches=file_matches,
            history_matches=history,
            candidate_only=not commit_verified,
            limitations=limitations,
        )
        status = ConnectorStatus.SUCCESS if commit_verified else ConnectorStatus.PARTIAL
        return self.result(
            status,
            data=lineage,
            coverage={
                "repo_path": str(self.repo_path),
                "commit_verified": commit_verified,
                "file_matches": len(file_matches),
                "history_matches": len(history),
            },
            warnings=limitations,
            records=len(file_matches) + len(history),
        )
