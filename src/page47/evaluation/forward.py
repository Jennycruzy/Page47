"""Verify that a directional finding was based on two Page 47 captures."""

from __future__ import annotations

from pathlib import Path

from page47.analysis.case import MatterCase, load_matter_case
from page47.analysis.drift import (
    PresentationConfig,
    compare_all_appearances,
    load_presentation_config,
)
from page47.records.store import RecordStore
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value
from page47.snapshotter.store import SnapshotStore


def _directional(value: object) -> bool:
    return value in {"clearer", "less_clear", "mixed"}


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
            and observation.evidence
            and all(link.origin == "observed_by_page47" for link in observation.evidence)
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
    with RecordStore(database) as records:
        rows = records.connection.execute(
            "SELECT DISTINCT matter_id FROM appearances "
            "WHERE matter_id IS NOT NULL ORDER BY matter_id"
        ).fetchall()
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
        "candidate_count": len(candidates),
        "integrity_root": integrity_root,
        "candidates": candidates,
        "definition": (
            "A candidate requires a directional comparison whose supporting evidence "
            "links each carry distinct Page 47 capture metadata. This report does not "
            "claim a positive case until the collector actually records one."
        ),
    }
