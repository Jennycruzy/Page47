#!/usr/bin/env python3
"""Validate the withheld selection answer key for the historical cohort."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

ROLES = frozenset({"candidate", "control"})
SNAPSHOT_FIELDS = (
    "code_revision",
    "created_at_utc",
    "database_sha256",
    "evidence_manifest_sha256",
    "evidence_chain_sha256",
    "evidence_integrity_root",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read answer key {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError("Answer key must contain an object")
    return decoded


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _positive(value: object, context: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{context} must be a positive integer")


def validate(path: Path, packet: Path | None = None) -> dict[str, int | str]:
    key = _load(path)
    if key.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    if key.get("artifact") != "page47_historical_challenge_answer_key":
        raise ValueError("artifact type is invalid")
    if key.get("status") != "withheld_from_reviewers":
        raise ValueError("status must remain withheld_from_reviewers")

    snapshot = key.get("source_snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("source_snapshot must be an object")
    for field in SNAPSHOT_FIELDS:
        if not isinstance(snapshot.get(field), str) or not snapshot[field].strip():
            raise ValueError(f"source_snapshot.{field} must be non-empty text")
    source_paths = snapshot.get("source_paths")
    if not isinstance(source_paths, dict):
        raise ValueError("source_snapshot.source_paths must be an object")
    for field, value in source_paths.items():
        if not isinstance(value, str) or value.startswith("/"):
            raise ValueError(f"source_snapshot.source_paths.{field} must be a relative path")

    selection = key.get("selection")
    if not isinstance(selection, dict):
        raise ValueError("selection must be an object")
    for field in ("candidate_count", "control_count", "eligible_review_matters"):
        _positive(selection.get(field), f"selection.{field}")
    excluded = selection.get("excluded_recurring_containers")
    if not isinstance(excluded, list):
        raise ValueError("selection.excluded_recurring_containers must be a list")
    if selection.get("excluded_recurring_container_count") != len(excluded):
        raise ValueError("excluded container count does not match its list")
    excluded_ids: set[int] = set()
    for index, item in enumerate(excluded):
        if not isinstance(item, dict):
            raise ValueError(f"selection.excluded_recurring_containers[{index}] must be an object")
        matter_id = item.get("matter_id")
        _positive(matter_id, f"excluded container {index}.matter_id")
        if matter_id in excluded_ids:
            raise ValueError("excluded container matter IDs must be unique")
        excluded_ids.add(matter_id)
        reason = item.get("reason")
        if not isinstance(reason, str) or not reason.startswith("excluded_recurring_"):
            raise ValueError(f"excluded container {index}.reason is invalid")

    raw_items = key.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("items must be a non-empty list")
    case_ids: set[str] = set()
    role_counts = {"candidate": 0, "control": 0}
    city = key.get("city")
    if not isinstance(city, str) or not city.strip():
        raise ValueError("city must be non-empty text")
    for index, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"items[{index}] must be an object")
        expected_keys = {
            "case_id",
            "city",
            "matter_id",
            "cohort_role",
            "selection_reasons",
            "selected_pairs",
            "review_pair",
        }
        if set(raw_item) != expected_keys:
            raise ValueError(f"items[{index}] has an invalid field shape")
        case_id = raw_item.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in case_ids:
            raise ValueError(f"items[{index}] has an invalid or duplicate case_id")
        case_ids.add(case_id)
        if raw_item.get("city") != city:
            raise ValueError(f"items[{index}] city does not match the answer key")
        matter_id = raw_item.get("matter_id")
        _positive(matter_id, f"items[{index}].matter_id")
        if matter_id in excluded_ids:
            raise ValueError(f"items[{index}] contains an excluded container")
        role = raw_item.get("cohort_role")
        if role not in ROLES:
            raise ValueError(f"items[{index}].cohort_role is invalid")
        role_counts[role] += 1
        reasons = raw_item.get("selection_reasons")
        pairs = raw_item.get("selected_pairs")
        if not isinstance(reasons, list) or not all(isinstance(item, str) for item in reasons):
            raise ValueError(f"items[{index}].selection_reasons must be a text list")
        if not isinstance(pairs, list):
            raise ValueError(f"items[{index}].selected_pairs must be a list")
        if role == "candidate" and not pairs:
            raise ValueError(f"items[{index}] candidate has no selected pair")
        if role == "control" and pairs:
            raise ValueError(f"items[{index}] control has selected pairs")

    candidate_count = selection["candidate_count"]
    control_count = selection["control_count"]
    if role_counts["candidate"] != candidate_count:
        raise ValueError("candidate count does not match answer-key items")
    if role_counts["control"] != control_count:
        raise ValueError("control count does not match answer-key items")

    if packet is not None:
        expected_packet_hash = key.get("review_packet_sha256")
        if expected_packet_hash != _sha256_file(packet):
            raise ValueError("review packet does not match review_packet_sha256")
        packet_root = _load(packet)
        packet_ids = {
            item.get("case_id")
            for item in packet_root.get("items", [])
            if isinstance(item, dict)
        }
        if packet_ids != case_ids:
            raise ValueError("answer-key case IDs do not match the reviewer packet")

    return {
        "city": city,
        "items": len(case_ids),
        "candidates": role_counts["candidate"],
        "controls": role_counts["control"],
        "excluded_containers": len(excluded_ids),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the withheld Page 47 challenge answer key"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--packet", type=Path)
    args = parser.parse_args()
    try:
        summary = validate(args.input, args.packet)
    except ValueError as error:
        print(json.dumps({"valid": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
