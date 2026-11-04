from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from groundtruth.models.connector import utc_now
from groundtruth.models.enums import ConfidenceLabel, MatchType


class StateBackupMatch(BaseModel):
    """One Lambda resource extracted from a user-supplied Terraform state file.

    Only identity and non-secret configuration fields are retained. The raw state
    document, module variables, outputs, environment blocks and provider
    credentials are never stored on this model.
    """

    model_config = ConfigDict(extra="forbid")

    address: str
    mode: str = "managed"
    resource_type: str = "aws_lambda_function"
    name: str
    module: str | None = None
    provider: str | None = None
    arn: str | None = None
    function_name: str | None = None
    role_arn: str | None = None
    handler: str | None = None
    runtime: str | None = None
    memory_size: int | None = None
    timeout: int | None = None
    architectures: list[str] = Field(default_factory=list)
    last_modified: str | None = None
    match_type: MatchType = MatchType.CANDIDATE_NAME
    match_confidence: ConfidenceLabel = ConfidenceLabel.LOW
    match_reason: str = ""
    origin: Literal["user_supplied"] = "user_supplied"


class StateBackupEvidence(BaseModel):
    """An in-memory summary of a locally parsed Terraform state backup.

    ``sha256`` is the digest of the original uploaded bytes. The raw bytes are
    discarded by the caller after parsing and are never persisted by GroundTruth.
    """

    model_config = ConfigDict(extra="forbid")

    filename: str
    sha256: str
    size_bytes: int
    terraform_version: str | None = None
    state_version: int = 4
    serial: int | None = None
    lineage: str | None = None
    resource_count: int = 0
    matches: list[StateBackupMatch] = Field(default_factory=list)
    origin: Literal["user_supplied"] = "user_supplied"
    parsed_at: datetime = Field(default_factory=utc_now)
    limitations: list[str] = Field(default_factory=list)
