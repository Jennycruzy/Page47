from __future__ import annotations

import pytest
from pydantic import ValidationError

from page47.agents.schemas import (
    AgentEvidence,
    AgentObservation,
    ArchivistReport,
    BriefLine,
    BriefWriterReport,
    ProcessReport,
    SkepticReport,
    SubstanceChange,
    SubstanceReport,
)
from page47.analysis.case import AppearanceRecord, MatterCase, MatterRecord
from page47.analysis.drift import EvidenceLink, PresentationConfig, compare_all_appearances
from page47.analysis.investigation import (
    _agent_reports,
    _brief_with_resolved_ids,
    _evidence_catalog,
    _validate_agent_reports,
    _validate_brief,
)
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


def test_agent_observation_ids_are_scoped_when_readers_reuse_an_id() -> None:
    evidence = AgentEvidence(
        label="record",
        url="https://records.example/item",
        captured_at="2026-09-05T00:00:00Z",
    )
    archivist = ArchivistReport(
        observations=[
            AgentObservation(
                observation_id="same",
                direction="less_clear",
                statement="The record changed.",
                evidence=[evidence],
            )
        ],
        summary="record",
    )
    process = ProcessReport(
        observations=[
            AgentObservation(
                observation_id="same",
                direction="less_clear",
                statement="The presentation changed.",
                evidence=[evidence],
            )
        ],
        summary="presentation",
    )
    reports, _aliases = _agent_reports(
        archivist,
        SubstanceReport(changes=[], no_substantive_change=True, summary="none"),
        process,
        SkepticReport(
            accepted_observation_ids=["same"],
            rejected_observations=[],
            summary="ambiguous",
        ),
    )
    assert reports.accepted_observation_ids == frozenset()
    assert {item.observation_id for item in reports.rejections} == {
        "archivist:same",
        "process:same",
    }


def test_brief_lines_use_the_accepted_record_text_and_evidence() -> None:
    record_evidence = EvidenceLink(
        "record",
        "https://records.example/item",
        "2026-09-05T00:00:00Z",
    )
    observation = ReviewedObservation(
        "process:item",
        "less_clear",
        "The item moved to the consent calendar.",
        (record_evidence,),
    )
    model_brief = BriefWriterReport(
        heading="Invented heading",
        lines=[
            BriefLine(
                observation_id="raw-item",
                text="An unsupported statement.",
                evidence=[
                    AgentEvidence(
                        label="invented",
                        url="https://example.invalid/fake",
                        captured_at="2023-01-01",
                    )
                ],
            )
        ],
        questions=[],
        limitation="unsupported",
    )
    safe = _brief_with_resolved_ids(
        model_brief,
        frozenset({"process:item"}),
        {"process:item": observation},
    )
    _validate_brief(
        model_brief,
        frozenset({"process:item"}),
        {"raw-item": ("process:item",)},
        {"process:item": observation},
    )
    assert safe.heading == "Worth a look"
    assert safe.lines[0].text == observation.text
    assert safe.lines[0].evidence[0].url == record_evidence.url
    assert safe.limitation == "Page 47 does not determine why these changes were made."


def test_agent_report_cannot_cite_a_record_outside_the_matter() -> None:
    archivist = ArchivistReport(
        observations=[
            AgentObservation(
                observation_id="outside",
                direction="less_clear",
                statement="The record changed.",
                evidence=[
                    AgentEvidence(
                        label="unrelated record",
                        url="https://example.invalid/unrelated",
                        captured_at="2026-09-05T00:00:00Z",
                    )
                ],
            )
        ],
        summary="record",
    )
    process = ProcessReport(observations=[], summary="presentation")
    reports = (
        archivist,
        SubstanceReport(changes=[], no_substantive_change=True, summary="none"),
        process,
        SkepticReport(accepted_observation_ids=[], rejected_observations=[], summary="review"),
        BriefWriterReport(heading="Review", lines=[], questions=[], limitation="Not assessed."),
    )

    with pytest.raises(ValueError, match="not in the stored matter"):
        _validate_agent_reports(reports, _evidence_catalog(case("regular")))


def test_substance_change_rejects_unavailable_placeholder_values() -> None:
    with pytest.raises(ValidationError, match="recorded value"):
        SubstanceChange(
            observation_id="height",
            statement="The height changed.",
            subject="maximum height",
            before="N/A",
            after="75 feet",
            page_number=1,
            excerpt="maximum height: 75 feet",
            evidence=AgentEvidence(
                label="attachment",
                url="https://records.example/attachment.pdf",
                captured_at="2026-09-05T00:00:00Z",
                page_number=1,
            ),
        )


def test_substance_change_rejects_same_before_and_after() -> None:
    with pytest.raises(ValidationError, match="different recorded values"):
        SubstanceChange(
            observation_id="salary",
            statement="The salary is recorded.",
            subject="salary",
            before="$242,020",
            after="$242,020",
            page_number=1,
            excerpt="annual salary of $242,020",
            evidence=AgentEvidence(
                label="attachment",
                url="https://records.example/attachment.pdf",
                captured_at="2026-09-05T00:00:00Z",
                page_number=1,
            ),
        )


def test_substance_change_rejects_mismatched_evidence_page() -> None:
    with pytest.raises(ValidationError, match="match the evidence page"):
        SubstanceChange(
            observation_id="salary",
            statement="The salary changed.",
            subject="salary",
            before="$200,000",
            after="$242,020",
            page_number=2,
            excerpt="annual salary of $242,020",
            evidence=AgentEvidence(
                label="attachment",
                url="https://records.example/attachment.pdf",
                captured_at="2026-09-05T00:00:00Z",
                page_number=1,
            ),
        )
