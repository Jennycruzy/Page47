from __future__ import annotations

from page47.analysis.case import AppearanceRecord, MatterCase, MatterRecord
from page47.analysis.drift import EvidenceLink, PresentationConfig, compare_all_appearances
from page47.analysis.policy import (
    AgentReports,
    EvidencePolicyConfig,
    ReviewedObservation,
    ReviewRejection,
    apply_evidence_policy,
)
from page47.records.store import SourceReference


def source(label: str) -> SourceReference:
    return SourceReference("api", f"https://records.example/{label}", "2026-09-05T00:00:00Z")


def appearance(item_id: int, placement: str | None) -> AppearanceRecord:
    item_source = source(f"item/{item_id}")
    return AppearanceRecord(
        event_item_id=item_id,
        matter_id=7,
        event_id=item_id,
        event_date="2026-09-01T00:00:00Z",
        body_id=1,
        body_name="Test body",
        title_as_presented="Recorded item",
        consent_value=None,
        pdf_placement=placement,
        pdf_evidence_pages=(3,) if placement is not None else (),
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
        source=item_source,
        pdf_source=source(f"agenda/{item_id}"),
        attachments=(),
    )


def case(*placements: str | None) -> MatterCase:
    matter_source = source("matter/7")
    matter = MatterRecord(
        matter_id=7,
        file_number=None,
        matter_name=None,
        current_title="Recorded item",
        type_name=None,
        status_name=None,
        body_id=1,
        body_name="Test body",
        intro_date=None,
        agenda_date=None,
        version=None,
        last_modified_utc=None,
        source=matter_source,
    )
    return MatterCase(
        city="Test city",
        matter=matter,
        appearances=tuple(
            appearance(index + 1, placement)
            for index, placement in enumerate(placements)
        ),
    )


CONFIG = PresentationConfig(
    minimum_appearances=2,
    minimum_title_overlap=1,
    timing_difference_hours=6,
    common_title_words=frozenset({"item"}),
)


def test_all_four_recorded_states_are_kept() -> None:
    assert compare_all_appearances(case("consent", "regular"), CONFIG).counts["clearer"] == 1
    assert compare_all_appearances(case("regular", "consent"), CONFIG).counts["less_clear"] == 1
    assert compare_all_appearances(case("regular", "regular"), CONFIG).counts["unchanged"] == 1
    assert compare_all_appearances(case("regular"), CONFIG).counts["cannot_determine"] == 1


def test_evidence_policy_is_counted_without_a_model_call() -> None:
    evidence = (EvidenceLink("record", "https://records.example/1", "2026-09-05T00:00:00Z"),)
    observations = (
        ReviewedObservation("one", "less_clear", "The item moved.", evidence),
        ReviewedObservation("two", "less_clear", "The title changed.", evidence),
        ReviewedObservation("three", "clearer", "The item moved back.", evidence),
    )
    reports = AgentReports(
        observations=observations,
        accepted_observation_ids=frozenset({"one", "two"}),
        rejections=(ReviewRejection("three", "The review record did not retain this point."),),
    )
    decision = apply_evidence_policy(reports, EvidencePolicyConfig(2))
    assert decision.publish is True
    assert decision.state == "less_clear"
    assert len(decision.rejected) == 1
    assert "Page 47 does not determine why" in decision.human_text
