#!/usr/bin/env python3
"""Validate a Page 47 four-arm comparison artifact."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ARMS = frozenset({"keyword", "search", "latest_document", "page47"})
STATES = frozenset({"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"})
DIMENSIONS = frozenset({"title", "placement", "substance", "timing"})
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


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


def _non_negative_integer(value: object, context: str, errors: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        errors.append(f"{context} must be a non-negative integer")


def _hash(value: object, context: str, errors: list[str]) -> None:
    item = _text(value, context, errors)
    if item is not None and SHA256_PATTERN.fullmatch(item) is None:
        errors.append(f"{context} must be a lowercase SHA-256 hex digest")


def _text_list(value: object, context: str, errors: list[str]) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        errors.append(f"{context} must be a text list")


def _diagnostics(value: object, context: str, errors: list[str]) -> None:
    diagnostics = _object(value, context, errors)
    if diagnostics is None:
        return
    dimensions = _object(diagnostics.get("dimensions"), f"{context}.dimensions", errors)
    if dimensions is None:
        return
    for dimension in DIMENSIONS:
        raw_dimension = _object(
            dimensions.get(dimension), f"{context}.dimensions.{dimension}", errors
        )
        if raw_dimension is None:
            continue
        for field in (
            "comparable_pairs",
            "directional_pairs",
            "neutral_pairs",
            "unavailable_pairs",
        ):
            if field in raw_dimension:
                _non_negative_integer(
                    raw_dimension.get(field),
                    f"{context}.dimensions.{dimension}.{field}",
                    errors,
                )
    _text_list(diagnostics.get("coverage_gaps"), f"{context}.coverage_gaps", errors)
    _text_list(diagnostics.get("reason_codes"), f"{context}.reason_codes", errors)
    _text_list(
        diagnostics.get("abstention_reason_codes"),
        f"{context}.abstention_reason_codes",
        errors,
    )
    skeptic = _object(diagnostics.get("skeptic"), f"{context}.skeptic", errors)
    if skeptic is not None:
        status = _text(skeptic.get("status"), f"{context}.skeptic.status", errors)
        if status is not None and status not in {"not_run", "reviewed"}:
            errors.append(f"{context}.skeptic.status is invalid")
        rejected_count = skeptic.get("rejected_count")
        if rejected_count is not None:
            _non_negative_integer(
                rejected_count, f"{context}.skeptic.rejected_count", errors
            )
    if not isinstance(diagnostics.get("pair_details"), list):
        errors.append(f"{context}.pair_details must be a list")


def validate(path: Path) -> dict[str, int | str]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read comparison artifact {path}: {error}") from error
    errors: list[str] = []
    root = _object(decoded, "comparison artifact", errors)
    if root is None:
        raise ValueError("; ".join(errors))
    if root.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    if root.get("status") != "review_required":
        errors.append("status must remain review_required until the outputs are checked")
    inputs = _object(root.get("evaluation_inputs"), "evaluation_inputs", errors)
    if inputs is not None:
        _text(inputs.get("code_revision"), "evaluation_inputs.code_revision", errors)
        _text(
            inputs.get("evaluation_timestamp_utc"),
            "evaluation_inputs.evaluation_timestamp_utc",
            errors,
        )
        for field in (
            "evaluation_manifest_sha256",
            "presentation_config_sha256",
            "record_database_sha256",
            "evidence_manifest_sha256",
            "evidence_chain_sha256",
            "evidence_integrity_root",
            "matter_ids_sha256",
        ):
            _hash(inputs.get(field), f"evaluation_inputs.{field}", errors)
        if "source_paths" in inputs:
            source_paths = _object(
                inputs.get("source_paths"), "evaluation_inputs.source_paths", errors
            )
            if source_paths is not None:
                for field in (
                    "evaluation_manifest",
                    "presentation_config",
                    "record_database",
                    "evidence_root",
                ):
                    _text(
                        source_paths.get(field),
                        f"evaluation_inputs.source_paths.{field}",
                        errors,
                    )
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
            if arm_name == "page47" and state not in STATES:
                errors.append(
                    f"cases[{index}].arms[{arm_index}].page47.state must be a valid state"
                )
            if not isinstance(arm.get("surfaced"), bool):
                errors.append(f"cases[{index}].arms[{arm_index}].surfaced must be boolean")
            signals = arm.get("signals")
            if not isinstance(signals, list) or not all(isinstance(item, str) for item in signals):
                errors.append(f"cases[{index}].arms[{arm_index}].signals must be text list")
            _evidence(arm.get("evidence"), f"cases[{index}].arms[{arm_index}].evidence", errors)
            _text(arm.get("reason"), f"cases[{index}].arms[{arm_index}].reason", errors)
            if arm_name == "page47":
                _diagnostics(
                    arm.get("diagnostics"),
                    f"cases[{index}].arms[{arm_index}].diagnostics",
                    errors,
                )
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
