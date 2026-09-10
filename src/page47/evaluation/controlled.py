"""Controlled directional evaluation for the deterministic presentation comparator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from page47.analysis.case import (
    AppearanceRecord,
    AttachmentRecord,
    MatterCase,
    MatterRecord,
    PageAnchor,
)
from page47.analysis.drift import DriftState, EvidenceLink, load_presentation_config
from page47.evaluation.comparison import _arm_results
from page47.records.store import SourceReference
from page47.snapshotter.config import JSONObject, JSONValue


@dataclass(frozen=True, slots=True)
class ControlledCase:
    case_id: str
    scenario: str
    expected_state: DriftState
    keyword_expected_surface: bool
    skeptic_expected: str
    reversal_of: str | None
    matter: MatterCase


def _source(case_id: str, path: str) -> SourceReference:
    return SourceReference(
        "controlled",
        f"https://controlled.example/page47/{case_id}/{path}",
        "2026-09-10T00:00:00Z",
    )


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be non-empty text")
    return value.strip()


def _optional_text(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _text(value, context)


def _attachment(
    case_id: str,
    appearance_index: int,
    attachment_index: int,
    raw: object,
) -> AttachmentRecord:
    if not isinstance(raw, dict):
        raise ValueError("Controlled attachment must be an object")
    name = _optional_text(raw.get("name"), "controlled attachment name")
    url_path = _text(
        raw.get("url", f"attachment-{appearance_index}-{attachment_index}.pdf"),
        "controlled attachment URL",
    )
    anchor_values = raw.get("anchors", [])
    if not isinstance(anchor_values, list) or not all(
        isinstance(item, str) for item in anchor_values
    ):
        raise ValueError("Controlled attachment anchors must be a text list")
    source = _source(case_id, f"appearance-{appearance_index}/{url_path}")
    anchors = tuple(
        PageAnchor(
            kind="controlled_subject",
            value=value,
            page_number=1,
            start_character=0,
            end_character=len(value),
            excerpt=value,
            source=source,
        )
        for value in anchor_values
    )
    return AttachmentRecord(
        attachment_id=appearance_index * 100 + attachment_index,
        matter_id=1,
        name=name,
        url=url_path,
        version="1",
        last_modified_utc=None,
        first_observed_by_us="2026-09-10T00:00:00Z",
        content_hash=_optional_text(raw.get("content_hash"), "controlled content hash"),
        supporting_document=True,
        source=source,
        reading_status="candidate",
        page_count=1,
        anchors=anchors,
        reading_source=source if anchors else None,
        evidence_root=Path("/tmp/page47-controlled-evidence"),
    )


def _case(raw: object) -> ControlledCase:
    if not isinstance(raw, dict):
        raise ValueError("Controlled case must be an object")
    case_id = _text(raw.get("case_id"), "controlled case_id")
    scenario = _text(raw.get("scenario"), f"{case_id}.scenario")
    expected = _text(raw.get("expected_state"), f"{case_id}.expected_state")
    if expected not in {"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"}:
        raise ValueError(f"{case_id}.expected_state was invalid")
    keyword_surface = raw.get("keyword_expected_surface")
    if not isinstance(keyword_surface, bool):
        raise ValueError(f"{case_id}.keyword_expected_surface must be boolean")
    skeptic_expected = _text(
        raw.get("skeptic_expected", "not_applicable"),
        f"{case_id}.skeptic_expected",
    )
    if skeptic_expected not in {"reject", "retain", "abstain", "not_applicable"}:
        raise ValueError(f"{case_id}.skeptic_expected was invalid")
    reversal_of = _optional_text(raw.get("reversal_of"), f"{case_id}.reversal_of")
    raw_appearances = raw.get("appearances")
    if not isinstance(raw_appearances, list) or not raw_appearances:
        raise ValueError(f"{case_id}.appearances must be non-empty")
    appearances: list[AppearanceRecord] = []
    for index, raw_appearance in enumerate(raw_appearances):
        if not isinstance(raw_appearance, dict):
            raise ValueError(f"{case_id}.appearances[{index}] must be an object")
        title = _optional_text(raw_appearance.get("title"), f"{case_id}.title")
        placement = raw_appearance.get("placement")
        if placement is not None and placement not in {"regular", "consent"}:
            raise ValueError(f"{case_id}.appearances[{index}].placement was invalid")
        raw_attachments = raw_appearance.get("attachments", [])
        if not isinstance(raw_attachments, list):
            raise ValueError(f"{case_id}.appearances[{index}].attachments must be a list")
        source = _source(case_id, f"appearance-{index}/record")
        pdf_source = _source(case_id, f"appearance-{index}/agenda") if placement else None
        attachments = tuple(
            _attachment(case_id, index + 1, attachment_index + 1, raw_attachment)
            for attachment_index, raw_attachment in enumerate(raw_attachments)
        )
        appearances.append(
            AppearanceRecord(
                event_item_id=index + 1,
                matter_id=1,
                event_id=index + 1,
                event_date=f"2026-09-{index + 1:02d}T00:00:00Z",
                body_id=1,
                body_name="Controlled body",
                title_as_presented=title,
                consent_value=None,
                pdf_placement=placement,
                pdf_evidence_pages=(1,) if placement else (),
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
                source=source,
                pdf_source=pdf_source,
                attachments=attachments,
            )
        )
    matter_source = _source(case_id, "matter")
    matter = MatterRecord(
        matter_id=1,
        file_number=case_id,
        matter_name=None,
        current_title=appearances[-1].title_as_presented,
        type_name="Controlled",
        status_name="Test fixture",
        body_id=1,
        body_name="Controlled body",
        intro_date=None,
        agenda_date=None,
        version="1",
        last_modified_utc=None,
        source=matter_source,
    )
    return ControlledCase(
        case_id=case_id,
        scenario=scenario,
        expected_state=cast(DriftState, expected),
        keyword_expected_surface=keyword_surface,
        skeptic_expected=skeptic_expected,
        reversal_of=reversal_of,
        matter=MatterCase("Controlled city", matter, tuple(appearances)),
    )


def load_controlled_cases(path: Path) -> tuple[ControlledCase, ...]:
    decoded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or decoded.get("schema_version") != 1:
        raise ValueError("Controlled evaluation fixture must have schema_version 1")
    raw_cases = decoded.get("cases")
    if not isinstance(raw_cases, list) or len(raw_cases) < 24:
        raise ValueError("Controlled evaluation fixture must contain at least 24 cases")
    cases = tuple(_case(raw_case) for raw_case in raw_cases)
    case_ids = {item.case_id for item in cases}
    if len(case_ids) != len(cases):
        raise ValueError("Controlled evaluation case IDs must be unique")
    for item in cases:
        if item.reversal_of is not None and item.reversal_of not in case_ids:
            raise ValueError(f"{item.case_id}.reversal_of references an unknown case")
    return cases


def _evidence_json(items: tuple[EvidenceLink, ...]) -> list[JSONValue]:
    output: list[JSONValue] = []
    for item in items:
        output.append(
            {
                "label": item.label,
                "url": item.url,
                "captured_at": item.captured_at,
                "page_number": item.page_number,
            }
        )
    return output


def run_controlled(
    *, fixture_path: Path, presentation_path: Path, output_path: Path
) -> JSONObject:
    config = load_presentation_config(presentation_path)
    cases = load_controlled_cases(fixture_path)
    rows: list[JSONValue] = []
    page47_correct = 0
    keyword_correct = 0
    reversal_pairs: list[tuple[str, str]] = []
    skeptic_expectations: dict[str, int] = {
        "reject": 0,
        "retain": 0,
        "abstain": 0,
        "not_applicable": 0,
    }
    by_id = {item.case_id: item for item in cases}
    actual_states: dict[str, DriftState] = {}
    for item in cases:
        arms = _arm_results(item.matter, config)
        page47 = next(result for result in arms if result.arm == "page47")
        keyword = next(result for result in arms if result.arm == "keyword")
        actual_state = page47.state
        if actual_state is None:
            raise ValueError(f"{item.case_id} Page 47 arm returned no state")
        actual_states[item.case_id] = actual_state
        page47_correct += actual_state == item.expected_state
        keyword_correct += keyword.surfaced == item.keyword_expected_surface
        skeptic_expectations[item.skeptic_expected] += 1
        arm_json: list[JSONValue] = []
        for result in arms:
            arm_json.append(result.as_json())
        rows.append(
            {
                "case_id": item.case_id,
                "scenario": item.scenario,
                "expected_state": item.expected_state,
                "keyword_expected_surface": item.keyword_expected_surface,
                "skeptic_expected": item.skeptic_expected,
                "arms": arm_json,
            }
        )
    for item in cases:
        if item.reversal_of is None or item.case_id <= item.reversal_of:
            continue
        other = by_id[item.reversal_of]
        first = actual_states[other.case_id]
        second = actual_states[item.case_id]
        expected_reverse = {
            ("clearer", "less_clear"),
            ("less_clear", "clearer"),
        }
        if (first, second) in expected_reverse:
            reversal_pairs.append((other.case_id, item.case_id))
    skeptic_expectation_output: JSONObject = {
        key: value for key, value in skeptic_expectations.items()
    }
    output: JSONObject = {
        "schema_version": 1,
        "fixture": str(fixture_path),
        "case_count": len(cases),
        "cases": rows,
        "metrics": {
            "page47_direction_accuracy": page47_correct / len(cases),
            "page47_correct": page47_correct,
            "keyword_surface_accuracy": keyword_correct / len(cases),
            "keyword_surface_correct": keyword_correct,
            "reversal_pairs_checked": sum(
                1
                for item in cases
                if item.reversal_of is not None and item.case_id > item.reversal_of
            ),
            "reversal_pairs_correct": len(reversal_pairs),
            "reversal_pairs": [list(pair) for pair in reversal_pairs],
            "skeptic_expectation_counts": skeptic_expectation_output,
            "skeptic_note": (
                "These expectations are fixture annotations for the separate Skeptic review; "
                "this deterministic comparator run does not invoke a model review."
            ),
        },
        "status": "review_required",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
