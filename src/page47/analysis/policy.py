"""Make the publication decision in deterministic Python after model review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from page47.analysis.drift import DriftState, EvidenceLink, state_from_direction_counts

ObservationDirection = Literal["clearer", "less_clear", "neutral"]


@dataclass(frozen=True, slots=True)
class ReviewedObservation:
    observation_id: str
    direction: ObservationDirection
    text: str
    evidence: tuple[EvidenceLink, ...]


@dataclass(frozen=True, slots=True)
class ReviewRejection:
    observation_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class AgentReports:
    observations: tuple[ReviewedObservation, ...]
    accepted_observation_ids: frozenset[str]
    rejections: tuple[ReviewRejection, ...]


@dataclass(frozen=True, slots=True)
class EvidencePolicyConfig:
    minimum_supported_observations: int


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    state: DriftState
    publish: bool
    accepted: tuple[ReviewedObservation, ...]
    rejected: tuple[ReviewRejection, ...]
    reason: str

    @property
    def human_text(self) -> str:
        state_text = {
            "clearer": "Presentation drift: clearer",
            "unchanged": "Presentation drift: unchanged",
            "less_clear": "Presentation drift: less clear",
            "mixed": "Presentation drift: mixed directions",
            "cannot_determine": "Presentation drift: could not determine",
        }[self.state]
        return "\n".join(
            (
                state_text,
                f"{len(self.accepted)} observations supported",
                f"{len(self.rejected)} interpretation(s) rejected by review",
                "Page 47 does not determine why these changes were made.",
            )
        )


def load_policy_config(path: Path) -> EvidencePolicyConfig:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Evidence policy configuration must be an object")
    evidence = decoded.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("Evidence policy configuration lacks evidence settings")
    value = evidence.get("minimum_supported_observations")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("minimum_supported_observations must be a positive integer")
    return EvidencePolicyConfig(minimum_supported_observations=value)


def apply_evidence_policy(
    reports: AgentReports,
    config: EvidencePolicyConfig,
) -> EvidenceDecision:
    accepted = tuple(
        observation
        for observation in reports.observations
        if observation.observation_id in reports.accepted_observation_ids
    )
    clearer_count = sum(1 for item in accepted if item.direction == "clearer")
    less_clear_count = sum(1 for item in accepted if item.direction == "less_clear")
    state = state_from_direction_counts(
        clearer_count=clearer_count,
        less_clear_count=less_clear_count,
        has_observations=bool(accepted),
    )
    publish = len(accepted) >= config.minimum_supported_observations and state != "cannot_determine"
    if publish:
        reason = (
            "The finding met the configured count of independently supported observations "
            "after review."
        )
    elif not accepted:
        reason = "No observation survived review with a primary evidence link."
    else:
        reason = "The finding did not reach the configured count of supported observations."
    return EvidenceDecision(
        state=state,
        publish=publish,
        accepted=accepted,
        rejected=reports.rejections,
        reason=reason,
    )
