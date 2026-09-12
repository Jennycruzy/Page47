import json
from pathlib import Path

from scripts.build_historical_challenge import (
    RawAppearance,
    _container_exclusion_reason,
    _pair_payload,
)
from scripts.validate_historical_challenge import validate


def _appearance(event_item_id: int, title: str) -> RawAppearance:
    return RawAppearance(
        event_item_id=event_item_id,
        event_date=f"2026-01-{event_item_id:02d}",
        title=title,
        placement=None,
        attachments=(),
    )


def test_recurring_container_titles_are_excluded() -> None:
    appearances = tuple(
        _appearance(index, "City Council Agenda (2026)") for index in (1, 2, 3)
    )

    assert _container_exclusion_reason(appearances) == "excluded_recurring_council_agenda"


def test_attachment_change_ids_are_deduplicated() -> None:
    appearance_a = RawAppearance(
        event_item_id=1,
        event_date="2026-01-01",
        title="Matter",
        placement=None,
        attachments=((46838, "agenda", "https://example.com/a.pdf", "old", "0"),),
    )
    appearance_b = RawAppearance(
        event_item_id=2,
        event_date="2026-01-02",
        title="Matter",
        placement=None,
        attachments=((46838, "agenda", "https://example.com/a.pdf", "new", "0"),),
    )

    payload = _pair_payload(
        appearance_a,
        appearance_b,
        ("attachment_changed",),
        frozenset({46838}),
    )

    assert payload["attachment_ids_with_multiple_captured_hashes"] == [46838]


def test_checked_in_reviewer_packet_is_blind_and_uniform() -> None:
    packet = Path("docs/historical-challenge-cohort.json")
    summary = validate(packet, require_labels=False)

    assert summary["items"] == 40
    assert all(
        set(item) == {"case_id", "city", "matter_id", "review_pair", "review", "case_payload"}
        for item in json.loads(packet.read_text())["items"]
    )
