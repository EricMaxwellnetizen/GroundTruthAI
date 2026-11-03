from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from groundtruth.models.connector import utc_now
from groundtruth.models.enums import ConfidenceLabel, MatchType, Sensitivity, SourceType


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: SourceType
    source_label: str
    observed_at: datetime
    queried_at: datetime = Field(default_factory=utc_now)
    resource_identity: str
    account_id: str | None = None
    region: str | None = None
    match_type: MatchType
    match_confidence: ConfidenceLabel = ConfidenceLabel.UNKNOWN
    source_record_id: str | None = None
    source_url: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    fixture: bool = False

    @field_validator("observed_at", "queried_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=utc_now().tzinfo)
        return value


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: SourceType
    source_label: str
    observed_at: datetime
    queried_at: datetime
    title: str
    detail: str
    match_type: MatchType
    match_confidence: ConfidenceLabel
    source_record_id: str | None = None
    source_url: str | None = None
    fixture: bool = False
