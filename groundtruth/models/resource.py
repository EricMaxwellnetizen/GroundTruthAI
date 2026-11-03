from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from groundtruth.models.connector import utc_now


class CloudResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["aws"] = "aws"
    service: str = "lambda"
    resource_type: str = "aws_lambda_function"
    account_id: str
    region: str
    name: str
    arn: str | None = None
    provider_id: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    status: str | None = None
    last_modified_at: datetime | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    safe_attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False

    @field_validator("observed_at", "last_modified_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=utc_now().tzinfo)
        return value

    @property
    def identity(self) -> str:
        return self.arn or f"{self.account_id}:{self.region}:{self.name}"


class LambdaDependency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    identifier: str
    arn: str | None = None
    relationship: str
    direction: str = "outbound"
    observed_at: datetime = Field(default_factory=utc_now)
    match_type: str = "inferred_dependency"
    attributes: dict[str, Any] = Field(default_factory=dict)
    fixture: bool = False
