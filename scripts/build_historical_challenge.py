#!/usr/bin/env python3
"""Build a mechanically selected, blind-review-ready historical challenge cohort."""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.analysis.case import MatterCase, load_matter_case  # noqa: E402, I001
from page47.records.store import RecordStore  # noqa: E402, I001
from page47.snapshotter.store import SnapshotStore  # noqa: E402, I001

SUPPORTED_PLACEMENTS = frozenset({"consent", "regular"})
ATTACHMENT_FIELDS = ("attachment_id", "name", "url", "content_hash", "version")
LABELS = frozenset({"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"})


@dataclass(frozen=True, slots=True)
class RawAppearance:
    event_item_id: int
    event_date: str | None
    title: str | None
    placement: str | None
    attachments: tuple[tuple[object, ...], ...]


@dataclass(frozen=True, slots=True)
class RawMatter:
    matter_id: int
    appearances: tuple[RawAppearance, ...]
    candidate_pairs: tuple[dict[str, object], ...]

    @property
    def is_candidate(self) -> bool:
        return bool(self.candidate_pairs)


def _normalise(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized or None


def _attachment_signature(appearance: RawAppearance) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted(appearance.attachments, key=lambda item: tuple(str(part) for part in item)))


def _pair_reasons(previous: RawAppearance, current: RawAppearance) -> tuple[str, ...]:
    reasons: list[str] = []
    if _normalise(previous.title) != _normalise(current.title):
        reasons.append("title_changed")
    if (
        previous.placement in SUPPORTED_PLACEMENTS
        and current.placement in SUPPORTED_PLACEMENTS
        and previous.placement != current.placement
    ):
        reasons.append("agenda_placement_changed")
    if _attachment_signature(previous) != _attachment_signature(current):
        reasons.append("attachment_set_changed")
    return tuple(reasons)


def _pair_payload(
    previous: RawAppearance,
    current: RawAppearance,
    reasons: tuple[str, ...],
) -> dict[str, object]:
    return {
        "previous_event_item_id": previous.event_item_id,
        "current_event_item_id": current.event_item_id,
        "previous_event_date": previous.event_date,
        "current_event_date": current.event_date,
        "previous_title": previous.title,
        "current_title": current.title,
        "previous_placement": previous.placement,
        "current_placement": current.placement,
        "reasons": list(reasons),
    }


def _raw_matters(connection: Any, minimum_appearances: int) -> tuple[RawMatter, ...]:
    rows = connection.execute(
        "SELECT a.matter_id, a.event_item_id, a.event_date, a.title_as_presented, "
        "a.pdf_placement, aa.attachment_id, aa.name AS attachment_name, aa.url AS attachment_url, "
        "at.content_hash AS attachment_content_hash, aa.version AS attachment_version "
        "FROM appearances AS a "
        "LEFT JOIN appearance_attachments AS aa ON aa.event_item_id = a.event_item_id "
        "LEFT JOIN attachments AS at ON at.attachment_id = aa.attachment_id "
        "WHERE a.matter_id IS NOT NULL "
        "ORDER BY a.matter_id, a.event_date, a.event_item_id, aa.attachment_id"
    ).fetchall()
    grouped: dict[int, dict[int, dict[str, object]]] = {}
    for row in rows:
        matter_id = row["matter_id"]
        event_item_id = row["event_item_id"]
        if (
            isinstance(matter_id, bool)
            or not isinstance(matter_id, int)
            or matter_id < 1
            or isinstance(event_item_id, bool)
            or not isinstance(event_item_id, int)
            or event_item_id < 1
        ):
            raise ValueError("Stored challenge record had an invalid matter or appearance ID")
        matter = grouped.setdefault(matter_id, {})
        appearance = matter.setdefault(
            event_item_id,
            {
                "event_date": row["event_date"],
                "title": row["title_as_presented"],
                "placement": row["pdf_placement"],
                "attachments": [],
            },
        )
        attachment_id = row["attachment_id"]
        if attachment_id is not None:
            attachments = appearance["attachments"]
            if not isinstance(attachments, list):
                raise ValueError("Challenge attachment accumulator was invalid")
            attachments.append(
                (
                    attachment_id,
                    row["attachment_name"],
                    row["attachment_url"],
                    row["attachment_content_hash"],
                    row["attachment_version"],
                )
            )

    output: list[RawMatter] = []
    for matter_id, raw_appearances in grouped.items():
        if len(raw_appearances) < minimum_appearances:
            continue
        appearances = tuple(
            RawAppearance(
                event_item_id=event_item_id,
                event_date=raw["event_date"] if isinstance(raw["event_date"], str) else None,
                title=raw["title"] if isinstance(raw["title"], str) else None,
                placement=raw["placement"] if isinstance(raw["placement"], str) else None,
                attachments=tuple(
                    sorted(
                        raw["attachments"],
                        key=lambda item: tuple(str(part) for part in item),
                    )
                ),
            )
            for event_item_id, raw in sorted(
                raw_appearances.items(),
                key=lambda item: (str(item[1]["event_date"] or ""), item[0]),
            )
        )
        pair_payloads: list[dict[str, object]] = []
        for previous, current in zip(appearances, appearances[1:], strict=False):
            reasons = _pair_reasons(previous, current)
            if reasons:
                pair_payloads.append(_pair_payload(previous, current, reasons))
        output.append(RawMatter(matter_id, appearances, tuple(pair_payloads)))
    return tuple(sorted(output, key=lambda item: item.matter_id))


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _source_snapshot(
    *,
    database: Path,
    evidence_root: Path,
    evidence: SnapshotStore,
    city: str,
    code_revision: str,
    selected_ids: tuple[int, ...],
    eligible_ids: tuple[int, ...],
    raw_matters: tuple[RawMatter, ...],
) -> dict[str, object]:
    manifest_sha256 = (
        _sha256_file(evidence.manifest_path) if evidence.manifest_path.is_file() else None
    )
    chain_sha256 = (
        _sha256_file(evidence.integrity_path) if evidence.integrity_path.is_file() else None
    )
    return {
        "code_revision": code_revision,
        "created_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "database_sha256": _sha256_file(database),
        "evidence_manifest_sha256": manifest_sha256,
        "evidence_chain_sha256": chain_sha256,
        "evidence_integrity_root": evidence.verify_integrity(),
        "eligible_matter_ids_sha256": _canonical_hash([f"{city}:{item}" for item in eligible_ids]),
        "selected_matter_ids_sha256": _canonical_hash([f"{city}:{item}" for item in selected_ids]),
        "candidate_pool_sha256": _canonical_hash(
            [
                {
                    "matter_id": matter.matter_id,
                    "candidate_pairs": list(matter.candidate_pairs),
                }
                for matter in raw_matters
            ]
        ),
        "source_paths": {
            "record_database": str(database),
            "evidence_root": str(evidence_root),
        },
        "note": (
            "Selection uses raw titles, supported agenda-placement values, and attachment "
            "identity fields only. It does not read or use Page 47 comparator results."
        ),
    }


def _review_slots() -> dict[str, object]:
    def slot() -> dict[str, object]:
        return {"label": None, "reason": None, "evidence": []}

    return {
        "reviewer_a": slot(),
        "reviewer_b": slot(),
        "adjudicated": slot(),
    }


def _item(
    *,
    city: str,
    case: MatterCase,
    role: str,
    selection_reasons: tuple[str, ...],
    selected_pairs: tuple[dict[str, object], ...],
    selection_index: int,
) -> dict[str, object]:
    return {
        "selection_index": selection_index,
        "case_id": f"{city}:{case.matter_id}",
        "city": city,
        "matter_id": case.matter_id,
        "cohort_role": role,
        "selection_reasons": list(selection_reasons),
        "selected_pairs": list(selected_pairs),
        "review": _review_slots(),
        "case_payload": case.structural_payload(),
    }


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a blind-review-ready real historical Page 47 challenge cohort"
    )
    parser.add_argument("--city", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-count", type=int, default=35)
    parser.add_argument("--control-count", type=int, default=10)
    parser.add_argument("--minimum-appearances", type=int, default=2)
    parser.add_argument("--seed", type=int, default=47)
    parser.add_argument("--code-revision", required=True)
    args = parser.parse_args()

    city = args.city.strip()
    if not city:
        raise ValueError("city must be non-empty text")
    candidate_count = _positive_integer(args.candidate_count, "candidate-count")
    control_count = _positive_integer(args.control_count, "control-count")
    minimum_appearances = _positive_integer(args.minimum_appearances, "minimum-appearances")
    if not args.code_revision.strip():
        raise ValueError("code-revision must be non-empty text")

    evidence = SnapshotStore(args.evidence_root)
    with RecordStore(args.database) as records:
        raw_matters = _raw_matters(records.connection, minimum_appearances)
        candidates = tuple(matter for matter in raw_matters if matter.is_candidate)
        controls = tuple(matter for matter in raw_matters if not matter.is_candidate)
        if len(candidates) < candidate_count:
            raise ValueError(
                f"Only {len(candidates)} mechanically selected candidates are available; "
                f"need {candidate_count}"
            )
        if len(controls) < control_count:
            raise ValueError(
                f"Only {len(controls)} mechanically selected controls are available; "
                f"need {control_count}"
            )
        randomizer = random.Random(args.seed)
        selected_candidates = tuple(
            sorted(randomizer.sample(candidates, candidate_count), key=lambda item: item.matter_id)
        )
        selected_controls = tuple(
            sorted(randomizer.sample(controls, control_count), key=lambda item: item.matter_id)
        )
        selected = selected_candidates + selected_controls
        selected_ids = tuple(item.matter_id for item in selected)
        eligible_ids = tuple(item.matter_id for item in raw_matters)
        source_snapshot = _source_snapshot(
            database=args.database,
            evidence_root=args.evidence_root,
            evidence=evidence,
            city=city,
            code_revision=args.code_revision,
            selected_ids=selected_ids,
            eligible_ids=eligible_ids,
            raw_matters=raw_matters,
        )
        items: list[dict[str, object]] = []
        for index, raw_matter in enumerate(selected, start=1):
            case = load_matter_case(records, city, raw_matter.matter_id, args.evidence_root)
            if raw_matter.is_candidate:
                reasons = tuple(
                    dict.fromkeys(
                        reason
                        for pair in raw_matter.candidate_pairs
                        for reason in pair["reasons"]
                        if isinstance(reason, str)
                    )
                )
                pairs = raw_matter.candidate_pairs
                role = "candidate"
            else:
                reasons = ("mechanical_control",)
                pairs = ()
                role = "control"
            items.append(
                _item(
                    city=city,
                    case=case,
                    role=role,
                    selection_reasons=reasons,
                    selected_pairs=pairs,
                    selection_index=index,
                )
            )

    output: dict[str, object] = {
        "schema_version": 1,
        "city": city,
        "status": "awaiting_independent_labels",
        "source_snapshot": source_snapshot,
        "selection": {
            "seed": args.seed,
            "minimum_appearances": minimum_appearances,
            "candidate_count": candidate_count,
            "control_count": control_count,
            "eligible_repeated_matters": len(raw_matters),
            "candidate_pool_size": len(candidates),
            "control_pool_size": len(controls),
            "order": "mechanically sampled candidates by matter ID, then controls by matter ID",
            "rules": [
                "candidate: adjacent title text changed",
                "candidate: adjacent supported agenda placement changed",
                "candidate: adjacent attachment identity set changed",
                "control: no candidate rule matched any adjacent pair",
            ],
            "page47_result_used_for_selection": False,
        },
        "label_policy": {
            "allowed_labels": sorted(LABELS),
            "reviewer_a": (
                "Label from the retained case payload and primary evidence without looking "
                "at Page 47's comparator output."
            ),
            "reviewer_b": (
                "Label independently from the retained case payload and primary evidence "
                "without looking at Page 47's comparator output."
            ),
            "adjudication": (
                "Resolve disagreements after both blind labels are retained; record the "
                "evidence and a plain-language reason."
            ),
            "evidence_requirement": (
                "Every non-pending label must retain at least one primary source URL and "
                "capture time; add a page number when applicable."
            ),
            "cohort_warning": (
                "This is a mechanically selected historical challenge cohort, not a "
                "prevalence sample or representative accuracy estimate."
            ),
        },
        "items": items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "city": city,
                "items": len(items),
                "candidates": candidate_count,
                "controls": control_count,
                "status": output["status"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
