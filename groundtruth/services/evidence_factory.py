from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from groundtruth.models.enums import ConfidenceLabel, MatchType, Sensitivity, SourceType
from groundtruth.models.evidence import EvidenceRecord
from groundtruth.utils.hashing import sha256_hex

SOURCE_SHORT = {
    SourceType.AWS_LAMBDA: "aws",
    SourceType.SCALR_RESOURCE_USAGE: "scalr",
    SourceType.SCALR_STATE: "state",
    SourceType.SCALR_WORKSPACE: "ws",
    SourceType.SCALR_RUN: "run",
    SourceType.GIT_COMMIT: "gitc",
    SourceType.GIT_FILE: "gitf",
    SourceType.CLOUDTRAIL: "ct",
    SourceType.CLOUDWATCH_METRIC: "cw",
    SourceType.CLOUDWATCH_OMNI: "omni",
    SourceType.FIXTURE: "fix",
    SourceType.MANUAL: "man",
}


class EvidenceFactory:
    def __init__(self, investigation_id: str, *, queried_at: datetime | None = None) -> None:
        self.investigation_id = investigation_id
        self.queried_at = queried_at or datetime.now(timezone.utc)
        self._seen: dict[str, str] = {}

    def evidence_id(self, source: SourceType, record_id: str, resource_identity: str) -> str:
        seed = f"{self.investigation_id}|{source.value}|{record_id}|{resource_identity}"
        digest = sha256_hex(seed)[:12]
        candidate = f"ev_{SOURCE_SHORT[source]}_{digest}"
        if candidate in self._seen and self._seen[candidate] != seed:
            candidate = f"ev_{SOURCE_SHORT[source]}_{sha256_hex(seed)[:18]}"
        self._seen[candidate] = seed
        return candidate

    def create(
        self,
        *,
        source: SourceType,
        source_label: str,
        observed_at: datetime,
        resource_identity: str,
        match_type: MatchType,
        record_id: str,
        facts: dict[str, Any] | None = None,
        account_id: str | None = None,
        region: str | None = None,
        match_confidence: ConfidenceLabel = ConfidenceLabel.UNKNOWN,
        source_url: str | None = None,
        limitations: list[str] | None = None,
        sensitivity: Sensitivity = Sensitivity.INTERNAL,
        fixture: bool = False,
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=self.evidence_id(source, record_id, resource_identity),
            source=source,
            source_label=source_label,
            observed_at=observed_at,
            queried_at=self.queried_at,
            resource_identity=resource_identity,
            account_id=account_id,
            region=region,
            match_type=match_type,
            match_confidence=match_confidence,
            source_record_id=record_id,
            source_url=source_url,
            facts=facts or {},
            limitations=limitations or [],
            sensitivity=sensitivity,
            fixture=fixture,
        )
