#!/usr/bin/env python3
"""Validate a Page 47 four-arm comparison artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ARMS = frozenset({"keyword", "search", "latest_document", "page47"})
STATES = frozenset({"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"})


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


def _evidence(value: object, context: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{context} must be a list")
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


def validate(path: Path) -> dict[str, int | str]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read comparison artifact {path}: {error}") from error
    errors: list[str] = []
    root = _object(decoded, "comparison artifact", errors)
    if root is None:
        raise ValueError("; ".join(errors))
    if root.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if root.get("status") != "review_required":
        errors.append("status must remain review_required until the outputs are checked")
    city = _text(root.get("city"), "city", errors)
    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("cases must be a non-empty list")
        raw_cases = []
    case_ids: set[str] = set()
    result_count = 0
    for index, raw_case in enumerate(raw_cases):
        case = _object(raw_case, f"cases[{index}]", errors)
        if case is None:
            continue
        case_id = _text(case.get("case_id"), f"cases[{index}].case_id", errors)
        if case_id is not None:
            if case_id in case_ids:
                errors.append(f"duplicate case_id {case_id}")
            case_ids.add(case_id)
        gold_label = case.get("gold_label")
        if gold_label is not None:
            label = _text(gold_label, f"cases[{index}].gold_label", errors)
            if label is not None and label not in {"yes", "no", "cannot_determine"}:
                errors.append(f"cases[{index}].gold_label is invalid")
        raw_arms = case.get("arms")
        if not isinstance(raw_arms, list):
            errors.append(f"cases[{index}].arms must be a list")
            continue
        seen_arms: set[str] = set()
        for arm_index, raw_arm in enumerate(raw_arms):
            arm = _object(raw_arm, f"cases[{index}].arms[{arm_index}]", errors)
            if arm is None:
                continue
            arm_name = _text(
                arm.get("arm"), f"cases[{index}].arms[{arm_index}].arm", errors
            )
            if arm_name is not None:
                if arm_name not in ARMS:
                    errors.append(f"unknown comparison arm {arm_name}")
                if arm_name in seen_arms:
                    errors.append(f"duplicate comparison arm {arm_name}")
                seen_arms.add(arm_name)
            state = arm.get("state")
            if state is not None and state not in STATES:
                errors.append(f"invalid state in cases[{index}].arms[{arm_index}]")
            if not isinstance(arm.get("surfaced"), bool):
                errors.append(f"cases[{index}].arms[{arm_index}].surfaced must be boolean")
            signals = arm.get("signals")
            if not isinstance(signals, list) or not all(isinstance(item, str) for item in signals):
                errors.append(f"cases[{index}].arms[{arm_index}].signals must be text list")
            _evidence(arm.get("evidence"), f"cases[{index}].arms[{arm_index}].evidence", errors)
            _text(arm.get("reason"), f"cases[{index}].arms[{arm_index}].reason", errors)
            result_count += 1
        if seen_arms != ARMS:
            errors.append(f"cases[{index}].arms must contain each of the four comparison arms")
    declared_count = root.get("case_count")
    if declared_count != len(case_ids):
        errors.append("case_count does not match the unique case count")
    if errors:
        raise ValueError("; ".join(errors))
    return {"city": city or "", "cases": len(case_ids), "arm_results": result_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Page 47 comparison artifact")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = validate(args.input)
    except ValueError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
