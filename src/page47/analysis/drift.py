"""Compare how a matter was presented, using only recorded observations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from page47.analysis.case import AppearanceRecord, MatterCase

DriftState = Literal["clearer", "unchanged", "less_clear", "mixed", "cannot_determine"]
Direction = Literal["clearer", "less_clear", "neutral"]


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    label: str
    url: str
    captured_at: str
    page_number: int | None = None

    def as_json(self) -> dict[str, str | int | None]:
        return {
            "label": self.label,
            "url": self.url,
            "captured_at": self.captured_at,
            "page_number": self.page_number,
        }


@dataclass(frozen=True, slots=True)
class PresentationObservation:
    key: str
    direction: Direction
    text: str
    evidence: tuple[EvidenceLink, ...]

    def as_json(self) -> dict[str, object]:
        return {
            "key": self.key,
            "direction": self.direction,
            "text": self.text,
            "evidence": [item.as_json() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class DriftComparison:
    state: DriftState
    previous_event_item_id: int | None
    current_event_item_id: int | None
    observations: tuple[PresentationObservation, ...]
    reason: str

    def as_json(self) -> dict[str, object]:
        return {
            "state": self.state,
            "previous_event_item_id": self.previous_event_item_id,
            "current_event_item_id": self.current_event_item_id,
            "observations": [item.as_json() for item in self.observations],
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DriftLedger:
    comparisons: tuple[DriftComparison, ...]

    @property
    def counts(self) -> dict[DriftState, int]:
        return {
            state: sum(1 for comparison in self.comparisons if comparison.state == state)
            for state in ("clearer", "unchanged", "less_clear", "mixed", "cannot_determine")
        }

    def as_json(self) -> dict[str, object]:
        return {
            "counts": self.counts,
            "comparisons": [comparison.as_json() for comparison in self.comparisons],
        }


@dataclass(frozen=True, slots=True)
class PresentationConfig:
    minimum_appearances: int
    minimum_title_overlap: int
    timing_difference_hours: int
    common_title_words: frozenset[str]


def state_from_direction_counts(
    *, clearer_count: int, less_clear_count: int, has_observations: bool
) -> DriftState:
    """Summarize supported presentation directions without cancelling them out."""

    if not has_observations:
        return "cannot_determine"
    if clearer_count > 0 and less_clear_count > 0:
        return "mixed"
    if less_clear_count > 0:
        return "less_clear"
    if clearer_count > 0:
        return "clearer"
    return "unchanged"


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"Unsupported presentation configuration value: {type(value).__name__}")


def load_presentation_config(path: Path) -> PresentationConfig:
    decoded = _json_value(yaml.safe_load(path.read_text(encoding="utf-8")))
    if not isinstance(decoded, dict):
        raise ValueError("Presentation configuration must be an object")
    comparison = decoded.get("comparison")
    if not isinstance(comparison, dict):
        raise ValueError("Presentation configuration lacks comparison settings")

    def integer(key: str, minimum: int) -> int:
        value = comparison.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"comparison.{key} must be an integer of at least {minimum}")
        return value

    raw_words = comparison.get("common_title_words")
    if not isinstance(raw_words, list) or not all(isinstance(item, str) for item in raw_words):
        raise ValueError("comparison.common_title_words must be a list of text")
    words = frozenset(item.casefold() for item in raw_words if item.strip())
    if not words:
        raise ValueError("comparison.common_title_words must not be empty")
    return PresentationConfig(
        minimum_appearances=integer("minimum_appearances", 2),
        minimum_title_overlap=integer("minimum_title_overlap", 1),
        timing_difference_hours=integer("timing_difference_hours", 1),
        common_title_words=words,
    )


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9]{3,}", text)}


def _subject_tokens(appearance: AppearanceRecord, common: frozenset[str]) -> set[str]:
    output: set[str] = set()
    for attachment in appearance.attachments:
        for anchor in attachment.anchors:
            output.update(_tokens(anchor.excerpt))
            output.update(_tokens(anchor.value))
    return output - common


def _link(label: str, source_url: str, captured_at: str, page: int | None = None) -> EvidenceLink:
    if not source_url or not captured_at:
        raise ValueError(f"Cannot make evidence link for {label} without source details")
    return EvidenceLink(label, source_url, captured_at, page)


def _title_observation(
    previous: AppearanceRecord,
    current: AppearanceRecord,
    config: PresentationConfig,
) -> PresentationObservation | None:
    previous_title = previous.title_as_presented
    current_title = current.title_as_presented
    if previous_title is None or current_title is None:
        return None
    if previous_title.strip().casefold() == current_title.strip().casefold():
        return PresentationObservation(
            "title_unchanged",
            "neutral",
            "The title stayed the same at these two appearances.",
            (
                _link("earlier title", previous.source.url, previous.source.captured_at),
                _link("later title", current.source.url, current.source.captured_at),
            ),
        )
    previous_overlap = len(
        _tokens(previous_title) & _subject_tokens(previous, config.common_title_words)
    )
    current_overlap = len(
        _tokens(current_title) & _subject_tokens(current, config.common_title_words)
    )
    if (
        previous_overlap < config.minimum_title_overlap
        and current_overlap < config.minimum_title_overlap
    ):
        direction: Direction = "neutral"
        text = (
            "The title changed, but the available page text does not show which title was "
            "more specific."
        )
    elif current_overlap < previous_overlap:
        direction = "less_clear"
        text = (
            "The later title shares fewer recorded subject words with the attached material "
            "than the earlier title."
        )
    elif current_overlap > previous_overlap:
        direction = "clearer"
        text = (
            "The later title shares more recorded subject words with the attached material "
            "than the earlier title."
        )
    else:
        direction = "neutral"
        text = "The title changed, but the recorded subject-word overlap was the same."
    return PresentationObservation(
        "title_changed",
        direction,
        text,
        (
            _link("earlier title", previous.source.url, previous.source.captured_at),
            _link("later title", current.source.url, current.source.captured_at),
        ),
    )


def _placement_observation(
    previous: AppearanceRecord,
    current: AppearanceRecord,
) -> PresentationObservation | None:
    if previous.pdf_placement not in {"consent", "regular"}:
        return None
    if current.pdf_placement not in {"consent", "regular"}:
        return None
    evidence: list[EvidenceLink] = []
    previous_page = previous.pdf_evidence_pages[0] if previous.pdf_evidence_pages else None
    current_page = current.pdf_evidence_pages[0] if current.pdf_evidence_pages else None
    previous_source = previous.pdf_source
    if previous_source is None:
        previous_source = previous.source
    current_source = current.pdf_source
    if current_source is None:
        current_source = current.source
    evidence.append(
        _link(
            "earlier agenda placement",
            previous_source.url,
            previous_source.captured_at,
            previous_page,
        )
    )
    evidence.append(
        _link(
            "later agenda placement",
            current_source.url,
            current_source.captured_at,
            current_page,
        )
    )
    if previous.pdf_placement == current.pdf_placement:
        return PresentationObservation(
            "agenda_placement_unchanged",
            "neutral",
            f"The item stayed on the {current.pdf_placement} agenda at these two appearances.",
            tuple(evidence),
        )
    if previous.pdf_placement == "regular" and current.pdf_placement == "consent":
        return PresentationObservation(
            "moved_to_consent",
            "less_clear",
            "The item moved from the regular agenda to the consent calendar.",
            tuple(evidence),
        )
    return PresentationObservation(
        "moved_to_regular",
        "clearer",
        "The item moved from the consent calendar to the regular agenda.",
        tuple(evidence),
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _attachment_lag(appearance: AppearanceRecord) -> float | None:
    event_date = _parse_datetime(appearance.event_date)
    lags: list[float] = []
    for attachment in appearance.attachments:
        changed = _parse_datetime(attachment.last_modified_utc)
        if event_date is not None and changed is not None:
            lags.append((event_date - changed).total_seconds() / 3600.0)
    if not lags:
        return None
    return min(lags)


def _timing_observation(
    previous: AppearanceRecord,
    current: AppearanceRecord,
    config: PresentationConfig,
) -> PresentationObservation | None:
    previous_lag = _attachment_lag(previous)
    current_lag = _attachment_lag(current)
    if previous_lag is None or current_lag is None:
        return None
    difference = previous_lag - current_lag
    if abs(difference) < config.timing_difference_hours:
        direction: Direction = "neutral"
        text = (
            "The recorded attachment-to-meeting timing changed by less than the configured "
            "comparison interval."
        )
    elif difference > 0:
        direction = "less_clear"
        text = (
            "The later appearance has an attachment timestamp closer to the meeting than "
            "the earlier appearance."
        )
    else:
        direction = "clearer"
        text = (
            "The later appearance has an attachment timestamp farther from the meeting than "
            "the earlier appearance."
        )
    evidence = (
        _link("earlier item record", previous.source.url, previous.source.captured_at),
        _link("later item record", current.source.url, current.source.captured_at),
    )
    return PresentationObservation("attachment_timing", direction, text, evidence)


def compare_latest_appearances(case: MatterCase, config: PresentationConfig) -> DriftComparison:
    if len(case.appearances) < config.minimum_appearances:
        current = case.appearances[-1] if case.appearances else None
        return DriftComparison(
            "cannot_determine",
            None,
            current.event_item_id if current else None,
            (),
            "Fewer than two recorded appearances are available for comparison.",
        )
    previous = case.appearances[-2]
    current = case.appearances[-1]
    possible = (
        _title_observation(previous, current, config),
        _placement_observation(previous, current),
        _timing_observation(previous, current, config),
    )
    observations = tuple(item for item in possible if item is not None)
    if not observations:
        return DriftComparison(
            "cannot_determine",
            previous.event_item_id,
            current.event_item_id,
            (),
            "The stored appearances do not contain enough comparable presentation details.",
        )
    less_clear = sum(1 for item in observations if item.direction == "less_clear")
    clearer = sum(1 for item in observations if item.direction == "clearer")
    state = state_from_direction_counts(
        clearer_count=clearer,
        less_clear_count=less_clear,
        has_observations=True,
    )
    return DriftComparison(
        state,
        previous.event_item_id,
        current.event_item_id,
        observations,
        "The result counts recorded observations in both directions; it does not assess motive.",
    )


def compare_all_appearances(case: MatterCase, config: PresentationConfig) -> DriftLedger:
    """Compare every adjacent recorded appearance, preserving unknown results."""

    if len(case.appearances) < config.minimum_appearances:
        return DriftLedger((compare_latest_appearances(case, config),))
    comparisons = tuple(
        _compare_pair(previous, current, config)
        for previous, current in zip(case.appearances, case.appearances[1:], strict=False)
    )
    return DriftLedger(comparisons)


def _compare_pair(
    previous: AppearanceRecord,
    current: AppearanceRecord,
    config: PresentationConfig,
) -> DriftComparison:
    possible = (
        _title_observation(previous, current, config),
        _placement_observation(previous, current),
        _timing_observation(previous, current, config),
    )
    observations = tuple(item for item in possible if item is not None)
    if not observations:
        return DriftComparison(
            "cannot_determine",
            previous.event_item_id,
            current.event_item_id,
            (),
            "The stored appearances do not contain enough comparable presentation details.",
        )
    less_clear = sum(1 for item in observations if item.direction == "less_clear")
    clearer = sum(1 for item in observations if item.direction == "clearer")
    state = state_from_direction_counts(
        clearer_count=clearer,
        less_clear_count=less_clear,
        has_observations=True,
    )
    return DriftComparison(
        state,
        previous.event_item_id,
        current.event_item_id,
        observations,
        "The result counts recorded observations in both directions; it does not assess motive.",
    )
