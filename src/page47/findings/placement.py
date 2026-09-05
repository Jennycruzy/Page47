"""Describe documented changes in consent placement without claiming intent."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from page47.records.store import PlacementHistoryItem

FindingState = Literal["moved_to_consent", "moved_from_consent", "unchanged", "cannot_determine"]


@dataclass(frozen=True, slots=True)
class PlacementFinding:
    state: FindingState
    text: str
    previous: PlacementHistoryItem | None
    current: PlacementHistoryItem | None


def compare_placement(history: tuple[PlacementHistoryItem, ...]) -> PlacementFinding:
    """Compare the two latest appearances with documented PDF placement."""

    documented = tuple(
        item for item in history if item.placement in {"consent", "regular"} and item.source
    )
    if len(documented) < 2:
        return PlacementFinding(
            "cannot_determine",
            (
                "Consent placement could not be compared because fewer than two appearances "
                "had matching agenda text."
            ),
            None,
            documented[-1] if documented else None,
        )
    previous, current = documented[-2:]
    if previous.placement == current.placement:
        return PlacementFinding(
            "unchanged",
            "This item had the same documented agenda placement at its two latest appearances.",
            previous,
            current,
        )
    if previous.placement == "regular" and current.placement == "consent":
        return PlacementFinding(
            "moved_to_consent",
            "This item moved from the regular agenda to the consent calendar.",
            previous,
            current,
        )
    return PlacementFinding(
        "moved_from_consent",
        "This item moved from the consent calendar to the regular agenda.",
        previous,
        current,
    )
