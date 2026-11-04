from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.connector import utc_now
from groundtruth.models.lineage import LineageResult
from groundtruth.models.resource import CloudResource
from groundtruth.models.state_backup import StateBackupEvidence
from groundtruth.utils.hashing import sha256_hex


class BundleIntegrity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["sha256"] = "sha256"
    checksum: str
    computed_at: datetime = Field(default_factory=utc_now)
    redaction_applied: bool = False


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_type: Literal["groundtruth.evidence_bundle"] = "groundtruth.evidence_bundle"
    schema_version: str = "1.0.0"
    exported_at: datetime = Field(default_factory=utc_now)
    investigation_id: str
    mode: Literal["fixture", "live"]
    fixture: bool
    resource: CloudResource
    status: str
    confidence: str
    confidence_rule: str
    status_reason: str
    confidence_reason: str
    current_owners: list[Any]
    historical_managers: list[Any]
    repository_lineage: Any | None
    actors: list[Any]
    cloudtrail_events: list[Any]
    activity: Any | None
    dependencies: list[Any]
    evidence: list[Any]
    graph: Any
    coverage: list[Any]
    limitations: list[str]
    unresolved_questions: list[str]
    recommendation: Any
    ai_explanation: Any | None
    omni: Any | None
    state_backup: StateBackupEvidence | None = None
    redaction_applied: bool
    integrity: BundleIntegrity | None = None

    @classmethod
    def from_lineage(
        cls,
        result: LineageResult,
        *,
        redaction_applied: bool = False,
        exported_at: datetime | None = None,
    ) -> "EvidenceBundle":
        bundle = cls(
            exported_at=exported_at or utc_now(),
            investigation_id=result.investigation_id,
            mode=result.mode,
            fixture=result.fixture,
            resource=result.resource,
            status=result.status.value,
            confidence=result.confidence.value,
            confidence_rule=result.confidence_rule,
            status_reason=result.status_reason,
            confidence_reason=result.confidence_reason,
            current_owners=[item.model_dump(mode="json") for item in result.current_owners],
            historical_managers=[item.model_dump(mode="json") for item in result.historical_managers],
            repository_lineage=result.repository_lineage.model_dump(mode="json") if result.repository_lineage else None,
            actors=[item.model_dump(mode="json") for item in result.actors],
            cloudtrail_events=[item.model_dump(mode="json") for item in result.cloudtrail_events],
            activity=result.activity.model_dump(mode="json") if result.activity else None,
            dependencies=[item.model_dump(mode="json") for item in result.dependencies],
            evidence=[item.model_dump(mode="json") for item in result.evidence],
            graph=result.graph.model_dump(mode="json"),
            coverage=[item.model_dump(mode="json") for item in result.coverage],
            limitations=result.limitations,
            unresolved_questions=result.unresolved_questions,
            recommendation=result.recommendation.model_dump(mode="json"),
            ai_explanation=result.ai_explanation.model_dump(mode="json") if result.ai_explanation else None,
            omni=result.omni.model_dump(mode="json") if result.omni else None,
            state_backup=result.state_backup.model_dump(mode="json") if result.state_backup else None,
            redaction_applied=redaction_applied,
        )
        bundle.attach_checksum()
        return bundle

    def payload_without_integrity(self) -> dict[str, Any]:
        data = self.model_dump(mode="json", exclude={"integrity"})
        return data

    def attach_checksum(self) -> str:
        checksum = sha256_hex(self.payload_without_integrity())
        self.integrity = BundleIntegrity(checksum=checksum, redaction_applied=self.redaction_applied)
        return checksum

    def verify_checksum(self) -> bool:
        if not self.integrity:
            return False
        return sha256_hex(self.payload_without_integrity()) == self.integrity.checksum
