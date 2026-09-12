#!/usr/bin/env python3
"""Correct a previously reviewed cohort without discarding its valid reviews."""

from __future__ import annotations

import argparse
import json
import random
from hashlib import sha256
from pathlib import Path
from typing import Any

REVIEW_PAIR_KEYS = (
    "previous_event_item_id",
    "current_event_item_id",
    "previous_event_date",
    "current_event_date",
    "previous_title",
    "current_title",
    "previous_placement",
    "current_placement",
)


def _load(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} must contain an object")
    return decoded


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _empty_review() -> dict[str, object]:
    def slot() -> dict[str, object]:
        return {"label": None, "reason": None, "evidence": []}

    return {"reviewer_a": slot(), "reviewer_b": slot(), "adjudicated": slot()}


def _pair_for_item(item: dict[str, Any]) -> tuple[dict[str, object], dict[str, object]]:
    selected_pairs = item.get("selected_pairs")
    if isinstance(selected_pairs, list) and selected_pairs:
        selected = selected_pairs[0]
        if not isinstance(selected, dict):
            raise ValueError(f"{item.get('case_id')} has an invalid selected pair")
        context = {key: selected.get(key) for key in REVIEW_PAIR_KEYS}
        if not all(isinstance(context[key], (str, type(None))) for key in REVIEW_PAIR_KEYS[2:]):
            raise ValueError(f"{item.get('case_id')} has invalid pair text fields")
        return context, selected

    payload = item.get("case_payload")
    appearances = payload.get("appearances") if isinstance(payload, dict) else None
    if not isinstance(appearances, list) or len(appearances) < 2:
        raise ValueError(f"{item.get('case_id')} has no adjacent pair")
    previous, current = appearances[0], appearances[1]
    if not isinstance(previous, dict) or not isinstance(current, dict):
        raise ValueError(f"{item.get('case_id')} has invalid appearances")
    context = {
        "previous_event_item_id": previous.get("event_item_id"),
        "current_event_item_id": current.get("event_item_id"),
        "previous_event_date": previous.get("event_date"),
        "current_event_date": current.get("event_date"),
        "previous_title": previous.get("title_as_presented"),
        "current_title": current.get("title_as_presented"),
        "previous_placement": previous.get("pdf_placement"),
        "current_placement": current.get("pdf_placement"),
    }
    return context, {**context, "attachment_ids_with_multiple_captured_hashes": [], "reasons": []}


def _safe_snapshot(raw: dict[str, Any]) -> dict[str, object]:
    fields = (
        "code_revision",
        "created_at_utc",
        "database_sha256",
        "evidence_manifest_sha256",
        "evidence_chain_sha256",
        "evidence_integrity_root",
    )
    snapshot = {field: raw.get(field) for field in fields}
    if any(not isinstance(value, str) or not value for value in snapshot.values()):
        raise ValueError("Legacy source snapshot is missing a required integrity field")
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a corrected blind packet from a previously reviewed cohort"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answer-key", type=Path, required=True)
    parser.add_argument("--exclude-matter-ids", required=True)
    parser.add_argument("--seed", type=int, default=47)
    args = parser.parse_args()

    excluded_ids = {
        int(value.strip())
        for value in args.exclude_matter_ids.split(",")
        if value.strip()
    }
    if not excluded_ids or any(value < 1 for value in excluded_ids):
        raise ValueError("exclude-matter-ids must contain positive integers")
    if args.answer_key.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError("answer-key must be outside the repository")

    legacy = _load(args.input)
    raw_items = legacy.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Legacy packet items must be a non-empty list")
    city = legacy.get("city")
    if not isinstance(city, str) or not city.strip():
        raise ValueError("Legacy packet city must be non-empty text")
    legacy_snapshot = legacy.get("source_snapshot")
    if not isinstance(legacy_snapshot, dict):
        raise ValueError("Legacy packet has no source snapshot")

    kept: list[dict[str, Any]] = []
    answer_items: list[dict[str, object]] = []
    excluded_seen: set[int] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Legacy packet item must be an object")
        matter_id = raw_item.get("matter_id")
        if not isinstance(matter_id, int) or isinstance(matter_id, bool):
            raise ValueError("Legacy packet matter IDs must be integers")
        if matter_id in excluded_ids:
            excluded_seen.add(matter_id)
            continue
        role = raw_item.get("cohort_role")
        if role not in {"candidate", "control"}:
            raise ValueError(f"{raw_item.get('case_id')} has an invalid cohort role")
        review_pair, answer_pair = _pair_for_item(raw_item)
        neutral_item = {
            "case_id": raw_item.get("case_id"),
            "city": city,
            "matter_id": matter_id,
            "review_pair": review_pair,
            "review": _empty_review(),
            "case_payload": raw_item.get("case_payload"),
        }
        kept.append(neutral_item)
        answer_items.append(
            {
                "case_id": raw_item.get("case_id"),
                "city": city,
                "matter_id": matter_id,
                "cohort_role": role,
                "selection_reasons": raw_item.get("selection_reasons", []),
                "selected_pairs": raw_item.get("selected_pairs", []),
                "review_pair": answer_pair,
            }
        )
    if excluded_seen != excluded_ids:
        missing = sorted(excluded_ids - excluded_seen)
        raise ValueError(f"Excluded matter IDs were not present in the legacy packet: {missing}")

    random.Random(args.seed).shuffle(kept)
    candidate_count = sum(
        item.get("cohort_role") == "candidate" for item in answer_items
    )
    control_count = len(answer_items) - candidate_count
    source_packet_sha256 = _sha256_file(args.input)
    source_snapshot = _safe_snapshot(legacy_snapshot)
    source_snapshot["legacy_source_packet_sha256"] = source_packet_sha256
    reviewer_packet: dict[str, object] = {
        "schema_version": 2,
        "city": city,
        "status": "awaiting_independent_labels",
        "source_snapshot": source_snapshot,
        "blind_review": {
            "answer_key_withheld": True,
            "shuffle_seed": args.seed,
            "order": (
                "Items are shuffled after removing recurring containers; order carries "
                "no cohort meaning."
            ),
            "review_unit": (
                "Each item has one fixed adjacent appearance pair for one matter-level "
                "label."
            ),
            "correction": (
                "Three recurring container records were removed from the previously "
                "reviewed cohort."
            ),
        },
        "label_policy": {
            "allowed_labels": [
                "cannot_determine",
                "clearer",
                "less_clear",
                "mixed",
                "unchanged",
            ],
            "reviewer_a": (
                "Use the retained case payload and primary evidence without reading "
                "comparator output."
            ),
            "reviewer_b": (
                "Use the retained case payload and primary evidence independently from "
                "Reviewer A."
            ),
            "adjudication": (
                "If labels disagree, record an adjudicated label with the evidence and "
                "reason."
            ),
            "evidence_requirement": (
                "Every non-pending label retains a primary source URL and capture time; "
                "add a page number when applicable."
            ),
            "cohort_warning": (
                "This corrected historical cohort is not a prevalence sample or "
                "representative accuracy estimate."
            ),
        },
        "items": kept,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(reviewer_packet, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    answer_key: dict[str, object] = {
        "schema_version": 1,
        "artifact": "page47_historical_challenge_answer_key",
        "status": "withheld_from_reviewers",
        "city": city,
        "review_packet_sha256": _sha256_file(args.output),
        "source_snapshot": source_snapshot,
        "selection": {
            "selection_mode": "corrected_legacy_cohort",
            "seed": args.seed,
            "candidate_count": candidate_count,
            "control_count": control_count,
            "eligible_review_matters": len(answer_items),
            "candidate_pool_size": candidate_count,
            "control_pool_size": control_count,
            "excluded_recurring_container_count": len(excluded_ids),
            "excluded_recurring_containers": [
                {"matter_id": matter_id, "reason": "excluded_recurring_container"}
                for matter_id in sorted(excluded_ids)
            ],
            "review_unit": "one fixed adjacent appearance pair per matter",
            "rules": [
                "retain the previously selected candidate and control matters",
                "exclude recurring agenda, minutes, and calendar container matters",
                "shuffle the corrected reviewer packet with the seed",
                "page47_result_used_for_selection: false",
            ],
            "legacy_source_note": (
                "This packet preserves completed reviews for valid matters from the prior cohort; "
                "the prior packet exposed selection metadata and is not described as blind."
            ),
        },
        "items": answer_items,
    }
    args.answer_key.parent.mkdir(parents=True, exist_ok=True)
    args.answer_key.write_text(
        json.dumps(answer_key, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "city": city,
                "items": len(answer_items),
                "candidates": candidate_count,
                "controls": control_count,
                "excluded_containers": len(excluded_ids),
                "output": str(args.output),
                "answer_key": str(args.answer_key),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
