from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from groundtruth.models.report import EvidenceBundle


@dataclass(frozen=True)
class StoredInvestigation:
    investigation_id: str
    created_at: datetime
    mode: str
    fixture: bool
    resource_name: str
    resource_arn: str | None
    status: str
    confidence: str
    recommendation_code: str
    checksum: str | None
    report: dict[str, Any]


@runtime_checkable
class InvestigationRepository(Protocol):
    def initialize(self) -> None: ...

    def save(self, bundle: EvidenceBundle) -> StoredInvestigation: ...

    def get(self, investigation_id: str) -> StoredInvestigation | None: ...

    def list(self, limit: int = 50) -> list[StoredInvestigation]: ...

    def delete(self, investigation_id: str) -> bool: ...

    def count(self) -> int: ...
