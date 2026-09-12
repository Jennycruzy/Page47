from __future__ import annotations

from dataclasses import replace
from pathlib import Path

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
from page47.analysis.case import (
    AppearanceRecord,
    AttachmentRecord,
    MatterCase,
    MatterRecord,
    PageAnchor,
)
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
    deterministic_vetoes,
)
from page47.analysis.signature import material_signature_changed, title_coverage_pair
from page47.records.store import SourceReference


def source(label: str) -> SourceReference:
    return SourceReference("api", f"https://records.example/{label}", "2026-09-05T00:00:00Z")


def appearance(
    item_id: int,
    placement: str | None,
    *,
    title: str = "Recorded item",
    attachment_last_modified: str | None = None,
    anchor_value: str | None = None,
) -> AppearanceRecord:
    item_source = source(f"item/{item_id}")
    attachments: tuple[AttachmentRecord, ...] = ()
    if attachment_last_modified is not None or anchor_value is not None:
        anchors = ()
        if anchor_value is not None:
            anchors = (
                PageAnchor(
                    kind="subject",
                    value=anchor_value,
                    page_number=1,
                    start_character=0,
                    end_character=len(anchor_value),
                    excerpt=anchor_value,
                    source=source(f"attachment/{item_id}"),
                ),
            )
        attachments = (
            AttachmentRecord(
                attachment_id=item_id,
                matter_id=7,
                name="agenda attachment",
                url=f"https://records.example/attachment/{item_id}",
                version=None,
                last_modified_utc=attachment_last_modified,
                first_observed_by_us="2026-09-01T00:00:00Z",
                content_hash=None,
                supporting_document=True,
                source=source(f"attachment/{item_id}"),
                reading_status=None,
                page_count=None,
                anchors=anchors,
                reading_source=None,
                evidence_root=Path("/tmp/page47-test"),
            ),
        )
    return AppearanceRecord(
        event_item_id=item_id,
        matter_id=7,
        event_id=item_id,
        event_date="2026-09-01T00:00:00Z",
        body_id=1,
        body_name="Test body",
        title_as_presented=title,
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
        attachments=attachments,
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


def test_structured_signature_detects_title_representativeness() -> None:
    earlier = appearance(
        1,
        "regular",
        title="Central Avenue Height Increase",
        anchor_value="Central Avenue height increase from 35 feet to 75 feet",
    )
    later = appearance(
        2,
        "regular",
        title="Miscellaneous Administrative Amendments",
        anchor_value="Central Avenue height increase from 35 feet to 75 feet",
    )

    earlier_coverage, later_coverage = title_coverage_pair(earlier, later)

    assert earlier_coverage.matched_facets > later_coverage.matched_facets
    assert earlier_coverage.total_facets > 0
    assert material_signature_changed(earlier, later) is False
    comparison = compare_all_appearances(
        MatterCase("Test city", case("regular", "regular").matter, (earlier, later)),
        CONFIG,
    ).comparisons[0]
    assert comparison.state == "less_clear"
    assert comparison.observations[0].details == {
        "method": "structured_substance_signature",
        "earlier": earlier_coverage.as_json(),
        "later": later_coverage.as_json(),
    }


def test_observed_origin_requires_two_distinct_captures() -> None:
    earlier_source = SourceReference(
        "api",
        "https://records.example/item/1",
        "2026-09-05T00:00:00Z",
        True,
        "capture-1",
        "response-1",
        "content-1",
        "2026-09-05T00:00:00Z",
    )
    later_source = SourceReference(
        "api",
        "https://records.example/item/2",
        "2026-09-06T00:00:00Z",
        True,
        "capture-2",
        "response-2",
        "content-2",
        "2026-09-06T00:00:00Z",
    )
    earlier = replace(
        appearance(
            1,
            "regular",
            title="Central Avenue Height Increase",
            anchor_value="Central Avenue height increase",
        ),
        source=earlier_source,
    )
    later = replace(
        appearance(
            2,
            "regular",
            title="Administrative Amendments",
            anchor_value="Central Avenue height increase",
        ),
        source=later_source,
    )

    comparison = compare_all_appearances(
        MatterCase("Test city", case("regular", "regular").matter, (earlier, later)),
        replace(CONFIG, forward_observation_baseline="2026-09-05T12:00:00Z"),
    ).comparisons[0]

    assert comparison.observations[0].evidence[0].origin == "observed_by_page47"
    assert comparison.observations[0].evidence[1].origin == "observed_by_page47"
    assert comparison.observations[0].evidence[1].capture_key == "capture-2"


def test_observed_origin_rejects_reverse_capture_chronology() -> None:
    earlier = replace(
        appearance(1, "regular"),
        source=SourceReference(
            "api",
            "https://records.example/item/1",
            "2026-09-06T00:00:00Z",
            True,
            "capture-1",
            "response-1",
            "content-1",
            "2026-09-06T00:00:00Z",
        ),
    )
    later = replace(
        appearance(2, "consent"),
        source=SourceReference(
            "api",
            "https://records.example/item/2",
            "2026-09-05T00:00:00Z",
            True,
            "capture-2",
            "response-2",
            "content-2",
            "2026-09-05T00:00:00Z",
        ),
    )

    comparison = compare_all_appearances(
        MatterCase("Test city", case("regular", "consent").matter, (earlier, later)),
        replace(CONFIG, forward_observation_baseline="2026-09-04T00:00:00Z"),
    ).comparisons[0]

    assert all(
        evidence.origin == "reconstructed_from_public_record"
        for observation in comparison.observations
        for evidence in observation.evidence
    )


def test_deterministic_veto_rejects_explained_less_clear_observation() -> None:
    earlier = appearance(
        1,
        "regular",
        title="Administrative Matter",
        anchor_value="Harbor Avenue sidewalk design",
    )
    later = appearance(
        2,
        "consent",
        title="Central Avenue Height Increase",
        anchor_value="Central Avenue height increase from 35 feet to 75 feet",
    )
    matter_case = MatterCase("Test city", case("regular", "consent").matter, (earlier, later))
    ledger = compare_all_appearances(matter_case, CONFIG)
    placement_evidence = next(
        item.evidence
        for item in ledger.comparisons[0].observations
        if item.key == "moved_to_consent"
    )
    accepted = (
        ReviewedObservation(
            "process:placement",
            "less_clear",
            "The matter moved to the consent calendar.",
            placement_evidence,
        ),
    )

    vetoes = deterministic_vetoes(matter_case, ledger, accepted)

    assert len(vetoes) == 1
    assert vetoes[0].observation_id == "process:placement"
    assert "material substance change" in vetoes[0].reason


def test_deterministic_veto_does_not_reject_an_unrelated_observation() -> None:
    earlier = appearance(
        1,
        "regular",
        title="Administrative Matter",
        anchor_value="Harbor Avenue sidewalk design",
    )
    later = appearance(
        2,
        "consent",
        title="Central Avenue Height Increase",
        anchor_value="Central Avenue height increase from 35 feet to 75 feet",
    )
    matter_case = MatterCase("Test city", case("regular", "consent").matter, (earlier, later))
    ledger = compare_all_appearances(matter_case, CONFIG)
    accepted = (
        ReviewedObservation(
            "process:other",
            "less_clear",
            "An unrelated process change.",
            (EvidenceLink("other", "https://records.example/other", "2026-09-05"),),
        ),
    )

    assert deterministic_vetoes(matter_case, ledger, accepted) == ()


def test_opposing_dimensions_are_mixed_not_unchanged() -> None:
    result = compare_all_appearances(
        MatterCase(
            city="Test city",
            matter=case("regular", "consent").matter,
            appearances=(
                appearance(
                    1,
                    "consent",
                    title="Housing item",
                    anchor_value="housing",
                ),
                appearance(
                    2,
                    "regular",
                    title="Recorded item",
                    anchor_value="housing",
                ),
            ),
        ),
        CONFIG,
    )

    assert result.counts["mixed"] == 1
    assert result.comparisons[0].state == "mixed"


def test_unreliable_attachment_timing_stays_unavailable() -> None:
    result = compare_all_appearances(
        MatterCase(
            city="Test city",
            matter=case("regular", "regular").matter,
            appearances=(
                appearance(
                    1,
                    None,
                    attachment_last_modified="2026-08-31T23:00:00Z",
                ),
                appearance(
                    2,
                    None,
                    attachment_last_modified="2026-08-31T00:00:00Z",
                ),
            ),
        ),
        CONFIG,
    )

    assert result.comparisons[0].state == "cannot_determine"
    assert result.counts["cannot_determine"] == 1


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


def test_evidence_policy_preserves_opposing_directions() -> None:
    evidence = (EvidenceLink("record", "https://records.example/1", "2026-09-05T00:00:00Z"),)
    reports = AgentReports(
        observations=(
            ReviewedObservation("less", "less_clear", "The title became less specific.", evidence),
            ReviewedObservation(
                "clearer", "clearer", "The item moved to the regular agenda.", evidence
            ),
        ),
        accepted_observation_ids=frozenset({"less", "clearer"}),
        rejections=(),
    )

    decision = apply_evidence_policy(reports, EvidencePolicyConfig(2))

    assert decision.state == "mixed"
    assert decision.publish is True
    assert "mixed directions" in decision.human_text


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


def test_captured_source_origin_survives_agent_review_and_brief_rebuild() -> None:
    evidence = AgentEvidence(
        label="captured record",
        url="https://records.example/item",
        captured_at="2026-09-05T00:00:00Z",
    )
    archivist = ArchivistReport(
        observations=[
            AgentObservation(
                observation_id="item",
                direction="less_clear",
                statement="The presentation changed.",
                evidence=[evidence],
            )
        ],
        summary="record",
    )
    process = ProcessReport(observations=[], summary="presentation")
    reports, _aliases = _agent_reports(
        archivist,
        SubstanceReport(changes=[], no_substantive_change=True, summary="none"),
        process,
        SkepticReport(
            accepted_observation_ids=["item"],
            rejected_observations=[],
            summary="accepted",
        ),
        {(
            evidence.url,
            evidence.captured_at,
        ): "observed_by_page47"},
    )

    observed = reports.observations[0]
    assert observed.evidence[0].origin == "observed_by_page47"
    safe = _brief_with_resolved_ids(
        BriefWriterReport(
            heading="Review",
            lines=[],
            questions=[],
            limitation="Not assessed.",
        ),
        reports.accepted_observation_ids,
        {observed.observation_id: observed},
    )
    assert safe.lines[0].evidence[0].origin == "observed_by_page47"


def test_empty_review_discards_placeholder_brief_lines() -> None:
    model_brief = BriefWriterReport(
        heading="Skeptic Brief",
        lines=[
            BriefLine(
                observation_id="N/A",
                text="No accepted observations available.",
                evidence=[
                    AgentEvidence(
                        label="N/A",
                        url="N/A",
                        captured_at="N/A",
                    )
                ],
            )
        ],
        questions=["Is there additional evidence to review?"],
        limitation="No accepted observations available.",
    )

    _validate_brief(model_brief, frozenset(), {}, {})
    safe = _brief_with_resolved_ids(model_brief, frozenset(), {})

    assert safe.heading == "No supported observations"
    assert safe.lines == []
    assert safe.questions == []


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
