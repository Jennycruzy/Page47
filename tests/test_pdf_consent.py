from pathlib import Path

import pytest

from page47.records.pdf_consent import AgendaPage, classify_item
from page47.records.runner import agenda_capture
from page47.snapshotter.http import FetchResult
from page47.snapshotter.store import SnapshotStore

AGENDA_URL = (
    "https://legistar2.granicus.com/seattle/meetings/2026/9/"
    "6871_A_Libraries%2C_Education%2C_and_Neighborhoods_Committee_26-09-09_"
    "Committee_Agenda.pdf"
)


def stored_agenda(tmp_path: Path, status: int, body: bytes) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "evidence")
    response = FetchResult(
        target="agenda:6871",
        url=AGENDA_URL,
        captured_at="2026-09-06T15:00:00Z",
        status=status,
        headers={},
        body=body,
        error_type=None,
        error=None,
        not_modified=False,
    )
    parse_status = "binary" if status == 200 else "unparsed"
    store.capture(response, "agenda_pdf", {"parse_status": parse_status})
    return store


def test_non_successful_agenda_capture_is_reported_before_pdf_reading(tmp_path: Path) -> None:
    store = stored_agenda(tmp_path, 404, b"<!DOCTYPE html>")

    with pytest.raises(ValueError, match="HTTP status 404"):
        agenda_capture(store, 6871, AGENDA_URL)


def test_malformed_successful_agenda_capture_is_reported(tmp_path: Path) -> None:
    store = stored_agenda(tmp_path, 200, b"<!DOCTYPE html>")

    with pytest.raises(ValueError, match="Could not read captured agenda PDF"):
        agenda_capture(store, 6871, AGENDA_URL)


def test_seattle_august_11_consent_item_is_found_under_heading() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 579\nBills: CB 121271"),
        AgendaPage(12, "I. ITEMS REMOVED FROM CONSENT CALENDAR\nCF 314550"),
    )
    result = classify_item(pages, "CB 121271")
    assert result.placement == "consent"
    assert result.evidence_pages == (3,)


def test_seattle_august_4_regular_item_is_outside_consent_section() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 578\nBills: CB 121265"),
        AgendaPage(8, "I. ITEMS REMOVED FROM CONSENT CALENDAR\n10. CF 314530"),
    )
    result = classify_item(pages, "CF 314530")
    assert result.placement == "regular"
    assert result.evidence_pages == (8,)


def test_missing_title_is_not_labeled() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 578"),
        AgendaPage(8, "I. ITEMS REMOVED FROM CONSENT CALENDAR"),
    )
    result = classify_item(pages, "An item that is not in this agenda")
    assert result.placement == "cannot_determine"
    assert result.evidence_pages == ()


def test_item_in_agenda_without_consent_section_is_regular() -> None:
    pages = (
        AgendaPage(
            1,
            "Transportation, Waterfront, and Seattle Center Committee\n"
            "Petition of THE YEW, LLC, for the vacation of a portion the alley lying within "
            "Block 2, Wegener's Addition to the City of Seattle.",
        ),
    )
    result = classify_item(
        pages,
        "Petition of THE YEW, LLC, for the vacation of a portion the alley lying within "
        "Block 2, Wegener's Addition to the City of Seattle.",
    )
    assert result.placement == "regular"
    assert result.evidence_pages == (1,)
