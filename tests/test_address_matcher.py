from __future__ import annotations

from page47.address.matcher import CensusAddress, match_case_to_area
from page47.analysis.case import AppearanceRecord, MatterCase, MatterRecord
from page47.records.store import SourceReference


def _source(label: str) -> SourceReference:
    return SourceReference("api", f"https://records.example/{label}", "2026-09-11T00:00:00Z")


def _case(*, title: str, body_name: str) -> MatterCase:
    matter_source = _source("matter")
    matter = MatterRecord(
        matter_id=7,
        file_number="AB-7",
        matter_name=None,
        current_title=title,
        type_name=None,
        status_name=None,
        body_id=1,
        body_name=body_name,
        intro_date=None,
        agenda_date=None,
        version=None,
        last_modified_utc=None,
        source=matter_source,
    )
    appearance = AppearanceRecord(
        event_item_id=1,
        matter_id=7,
        event_id=1,
        event_date="2026-09-11T00:00:00Z",
        body_id=1,
        body_name=body_name,
        title_as_presented=title,
        consent_value=None,
        pdf_placement=None,
        pdf_evidence_pages=(),
        pdf_placement_reason=None,
        agenda_sequence=None,
        agenda_number=None,
        action_taken=None,
        action_text=None,
        passed_flag_name=None,
        matter_version_at_event=None,
        agenda_note=None,
        minutes_note=None,
        item_last_modified_utc=None,
        source=_source("appearance"),
        pdf_source=None,
        attachments=(),
    )
    return MatterCase("Seattle, Washington", matter, (appearance,))


def _address(street_name: str) -> CensusAddress:
    return CensusAddress(
        requested=f"1200 {street_name}, Seattle, WA",
        matched_address=f"1200 {street_name}, Seattle, WA",
        street_name=street_name,
        city="Seattle",
        state="WA",
        latitude=None,
        longitude=None,
        source=_source("geocoder"),
    )


def test_area_match_explains_direct_public_text_basis() -> None:
    result = match_case_to_area(
        _case(title="Pine Street safety improvements", body_name="Full Council"),
        _address("Pine Street"),
        None,
    )

    assert result.status == "confirmed"
    assert result.basis == "direct_public_text"
    assert result.matched_terms == ("pine", "street")
    assert result.matched_fields == ("matter.current_title", "appearance.title_as_presented")
    assert "matter.current_title" in result.reason
    assert result.as_json()["basis"] == "direct_public_text"


def test_area_match_does_not_call_a_body_name_a_direct_geographic_match() -> None:
    result = match_case_to_area(
        _case(title="Administrative amendments", body_name="Capitol Hill Council"),
        None,
        "Capitol Hill",
    )

    assert result.status == "may_affect"
    assert result.basis == "inferred_relevance"
    assert result.matched_terms == ("capitol", "hill")
    assert result.matched_fields == ("appearance.body_name",)
    assert "not identified directly" in result.reason
