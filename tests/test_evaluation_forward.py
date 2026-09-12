from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from page47.analysis.drift import load_presentation_config
from page47.evaluation.controlled import load_controlled_cases
from page47.evaluation.forward import forward_case_candidates, scan_forward_observations
from page47.records.store import AppearanceObservation, RecordStore, SourceReference


def test_forward_candidate_requires_directional_evidence_from_distinct_captures() -> None:
    controlled = next(
        item
        for item in load_controlled_cases(Path("config/evaluation-controlled.json"))
        if item.case_id == "case-02-title-less-clear"
    )
    observed_appearances = tuple(
        replace(
            appearance,
            source=SourceReference(
                "api",
                appearance.source.url,
                f"2026-09-{index + 1:02d}T00:00:00Z",
                True,
                f"capture-{index + 1}",
                f"response-{index + 1}",
                f"content-{index + 1}",
                f"2026-09-{index + 1:02d}T00:00:00Z",
            ),
        )
        for index, appearance in enumerate(controlled.matter.appearances)
    )
    case = replace(controlled.matter, appearances=observed_appearances)
    config = replace(
        load_presentation_config(Path("config/presentation.yaml")),
        forward_observation_baseline="2026-09-01T12:00:00Z",
    )

    candidates = forward_case_candidates(
        case,
        config,
    )

    assert len(candidates) == 1
    assert candidates[0]["state"] == "less_clear"
    assert candidates[0]["ready_for_investigation"] is True


def test_historical_fixture_is_not_marked_forward_observed() -> None:
    controlled = next(
        item
        for item in load_controlled_cases(Path("config/evaluation-controlled.json"))
        if item.case_id == "case-02-title-less-clear"
    )

    candidates = forward_case_candidates(
        controlled.matter,
        load_presentation_config(Path("config/presentation.yaml")),
    )

    assert candidates == []


def test_forward_scan_skips_orphaned_appearance_rows(tmp_path: Path) -> None:
    source = SourceReference(
        kind="api",
        url="https://records.example/items/orphan",
        captured_at="2026-09-11T00:00:00Z",
    )
    with RecordStore(tmp_path / "records.sqlite3") as store:
        store.upsert_appearance(
            AppearanceObservation(
                event_item_id=900,
                matter_id=999,
                event_id=900,
                event_date="2026-09-11",
                body_id=1,
                body_name="Full Council",
                title_as_presented="Orphaned matter",
                consent_value=None,
                pdf_placement=None,
                pdf_evidence_pages_json=None,
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
                source=source,
                provenance={"title_as_presented": source.as_json()},
            )
        )
        store.commit()

    result = scan_forward_observations(
        city="Seattle, Washington",
        database=tmp_path / "records.sqlite3",
        evidence_root=tmp_path / "evidence",
        presentation_path=Path("config/presentation.yaml"),
    )

    assert result["status"] == "awaiting_real_transition"
    assert result["case_count_checked"] == 0
    assert result["skipped_orphan_matter_count"] == 1
    assert result["candidate_count"] == 0
