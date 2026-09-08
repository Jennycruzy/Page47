from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_evaluation_set import validate


def _export(tmp_path: Path, *, label: str | None) -> Path:
    item = {
        "case_id": "Seattle, Washington:1",
        "city": "Seattle, Washington",
        "gold_label": label,
        "gold_label_reason": "The recorded presentation changed." if label else None,
        "gold_evidence": (
            [
                {
                    "url": "https://records.example/item/1",
                    "captured_at": "2026-09-08T00:00:00Z",
                }
            ]
            if label
            else []
        ),
    }
    path = tmp_path / "evaluation.json"
    path.write_text(
        json.dumps(
            {
                "city": "Seattle, Washington",
                "gold_case_ids": [item["case_id"]],
                "items": [item],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_unlabeled_export_can_be_shape_checked(tmp_path: Path) -> None:
    summary = validate(_export(tmp_path, label=None), require_labels=False)
    assert summary["labels"] == 0


def test_label_gate_rejects_unlabeled_gold_item(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gold_label is not filled"):
        validate(_export(tmp_path, label=None), require_labels=True)


def test_label_gate_accepts_label_reason_and_evidence(tmp_path: Path) -> None:
    summary = validate(_export(tmp_path, label="cannot_determine"), require_labels=True)
    assert summary["labels"] == 1
    assert summary["cannot_determine"] == 1
