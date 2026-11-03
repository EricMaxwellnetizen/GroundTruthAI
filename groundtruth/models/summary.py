from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.connector import utc_now
from groundtruth.models.enums import ConfidenceLabel, LineageStatus, RecommendationCode


class InvestigationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    investigation_id: str
    created_at: datetime = Field(default_factory=utc_now)
    mode: Literal["fixture", "live"] = "fixture"
    fixture: bool = False
    account_id: str | None = None
    region: str | None = None
    resource_arn: str | None = None
    resource_name: str
    status: LineageStatus
    confidence: ConfidenceLabel
    recommendation: RecommendationCode
    label: str = ""
