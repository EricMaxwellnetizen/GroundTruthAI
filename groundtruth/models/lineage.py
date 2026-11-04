from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.ai import AIExplanation
from groundtruth.models.connector import utc_now
from groundtruth.models.enums import (
    ConfidenceLabel,
    ConnectorStatus,
    LineageStatus,
    MatchType,
    PrincipalType,
    RecommendationCode,
    SourceType,
)
from groundtruth.models.evidence import EvidenceRecord, TimelineEntry
from groundtruth.models.graph import EvidenceGraph
from groundtruth.models.resource import CloudResource
from groundtruth.models.state_backup import StateBackupEvidence


class WorkspaceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    environment: str | None = None
    active: bool | None = None
    vcs_repo_identifier: str | None = None
    working_directory: str | None = None
    branch: str | None = None
    source_url: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False


class RunEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    workspace_id: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    source: str | None = None
    actor: str | None = None
    vcs_revision: str | None = None
    source_url: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False


class StateVersionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: datetime | None = None
    source_url: str | None = None
    fixture: bool = False


class ResourceUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    external_id: str
    address: str
    name: str
    is_active: bool
    is_duplicate: bool = False
    updated_at: datetime | None = None
    updated_by_email: str | None = None
    workspace: WorkspaceRef | None = None
    run: RunEvidence | None = None
    state_version: StateVersionEvidence | None = None
    environment: str | None = None
    account_id: str | None = None
    region: str | None = None
    source_url: str | None = None
    limitations: list[str] = Field(default_factory=list)
    fixture: bool = False


class ScalrDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_usages: list[ResourceUsageRecord] = Field(default_factory=list)
    workspaces: list[WorkspaceRef] = Field(default_factory=list)
    runs: list[RunEvidence] = Field(default_factory=list)
    queried_filter: str | None = None
    retention_note: str = (
        "Scalr public documentation checked 2026-11-02: apply runs are retained for three years, "
        "plan-only runs for 30 days, and the last 100 state files per workspace, subject to documented exceptions. "
        "A missing historical record is not proof that an event did not occur."
    )


class OwnershipEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["current", "historical"]
    workspace: WorkspaceRef
    resource_address: str
    resource_usage_id: str
    state_version: StateVersionEvidence | None = None
    run: RunEvidence | None = None
    last_seen_at: datetime | None = None
    match_type: MatchType
    evidence_ids: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    fixture: bool = False


class GitFileEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    matched_string: str
    match_type: MatchType
    snippet: str = ""
    line: int | None = None
    commit_sha: str | None = None
    source_url: str | None = None
    evidence_id: str | None = None
    fixture: bool = False


class GitCommitEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str
    repository_url: str | None = None
    sha: str
    author_name: str | None = None
    author_email: str | None = None
    committed_at: datetime | None = None
    committer_name: str | None = None
    committer_email: str | None = None
    message: str = ""
    files: list[GitFileEvidence] = Field(default_factory=list)
    source_url: str | None = None
    evidence_id: str | None = None
    fixture: bool = False


class RepositoryLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    repository: str
    repository_url: str | None = None
    working_directory: str | None = None
    branch: str | None = None
    vcs_revision: str | None = None
    run_id: str | None = None
    workspace_id: str | None = None
    commit_verified: bool = False
    commit: GitCommitEvidence | None = None
    file_matches: list[GitFileEvidence] = Field(default_factory=list)
    history_matches: list[GitFileEvidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    candidate_only: bool = False
    limitations: list[str] = Field(default_factory=list)


class CloudTrailEventEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_time: datetime
    queried_at: datetime = Field(default_factory=utc_now)
    event_source: str
    event_name: str
    region: str | None = None
    account_id: str | None = None
    principal_type: PrincipalType = PrincipalType.UNKNOWN
    principal_arn: str | None = None
    principal_id: str | None = None
    session_issuer_arn: str | None = None
    source_identity: str | None = None
    user_agent: str | None = None
    resource_arns: list[str] = Field(default_factory=list)
    resource_names: list[str] = Field(default_factory=list)
    match_type: MatchType = MatchType.EXACT_EVENT_RESOURCE
    evidence_id: str | None = None
    fixture: bool = False
    limitations: list[str] = Field(default_factory=list)


class CloudWatchActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_start: datetime
    window_end: datetime
    period_seconds: int
    queried_at: datetime = Field(default_factory=utc_now)
    metric_namespace: str = "AWS/Lambda"
    dimensions: dict[str, str] = Field(default_factory=dict)
    latest_nonzero_invocations_at: datetime | None = None
    latest_nonzero_invocation_sum: float | None = None
    total_invocations: float = 0.0
    total_errors: float = 0.0
    total_throttles: float = 0.0
    average_duration_ms: float | None = None
    maximum_duration_ms: float | None = None
    invocation_datapoints: int = 0
    error_datapoints: int = 0
    throttle_datapoints: int = 0
    no_datapoints: bool = True
    evidence_id: str | None = None
    fixture: bool = False
    limitations: list[str] = Field(default_factory=list)


class CoverageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    status: ConnectorStatus
    required: bool = False
    queried_at: datetime = Field(default_factory=utc_now)
    account_id: str | None = None
    region: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    pages: int = 0
    records: int = 0
    error: str | None = None
    notes: list[str] = Field(default_factory=list)
    fixture: bool = False

    @property
    def is_gap(self) -> bool:
        return self.status in {
            ConnectorStatus.PARTIAL,
            ConnectorStatus.NOT_CONFIGURED,
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.RATE_LIMITED,
            ConnectorStatus.FAILED,
            ConnectorStatus.NOT_FOUND,
        }


class ActorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: SourceType
    identity_type: str
    identifier: str
    display_name: str | None = None
    timestamp: datetime | None = None
    evidence_id: str
    notes: str = ""
    fixture: bool = False


class DependencyEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    identifier: str
    arn: str | None = None
    relationship: str
    direction: str = "outbound"
    observed_at: datetime = Field(default_factory=utc_now)
    match_type: MatchType = MatchType.INFERRED_DEPENDENCY
    evidence_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False


class Recommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: RecommendationCode
    title: str
    explanation: str
    blocked_adoption: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class OmniContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool = False
    url: str | None = None
    space: str | None = None
    label: str = "CloudWatch Omni"
    limitations: list[str] = Field(default_factory=list)


class LineageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0.0"
    investigation_id: str
    created_at: datetime = Field(default_factory=utc_now)
    mode: Literal["fixture", "live"] = "fixture"
    fixture: bool = False
    resource: CloudResource
    status: LineageStatus
    confidence: ConfidenceLabel
    status_reason: str
    confidence_rule: str
    confidence_reason: str
    current_owners: list[OwnershipEvidence] = Field(default_factory=list)
    historical_managers: list[OwnershipEvidence] = Field(default_factory=list)
    repository_lineage: RepositoryLineage | None = None
    actors: list[ActorEvidence] = Field(default_factory=list)
    cloudtrail_events: list[CloudTrailEventEvidence] = Field(default_factory=list)
    activity: CloudWatchActivity | None = None
    dependencies: list[DependencyEvidence] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    graph: EvidenceGraph = Field(default_factory=EvidenceGraph)
    coverage: list[CoverageRecord] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    recommendation: Recommendation
    ai_explanation: AIExplanation | None = None
    omni: OmniContext | None = None
    state_backup: StateBackupEvidence | None = None
    redaction_applied: bool = False

    @property
    def evidence_ids(self) -> list[str]:
        return [item.evidence_id for item in self.evidence]

    @property
    def timeline(self) -> list[TimelineEntry]:
        entries: list[TimelineEntry] = []
        for item in self.evidence:
            title = item.facts.get("title") or item.source_label
            detail = item.facts.get("detail") or ""
            entries.append(
                TimelineEntry(
                    evidence_id=item.evidence_id,
                    source=item.source,
                    source_label=item.source_label,
                    observed_at=item.observed_at,
                    queried_at=item.queried_at,
                    title=str(title),
                    detail=str(detail),
                    match_type=item.match_type,
                    match_confidence=item.match_confidence,
                    source_record_id=item.source_record_id,
                    source_url=item.source_url,
                    fixture=item.fixture,
                )
            )
        return sorted(entries, key=lambda entry: (entry.observed_at, entry.evidence_id))

    def evidence_by_id(self, evidence_id: str) -> EvidenceRecord | None:
        return next((item for item in self.evidence if item.evidence_id == evidence_id), None)

    def coverage_gaps(self) -> list[CoverageRecord]:
        return [record for record in self.coverage if record.is_gap]
