from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.enums import ConnectorStatus


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ConnectorStatus
    source: str
    queried_at: datetime = Field(default_factory=utc_now)
    data: Any = None
    coverage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    pages: int = 0
    records: int = 0
    fixture: bool = False

    @property
    def succeeded(self) -> bool:
        return self.status in {ConnectorStatus.SUCCESS, ConnectorStatus.PARTIAL, ConnectorStatus.NOT_FOUND}

    @property
    def failed(self) -> bool:
        return self.status in {
            ConnectorStatus.PERMISSION_DENIED,
            ConnectorStatus.RATE_LIMITED,
            ConnectorStatus.FAILED,
            ConnectorStatus.NOT_CONFIGURED,
        }

    def as_coverage(self, *, required: bool = False, notes: list[str] | None = None) -> dict[str, Any]:
        return {
            "source": self.source,
            "status": self.status,
            "required": required,
            "queried_at": self.queried_at,
            "pages": self.pages,
            "records": self.records,
            "error": self.error,
            "notes": notes or self.warnings,
            "fixture": self.fixture,
            **self.coverage,
        }


class ConnectionTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: ConnectorStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    tested_at: datetime = Field(default_factory=utc_now)
    fixture: bool = False
