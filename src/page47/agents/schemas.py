"""Structured outputs expected from each investigation node."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

Direction = Literal["clearer", "less_clear", "neutral"]

_UNAVAILABLE_VALUES = frozenset(
    {
        "n/a",
        "na",
        "unknown",
        "not available",
        "not applicable",
        "could not determine",
    }
)


def _real_value(value: str | None) -> bool:
    return value is not None and value.strip().casefold() not in _UNAVAILABLE_VALUES


class AgentEvidence(BaseModel):
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)
    captured_at: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)


class AgentObservation(BaseModel):
    observation_id: str = Field(min_length=1)
    direction: Direction
    statement: str = Field(min_length=1)
    evidence: list[AgentEvidence] = Field(min_length=1)


class ArchivistReport(BaseModel):
    observations: list[AgentObservation]
    summary: str = Field(min_length=1)


class SubstanceChange(BaseModel):
    observation_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    before: str | None = Field(default=None, min_length=1)
    after: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    unit: str | None = None
    page_number: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    evidence: AgentEvidence

    @model_validator(mode="after")
    def has_document_value(self) -> Self:
        has_before = self.before is not None
        has_after = self.after is not None
        if has_before != has_after:
            raise ValueError("before and after must be supplied together")
        if self.value is None and not (has_before and has_after):
            raise ValueError("A document change needs a value or an explicit change")
        if has_before and has_after:
            before = self.before
            after = self.after
            if before is None or after is None:
                raise ValueError("before and after must be supplied together")
            if before.strip() == after.strip():
                raise ValueError("before and after must identify different recorded values")
        if self.evidence.page_number != self.page_number:
            raise ValueError("The change page must match the evidence page")
        for name, value in (
            ("before", self.before),
            ("after", self.after),
            ("value", self.value),
        ):
            if value is not None and not _real_value(value):
                raise ValueError(f"Substance {name} must be a recorded value, not a placeholder")
        return self


class SubstanceReport(BaseModel):
    changes: list[SubstanceChange]
    no_substantive_change: bool
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def change_status_matches_contents(self) -> Self:
        if bool(self.changes) == self.no_substantive_change:
            raise ValueError(
                "no_substantive_change must be true only when no document changes are listed"
            )
        return self


class ProcessReport(BaseModel):
    observations: list[AgentObservation]
    summary: str = Field(min_length=1)


class RejectedObservation(BaseModel):
    observation_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SkepticReport(BaseModel):
    accepted_observation_ids: list[str]
    rejected_observations: list[RejectedObservation]
    summary: str = Field(min_length=1)


class BriefLine(BaseModel):
    observation_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence: list[AgentEvidence] = Field(min_length=1)


class BriefWriterReport(BaseModel):
    heading: str = Field(min_length=1)
    lines: list[BriefLine]
    questions: list[str]
    limitation: str = Field(min_length=1)

    @model_validator(mode="after")
    def questions_are_questions(self) -> Self:
        for question in self.questions:
            if not question.strip().endswith("?"):
                raise ValueError("Brief writer questions must end with a question mark")
        return self
