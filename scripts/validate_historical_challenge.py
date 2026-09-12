#!/usr/bin/env python3
"""Validate the historical challenge cohort and its independent label slots."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ALLOWED_LABELS = frozenset({"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"})
SLOTS = ("reviewer_a", "reviewer_b", "adjudicated")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REVIEWER_ITEM_KEYS = frozenset(
    {"case_id", "city", "matter_id", "review_pair", "review", "case_payload"}
)
REVIEW_PAIR_KEYS = frozenset(
    {
        "previous_event_item_id",
        "current_event_item_id",
        "previous_event_date",
        "current_event_date",
        "previous_title",
        "current_title",
        "previous_placement",
        "current_placement",
    }
)


def _text(value: object, context: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{context} must be non-empty text")
        return None
    return value.strip()


def _optional_text(value: object, context: str, errors: list[str]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        errors.append(f"{context} must be text or null")


def _object(value: object, context: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{context} must be an object")
        return None
    return value


def _positive_integer(value: object, context: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        errors.append(f"{context} must be a positive integer")


def _hash(value: object, context: str, errors: list[str], *, optional: bool = False) -> None:
    if optional and value is None:
        return
    item = _text(value, context, errors)
    if item is not None and SHA256_PATTERN.fullmatch(item) is None:
        errors.append(f"{context} must be a lowercase SHA-256 hex digest")


def _evidence(value: object, context: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{context} must contain at least one primary source")
        return
    for index, raw in enumerate(value):
        item = _object(raw, f"{context}[{index}]", errors)
        if item is None:
            continue
        url = _text(item.get("url"), f"{context}[{index}].url", errors)
        if url is not None and not url.startswith(("https://", "http://")):
            errors.append(f"{context}[{index}].url must be an HTTP(S) URL")
        _text(item.get("captured_at"), f"{context}[{index}].captured_at", errors)
        page = item.get("page_number")
        if page is not None and (
            isinstance(page, bool) or not isinstance(page, int) or page < 1
        ):
            errors.append(f"{context}[{index}].page_number must be a positive integer")


def _review_slot(
    value: object,
    context: str,
    errors: list[str],
    *,
    require_label: bool,
) -> bool:
    slot = _object(value, context, errors)
    if slot is None:
        return False
    label = slot.get("label")
    if label is None:
        if require_label:
            errors.append(f"{context}.label is not filled")
        return False
    if not isinstance(label, str) or label not in ALLOWED_LABELS:
        errors.append(f"{context}.label is invalid")
        return False
    _text(slot.get("reason"), f"{context}.reason", errors)
    _evidence(slot.get("evidence"), f"{context}.evidence", errors)
    return True


def validate(path: Path, *, require_labels: bool) -> dict[str, int | str]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read historical challenge cohort {path}: {error}") from error
    errors: list[str] = []
    root = _object(decoded, "historical challenge cohort", errors)
    if root is None:
        raise ValueError("; ".join(errors))
    if root.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    status = _text(root.get("status"), "status", errors)
    if status is not None and status not in {
        "awaiting_independent_labels",
        "awaiting_adjudication",
        "labels_complete",
    }:
        errors.append("status is invalid")
    city = _text(root.get("city"), "city", errors)

    source_snapshot = _object(root.get("source_snapshot"), "source_snapshot", errors)
    if source_snapshot is not None:
        _text(source_snapshot.get("code_revision"), "source_snapshot.code_revision", errors)
        _text(source_snapshot.get("created_at_utc"), "source_snapshot.created_at_utc", errors)
        for field in (
            "database_sha256",
            "evidence_manifest_sha256",
            "evidence_chain_sha256",
            "evidence_integrity_root",
        ):
            _hash(
                source_snapshot.get(field),
                f"source_snapshot.{field}",
                errors,
                optional=field.startswith("evidence_"),
            )
        if "source_paths" in source_snapshot:
            errors.append("source_snapshot must not expose source_paths in the reviewer packet")

    if "selection" in root:
        errors.append("selection metadata must be withheld from the reviewer packet")
    blind_review = _object(root.get("blind_review"), "blind_review", errors)
    if blind_review is not None:
        if blind_review.get("answer_key_withheld") is not True:
            errors.append("blind_review.answer_key_withheld must be true")
        _positive_integer(blind_review.get("shuffle_seed"), "blind_review.shuffle_seed", errors)
        _text(blind_review.get("order"), "blind_review.order", errors)
        _text(blind_review.get("review_unit"), "blind_review.review_unit", errors)

    raw_items = root.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        errors.append("items must be a non-empty list")
        raw_items = []
    case_ids: set[str] = set()
    labels = {slot: 0 for slot in SLOTS}
    pair_keys: frozenset[str] | None = None
    for index, raw_item in enumerate(raw_items):
        item = _object(raw_item, f"items[{index}]", errors)
        if item is None:
            continue
        unexpected_keys = set(item) - REVIEWER_ITEM_KEYS
        missing_keys = REVIEWER_ITEM_KEYS - set(item)
        if unexpected_keys:
            errors.append(
                f"items[{index}] contains withheld or unknown fields: "
                f"{sorted(unexpected_keys)}"
            )
        if missing_keys:
            errors.append(f"items[{index}] is missing fields: {sorted(missing_keys)}")
        for forbidden in ("cohort_role", "selection_reasons", "selected_pairs", "selection_index"):
            if forbidden in item:
                errors.append(f"items[{index}] exposes withheld field {forbidden}")
        case_id = _text(item.get("case_id"), f"items[{index}].case_id", errors)
        if case_id is not None:
            if case_id in case_ids:
                errors.append(f"duplicate case_id {case_id}")
            case_ids.add(case_id)
        if city is not None and item.get("city") != city:
            errors.append(f"items[{index}].city does not match the cohort city")
        matter_id = item.get("matter_id")
        _positive_integer(matter_id, f"items[{index}].matter_id", errors)
        pair = _object(item.get("review_pair"), f"items[{index}].review_pair", errors)
        if pair is not None:
            current_pair_keys = frozenset(pair)
            if current_pair_keys != REVIEW_PAIR_KEYS:
                errors.append(
                    f"items[{index}].review_pair must have the same neutral fields for every case"
                )
            if pair_keys is None:
                pair_keys = current_pair_keys
            elif pair_keys != current_pair_keys:
                errors.append("review_pair fields are not structurally identical across cases")
            _positive_integer(
                pair.get("previous_event_item_id"),
                f"items[{index}].review_pair.previous_event_item_id",
                errors,
            )
            _positive_integer(
                pair.get("current_event_item_id"),
                f"items[{index}].review_pair.current_event_item_id",
                errors,
            )
            _optional_text(
                pair.get("previous_event_date"),
                f"items[{index}].review_pair.previous_event_date",
                errors,
            )
            _optional_text(
                pair.get("current_event_date"),
                f"items[{index}].review_pair.current_event_date",
                errors,
            )
            _optional_text(
                pair.get("previous_title"),
                f"items[{index}].review_pair.previous_title",
                errors,
            )
            _optional_text(
                pair.get("current_title"),
                f"items[{index}].review_pair.current_title",
                errors,
            )
            _optional_text(
                pair.get("previous_placement"),
                f"items[{index}].review_pair.previous_placement",
                errors,
            )
            _optional_text(
                pair.get("current_placement"),
                f"items[{index}].review_pair.current_placement",
                errors,
            )
        payload = _object(item.get("case_payload"), f"items[{index}].case_payload", errors)
        if payload is not None:
            appearances = payload.get("appearances")
            if not isinstance(appearances, list) or not appearances:
                errors.append(f"items[{index}].case_payload.appearances must be non-empty")
        review = _object(item.get("review"), f"items[{index}].review", errors)
        if review is None:
            continue
        for slot in SLOTS:
            if _review_slot(
                review.get(slot),
                f"items[{index}].review.{slot}",
                errors,
                require_label=require_labels,
            ):
                labels[slot] += 1

    if require_labels and status != "labels_complete":
        errors.append("status must be labels_complete when labels are required")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "city": city or "",
        "items": len(case_ids),
        "reviewer_a_labels": labels["reviewer_a"],
        "reviewer_b_labels": labels["reviewer_b"],
        "adjudicated_labels": labels["adjudicated"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Page 47 historical challenge cohort")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--require-labels",
        action="store_true",
        help="require both independent labels and an adjudicated label for every case",
    )
    args = parser.parse_args()
    try:
        summary = validate(args.input, require_labels=args.require_labels)
    except ValueError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
