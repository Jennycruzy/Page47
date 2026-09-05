"""Structured outputs expected from each investigation node."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Direction = Literal["clearer", "less_clear", "neutral"]


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
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)
    unit: str | None = None
    page_number: int = Field(ge=1)
    excerpt: str = Field(min_length=1)
    evidence: AgentEvidence


class SubstanceReport(BaseModel):
    changes: list[SubstanceChange]
    no_substantive_change: bool
    summary: str = Field(min_length=1)


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
