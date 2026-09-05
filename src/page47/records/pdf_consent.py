"""Find Seattle consent placement from the published agenda text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Literal

Placement = Literal["consent", "regular", "cannot_determine"]


@dataclass(frozen=True, slots=True)
class AgendaPage:
    """Text extracted from one published agenda page."""

    number: int
    text: str


@dataclass(frozen=True, slots=True)
class PlacementResult:
    placement: Placement
    evidence_pages: tuple[int, ...]
    reason: str


def extract_pages(pdf_bytes: bytes) -> tuple[AgendaPage, ...]:
    """Extract page text from a captured PDF, preserving its page numbers."""

    try:
        from pypdf import PdfReader  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("PDF reading requires the project's pypdf dependency") from error
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[AgendaPage] = []
    for number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        if not isinstance(text, str):
            text = ""
        pages.append(AgendaPage(number, text))
    return tuple(pages)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _title_matches(page_text: str, title: str) -> bool:
    page = _normalise(page_text)
    candidate = _normalise(title)
    if not candidate:
        return False
    return candidate in page or page in candidate


def _page_for_position(pages: tuple[AgendaPage, ...], position: int) -> int:
    offset = 0
    for page in pages:
        page_text = _normalise(page.text)
        if position < offset + len(page_text):
            return page.number
        offset += len(page_text) + 1
    return pages[-1].number


def classify_item(pages: tuple[AgendaPage, ...], title: str) -> PlacementResult:
    """Classify one API item using only the published agenda text.

    A title must be found in the consent section or elsewhere in the agenda.
    The result is deliberately indeterminate when the PDF does not contain a
    reliable title match.
    """

    if not pages:
        return PlacementResult(
            "cannot_determine", (), "The published agenda has no consent heading."
        )
    normalised_pages = tuple(_normalise(page.text) for page in pages)
    document = " ".join(normalised_pages)
    consent_start = document.find("approval of consent calendar")
    if consent_start < 0:
        candidate = _normalise(title)
        title_start = document.find(candidate)
        if title_start < 0 and candidate:
            title_start = document.find(candidate[:120])
        if title_start >= 0:
            return PlacementResult(
                "regular",
                (_page_for_position(pages, title_start),),
                "The agenda has no consent section and the item title appears in its text.",
            )
        return PlacementResult(
            "cannot_determine", (), "The published agenda has no consent heading."
        )
    consent_end = document.find("items removed from consent calendar", consent_start)
    if consent_end < 0:
        consent_end = len(document)
    candidate = _normalise(title)
    if candidate in {
        "approval of consent calendar",
        "items removed from consent calendar",
    }:
        return PlacementResult(
            "cannot_determine", (), "The title is a section heading, not a matter."
        )
    title_start = document.find(candidate)
    if title_start < 0 and candidate:
        title_start = document.find(candidate[:120])
    if title_start < 0:
        return PlacementResult(
            "cannot_determine", (), "The item title was not found in the published agenda text."
        )
    page_number = _page_for_position(pages, title_start)
    if consent_start <= title_start < consent_end:
        return PlacementResult(
            "consent", (page_number,), "The item title appears under the consent heading."
        )
    if title_start < consent_start or title_start >= consent_end:
        return PlacementResult(
            "regular", (page_number,), "The item title appears outside the consent section."
        )
    raise AssertionError("unreachable placement branch")
