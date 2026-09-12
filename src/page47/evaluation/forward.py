"""Verify that a directional finding was based on two Page 47 captures."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from page47.analysis.case import MatterCase, load_matter_case
from page47.analysis.drift import (
    PresentationConfig,
    PresentationObservation,
    compare_all_appearances,
    load_presentation_config,
)
from page47.records.store import RecordStore
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value
from page47.snapshotter.store import SnapshotStore


def _directional(value: object) -> bool:
    return value in {"clearer", "less_clear", "mixed"}


def _time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _verified_forward_evidence(observation: PresentationObservation) -> bool:
    evidence = observation.evidence
    if len(evidence) < 2:
        return False
    if any(
        link.origin != "observed_by_page47"
        or link.capture_key is None
        or link.response_sha256 is None
        for link in evidence
    ):
        return False
    if len({link.capture_key for link in evidence}) != len(evidence):
        return False
    earlier = _time(evidence[0].captured_at)
    later = _time(evidence[-1].captured_at)
    return (
        earlier is not None
        and later is not None
        and earlier < later
        and evidence[-1].collector_run_id is not None
    )


def forward_case_candidates(
    case: MatterCase,
    config: PresentationConfig,
) -> list[JSONObject]:
    """Return directional comparisons whose evidence is fully forward-observed."""

    candidates: list[JSONObject] = []
    ledger = compare_all_appearances(case, config)
    for index, comparison in enumerate(ledger.comparisons):
        if not _directional(comparison.state):
            continue
        observed = [
            observation
            for observation in comparison.observations
            if observation.direction in {"clearer", "less_clear"}
            and _verified_forward_evidence(observation)
        ]
        if not observed:
            continue
        observation_json: list[JSONValue] = []
        for item in observed:
            value = as_json_value(item.as_json())
            if not isinstance(value, dict):
                raise ValueError("Forward observation did not produce an object")
            observation_json.append(value)
        candidates.append(
            {
                "comparison_index": index,
                "matter_id": case.matter_id,
                "state": comparison.state,
                "previous_event_item_id": comparison.previous_event_item_id,
                "current_event_item_id": comparison.current_event_item_id,
                "observations": observation_json,
                "ready_for_investigation": True,
            }
        )
    return candidates


def scan_forward_observations(
    *,
    city: str,
    database: Path,
    evidence_root: Path,
    presentation_path: Path,
) -> JSONObject:
    """Scan the normalized store without inventing or fabricating a positive case."""

    snapshots = SnapshotStore(evidence_root)
    integrity_root = snapshots.verify_integrity()
    config = load_presentation_config(presentation_path)
    candidates: list[JSONValue] = []
    checked = 0
    skipped_orphan_matter_count = 0
    with RecordStore(database) as records:
        rows = records.connection.execute(
            "SELECT DISTINCT a.matter_id FROM appearances a "
            "JOIN matters m ON m.matter_id = a.matter_id "
            "WHERE a.matter_id IS NOT NULL ORDER BY a.matter_id"
        ).fetchall()
        orphan_row = records.connection.execute(
            "SELECT COUNT(DISTINCT a.matter_id) FROM appearances a "
            "LEFT JOIN matters m ON m.matter_id = a.matter_id "
            "WHERE a.matter_id IS NOT NULL AND m.matter_id IS NULL"
        ).fetchone()
        if orphan_row is None or not isinstance(orphan_row[0], int):
            raise ValueError("Could not count orphaned appearances")
        skipped_orphan_matter_count = orphan_row[0]
        for row in rows:
            matter_id = row[0]
            if isinstance(matter_id, bool) or not isinstance(matter_id, int) or matter_id < 1:
                raise ValueError("Stored forward-observation matter ID was invalid")
            checked += 1
            case = load_matter_case(records, city, matter_id, evidence_root)
            candidates.extend(forward_case_candidates(case, config))
    return {
        "schema_version": 1,
        "city": city,
        "status": "forward_positive_case_found" if candidates else "awaiting_real_transition",
        "case_count_checked": checked,
        "skipped_orphan_matter_count": skipped_orphan_matter_count,
        "candidate_count": len(candidates),
        "integrity_root": integrity_root,
        "candidates": candidates,
        "definition": (
            "A candidate requires a directional comparison whose supporting evidence "
            "links each carry distinct Page 47 capture metadata. This report does not "
            "claim a positive case until the collector actually records one."
        ),
    }
