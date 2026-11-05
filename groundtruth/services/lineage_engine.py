from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from groundtruth.config import Settings
from groundtruth.models.connector import ConnectorResult
from groundtruth.models.enums import (
    ConfidenceLabel,
    ConnectorStatus,
    LineageStatus,
    MatchType,
    PrincipalType,
    RecommendationCode,
    Sensitivity,
    SourceType,
)
from groundtruth.models.evidence import EvidenceRecord
from groundtruth.models.graph import EvidenceGraph, GraphEdge, GraphNode
from groundtruth.models.lineage import (
    ActorEvidence,
    CloudTrailEventEvidence,
    CloudWatchActivity,
    CoverageRecord,
    DependencyEvidence,
    LineageResult,
    OmniContext,
    OwnershipEvidence,
    Recommendation,
    RepositoryLineage,
    ResourceUsageRecord,
    RunEvidence,
    ScalrDataset,
)
from groundtruth.models.resource import CloudResource
from groundtruth.models.state_backup import StateBackupEvidence
from groundtruth.services.evidence_factory import EvidenceFactory
from groundtruth.services.identity import IdentityError, is_lambda_arn, match_external_identity, parse_lambda_arn
from groundtruth.services.state_backup import select_state_backup_match
from groundtruth.utils.hashing import sha256_hex
from groundtruth.utils.redaction import redact_tags, safe_text
from groundtruth.utils.urls import build_aws_console_url

REQUIRED_FAILURES = {
    ConnectorStatus.NOT_CONFIGURED,
    ConnectorStatus.PERMISSION_DENIED,
    ConnectorStatus.RATE_LIMITED,
    ConnectorStatus.FAILED,
}

SECRET_ASSIGNMENT = re.compile(
    r"(?i)((?:secret|token|password|passwd|private[_-]?key|api[_-]?key|access[_-]?key|credential)\s*[:=]\s*)([\"']?)[^\"'\s,}]+"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _safe_snippet(value: str) -> str:
    return safe_text(SECRET_ASSIGNMENT.sub(r"\1\2[redacted]", value or ""), limit=600)


def _node_id(prefix: str, key: str) -> str:
    return f"node_{prefix}_{sha256_hex(key)[:12]}"


def _edge_id(source: str, target: str, edge_type: str, evidence_id: str) -> str:
    return f"edge_{sha256_hex(f'{source}|{target}|{edge_type}|{evidence_id}')[:16]}"


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_failed(status: ConnectorStatus) -> bool:
    return status in REQUIRED_FAILURES or status == ConnectorStatus.NOT_FOUND


class LineageEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def investigate(
        self,
        resource: CloudResource,
        *,
        aws_result: ConnectorResult,
        scalr_result: ConnectorResult,
        git_lineage: RepositoryLineage | None,
        git_result: ConnectorResult | None,
        cloudtrail_result: ConnectorResult,
        cloudwatch_result: ConnectorResult,
        omni_result: ConnectorResult,
        mode: str | None = None,
        state_backup: StateBackupEvidence | None = None,
    ) -> LineageResult:
        fixture = any(
            [
                resource.fixture,
                aws_result.fixture,
                scalr_result.fixture,
                cloudtrail_result.fixture,
                cloudwatch_result.fixture,
                omni_result.fixture,
                bool(git_result and git_result.fixture),
            ]
        )
        investigation_id = f"inv_{uuid.uuid4().hex[:16]}"
        factory = EvidenceFactory(investigation_id)
        evidence: list[EvidenceRecord] = []
        graph = EvidenceGraph()
        actors: list[ActorEvidence] = []
        dependencies: list[DependencyEvidence] = []
        current_owners: list[OwnershipEvidence] = []
        historical_managers: list[OwnershipEvidence] = []
        candidate_evidence_ids: list[str] = []
        limitations: list[str] = []
        unresolved: list[str] = []

        def add_evidence(item: EvidenceRecord | None) -> EvidenceRecord | None:
            if item is None:
                return None
            if not any(existing.evidence_id == item.evidence_id for existing in evidence):
                evidence.append(item)
            return item

        def add_actor(actor: ActorEvidence) -> None:
            key = (actor.source.value, actor.identity_type, actor.identifier)
            if not any(
                (existing.source.value, existing.identity_type, existing.identifier) == key for existing in actors
            ):
                actors.append(actor)

        def add_node(node: GraphNode) -> None:
            graph.add_node(node)

        def add_edge(
            source_node: str,
            target_node: str,
            edge_type: str,
            label: str,
            evidence_item: EvidenceRecord,
            *,
            match_type: MatchType | None = None,
            confidence: ConfidenceLabel | None = None,
            inferred: bool = False,
            observed_at: datetime | None = None,
        ) -> None:
            graph.add_edge(
                GraphEdge(
                    edge_id=_edge_id(source_node, target_node, edge_type, evidence_item.evidence_id),
                    source_node=source_node,
                    target_node=target_node,
                    edge_type=edge_type,
                    label=label,
                    source_evidence_id=evidence_item.evidence_id,
                    observed_at=observed_at or evidence_item.observed_at,
                    match_type=match_type or evidence_item.match_type,
                    confidence=confidence or evidence_item.match_confidence,
                    inferred=inferred,
                    fixture=fixture,
                )
            )

        resource_node = _node_id("resource", resource.identity)
        add_node(
            GraphNode(
                node_id=resource_node,
                node_type=resource.resource_type,
                label=resource.name,
                attributes={
                    "account_id": resource.account_id,
                    "region": resource.region,
                    "arn": resource.arn,
                    "status": resource.status,
                },
                fixture=fixture,
            )
        )

        add_evidence(
            factory.create(
                source=SourceType.AWS_LAMBDA,
                source_label="AWS Lambda resource",
                observed_at=resource.observed_at,
                resource_identity=resource.identity,
                match_type=MatchType.EXACT_ARN,
                record_id=resource.identity,
                facts={
                    "title": f"Observed Lambda function {resource.name}",
                    "detail": (
                        f"{resource.resource_type} {resource.name} in {resource.region}; "
                        f"status {resource.status or 'unknown'}; last modified {_iso(resource.last_modified_at) or 'unknown'}."
                    ),
                    "status": resource.status,
                    "last_modified_at": _iso(resource.last_modified_at),
                    "tags": redact_tags(resource.tags),
                    "safe_attributes": resource.safe_attributes,
                },
                account_id=resource.account_id,
                region=resource.region,
                match_confidence=ConfidenceLabel.HIGH,
                source_url=build_aws_console_url(resource.arn, resource.region),
                limitations=[
                    "Read-only get_function response; environment variable values and package code are not included."
                ],
                sensitivity=Sensitivity.INTERNAL,
                fixture=fixture,
            )
        )

        identity_conflict = False
        state_backup_exact = False
        if state_backup is not None:
            selected_state = select_state_backup_match(state_backup, resource)
            if selected_state is not None:
                state_match, state_match_type, state_match_confidence, state_match_reason = selected_state
                state_backup_exact = state_match_type == MatchType.EXACT_ARN
                state_evidence = add_evidence(
                    factory.create(
                        source=SourceType.TERRAFORM_STATE_BACKUP,
                        source_label="User-supplied Terraform state backup",
                        observed_at=state_backup.parsed_at,
                        resource_identity=resource.identity,
                        match_type=state_match_type,
                        record_id=f"{state_backup.sha256}:{state_match.address}",
                        facts={
                            "title": f"User-supplied state address {state_match.address}",
                            "detail": (
                                f"State snapshot {state_backup.filename} "
                                f"(serial {state_backup.serial if state_backup.serial is not None else 'unknown'}) "
                                f"contains {state_match.address}. {state_match_reason}"
                            ),
                            "address": state_match.address,
                            "provider": state_match.provider,
                            "arn": state_match.arn,
                            "role_arn": state_match.role_arn,
                            "function_name": state_match.function_name,
                            "runtime": state_match.runtime,
                            "handler": state_match.handler,
                            "memory_size": state_match.memory_size,
                            "timeout": state_match.timeout,
                            "sha256": state_backup.sha256,
                            "serial": state_backup.serial,
                            "terraform_version": state_backup.terraform_version,
                            "origin": "user_supplied",
                        },
                        account_id=resource.account_id,
                        region=resource.region,
                        match_confidence=state_match_confidence,
                        limitations=[
                            *state_backup.limitations,
                            state_match_reason,
                            "User-supplied state cannot override exact live evidence.",
                        ],
                        sensitivity=Sensitivity.INTERNAL,
                        fixture=fixture,
                        origin="user_supplied",
                    )
                )
                if state_evidence is not None and not state_backup_exact:
                    candidate_evidence_ids.append(state_evidence.evidence_id)
        dataset = scalr_result.data if isinstance(scalr_result.data, ScalrDataset) else ScalrDataset()
        seen_workspaces: set[str] = set()
        seen_runs: set[str] = set()
        seen_states: set[str] = set()

        for usage in dataset.resource_usages:
            exact, match_type, match_reason = self._match_usage(resource, usage)
            if not exact or match_type is None:
                if self._usage_mentions_resource(resource, usage):
                    candidate_evidence = add_evidence(
                        factory.create(
                            source=SourceType.SCALR_RESOURCE_USAGE,
                            source_label="Scalr resource usage candidate",
                            observed_at=usage.updated_at or _now(),
                            resource_identity=resource.identity,
                            match_type=MatchType.CANDIDATE_NAME,
                            record_id=usage.id,
                            facts={
                                "title": f"Scalr usage name candidate: {usage.address}",
                                "detail": match_reason,
                                "workspace": usage.workspace.name if usage.workspace else None,
                                "address": usage.address,
                                "external_id": usage.external_id,
                            },
                            account_id=usage.account_id,
                            region=usage.region,
                            match_confidence=ConfidenceLabel.LOW,
                            source_url=usage.source_url,
                            limitations=[match_reason, "Name evidence alone cannot establish ownership."],
                            fixture=fixture,
                        )
                    )
                    if candidate_evidence:
                        candidate_evidence_ids.append(candidate_evidence.evidence_id)
                continue

            if usage.account_id and usage.account_id != resource.account_id:
                identity_conflict = True
            if usage.region and usage.region != resource.region:
                identity_conflict = True

            usage_evidence = add_evidence(
                factory.create(
                    source=SourceType.SCALR_RESOURCE_USAGE,
                    source_label="Scalr resource usage",
                    observed_at=usage.updated_at or _now(),
                    resource_identity=resource.identity,
                    match_type=match_type,
                    record_id=usage.id,
                    facts={
                        "title": f"Scalr state binding: {usage.address}",
                        "detail": (
                            f"{'Active' if usage.is_active else 'Inactive'} resource usage in "
                            f"{usage.workspace.name if usage.workspace else 'unknown workspace'}; {match_reason}"
                        ),
                        "address": usage.address,
                        "is_active": usage.is_active,
                        "is_duplicate": usage.is_duplicate,
                        "updated_at": _iso(usage.updated_at),
                        "updated_by_email": usage.updated_by_email,
                        "workspace_id": usage.workspace.id if usage.workspace else None,
                        "workspace_name": usage.workspace.name if usage.workspace else None,
                    },
                    account_id=usage.account_id,
                    region=usage.region,
                    match_confidence=ConfidenceLabel.HIGH,
                    source_url=usage.source_url or (usage.workspace.source_url if usage.workspace else None),
                    limitations=usage.limitations
                    + (["Scalr marks this usage as duplicate state coverage."] if usage.is_duplicate else []),
                    fixture=fixture,
                )
            )
            if usage_evidence is None:
                continue
            usage_node = _node_id("usage", usage.id)
            add_node(
                GraphNode(
                    node_id=usage_node,
                    node_type="scalr_resource_usage",
                    label=usage.address,
                    source_evidence_id=usage_evidence.evidence_id,
                    attributes={
                        "active": usage.is_active,
                        "duplicate": usage.is_duplicate,
                        "workspace": usage.workspace.name if usage.workspace else None,
                    },
                    fixture=fixture,
                )
            )
            add_edge(
                resource_node,
                usage_node,
                "MATCHES_EXACT_ID",
                "exact Scalr state binding",
                usage_evidence,
            )

            workspace = usage.workspace
            workspace_evidence: EvidenceRecord | None = None
            if workspace is not None:
                workspace_evidence = add_evidence(
                    factory.create(
                        source=SourceType.SCALR_WORKSPACE,
                        source_label="Scalr workspace",
                        observed_at=usage.updated_at or _now(),
                        resource_identity=resource.identity,
                        match_type=MatchType.WORKSPACE_RELATION,
                        record_id=workspace.id,
                        facts={
                            "title": f"Scalr workspace {workspace.name}",
                            "detail": (
                                f"Workspace {workspace.name} is {'active' if workspace.active is not False else 'inactive'}; "
                                f"repository {workspace.vcs_repo_identifier or 'not recorded'}; "
                                f"working directory {workspace.working_directory or 'not recorded'}."
                            ),
                            "environment": workspace.environment,
                            "active": workspace.active,
                            "vcs_repo_identifier": workspace.vcs_repo_identifier,
                            "working_directory": workspace.working_directory,
                            "branch": workspace.branch,
                        },
                        account_id=usage.account_id,
                        region=usage.region,
                        match_confidence=ConfidenceLabel.HIGH,
                        source_url=workspace.source_url,
                        limitations=[],
                        fixture=fixture,
                    )
                )
                if workspace_evidence:
                    workspace_node = _node_id("workspace", workspace.id)
                    if workspace.id not in seen_workspaces:
                        seen_workspaces.add(workspace.id)
                        add_node(
                            GraphNode(
                                node_id=workspace_node,
                                node_type="scalr_workspace",
                                label=workspace.name,
                                source_evidence_id=workspace_evidence.evidence_id,
                                attributes={
                                    "active": workspace.active,
                                    "environment": workspace.environment,
                                    "repository": workspace.vcs_repo_identifier,
                                },
                                fixture=fixture,
                            )
                        )
                    add_edge(
                        usage_node,
                        workspace_node,
                        "MANAGED_BY_WORKSPACE",
                        "state binding belongs to workspace",
                        workspace_evidence,
                    )
                    add_edge(
                        resource_node,
                        workspace_node,
                        "MANAGED_BY_WORKSPACE",
                        "workspace holds this resource",
                        usage_evidence,
                    )

            run = usage.run
            run_evidence: EvidenceRecord | None = None
            if run is not None:
                run_evidence = add_evidence(
                    factory.create(
                        source=SourceType.SCALR_RUN,
                        source_label="Scalr run",
                        observed_at=run.created_at or usage.updated_at or _now(),
                        resource_identity=resource.identity,
                        match_type=MatchType.WORKSPACE_RELATION,
                        record_id=run.id,
                        facts={
                            "title": f"Scalr run {run.id}",
                            "detail": (
                                f"Run status {run.status or 'unknown'} from {run.source or 'unknown source'}; "
                                f"actor {run.actor or usage.updated_by_email or 'unknown'}."
                            ),
                            "status": run.status,
                            "source": run.source,
                            "actor": run.actor,
                            "vcs_revision": run.vcs_revision,
                            "workspace_id": run.workspace_id,
                            "attributes": run.attributes,
                        },
                        account_id=usage.account_id,
                        region=usage.region,
                        match_confidence=ConfidenceLabel.HIGH
                        if run.status in {"applied", "applied_never_tested", "planned_and_finished"}
                        else ConfidenceLabel.MEDIUM,
                        source_url=run.source_url,
                        limitations=[
                            "Run actor is the person or service that applied the change, not automatically the owner."
                        ],
                        fixture=fixture,
                    )
                )
                if run_evidence:
                    run_node = _node_id("run", run.id)
                    if run.id not in seen_runs:
                        seen_runs.add(run.id)
                        add_node(
                            GraphNode(
                                node_id=run_node,
                                node_type="scalr_run",
                                label=run.id,
                                source_evidence_id=run_evidence.evidence_id,
                                attributes={"status": run.status, "source": run.source},
                                fixture=fixture,
                            )
                        )
                    add_edge(
                        resource_node if workspace is None else usage_node,
                        run_node,
                        "RUN_EXECUTED_IN_WORKSPACE",
                        "run changed this state",
                        run_evidence,
                    )
                    actor = self._scalr_actor(run, usage, run_evidence, fixture)
                    if actor:
                        add_actor(actor)
                        actor_node = _node_id("actor", f"{actor.source.value}:{actor.identity_type}:{actor.identifier}")
                        add_node(
                            GraphNode(
                                node_id=actor_node,
                                node_type="actor",
                                label=actor.display_name or actor.identifier,
                                source_evidence_id=run_evidence.evidence_id,
                                attributes={"identity_type": actor.identity_type},
                                fixture=fixture,
                            )
                        )
                        add_edge(
                            run_node,
                            actor_node,
                            "EVENT_PERFORMED_BY_PRINCIPAL",
                            "run actor",
                            run_evidence,
                        )

            state = usage.state_version
            state_evidence: EvidenceRecord | None = None
            if state is not None:
                state_evidence = add_evidence(
                    factory.create(
                        source=SourceType.SCALR_STATE,
                        source_label="Scalr state version",
                        observed_at=state.created_at or usage.updated_at or _now(),
                        resource_identity=resource.identity,
                        match_type=MatchType.WORKSPACE_RELATION,
                        record_id=state.id,
                        facts={
                            "title": f"Scalr state version {state.id}",
                            "detail": "State version recorded by Scalr for this resource usage.",
                            "state_version_id": state.id,
                        },
                        account_id=usage.account_id,
                        region=usage.region,
                        match_confidence=ConfidenceLabel.HIGH,
                        source_url=state.source_url,
                        fixture=fixture,
                    )
                )
                if state_evidence:
                    state_node = _node_id("state", state.id)
                    if state.id not in seen_states:
                        seen_states.add(state.id)
                        add_node(
                            GraphNode(
                                node_id=state_node,
                                node_type="scalr_state_version",
                                label=state.id,
                                source_evidence_id=state_evidence.evidence_id,
                                fixture=fixture,
                            )
                        )
                    add_edge(
                        usage_node,
                        state_node,
                        "PRESENT_IN_STATE_VERSION",
                        "resource address present in state",
                        state_evidence,
                    )

            if workspace is None:
                candidate_evidence_ids.append(usage_evidence.evidence_id)
                limitations.append(
                    f"Scalr usage {usage.id} matched the exact identity but did not expose a workspace relationship."
                )
                continue

            active = usage.is_active and workspace.active is not False
            owner = OwnershipEvidence(
                kind="current" if active else "historical",
                workspace=workspace,
                resource_address=usage.address,
                resource_usage_id=usage.id,
                state_version=usage.state_version,
                run=usage.run,
                last_seen_at=usage.updated_at
                or (usage.run.created_at if usage.run else None)
                or (usage.state_version.created_at if usage.state_version else None),
                match_type=match_type,
                evidence_ids=_dedupe(
                    [usage_evidence.evidence_id]
                    + ([workspace_evidence.evidence_id] if workspace_evidence else [])
                    + ([run_evidence.evidence_id] if run_evidence else [])
                    + ([state_evidence.evidence_id] if state_evidence else [])
                ),
                limitations=usage.limitations
                + (["Scalr marks this usage as duplicate state coverage."] if usage.is_duplicate else []),
                fixture=fixture,
            )
            if active:
                current_owners.append(owner)
            else:
                historical_managers.append(owner)

        current_owners = self._dedupe_owners(current_owners)
        historical_managers = self._dedupe_owners(historical_managers)

        git_candidate = False
        git_exact_evidence = False
        if git_lineage is not None:
            commit = git_lineage.commit
            commit_evidence: EvidenceRecord | None = None
            if commit is not None:
                verified = bool(git_lineage.commit_verified and commit.sha)
                commit_evidence = add_evidence(
                    factory.create(
                        source=SourceType.GIT_COMMIT,
                        source_label="Git commit",
                        observed_at=commit.committed_at or _now(),
                        resource_identity=resource.identity,
                        match_type=MatchType.EXACT_COMMIT_SHA if verified else MatchType.CANDIDATE_NAME,
                        record_id=commit.sha,
                        facts={
                            "title": f"Git commit {commit.sha[:12]} in {commit.repository}",
                            "detail": f"{commit.message or 'Commit context'}; author {commit.author_name or 'unknown'}.",
                            "repository": commit.repository,
                            "sha": commit.sha,
                            "author_name": commit.author_name,
                            "author_email": commit.author_email,
                            "committed_at": _iso(commit.committed_at),
                            "message": commit.message,
                            "verified": verified,
                        },
                        account_id=resource.account_id,
                        region=resource.region,
                        match_confidence=ConfidenceLabel.HIGH if verified else ConfidenceLabel.LOW,
                        source_url=commit.source_url,
                        limitations=list(git_lineage.limitations),
                        fixture=fixture,
                    )
                )
                if commit_evidence:
                    commit_node = _node_id("commit", f"{commit.repository}:{commit.sha}")
                    add_node(
                        GraphNode(
                            node_id=commit_node,
                            node_type="git_commit",
                            label=commit.sha[:12],
                            source_evidence_id=commit_evidence.evidence_id,
                            attributes={"repository": commit.repository, "verified": verified},
                            fixture=fixture,
                        )
                    )
                    repo_node = _node_id("repository", commit.repository)
                    add_node(
                        GraphNode(
                            node_id=repo_node,
                            node_type="git_repository",
                            label=commit.repository,
                            source_evidence_id=commit_evidence.evidence_id,
                            attributes={"repository_url": commit.repository_url},
                            fixture=fixture,
                        )
                    )
                    add_edge(
                        commit_node,
                        repo_node,
                        "REVISION_BELONGS_TO_REPOSITORY",
                        "commit belongs to repository",
                        commit_evidence,
                    )
                    if git_lineage.run_id and commit.sha:
                        add_edge(
                            _node_id("run", git_lineage.run_id),
                            commit_node,
                            "RUN_USED_VCS_REVISION",
                            "run used this revision",
                            commit_evidence,
                            match_type=MatchType.EXACT_COMMIT_SHA,
                            confidence=ConfidenceLabel.HIGH if verified else ConfidenceLabel.LOW,
                            inferred=not verified,
                        )
                    author_actor = self._git_actor(commit, commit_evidence, fixture, role="author")
                    if author_actor:
                        add_actor(author_actor)
                    committer_actor = self._git_actor(commit, commit_evidence, fixture, role="committer")
                    if committer_actor:
                        add_actor(committer_actor)

            for file_match in git_lineage.file_matches + git_lineage.history_matches:
                exact_file = file_match.match_type in {MatchType.EXACT_ADDRESS, MatchType.EXACT_NAME_CONTEXT}
                exact_file = exact_file and bool(git_lineage.commit_verified)
                candidate = not exact_file or git_lineage.candidate_only
                if candidate:
                    git_candidate = True
                else:
                    git_exact_evidence = True
                file_confidence = (
                    ConfidenceLabel.HIGH
                    if exact_file
                    else ConfidenceLabel.MEDIUM
                    if file_match.match_type == MatchType.EXACT_ADDRESS
                    else ConfidenceLabel.LOW
                )
                file_evidence = add_evidence(
                    factory.create(
                        source=SourceType.GIT_FILE,
                        source_label="Git file match",
                        observed_at=commit.committed_at if commit and commit.committed_at else _now(),
                        resource_identity=resource.identity,
                        match_type=file_match.match_type,
                        record_id=f"{file_match.path}:{file_match.commit_sha or git_lineage.vcs_revision or ''}:{file_match.line or ''}",
                        facts={
                            "title": f"Terraform evidence in {file_match.path}",
                            "detail": (
                                f"Matched '{file_match.matched_string}'"
                                f"{f' at line {file_match.line}' if file_match.line else ''}."
                            ),
                            "path": file_match.path,
                            "matched_string": file_match.matched_string,
                            "line": file_match.line,
                            "snippet": _safe_snippet(file_match.snippet),
                            "commit_sha": file_match.commit_sha,
                            "candidate": candidate,
                        },
                        account_id=resource.account_id,
                        region=resource.region,
                        match_confidence=file_confidence,
                        source_url=file_match.source_url,
                        limitations=(
                            ["Candidate name/path evidence only; not an exact identity match."] if candidate else []
                        ),
                        fixture=fixture,
                    )
                )
                if file_evidence:
                    file_node = _node_id(
                        "gitfile", f"{file_match.path}:{file_match.commit_sha or git_lineage.vcs_revision or ''}"
                    )
                    add_node(
                        GraphNode(
                            node_id=file_node,
                            node_type="git_file",
                            label=file_match.path,
                            source_evidence_id=file_evidence.evidence_id,
                            attributes={"line": file_match.line, "matched_string": file_match.matched_string},
                            fixture=fixture,
                        )
                    )
                    add_edge(
                        resource_node,
                        file_node,
                        "MATCHES_EXACT_ID" if not candidate else "CANDIDATE_MATCH",
                        "Terraform file evidence",
                        file_evidence,
                        match_type=file_match.match_type,
                        confidence=file_confidence,
                        inferred=candidate,
                    )
                    if candidate:
                        candidate_evidence_ids.append(file_evidence.evidence_id)

        for event in cloudtrail_result.data if isinstance(cloudtrail_result.data, list) else []:
            if not isinstance(event, CloudTrailEventEvidence):
                continue
            exact_event = event.match_type == MatchType.EXACT_EVENT_RESOURCE
            event_evidence = add_evidence(
                factory.create(
                    source=SourceType.CLOUDTRAIL,
                    source_label="CloudTrail management event",
                    observed_at=event.event_time,
                    resource_identity=resource.identity,
                    match_type=event.match_type,
                    record_id=event.event_id,
                    facts={
                        "title": f"CloudTrail: {event.event_name}",
                        "detail": (
                            f"{event.event_name} by {event.principal_arn or event.source_identity or event.principal_id or 'unknown principal'} "
                            f"at {event.event_time.isoformat()}."
                        ),
                        "event_source": event.event_source,
                        "event_name": event.event_name,
                        "principal_type": event.principal_type.value,
                        "principal_arn": event.principal_arn,
                        "source_identity": event.source_identity,
                        "user_agent": event.user_agent,
                        "resource_arns": event.resource_arns,
                        "resource_names": event.resource_names,
                    },
                    account_id=event.account_id,
                    region=event.region,
                    match_confidence=ConfidenceLabel.HIGH if exact_event else ConfidenceLabel.LOW,
                    limitations=event.limitations
                    + ["CloudTrail management events are not invocation history and are subject to retention limits."],
                    fixture=fixture,
                )
            )
            if event_evidence:
                event_node = _node_id("event", event.event_id)
                add_node(
                    GraphNode(
                        node_id=event_node,
                        node_type="cloudtrail_event",
                        label=event.event_name,
                        source_evidence_id=event_evidence.evidence_id,
                        attributes={"event_time": event.event_time.isoformat()},
                        fixture=fixture,
                    )
                )
                add_edge(
                    event_node,
                    resource_node,
                    "EVENT_RECORDED_FOR_RESOURCE",
                    "event names this resource",
                    event_evidence,
                    observed_at=event.event_time,
                )
                comment = self._cloudtrail_actor(event, event_evidence, fixture)
                if comment:
                    add_actor(comment)
                    actor_node = _node_id(
                        "actor", f"{comment.source.value}:{comment.identity_type}:{comment.identifier}"
                    )
                    add_node(
                        GraphNode(
                            node_id=actor_node,
                            node_type="actor",
                            label=comment.display_name or comment.identifier,
                            source_evidence_id=event_evidence.evidence_id,
                            attributes={"identity_type": comment.identity_type},
                            fixture=fixture,
                        )
                    )
                    add_edge(
                        event_node,
                        actor_node,
                        "EVENT_PERFORMED_BY_PRINCIPAL",
                        "event principal",
                        event_evidence,
                        observed_at=event.event_time,
                    )

        activity = cloudwatch_result.data if isinstance(cloudwatch_result.data, CloudWatchActivity) else None
        if activity is not None:
            activity_evidence = add_evidence(
                factory.create(
                    source=SourceType.CLOUDWATCH_METRIC,
                    source_label="CloudWatch Lambda metrics",
                    observed_at=activity.latest_nonzero_invocations_at or activity.window_end,
                    resource_identity=resource.identity,
                    match_type=MatchType.EXACT_NAME_CONTEXT,
                    record_id=f"{activity.metric_namespace}:{activity.window_start.isoformat()}:{activity.window_end.isoformat()}",
                    facts={
                        "title": "CloudWatch Lambda activity window",
                        "detail": (
                            f"{activity.total_invocations:.0f} invocations across {activity.invocation_datapoints} datapoints; "
                            + (
                                "no datapoints returned."
                                if activity.no_datapoints
                                else "latest nonzero bucket at "
                                + (
                                    activity.latest_nonzero_invocations_at.isoformat()
                                    if activity.latest_nonzero_invocations_at
                                    else "unknown"
                                )
                                + "."
                            )
                        ),
                        "window_start": activity.window_start.isoformat(),
                        "window_end": activity.window_end.isoformat(),
                        "period_seconds": activity.period_seconds,
                        "total_invocations": activity.total_invocations,
                        "total_errors": activity.total_errors,
                        "total_throttles": activity.total_throttles,
                        "latest_nonzero_invocations_at": _iso(activity.latest_nonzero_invocations_at),
                        "latest_nonzero_invocation_sum": activity.latest_nonzero_invocation_sum,
                        "invocation_datapoints": activity.invocation_datapoints,
                        "no_datapoints": activity.no_datapoints,
                    },
                    account_id=resource.account_id,
                    region=resource.region,
                    match_confidence=ConfidenceLabel.MEDIUM,
                    limitations=activity.limitations
                    + ["Metric buckets are aggregate intervals, not exact invocation timestamps."],
                    fixture=fixture,
                )
            )
            if activity_evidence:
                activity_node = _node_id(
                    "metric",
                    f"{resource.identity}:{activity.window_start.isoformat()}:{activity.window_end.isoformat()}",
                )
                add_node(
                    GraphNode(
                        node_id=activity_node,
                        node_type="cloudwatch_activity",
                        label="Lambda metric activity",
                        source_evidence_id=activity_evidence.evidence_id,
                        attributes={"no_datapoints": activity.no_datapoints},
                        fixture=fixture,
                    )
                )
                add_edge(
                    activity_node,
                    resource_node,
                    "METRIC_OBSERVED_FOR_RESOURCE",
                    "metrics observed for function",
                    activity_evidence,
                    observed_at=activity.window_end,
                )

        omni = omni_result.data if isinstance(omni_result.data, OmniContext) else None
        if omni is not None and omni.configured:
            omni_evidence = add_evidence(
                factory.create(
                    source=SourceType.CLOUDWATCH_OMNI,
                    source_label="CloudWatch Omni link",
                    observed_at=_now(),
                    resource_identity=resource.identity,
                    match_type=MatchType.MANUAL_ATTACHMENT,
                    record_id=omni.url or "omni",
                    facts={
                        "title": "CloudWatch Omni handoff link",
                        "detail": f"Optional observability context link for {omni.space or 'the configured space'}.",
                        "url": omni.url,
                        "space": omni.space,
                    },
                    account_id=resource.account_id,
                    region=resource.region,
                    match_confidence=ConfidenceLabel.LOW,
                    source_url=omni.url,
                    limitations=omni.limitations
                    + ["GroundTruth stores a link only; no Omni API data is queried or asserted."],
                    fixture=fixture,
                )
            )
            if omni_evidence:
                omni_node = _node_id("omni", omni.url or "omni")
                add_node(
                    GraphNode(
                        node_id=omni_node,
                        node_type="observability_link",
                        label=omni.label,
                        source_evidence_id=omni_evidence.evidence_id,
                        attributes={"space": omni.space},
                        fixture=fixture,
                    )
                )
                add_edge(
                    resource_node,
                    omni_node,
                    "DEPENDS_ON",
                    "optional observability link",
                    omni_evidence,
                    match_type=MatchType.MANUAL_ATTACHMENT,
                    confidence=ConfidenceLabel.LOW,
                    inferred=True,
                )

        dependencies = self._aws_dependencies(
            resource,
            aws_result,
            factory,
            add_evidence,
            add_node,
            add_edge,
            resource_node,
            fixture,
        )

        status, confidence, status_reason, confidence_rule, confidence_reason = self._decide(
            resource,
            aws_result,
            scalr_result,
            current_owners,
            historical_managers,
            candidate_evidence_ids,
            git_candidate,
            git_exact_evidence,
            identity_conflict,
            state_backup_exact,
        )
        recommendation = self._recommend(
            status,
            current_owners,
            historical_managers,
            candidate_evidence_ids,
            scalr_result,
            cloudtrail_result,
            activity,
            aws_result,
        )
        coverage = self._coverage(
            resource,
            aws_result,
            scalr_result,
            git_result,
            cloudtrail_result,
            cloudwatch_result,
            omni_result,
            dataset,
        )
        if state_backup is not None:
            coverage.append(
                CoverageRecord(
                    source="terraform_state_backup",
                    status=ConnectorStatus.SUCCESS,
                    required=False,
                    queried_at=state_backup.parsed_at,
                    records=len(state_backup.matches),
                    notes=[
                        "Locally parsed user-supplied Terraform state snapshot; raw state was not persisted or sent to the model.",
                        f"Snapshot SHA-256: {state_backup.sha256}.",
                        *state_backup.limitations,
                    ],
                    fixture=fixture,
                )
            )

        limitations.extend(
            self._limitations(resource, scalr_result, git_lineage, cloudtrail_result, activity, omni, fixture)
        )
        if state_backup is not None:
            limitations.append(
                "A user-supplied Terraform state snapshot is point-in-time evidence and cannot establish current ownership."
            )
        unresolved.extend(
            self._unresolved_questions(
                status,
                resource,
                git_lineage,
                current_owners,
                historical_managers,
                cloudtrail_result,
                activity,
                scalr_result,
            )
        )
        if status == LineageStatus.CURRENT_OWNER_FOUND and historical_managers:
            unresolved.append("Are the historical workspaces still used by a team, or are they retired?")
        if status == LineageStatus.MULTIPLE_ACTIVE_OWNERS:
            unresolved.append("Which active workspace is authoritative for this exact Lambda ARN?")

        return LineageResult(
            investigation_id=investigation_id,
            mode="fixture" if fixture and (mode in {None, "fixture"}) else (mode or "live"),
            fixture=fixture,
            resource=resource,
            status=status,
            confidence=confidence,
            status_reason=status_reason,
            confidence_rule=confidence_rule,
            confidence_reason=confidence_reason,
            current_owners=current_owners,
            historical_managers=historical_managers,
            repository_lineage=git_lineage,
            actors=actors,
            cloudtrail_events=[
                item for item in (cloudtrail_result.data or []) if isinstance(item, CloudTrailEventEvidence)
            ],
            activity=activity,
            dependencies=dependencies,
            evidence=evidence,
            graph=graph,
            coverage=coverage,
            limitations=_dedupe(limitations),
            unresolved_questions=_dedupe(unresolved),
            recommendation=recommendation,
            omni=omni,
            state_backup=state_backup,
            redaction_applied=False,
        )

    def _match_usage(self, resource: CloudResource, usage: ResourceUsageRecord) -> tuple[bool, MatchType | None, str]:
        try:
            return match_external_identity(
                resource,
                external_id=usage.external_id,
                name=usage.name,
                account_id=usage.account_id,
                region=usage.region,
            )
        except (IdentityError, ValueError):
            return False, None, "The Scalr usage identity could not be parsed safely."

    @staticmethod
    def _usage_mentions_resource(resource: CloudResource, usage: ResourceUsageRecord) -> bool:
        values = {usage.name, usage.external_id}
        if usage.external_id and is_lambda_arn(usage.external_id):
            try:
                values.add(parse_lambda_arn(usage.external_id).function_name)
            except IdentityError:
                pass
        return resource.name in values

    @staticmethod
    def _dedupe_owners(owners: list[OwnershipEvidence]) -> list[OwnershipEvidence]:
        result: list[OwnershipEvidence] = []
        seen: set[tuple[str, str]] = set()
        for owner in owners:
            key = (owner.workspace.id, owner.resource_address)
            if key not in seen:
                seen.add(key)
                result.append(owner)
        return result

    def _scalr_actor(
        self,
        run: RunEvidence,
        usage: ResourceUsageRecord,
        evidence: EvidenceRecord,
        fixture: bool,
    ) -> ActorEvidence | None:
        identifier = (run.actor or usage.updated_by_email or "").strip()
        if not identifier:
            return None
        identity_type = "scalr_run_actor"
        if identifier.startswith("user:"):
            identifier = identifier[5:]
        elif identifier.startswith("service:"):
            identifier = identifier[8:]
            identity_type = "scalr_service_actor"
        display = identifier
        if "@" in identifier:
            display = identifier
        return ActorEvidence(
            source=SourceType.SCALR_RUN,
            identity_type=identity_type,
            identifier=identifier,
            display_name=display,
            timestamp=run.created_at or usage.updated_at,
            evidence_id=evidence.evidence_id,
            notes="Scalr run actor; this is not automatically the current owner.",
            fixture=fixture,
        )

    def _git_actor(
        self,
        commit: Any,
        evidence: EvidenceRecord,
        fixture: bool,
        *,
        role: str,
    ) -> ActorEvidence | None:
        if role == "author":
            name, email = commit.author_name, commit.author_email
        else:
            name, email = commit.committer_name, commit.committer_email
        identifier = (email or name or "").strip()
        if not identifier:
            return None
        return ActorEvidence(
            source=SourceType.GIT_COMMIT,
            identity_type=f"git_{role}",
            identifier=identifier,
            display_name=name or identifier,
            timestamp=commit.committed_at,
            evidence_id=evidence.evidence_id,
            notes=f"Git {role}; this is not automatically the current owner.",
            fixture=fixture,
        )

    def _cloudtrail_actor(
        self,
        event: CloudTrailEventEvidence,
        evidence: EvidenceRecord,
        fixture: bool,
    ) -> ActorEvidence | None:
        identifier = event.principal_arn or event.source_identity or event.principal_id
        if not identifier:
            return None
        display = event.source_identity or event.principal_arn.rsplit("/", 1)[-1] if event.principal_arn else None
        return ActorEvidence(
            source=SourceType.CLOUDTRAIL,
            identity_type=event.principal_type.value if isinstance(event.principal_type, PrincipalType) else "unknown",
            identifier=identifier,
            display_name=display,
            timestamp=event.event_time,
            evidence_id=evidence.evidence_id,
            notes="CloudTrail principal for a management event; this is not automatically the current owner.",
            fixture=fixture,
        )

    def _aws_dependencies(
        self,
        resource: CloudResource,
        aws_result: ConnectorResult,
        factory: EvidenceFactory,
        add_evidence: Any,
        add_node: Any,
        add_edge: Any,
        resource_node: str,
        fixture: bool,
    ) -> list[DependencyEvidence]:
        payload = _safe_dict(aws_result.data)
        dependencies: list[DependencyEvidence] = []

        def add(
            *,
            kind: str,
            name: str,
            identifier: str,
            relationship: str,
            arn: str | None,
            attributes: dict[str, Any],
            observed_at: datetime,
        ) -> None:
            evidence = add_evidence(
                factory.create(
                    source=SourceType.AWS_LAMBDA,
                    source_label="AWS Lambda dependency",
                    observed_at=observed_at,
                    resource_identity=resource.identity,
                    match_type=MatchType.EXACT_ARN if arn else MatchType.INFERRED_DEPENDENCY,
                    record_id=f"{kind}:{identifier}",
                    facts={
                        "title": f"Lambda dependency: {name}",
                        "detail": f"{kind} related to {resource.name}; relationship {relationship}.",
                        "kind": kind,
                        "name": name,
                        "identifier": identifier,
                        "arn": arn,
                        "relationship": relationship,
                        "attributes": attributes,
                    },
                    account_id=resource.account_id,
                    region=resource.region,
                    match_confidence=ConfidenceLabel.HIGH if arn else ConfidenceLabel.MEDIUM,
                    limitations=[
                        "Dependency context comes from read-only AWS configuration; it does not establish ownership."
                    ],
                    fixture=fixture,
                )
            )
            if evidence is None:
                return
            dependency = DependencyEvidence(
                kind=kind,
                name=name,
                identifier=identifier,
                arn=arn,
                relationship=relationship,
                observed_at=observed_at,
                match_type=evidence.match_type,
                evidence_id=evidence.evidence_id,
                attributes=attributes,
                fixture=fixture,
            )
            dependencies.append(dependency)
            node = _node_id("dependency", f"{kind}:{identifier}")
            add_node(
                GraphNode(
                    node_id=node,
                    node_type=f"dependency_{kind}",
                    label=name,
                    source_evidence_id=evidence.evidence_id,
                    attributes={"relationship": relationship, "arn": arn},
                    fixture=fixture,
                )
            )
            add_edge(
                resource_node,
                node,
                "DEPENDS_ON",
                relationship,
                evidence,
                match_type=evidence.match_type,
                confidence=evidence.match_confidence,
                inferred=not bool(arn),
            )

        role_arn = resource.safe_attributes.get("role")
        role_info = _safe_dict(payload.get("role"))
        if role_info.get("Arn") or role_arn:
            arn = role_info.get("Arn") or role_arn
            name = role_info.get("RoleName") or str(arn).rsplit("/", 1)[-1]
            add(
                kind="iam_role",
                name=str(name),
                identifier=str(arn),
                relationship="execution_role",
                arn=str(arn),
                attributes={
                    "role_name": role_info.get("RoleName"),
                    "path": role_info.get("Path"),
                    "create_date": _iso(role_info.get("CreateDate"))
                    if isinstance(role_info.get("CreateDate"), datetime)
                    else role_info.get("CreateDate"),
                },
                observed_at=resource.observed_at,
            )

        mappings = payload.get("event_source_mappings") or []
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            identifier = mapping.get("UUID") or mapping.get("EventSourceMappingArn") or mapping.get("EventSourceArn")
            if not identifier:
                continue
            add(
                kind="event_source_mapping",
                name=mapping.get("EventSourceArn") or str(identifier),
                identifier=str(identifier),
                relationship="event_source_mapping",
                arn=mapping.get("EventSourceMappingArn"),
                attributes={
                    "state": mapping.get("State"),
                    "batch_size": mapping.get("BatchSize"),
                    "event_source_arn": mapping.get("EventSourceArn"),
                    "function_arn": mapping.get("FunctionArn"),
                },
                observed_at=_now(),
            )

        aliases = payload.get("aliases") or []
        for alias in aliases:
            if not isinstance(alias, dict):
                continue
            name = alias.get("Name")
            arn = alias.get("AliasArn")
            if not name:
                continue
            add(
                kind="alias",
                name=str(name),
                identifier=str(arn or name),
                relationship="alias",
                arn=arn,
                attributes={
                    "function_version": alias.get("FunctionVersion"),
                    "description_present": bool(alias.get("Description")),
                },
                observed_at=_now(),
            )

        url_config = _safe_dict(payload.get("function_url"))
        if url_config.get("FunctionUrl"):
            add(
                kind="function_url",
                name="Function URL",
                identifier=str(url_config.get("FunctionUrl")),
                relationship="url_invocation_endpoint",
                arn=None,
                attributes={"auth_type": url_config.get("AuthType"), "cors_configured": bool(url_config.get("Cors"))},
                observed_at=_now(),
            )

        invoke_config = _safe_dict(payload.get("event_invoke_config"))
        destination_config = _safe_dict(invoke_config.get("DestinationConfig"))
        if destination_config:
            destinations = []
            for key in ("OnSuccess", "OnFailure"):
                destination = _safe_dict(destination_config.get(key))
                if destination.get("Destination"):
                    destinations.append({"event": key, "destination": destination.get("Destination")})
            if destinations:
                add(
                    kind="async_destination",
                    name="Async invocation destination",
                    identifier="|".join(item["destination"] for item in destinations),
                    relationship="async_invocation_destination",
                    arn=None,
                    attributes={
                        "destinations": destinations,
                        "maximum_retry_attempts": invoke_config.get("MaximumRetryAttempts"),
                        "maximum_event_age_in_seconds": invoke_config.get("MaximumEventAgeInSeconds"),
                    },
                    observed_at=_now(),
                )

        return dependencies

    def _decide(
        self,
        resource: CloudResource,
        aws_result: ConnectorResult,
        scalr_result: ConnectorResult,
        current_owners: list[OwnershipEvidence],
        historical_managers: list[OwnershipEvidence],
        candidate_evidence_ids: list[str],
        git_candidate: bool,
        git_exact_evidence: bool,
        identity_conflict: bool,
        state_backup_exact: bool = False,
    ) -> tuple[LineageStatus, ConfidenceLabel, str, str, str]:
        if not resource.account_id or not resource.region:
            return (
                LineageStatus.IDENTITY_AMBIGUOUS,
                ConfidenceLabel.UNKNOWN,
                "The target Lambda does not have a complete account and region identity.",
                "UNKNOWN: identity context is incomplete.",
                "Multiple identities or missing account/region context prevent safe matching.",
            )
        if _status_failed(aws_result.status):
            return (
                LineageStatus.INSUFFICIENT_ACCESS,
                ConfidenceLabel.UNKNOWN,
                f"The AWS Lambda resource could not be queried safely ({aws_result.status.value}).",
                "UNKNOWN: a required AWS source failed or was not configured.",
                aws_result.error or "AWS Lambda read access is insufficient.",
            )
        if _status_failed(scalr_result.status):
            return (
                LineageStatus.INSUFFICIENT_ACCESS,
                ConfidenceLabel.UNKNOWN,
                f"Scalr resource usage could not be queried ({scalr_result.status.value}).",
                "UNKNOWN: a required Scalr source failed or was not configured.",
                scalr_result.error or "Scalr resource-usage read access is insufficient.",
            )
        if identity_conflict:
            return (
                LineageStatus.IDENTITY_AMBIGUOUS,
                ConfidenceLabel.UNKNOWN,
                "Scalr records contain contradictory account or region values for the same exact identity.",
                "UNKNOWN: contradictory exact IDs prevent safe ownership matching.",
                "The target ARN is exact, but a related Scalr record disagrees on account or region.",
            )
        if scalr_result.status == ConnectorStatus.PARTIAL and not current_owners and not historical_managers:
            return (
                LineageStatus.INSUFFICIENT_ACCESS,
                ConfidenceLabel.UNKNOWN,
                "Scalr coverage was incomplete, so ownership cannot be ruled in or out.",
                "UNKNOWN: required pagination or coverage is incomplete.",
                "Scalr returned partial data; an empty owner list is not evidence of no owner.",
            )
        if len(current_owners) > 1:
            return (
                LineageStatus.MULTIPLE_ACTIVE_OWNERS,
                ConfidenceLabel.HIGH,
                f"{len(current_owners)} active Scalr workspaces claim the same Lambda ARN.",
                "HIGH: two or more active exact state/workspace associations match the resource.",
                "More than one active workspace/state binding references this exact ARN; adoption is unsafe.",
            )
        if len(current_owners) == 1:
            if scalr_result.status == ConnectorStatus.PARTIAL:
                return (
                    LineageStatus.CURRENT_OWNER_FOUND,
                    ConfidenceLabel.MEDIUM,
                    f"One active Scalr workspace ({current_owners[0].workspace.name}) holds the exact ARN, but coverage is partial.",
                    "MEDIUM: exact active association found, but required Scalr coverage is incomplete.",
                    "A second active owner could exist beyond the incomplete pages.",
                )
            return (
                LineageStatus.CURRENT_OWNER_FOUND,
                ConfidenceLabel.HIGH,
                f"Exactly one active Scalr workspace ({current_owners[0].workspace.name}) holds the exact ARN.",
                "HIGH: exact ARN/provider identity plus a direct active state/workspace association.",
                "The active workspace relationship and exact resource identity agree.",
            )
        if historical_managers:
            if scalr_result.status == ConnectorStatus.PARTIAL:
                confidence = ConfidenceLabel.MEDIUM
                confidence_reason = "Historical exact association found, but Scalr coverage is incomplete."
            else:
                confidence = ConfidenceLabel.HIGH
                confidence_reason = (
                    "The exact identity appears in accessible historical state/usage, but not in active records."
                )
            return (
                LineageStatus.HISTORICAL_OWNER_FOUND,
                confidence,
                f"No active state binding was found, but {len(historical_managers)} historical Scalr binding(s) match the exact ARN.",
                "HIGH: exact ARN/provider identity plus a direct historical state/workspace association."
                if confidence == ConfidenceLabel.HIGH
                else "MEDIUM: exact historical association found, but required coverage is incomplete.",
                confidence_reason,
            )
        if state_backup_exact:
            return (
                LineageStatus.CANDIDATE_LINEAGE,
                ConfidenceLabel.MEDIUM,
                "No live Scalr state binding was found, but the user-supplied state snapshot contains the exact ARN.",
                "MEDIUM: exact identity in a user-supplied snapshot without a live state/workspace association.",
                "The uploaded snapshot is point-in-time and unverified; it cannot prove current management by itself.",
            )
        if git_candidate or candidate_evidence_ids:
            if git_exact_evidence:
                return (
                    LineageStatus.CANDIDATE_LINEAGE,
                    ConfidenceLabel.MEDIUM,
                    "No exact Scalr state binding was found; exact Git address evidence exists but the state/workspace chain is incomplete.",
                    "MEDIUM: exact evidence in one strong source without a direct state/workspace association.",
                    "Git context is strong but cannot prove current management by itself.",
                )
            return (
                LineageStatus.CANDIDATE_LINEAGE,
                ConfidenceLabel.LOW,
                "No exact state binding was found; only candidate name/path evidence exists.",
                "LOW: candidate name/tag/path/description similarity only.",
                "The evidence resembles the resource but does not establish an exact identity relationship.",
            )
        return (
            LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES,
            ConfidenceLabel.UNKNOWN,
            "No exact active or historical state binding was found in the sources that were successfully checked.",
            "UNKNOWN: no usable ownership evidence was found; absence is not proof of no owner.",
            "All required sources were readable, but none contained an exact ownership relationship.",
        )

    def _recommend(
        self,
        status: LineageStatus,
        current_owners: list[OwnershipEvidence],
        historical_managers: list[OwnershipEvidence],
        candidate_evidence_ids: list[str],
        scalr_result: ConnectorResult,
        cloudtrail_result: ConnectorResult,
        activity: CloudWatchActivity | None,
        aws_result: ConnectorResult,
    ) -> Recommendation:
        current_ids = _dedupe([item for owner in current_owners for item in owner.evidence_ids])
        historical_ids = _dedupe([item for owner in historical_managers for item in owner.evidence_ids])
        if status == LineageStatus.CURRENT_OWNER_FOUND:
            workspace = current_owners[0].workspace.name
            return Recommendation(
                code=RecommendationCode.INSPECT_CURRENT_WORKSPACE,
                title=f"Inspect workspace {workspace} before changing the Lambda",
                explanation=(
                    f"Start with the active Scalr workspace {workspace} and its exact state address "
                    f"{current_owners[0].resource_address}. Confirm the repository working directory and the team that owns the workspace."
                ),
                blocked_adoption=False,
                evidence_ids=current_ids,
            )
        if status == LineageStatus.HISTORICAL_OWNER_FOUND:
            workspace = historical_managers[0].workspace.name
            return Recommendation(
                code=RecommendationCode.INSPECT_LAST_KNOWN_STATE_AND_RUN,
                title=f"Review the last known state and run in {workspace}",
                explanation=(
                    "The Lambda is not active in the Scalr records checked, but a historical binding exists. "
                    "Review the last known state version and run before treating the resource as unmanaged."
                ),
                blocked_adoption=False,
                evidence_ids=historical_ids,
            )
        if status == LineageStatus.MULTIPLE_ACTIVE_OWNERS:
            return Recommendation(
                code=RecommendationCode.RESOLVE_DUPLICATE_STATE_OWNERSHIP,
                title="Resolve duplicate state ownership before any change",
                explanation=(
                    "Multiple active workspaces claim the same Lambda ARN. Determine which workspace is authoritative, "
                    "then remove the duplicate state ownership through a reviewed change. Do not adopt or modify the resource yet."
                ),
                blocked_adoption=True,
                evidence_ids=current_ids,
            )
        if status == LineageStatus.INSUFFICIENT_ACCESS:
            missing = []
            if _status_failed(scalr_result.status):
                missing.append("Scalr read-only resource usage")
            if _status_failed(aws_result.status):
                missing.append("AWS Lambda read access")
            detail = ", ".join(missing) if missing else "the incomplete source coverage"
            return Recommendation(
                code=RecommendationCode.REQUEST_MISSING_READ_PERMISSION,
                title=f"Request access to {detail}",
                explanation=(
                    "No ownership conclusion is possible until the missing source is readable. "
                    "Ask for read-only access and rerun the investigation; do not infer ownership from the gap."
                ),
                blocked_adoption=False,
                evidence_ids=[],
            )
        if status == LineageStatus.CANDIDATE_LINEAGE:
            return Recommendation(
                code=RecommendationCode.REVIEW_CANDIDATE_MATCH_MANUALLY,
                title="Review candidate evidence manually",
                explanation=(
                    "The evidence is a name, tag, path, or similarly worded Terraform address rather than an exact state binding. "
                    "Verify the account, region, and full Terraform address with the repository owner before using it."
                ),
                blocked_adoption=False,
                evidence_ids=_dedupe(candidate_evidence_ids),
            )
        if status == LineageStatus.IDENTITY_AMBIGUOUS:
            return Recommendation(
                code=RecommendationCode.SUPPLY_EXACT_RESOURCE_ARN,
                title="Supply an exact Lambda ARN and account/region context",
                explanation=(
                    "Confirm the target ARN, account, and region. Do not match by name alone when identities conflict."
                ),
                blocked_adoption=True,
                evidence_ids=[],
            )
        if cloudtrail_result.status in {
            ConnectorStatus.PARTIAL,
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.NOT_CONFIGURED,
        }:
            return Recommendation(
                code=RecommendationCode.CHECK_CLOUDTRAIL_RETENTION_OR_TRAIL,
                title="Check CloudTrail coverage or a longer-retained trail",
                explanation=(
                    "The default CloudTrail event history is limited. Check whether a trail or data lake retains older management events "
                    "before concluding that no actor evidence exists."
                ),
                blocked_adoption=False,
                evidence_ids=[],
            )
        if activity is not None and activity.no_datapoints:
            return Recommendation(
                code=RecommendationCode.CHECK_CLOUDWATCH_ACTIVITY_DATA,
                title="Check CloudWatch activity in the correct region and window",
                explanation=(
                    "CloudWatch returned no datapoints for the Lambda. Confirm the region, metric window, and permissions; "
                    "absence of datapoints is not proof that the function is unused."
                ),
                blocked_adoption=False,
                evidence_ids=[],
            )
        return Recommendation(
            code=RecommendationCode.PREPARE_SEPARATE_ADOPTION_PROPOSAL,
            title="Prepare a separate adoption proposal",
            explanation=(
                "GroundTruth found no exact owner in the checked sources. Treat that as unknown, not unowned. "
                "If adoption is proposed, prepare a separate reviewed plan with the resource owner and do not change infrastructure from this tool."
            ),
            blocked_adoption=False,
            evidence_ids=[],
        )

    def _coverage(
        self,
        resource: CloudResource,
        aws_result: ConnectorResult,
        scalr_result: ConnectorResult,
        git_result: ConnectorResult | None,
        cloudtrail_result: ConnectorResult,
        cloudwatch_result: ConnectorResult,
        omni_result: ConnectorResult,
        dataset: ScalrDataset,
    ) -> list[CoverageRecord]:
        records = [
            self._coverage_record(
                aws_result,
                required=True,
                account_id=resource.account_id,
                region=resource.region,
                notes=["Read-only Lambda configuration and tags; environment values are excluded."],
            ),
            self._coverage_record(
                scalr_result,
                required=True,
                account_id=resource.account_id,
                region=resource.region,
                notes=[
                    f"Scalr filter: {dataset.queried_filter}"
                    if dataset.queried_filter
                    else "Scalr filter configured by environment.",
                    "Apply runs are retained for three years, plan-only runs for 30 days, and the last 100 state files per workspace. Missing history is not proof that an event did not occur.",
                ],
            ),
        ]
        if git_result is not None:
            records.append(
                self._coverage_record(
                    git_result,
                    required=False,
                    account_id=resource.account_id,
                    region=resource.region,
                    notes=["Repository evidence is context; it does not prove current state ownership."],
                )
            )
        else:
            records.append(
                CoverageRecord(
                    source="git",
                    status=ConnectorStatus.NOT_CONFIGURED,
                    required=False,
                    account_id=resource.account_id,
                    region=resource.region,
                    notes=["No repository lineage was supplied."],
                    fixture=resource.fixture,
                )
            )
        records.append(
            self._coverage_record(
                cloudtrail_result,
                required=False,
                account_id=resource.account_id,
                region=resource.region,
                notes=[
                    "LookupEvents covers management events only and normally the last 90 days; it is not invocation history."
                ],
            )
        )
        records.append(
            self._coverage_record(
                cloudwatch_result,
                required=False,
                account_id=resource.account_id,
                region=resource.region,
                notes=["Metric datapoints are aggregate intervals; absence of datapoints is not proof of inactivity."],
            )
        )
        records.append(
            self._coverage_record(
                omni_result,
                required=False,
                account_id=resource.account_id,
                region=resource.region,
                notes=["Optional link/context only; no undocumented Omni API is called."],
            )
        )
        return records

    @staticmethod
    def _coverage_record(
        result: ConnectorResult,
        *,
        required: bool,
        account_id: str | None = None,
        region: str | None = None,
        notes: list[str] | None = None,
    ) -> CoverageRecord:
        return CoverageRecord(
            source=result.source,
            status=result.status,
            required=required,
            queried_at=result.queried_at,
            account_id=account_id,
            region=region,
            pages=result.pages,
            records=result.records,
            error=result.error,
            notes=_dedupe(list(notes or []) + list(result.warnings)),
            fixture=result.fixture,
        )

    def _limitations(
        self,
        resource: CloudResource,
        scalr_result: ConnectorResult,
        git_lineage: RepositoryLineage | None,
        cloudtrail_result: ConnectorResult,
        activity: CloudWatchActivity | None,
        omni: OmniContext | None,
        fixture: bool,
    ) -> list[str]:
        limitations = [
            "GroundTruth is read-only: it does not apply, import, delete, or invoke anything.",
            "A missing record is not proof that no owner or event exists.",
        ]
        if fixture:
            limitations.append("Simulated environment: records mirror live payload formats for the Northgate tenant; connect live credentials to investigate a real account.")
        limitations.extend(scalr_result.warnings)
        if git_lineage:
            limitations.extend(git_lineage.limitations)
            if not git_lineage.commit_verified:
                limitations.append("Repository commit verification is incomplete for at least one evidence item.")
        if cloudtrail_result.status in {
            ConnectorStatus.PARTIAL,
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.NOT_CONFIGURED,
        }:
            limitations.append(
                "CloudTrail coverage is incomplete; management-event history may not include the relevant change."
            )
        if activity:
            limitations.extend(activity.limitations)
        if omni and omni.limitations:
            limitations.extend(omni.limitations)
        return limitations

    def _unresolved_questions(
        self,
        status: LineageStatus,
        resource: CloudResource,
        git_lineage: RepositoryLineage | None,
        current_owners: list[OwnershipEvidence],
        historical_managers: list[OwnershipEvidence],
        cloudtrail_result: ConnectorResult,
        activity: CloudWatchActivity | None,
        scalr_result: ConnectorResult,
    ) -> list[str]:
        questions: list[str] = []
        if not git_lineage:
            questions.append("Which repository and working directory contain this Terraform resource?")
        if current_owners and not current_owners[0].run:
            questions.append("Which run last applied the active workspace?")
        if status == LineageStatus.HISTORICAL_OWNER_FOUND:
            questions.append("Why is the historical binding no longer active in Scalr?")
        if status == LineageStatus.CANDIDATE_LINEAGE:
            questions.append("Does the candidate Terraform address refer to this exact account and region?")
        if status == LineageStatus.INSUFFICIENT_ACCESS:
            questions.append("Which read-only permission or configuration is missing for the failed source?")
        if scalr_result.status == ConnectorStatus.PARTIAL:
            questions.append("Are there additional Scalr resource-usage records beyond the pagination cap?")
        if cloudtrail_result.status in {
            ConnectorStatus.PARTIAL,
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.NOT_CONFIGURED,
        }:
            questions.append("Who changed this resource within the CloudTrail retention window?")
        if activity is not None and activity.no_datapoints:
            questions.append("Is the function currently invoked? CloudWatch returned no datapoints.")
        if status == LineageStatus.UNATTRIBUTED_IN_CHECKED_SOURCES:
            questions.append("Could an unqueried source, older history, or an out-of-region workspace hold ownership?")
        if resource.tags.get("Owner"):
            questions.append("Does the Owner tag reflect a team, a person, or only a cost-allocation label?")
        return questions
