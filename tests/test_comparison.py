from __future__ import annotations

from page47.analysis.case import AppearanceRecord, MatterCase, MatterRecord
from page47.analysis.drift import PresentationConfig
from page47.evaluation.comparison import (
    _keyword_arm,
    _latest_document_arm,
    _metrics,
    _page47_arm,
    _search_arm,
)
from page47.records.store import SourceReference


def source(label: str) -> SourceReference:
    return SourceReference(
        "api",
        f"https://records.example/{label}",
        "2026-09-05T00:00:00Z",
    )


def case(*titles: str, placements: tuple[str | None, ...]) -> MatterCase:
    matter = MatterRecord(
        matter_id=7,
        file_number=None,
        matter_name=None,
        current_title=titles[-1],
        type_name=None,
        status_name=None,
        body_id=1,
        body_name="Test body",
        intro_date=None,
        agenda_date=None,
        version=None,
        last_modified_utc=None,
        source=source("matter/7"),
    )
    appearances = tuple(
        AppearanceRecord(
            event_item_id=index + 1,
            matter_id=7,
            event_id=index + 1,
            event_date="2026-09-01T00:00:00Z",
            body_id=1,
            body_name="Test body",
            title_as_presented=title,
            consent_value=None,
            pdf_placement=placements[index],
            pdf_evidence_pages=(3,) if placements[index] is not None else (),
            pdf_placement_reason=None,
            agenda_sequence=1,
            agenda_number="1",
            action_taken=None,
            action_text=None,
            passed_flag_name=None,
            matter_version_at_event=None,
            agenda_note=None,
            minutes_note=None,
            item_last_modified_utc=None,
            source=source(f"item/{index + 1}"),
            pdf_source=source(f"agenda/{index + 1}"),
            attachments=(),
        )
        for index, title in enumerate(titles)
    )
    return MatterCase("Test city", matter, appearances)


CONFIG = PresentationConfig(
    minimum_appearances=2,
    minimum_title_overlap=1,
    timing_difference_hours=6,
    common_title_words=frozenset({"item"}),
)


def test_four_arms_keep_their_boundaries_explicit() -> None:
    matter = case(
        "Recorded item",
        "Renamed housing item",
        placements=("regular", "consent"),
    )

    keyword = _keyword_arm(matter)
    search = _search_arm(matter)
    latest = _latest_document_arm(matter)
    page47 = _page47_arm(matter, CONFIG)

    assert keyword.surfaced is True
    assert keyword.state is None
    assert search.surfaced is False
    assert search.state is None
    assert latest.surfaced is False
    assert latest.state is None
    assert page47.state == "less_clear"
    assert page47.surfaced is True


def test_comparison_metrics_preserve_historical_abstention_audit() -> None:
    rows = [
        {
            "case_id": "Test city:1",
            "gold_label": "cannot_determine",
            "arms": [
                {"arm": "page47", "state": "cannot_determine", "surfaced": False},
                {"arm": "keyword", "state": None, "surfaced": True},
            ],
        },
        {
            "case_id": "Test city:2",
            "gold_label": "yes",
            "arms": [
                {"arm": "page47", "state": "less_clear", "surfaced": True},
                {"arm": "keyword", "state": None, "surfaced": False},
            ],
        },
    ]

    metrics = _metrics(rows)

    assert metrics["gold_label_counts"] == {"yes": 1, "no": 0, "cannot_determine": 1}
    audit = metrics["historical_abstention_audit"]
    assert isinstance(audit, dict)
    assert audit["cases_expected_to_abstain"] == 1
    assert audit["page47_overclaims"] == 0
