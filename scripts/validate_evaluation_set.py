#!/usr/bin/env python3
"""Validate the hand-labelled evaluation export without calculating metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ALLOWED_LABELS = frozenset({"yes", "no", "cannot_determine"})


def _text(value: object, context: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{context} must be non-empty text")
        return None
    return value.strip()


def _object(value: object, context: str, errors: list[str]) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        errors.append(f"{context} must be an object")
        return None
    return value


def _gold_evidence(value: object, context: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{context} must contain at least one primary record")
        return
    for index, raw in enumerate(value):
        evidence = _object(raw, f"{context}[{index}]", errors)
        if evidence is None:
            continue
        url = _text(evidence.get("url"), f"{context}[{index}].url", errors)
        if url is not None and not url.startswith(("https://", "http://")):
            errors.append(f"{context}[{index}].url must be an HTTP(S) URL")
        _text(evidence.get("captured_at"), f"{context}[{index}].captured_at", errors)
        page = evidence.get("page_number")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int) or page < 1):
            errors.append(f"{context}[{index}].page_number must be a positive integer")


def validate(path: Path, *, require_labels: bool) -> dict[str, int | str]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read evaluation export {path}: {error}") from error
    errors: list[str] = []
    root = _object(decoded, "evaluation export", errors)
    if root is None:
        raise ValueError("; ".join(errors))

    city = _text(root.get("city"), "city", errors)
    raw_items = root.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        errors.append("items must be a non-empty list")
        raw_items = []
    raw_gold_ids = root.get("gold_case_ids")
    if not isinstance(raw_gold_ids, list) or not raw_gold_ids:
        errors.append("gold_case_ids must be a non-empty list")
        raw_gold_ids = []
    gold_ids: list[str] = []
    for index, value in enumerate(raw_gold_ids):
        item_id = _text(value, f"gold_case_ids[{index}]", errors)
        if item_id is not None:
            gold_ids.append(item_id)
    if len(set(gold_ids)) != len(gold_ids):
        errors.append("gold_case_ids must be unique")

    items: dict[str, dict[str, Any]] = {}
    for index, raw_item in enumerate(raw_items):
        item = _object(raw_item, f"items[{index}]", errors)
        if item is None:
            continue
        case_id = _text(item.get("case_id"), f"items[{index}].case_id", errors)
        if case_id is None:
            continue
        if case_id in items:
            errors.append(f"items contains duplicate case_id {case_id}")
        else:
            items[case_id] = item
        if city is not None and item.get("city") != city:
            errors.append(f"items[{index}].city does not match the export city")

    missing_gold = [case_id for case_id in gold_ids if case_id not in items]
    if missing_gold:
        errors.append(f"gold_case_ids missing from items: {', '.join(missing_gold[:3])}")
    gold_set = set(gold_ids)
    labels = 0
    cannot_determine = 0
    for case_id in gold_ids:
        item = items.get(case_id)
        if item is None:
            continue
        label = item.get("gold_label")
        if label is None:
            if require_labels:
                errors.append(f"{case_id}.gold_label is not filled")
            continue
        if label not in ALLOWED_LABELS:
            errors.append(f"{case_id}.gold_label is invalid")
            continue
        labels += 1
        if label == "cannot_determine":
            cannot_determine += 1
        _text(item.get("gold_label_reason"), f"{case_id}.gold_label_reason", errors)
        _gold_evidence(item.get("gold_evidence"), f"{case_id}.gold_evidence", errors)

    if require_labels and labels != len(gold_set):
        errors.append(f"expected {len(gold_set)} gold labels, found {labels}")
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "city": city or "",
        "items": len(items),
        "gold_items": len(gold_set),
        "labels": labels,
        "cannot_determine": cannot_determine,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Page 47 evaluation labels")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--allow-unlabeled",
        action="store_true",
        help="validate the export shape while gold labels are still pending",
    )
    args = parser.parse_args()
    try:
        summary = validate(args.input, require_labels=not args.allow_unlabeled)
    except ValueError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
