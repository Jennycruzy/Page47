from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from page47.analysis.drift import load_presentation_config
from page47.evaluation.controlled import load_controlled_cases
from page47.evaluation.forward import forward_case_candidates
from page47.records.store import SourceReference


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
            ),
        )
        for index, appearance in enumerate(controlled.matter.appearances)
    )
    case = replace(controlled.matter, appearances=observed_appearances)

    candidates = forward_case_candidates(
        case,
        load_presentation_config(Path("config/presentation.yaml")),
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
