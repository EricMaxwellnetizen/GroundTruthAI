from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    evidence_ids: list[str] = Field(min_length=1)


class AINextStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class AIExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_by: Literal["muse-spark", "deterministic_fallback"] = "muse-spark"
    model: str | None = None
    summary: str
    established_facts: list[AIFact] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    next_steps: list[AINextStep] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tool_calls_used: int = 0

    @field_validator("summary")
    @classmethod
    def _summary_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("summary must not be empty")
        return value
