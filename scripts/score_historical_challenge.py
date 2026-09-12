#!/usr/bin/env python3
"""Score Page 47 against the independently labelled historical challenge cohort."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.analysis.case import load_matter_case  # noqa: E402, I001
from page47.analysis.drift import load_presentation_config  # noqa: E402, I001
from page47.evaluation.comparison import _page47_arm  # noqa: E402, I001
from page47.records.store import RecordStore  # noqa: E402, I001
from page47.snapshotter.store import SnapshotStore  # noqa: E402, I001

STATES = ("clearer", "less_clear", "mixed", "unchanged", "cannot_determine")
SURFACED_STATES = frozenset({"clearer", "less_clear", "mixed"})
ROLES = frozenset({"candidate", "control"})
SNAPSHOT_FIELDS = (
    "code_revision",
    "created_at_utc",
    "database_sha256",
    "evidence_manifest_sha256",
    "evidence_chain_sha256",
    "evidence_integrity_root",
)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} must contain an object")
    return decoded


def _number(value: int | float | None) -> int | float | None:
    return round(value, 3) if isinstance(value, float) else value


def _metrics(actual: list[str], predicted: list[str]) -> dict[str, Any]:
    matrix: dict[str, dict[str, int]] = {
        state: {candidate: 0 for candidate in STATES} for state in STATES
    }
    for expected, observed in zip(actual, predicted, strict=True):
        matrix[expected][observed] += 1
    per_state: dict[str, dict[str, int | float | None]] = {}
    for state in STATES:
        true_positive = matrix[state][state]
        predicted_count = sum(matrix[expected][state] for expected in STATES)
        actual_count = sum(matrix[state].values())
        per_state[state] = {
            "support": actual_count,
            "predicted": predicted_count,
            "true_positive": true_positive,
            "precision": _number(
                true_positive / predicted_count if predicted_count else None
            ),
            "recall": _number(true_positive / actual_count if actual_count else None),
        }
    actual_surfaced = sum(state in SURFACED_STATES for state in actual)
    predicted_surfaced = sum(state in SURFACED_STATES for state in predicted)
    correct_surfaced = sum(
        expected in SURFACED_STATES and observed in SURFACED_STATES
        for expected, observed in zip(actual, predicted, strict=True)
    )
    actual_abstentions = actual.count("cannot_determine")
    predicted_abstentions = predicted.count("cannot_determine")
    correct_abstentions = sum(
        expected == observed == "cannot_determine"
        for expected, observed in zip(actual, predicted, strict=True)
    )
    return {
        "cases": len(actual),
        "confusion_matrix": matrix,
        "per_state": per_state,
        "surfaced_positive_precision": _number(
            correct_surfaced / predicted_surfaced if predicted_surfaced else None
        ),
        "surfaced_positive_recall": _number(
            correct_surfaced / actual_surfaced if actual_surfaced else None
        ),
        "abstention": {
            "actual": actual_abstentions,
            "predicted": predicted_abstentions,
            "correct": correct_abstentions,
            "correctness": _number(
                correct_abstentions / actual_abstentions if actual_abstentions else None
            ),
        },
    }


def _reviewer_agreement(items: list[dict[str, Any]]) -> dict[str, Any]:
    reviewer_a: list[str] = []
    reviewer_b: list[str] = []
    for item in items:
        review = item["review"]
        reviewer_a.append(review["reviewer_a"]["label"])
        reviewer_b.append(review["reviewer_b"]["label"])
    agreements = sum(left == right for left, right in zip(reviewer_a, reviewer_b, strict=True))
    total = len(items)
    observed = agreements / total if total else None
    left_counts = Counter(reviewer_a)
    right_counts = Counter(reviewer_b)
    expected = (
        sum(left_counts[state] * right_counts[state] for state in STATES) / (total * total)
        if total
        else None
    )
    kappa = None
    if observed is not None and expected is not None and expected < 1:
        kappa = (observed - expected) / (1 - expected)
    return {
        "cases": total,
        "exact_agreement": agreements,
        "agreement_rate": _number(observed),
        "cohen_kappa": _number(kappa),
        "reviewer_a_distribution": dict(sorted(left_counts.items())),
        "reviewer_b_distribution": dict(sorted(right_counts.items())),
    }


def _strings(value: object) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        output: set[str] = set()
        for item in value:
            output.update(_strings(item))
        return output
    if isinstance(value, dict):
        output = set()
        for item in value.values():
            output.update(_strings(item))
        return output
    return set()


def _provenance(items: list[dict[str, Any]]) -> dict[str, Any]:
    evidence_items = 0
    valid_evidence_items = 0
    complete_cases = 0
    for item in items:
        sources = _strings(item["case_payload"])
        adjudicated_evidence = item["review"]["adjudicated"]["evidence"]
        case_valid = True
        for evidence in adjudicated_evidence:
            evidence_items += 1
            if not isinstance(evidence, dict):
                case_valid = False
                continue
            url = evidence.get("url")
            captured_at = evidence.get("captured_at")
            valid = isinstance(url, str) and url in sources and isinstance(captured_at, str)
            if valid:
                valid_evidence_items += 1
            else:
                case_valid = False
        if case_valid:
            complete_cases += 1
    return {
        "cases": len(items),
        "cases_with_valid_adjudicated_evidence": complete_cases,
        "evidence_items": evidence_items,
        "valid_evidence_items": valid_evidence_items,
        "validity_rate": _number(
            valid_evidence_items / evidence_items if evidence_items else None
        ),
    }


def _coverage(results: list[dict[str, Any]]) -> dict[str, Any]:
    dimensions = {
        dimension: {"cases_with_comparable_pair": 0, "comparable_pairs": 0}
        for dimension in ("title", "placement", "substance", "timing")
    }
    for result in results:
        raw_dimensions = result["diagnostics"].get("dimensions", {})
        for dimension, summary in dimensions.items():
            raw = raw_dimensions.get(dimension)
            if not isinstance(raw, dict):
                continue
            comparable = raw.get("comparable_pairs")
            if not isinstance(comparable, int) or isinstance(comparable, bool):
                continue
            summary["comparable_pairs"] += comparable
            if comparable > 0:
                summary["cases_with_comparable_pair"] += 1
    return dimensions


def _verify_snapshot(
    snapshot: dict[str, Any], database: Path, evidence_root: Path
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("The answer key has no source_snapshot")
    expected_database = snapshot.get("database_sha256")
    actual_database = _sha256_file(database)
    if expected_database != actual_database:
        raise ValueError("The scoring database does not match the cohort source snapshot")
    evidence = SnapshotStore(evidence_root)
    integrity_root = evidence.verify_integrity()
    if snapshot.get("evidence_integrity_root") != integrity_root:
        raise ValueError("The scoring evidence root does not match the cohort source snapshot")
    for path_key, path in (
        ("evidence_manifest_sha256", evidence.manifest_path),
        ("evidence_chain_sha256", evidence.integrity_path),
    ):
        expected = snapshot.get(path_key)
        actual = _sha256_file(path) if path.is_file() else None
        if expected != actual:
            raise ValueError(f"The scoring {path_key} does not match the cohort source snapshot")
    return {
        "database_sha256": actual_database,
        "evidence_integrity_root": integrity_root,
        "evidence_manifest_sha256": snapshot.get("evidence_manifest_sha256"),
        "evidence_chain_sha256": snapshot.get("evidence_chain_sha256"),
    }


def _load_answer_key(
    path: Path,
    cohort_path: Path,
    cohort: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str]]:
    answer_key = _load(path)
    if answer_key.get("schema_version") != 1:
        raise ValueError("The answer key schema_version must be 1")
    if answer_key.get("artifact") != "page47_historical_challenge_answer_key":
        raise ValueError("The answer key artifact type is invalid")
    if answer_key.get("status") != "withheld_from_reviewers":
        raise ValueError("The answer key must remain marked withheld_from_reviewers")
    expected_packet_hash = answer_key.get("review_packet_sha256")
    if expected_packet_hash != _sha256_file(cohort_path):
        raise ValueError("The reviewer packet does not match the answer key")
    packet_city = cohort.get("city")
    if answer_key.get("city") != packet_city:
        raise ValueError("The answer key city does not match the reviewer packet")
    packet_snapshot = cohort.get("source_snapshot")
    answer_snapshot = answer_key.get("source_snapshot")
    if not isinstance(packet_snapshot, dict) or not isinstance(answer_snapshot, dict):
        raise ValueError("The reviewer packet and answer key must both have source snapshots")
    for field in SNAPSHOT_FIELDS:
        if packet_snapshot.get(field) != answer_snapshot.get(field):
            raise ValueError(
                f"The answer key and reviewer packet differ at source_snapshot.{field}"
            )

    raw_answer_items = answer_key.get("items")
    if not isinstance(raw_answer_items, list) or not raw_answer_items:
        raise ValueError("The answer key items are invalid")
    roles: dict[str, str] = {}
    for index, raw_item in enumerate(raw_answer_items):
        if not isinstance(raw_item, dict):
            raise ValueError(f"answer_key.items[{index}] must be an object")
        case_id = raw_item.get("case_id")
        role = raw_item.get("cohort_role")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in roles:
            raise ValueError(f"answer_key.items[{index}] has an invalid or duplicate case_id")
        if role not in ROLES:
            raise ValueError(f"answer_key.items[{index}] has an invalid cohort_role")
        roles[case_id] = role
    raw_packet_items = cohort.get("items")
    if not isinstance(raw_packet_items, list):
        raise ValueError("The reviewer packet items are invalid")
    packet_ids = {
        item.get("case_id")
        for item in raw_packet_items
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }
    if packet_ids != set(roles):
        raise ValueError("The answer key and reviewer packet contain different case IDs")
    return answer_key, roles


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the labelled Page 47 historical cohort")
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--answer-key", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()

    from validate_historical_challenge import validate  # noqa: PLC0415

    validate(args.cohort, require_labels=True)
    cohort = _load(args.cohort)
    city = cohort.get("city")
    raw_items = cohort.get("items")
    if not isinstance(city, str) or not city.strip() or not isinstance(raw_items, list):
        raise ValueError("The cohort city or items are invalid")
    if not args.code_revision.strip():
        raise ValueError("code-revision must be non-empty text")
    answer_key, roles_by_case_id = _load_answer_key(args.answer_key, args.cohort, cohort)
    answer_snapshot = answer_key.get("source_snapshot")
    if not isinstance(answer_snapshot, dict):
        raise ValueError("The answer key source snapshot is invalid")
    snapshot = _verify_snapshot(answer_snapshot, args.database, args.evidence_root)
    config = load_presentation_config(args.presentation)
    actual: list[str] = []
    predicted: list[str] = []
    roles: list[str] = []
    results: list[dict[str, Any]] = []
    with RecordStore(args.database) as records:
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"items[{index}] must be an object")
            matter_id = raw_item.get("matter_id")
            review = raw_item.get("review")
            if (
                isinstance(matter_id, bool)
                or not isinstance(matter_id, int)
                or not isinstance(review, dict)
            ):
                raise ValueError(f"items[{index}] has invalid scoring fields")
            adjudicated = review.get("adjudicated")
            if not isinstance(adjudicated, dict) or not isinstance(adjudicated.get("label"), str):
                raise ValueError(f"items[{index}] has no adjudicated label")
            case = load_matter_case(records, city, matter_id, args.evidence_root)
            arm = _page47_arm(case, config)
            if arm.state is None:
                raise ValueError(f"items[{index}] produced no Page 47 state")
            expected = adjudicated["label"]
            case_id = raw_item.get("case_id")
            if not isinstance(case_id, str) or case_id not in roles_by_case_id:
                raise ValueError(f"items[{index}] has no answer-key role")
            role = roles_by_case_id[case_id]
            actual.append(expected)
            predicted.append(arm.state)
            roles.append(role)
            result = arm.as_json()
            results.append(result)

    by_role: dict[str, dict[str, Any]] = {}
    for role in ("candidate", "control"):
        selected = [index for index, value in enumerate(roles) if value == role]
        by_role[role] = _metrics(
            [actual[index] for index in selected],
            [predicted[index] for index in selected],
        )
    output: dict[str, Any] = {
        "schema_version": 1,
        "status": "review_required",
        "city": city,
        "cohort": str(args.cohort),
        "evaluation_inputs": {
            "cohort_sha256": _sha256_file(args.cohort),
            "answer_key_sha256": _sha256_file(args.answer_key),
            "database_sha256": snapshot["database_sha256"],
            "evidence_integrity_root": snapshot["evidence_integrity_root"],
            "presentation_sha256": _sha256_file(args.presentation),
            "code_revision": args.code_revision,
        },
        "methodology": {
            "label": "Adjudicated five-way labels retained after two independent reviews.",
            "prediction": (
                "Current deterministic Page 47 comparator run over the pinned database "
                "and evidence root."
            ),
            "cohort_warning": (
                "This is a mechanically selected historical challenge cohort, not a "
                "representative accuracy estimate."
            ),
        },
        "metrics": {
            "overall": _metrics(actual, predicted),
            "by_cohort_role": by_role,
            "reviewer_agreement": _reviewer_agreement(raw_items),
            "evidence_coverage": _coverage(results),
            "provenance": _provenance(raw_items),
        },
        "cases": [
            {
                "case_id": raw_item.get("case_id"),
                "matter_id": raw_item.get("matter_id"),
                "cohort_role": raw_item.get("cohort_role"),
                "expected_state": actual[index],
                "predicted_state": predicted[index],
                "surfaced": results[index].get("surfaced"),
                "diagnostics": results[index].get("diagnostics"),
            }
            for index, raw_item in enumerate(raw_items)
            if isinstance(raw_item, dict)
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "city": city,
                "cases": len(actual),
                "output": str(args.output),
                "status": output["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
