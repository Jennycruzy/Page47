"""Small deterministic substance signatures for title representativeness."""

from __future__ import annotations

import re
from dataclasses import dataclass

from page47.analysis.case import AppearanceRecord

_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "along",
        "and",
        "are",
        "from",
        "into",
        "item",
        "miscellaneous",
        "more",
        "public",
        "record",
        "the",
        "this",
        "to",
        "with",
    }
)

_ACTION_WORDS = frozenset(
    {
        "adopt",
        "approve",
        "authorize",
        "change",
        "decrease",
        "design",
        "expand",
        "fund",
        "increase",
        "modify",
        "permit",
        "raise",
        "rezone",
        "replace",
        "remove",
        "lower",
    }
)

_OBJECT_WORDS = frozenset(
    {
        "amendment",
        "code",
        "development",
        "district",
        "funding",
        "height",
        "housing",
        "parking",
        "policy",
        "program",
        "sidewalk",
        "transit",
        "use",
        "zoning",
    }
)

_QUANTITY_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|feet?|ft|meters?|m|miles?|mi|acres?|units?)\b",
    re.IGNORECASE,
)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]{3,}")


@dataclass(frozen=True, slots=True)
class SubstanceSignature:
    """The observable facets that a title could represent."""

    subjects: frozenset[str]
    actions: frozenset[str]
    objects: frozenset[str]
    quantities: frozenset[str]

    @property
    def total_facets(self) -> int:
        return sum(
            len(group)
            for group in (self.subjects, self.actions, self.objects, self.quantities)
        )

    def as_json(self) -> dict[str, object]:
        return {
            "subjects": sorted(self.subjects),
            "actions": sorted(self.actions),
            "objects": sorted(self.objects),
            "quantities": sorted(self.quantities),
        }


@dataclass(frozen=True, slots=True)
class TitleCoverage:
    matched_facets: int
    total_facets: int
    matched: SubstanceSignature

    @property
    def ratio(self) -> float:
        if self.total_facets == 0:
            return 0.0
        return self.matched_facets / self.total_facets

    def as_json(self) -> dict[str, object]:
        return {
            "matched_facets": self.matched_facets,
            "total_facets": self.total_facets,
            "ratio": round(self.ratio, 3),
            "matched": self.matched.as_json(),
        }


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_PATTERN.findall(value)}


def _quantities(value: str) -> set[str]:
    quantities: set[str] = set()
    for match in _QUANTITY_PATTERN.finditer(value):
        normalized = re.sub(r"\s+", " ", match.group(0).casefold()).strip()
        quantities.add(normalized)
    return quantities


def signature_for_appearance(appearance: AppearanceRecord) -> SubstanceSignature:
    """Extract transparent facets from retained document anchors.

    Anchors are already page-bounded evidence selected by the document reader. This
    function only categorizes exact text; it does not ask a model to score a title.
    """

    texts: list[str] = []
    for attachment in appearance.attachments:
        for anchor in attachment.anchors:
            texts.extend((anchor.value, anchor.excerpt))
    combined = " ".join(texts)
    tokens = _tokens(combined)
    actions = tokens & _ACTION_WORDS
    objects = tokens & _OBJECT_WORDS
    quantities = _quantities(combined)
    quantity_tokens = {
        token
        for quantity in quantities
        for token in _tokens(quantity)
    }
    subjects = tokens - _STOP_WORDS - _ACTION_WORDS - _OBJECT_WORDS - quantity_tokens
    return SubstanceSignature(
        subjects=frozenset(subjects),
        actions=frozenset(actions),
        objects=frozenset(objects),
        quantities=frozenset(quantities),
    )


def title_coverage(title: str, signature: SubstanceSignature) -> TitleCoverage:
    title_tokens = _tokens(title)
    title_quantities = _quantities(title)
    matched_subjects = signature.subjects & title_tokens
    matched_actions = signature.actions & title_tokens
    matched_objects = signature.objects & title_tokens
    matched_quantities = signature.quantities & title_quantities
    matched = SubstanceSignature(
        subjects=frozenset(matched_subjects),
        actions=frozenset(matched_actions),
        objects=frozenset(matched_objects),
        quantities=frozenset(matched_quantities),
    )
    matched_facets = sum(
        len(group)
        for group in (
            matched.subjects,
            matched.actions,
            matched.objects,
            matched.quantities,
        )
    )
    return TitleCoverage(matched_facets, signature.total_facets, matched)


def title_coverage_pair(
    previous: AppearanceRecord,
    current: AppearanceRecord,
) -> tuple[TitleCoverage, TitleCoverage]:
    previous_signature = signature_for_appearance(previous)
    current_signature = signature_for_appearance(current)
    previous_title = previous.title_as_presented or ""
    current_title = current.title_as_presented or ""
    return (
        title_coverage(previous_title, previous_signature),
        title_coverage(current_title, current_signature),
    )


def material_signature_changed(
    previous: AppearanceRecord,
    current: AppearanceRecord,
) -> bool:
    previous_signature = signature_for_appearance(previous)
    current_signature = signature_for_appearance(current)
    return any(
        getattr(previous_signature, name) != getattr(current_signature, name)
        for name in ("subjects", "actions", "objects", "quantities")
    )
