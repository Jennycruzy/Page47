from __future__ import annotations

import json
from pathlib import Path

from page47.evaluation.controlled import load_controlled_cases, run_controlled

ROOT = Path(__file__).resolve().parents[1]


def test_controlled_fixture_has_directional_and_adversarial_cases() -> None:
    cases = load_controlled_cases(ROOT / "config/evaluation-controlled.json")

    assert len(cases) == 28
    assert {case.expected_state for case in cases} == {
        "clearer",
        "less_clear",
        "mixed",
        "unchanged",
        "cannot_determine",
    }
    assert any(case.skeptic_expected == "reject" for case in cases)
    assert any("prompt-injection" in case.scenario for case in cases)


def test_controlled_evaluation_is_directionally_reversible(tmp_path: Path) -> None:
    output_path = tmp_path / "controlled-results.json"
    result = run_controlled(
        fixture_path=ROOT / "config/evaluation-controlled.json",
        presentation_path=ROOT / "config/presentation.yaml",
        output_path=output_path,
    )

    assert result["status"] == "review_required"
    metrics = result["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["page47_direction_accuracy"] == 1.0
    assert metrics["keyword_surface_accuracy"] == 1.0
    assert metrics["reversal_pairs_checked"] == 2
    assert metrics["reversal_pairs_correct"] == 2
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["case_count"] == 28
