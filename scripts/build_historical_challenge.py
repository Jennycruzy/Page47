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
CONTAINER_TITLE_PATTERNS = (
    ("recurring_council_agenda", re.compile(r"^(?:city )?council agenda(?: \(\d{4}\))?$")),
    (
        "recurring_council_briefing_minutes",
        re.compile(r"^(?:city )?council briefing minutes(?: \(\d{4}\))?$"),
    ),
    ("recurring_council_minutes", re.compile(r"^(?:city )?council minutes(?: \(\d{4}\))?$")),
    ("recurring_meeting_agenda", re.compile(r"^meeting agenda(?: \(\d{4}\))?$")),
    ("recurring_meeting_minutes", re.compile(r"^meeting minutes(?: \(\d{4}\))?$")),
    ("recurring_council_calendar", re.compile(r"^(?:city )?council calendar(?: \(\d{4}\))?$")),
)


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

    @property
    def container_exclusion_reason(self) -> str | None:
        return _container_exclusion_reason(self.appearances)


def _normalise(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value).strip().casefold()
    return normalized or None


def _container_exclusion_reason(appearances: tuple[RawAppearance, ...]) -> str | None:
    """Exclude recurring agenda/minutes containers, not substantive matters."""

    if len(appearances) < 3:
        return None
    kinds: set[str] = set()
    for appearance in appearances:
        title = _normalise(appearance.title)
        if title is None:
            return None
        for kind, pattern in CONTAINER_TITLE_PATTERNS:
            if pattern.fullmatch(title):
                kinds.add(kind)
                break
        else:
            return None
    if len(kinds) != 1:
        return None
    return f"excluded_{next(iter(kinds))}"


def _attachment_signature(appearance: RawAppearance) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted(appearance.attachments, key=lambda item: tuple(str(part) for part in item)))


def _pair_reasons(
    previous: RawAppearance,
    current: RawAppearance,
    changed_attachment_ids: frozenset[int],
) -> tuple[str, ...]:
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
    appearance_attachment_ids = {
        item[0]
        for item in (*previous.attachments, *current.attachments)
        if isinstance(item[0], int) and not isinstance(item[0], bool)
    }
    if appearance_attachment_ids & changed_attachment_ids:
        reasons.append("attachment_content_hash_changed")
    return tuple(reasons)


def _pair_payload(
    previous: RawAppearance,
    current: RawAppearance,
    reasons: tuple[str, ...],
    changed_attachment_ids: frozenset[int],
) -> dict[str, object]:
    changed_ids = sorted(
        {
            item[0]
            for item in (*previous.attachments, *current.attachments)
            if isinstance(item[0], int)
            and not isinstance(item[0], bool)
            and item[0] in changed_attachment_ids
        }
    )
    return {
        "previous_event_item_id": previous.event_item_id,
        "current_event_item_id": current.event_item_id,
        "previous_event_date": previous.event_date,
        "current_event_date": current.event_date,
        "previous_title": previous.title,
        "current_title": current.title,
        "previous_placement": previous.placement,
        "current_placement": current.placement,
        "attachment_ids_with_multiple_captured_hashes": changed_ids,
        "reasons": list(reasons),
    }


def _review_pair_context(
    previous: RawAppearance,
    current: RawAppearance,
) -> dict[str, object]:
    """Return the same one-pair review context for every reviewer item."""

    return {
        "previous_event_item_id": previous.event_item_id,
        "current_event_item_id": current.event_item_id,
        "previous_event_date": previous.event_date,
        "current_event_date": current.event_date,
        "previous_title": previous.title,
        "current_title": current.title,
        "previous_placement": previous.placement,
        "current_placement": current.placement,
    }


def _changed_attachment_ids(evidence: SnapshotStore) -> frozenset[int]:
    hashes_by_attachment: dict[int, set[str]] = {}
    for record in evidence.records:
        target = record.get("target")
        status = record.get("status")
        content_hash = record.get("content_sha256")
        if (
            not isinstance(target, str)
            or not target.startswith("attachment:")
            or status != 200
            or not isinstance(content_hash, str)
        ):
            continue
        raw_id = target.removeprefix("attachment:")
        if not raw_id.isdigit():
            continue
        attachment_id = int(raw_id)
        hashes_by_attachment.setdefault(attachment_id, set()).add(content_hash)
    return frozenset(
        attachment_id
        for attachment_id, hashes in hashes_by_attachment.items()
        if len(hashes) > 1
    )


def _raw_matters(
    connection: Any,
    minimum_appearances: int,
    changed_attachment_ids: frozenset[int],
) -> tuple[RawMatter, ...]:
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
        appearance_items: list[RawAppearance] = []
        for event_item_id, raw in sorted(
            raw_appearances.items(),
            key=lambda item: (str(item[1]["event_date"] or ""), item[0]),
        ):
            raw_attachments = raw["attachments"]
            if not isinstance(raw_attachments, list):
                raise ValueError("Challenge attachment accumulator was invalid")
            appearance_items.append(
                RawAppearance(
                    event_item_id=event_item_id,
                    event_date=raw["event_date"] if isinstance(raw["event_date"], str) else None,
                    title=raw["title"] if isinstance(raw["title"], str) else None,
                    placement=raw["placement"] if isinstance(raw["placement"], str) else None,
                    attachments=tuple(
                        sorted(
                            raw_attachments,
                            key=lambda item: tuple(str(part) for part in item),
                        )
                    ),
                )
            )
        appearances = tuple(appearance_items)
        pair_payloads: list[dict[str, object]] = []
        for previous, current in zip(appearances, appearances[1:], strict=False):
            reasons = _pair_reasons(previous, current, changed_attachment_ids)
            if reasons:
                pair_payloads.append(
                    _pair_payload(previous, current, reasons, changed_attachment_ids)
                )
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
    raw_eligible_ids: tuple[int, ...],
    excluded_ids: tuple[int, ...],
    candidate_matters: tuple[RawMatter, ...],
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
        "raw_eligible_matter_ids_sha256": _canonical_hash(
            [f"{city}:{item}" for item in raw_eligible_ids]
        ),
        "eligible_matter_ids_sha256": _canonical_hash([f"{city}:{item}" for item in eligible_ids]),
        "excluded_container_ids_sha256": _canonical_hash(
            [f"{city}:{item}" for item in excluded_ids]
        ),
        "selected_matter_ids_sha256": _canonical_hash([f"{city}:{item}" for item in selected_ids]),
        "candidate_pool_sha256": _canonical_hash(
            [
                {
                    "matter_id": matter.matter_id,
                    "candidate_pairs": list(matter.candidate_pairs),
                }
                for matter in candidate_matters
            ]
        ),
        "source_paths": {
            "record_database": "runtime/records/seattle.sqlite3",
            "evidence_root": "runtime/evidence/seattle",
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


def _reviewer_item(
    *,
    city: str,
    case: MatterCase,
    review_pair: dict[str, object],
) -> dict[str, object]:
    return {
        "case_id": f"{city}:{case.matter_id}",
        "city": city,
        "matter_id": case.matter_id,
        "review_pair": review_pair,
        "review": _review_slots(),
        "case_payload": case.structural_payload(),
    }


def _answer_item(
    *,
    city: str,
    case: MatterCase,
    role: str,
    selection_reasons: tuple[str, ...],
    selected_pairs: tuple[dict[str, object], ...],
    review_pair: dict[str, object],
) -> dict[str, object]:
    return {
        "case_id": f"{city}:{case.matter_id}",
        "city": city,
        "matter_id": case.matter_id,
        "cohort_role": role,
        "selection_reasons": list(selection_reasons),
        "selected_pairs": list(selected_pairs),
        "review_pair": review_pair,
    }


def _review_pair_for_matter(
    matter: RawMatter,
) -> tuple[dict[str, object], dict[str, object]]:
    """Choose one deterministic adjacent pair for the matter-level review unit."""

    if matter.candidate_pairs:
        selected = matter.candidate_pairs[0]
        previous_id = selected.get("previous_event_item_id")
        current_id = selected.get("current_event_item_id")
        if isinstance(previous_id, int) and isinstance(current_id, int):
            appearances_by_id = {item.event_item_id: item for item in matter.appearances}
            previous = appearances_by_id.get(previous_id)
            current = appearances_by_id.get(current_id)
            if previous is not None and current is not None:
                return _review_pair_context(previous, current), selected
    if len(matter.appearances) < 2:
        raise ValueError(f"Matter {matter.matter_id} has no adjacent pair for review")
    previous, current = matter.appearances[0:2]
    context = _review_pair_context(previous, current)
    return context, {**context, "attachment_ids_with_multiple_captured_hashes": [], "reasons": []}


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
    parser.add_argument(
        "--answer-key",
        type=Path,
        required=True,
        help="write the withheld selection answer key outside the repository",
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=None,
        help="number of candidates to sample; defaults to every eligible candidate",
    )
    parser.add_argument("--control-count", type=int, default=35)
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
    try:
        args.answer_key.resolve().relative_to(REPOSITORY_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("answer-key must be outside the repository so reviewers cannot see it")

    evidence = SnapshotStore(args.evidence_root)
    with RecordStore(args.database) as records:
        changed_attachment_ids = _changed_attachment_ids(evidence)
        raw_matters = _raw_matters(
            records.connection,
            minimum_appearances,
            changed_attachment_ids,
        )
        excluded_containers = tuple(
            matter for matter in raw_matters if matter.container_exclusion_reason is not None
        )
        eligible_matters = tuple(
            matter for matter in raw_matters if matter.container_exclusion_reason is None
        )
        candidates = tuple(matter for matter in eligible_matters if matter.is_candidate)
        controls = tuple(matter for matter in eligible_matters if not matter.is_candidate)
        candidate_count = (
            len(candidates)
            if args.candidate_count is None
            else _positive_integer(args.candidate_count, "candidate-count")
        )
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
        selected = list(selected_candidates + selected_controls)
        randomizer.shuffle(selected)
        selected_ids = tuple(sorted(item.matter_id for item in selected))
        raw_eligible_ids = tuple(item.matter_id for item in raw_matters)
        eligible_ids = tuple(item.matter_id for item in eligible_matters)
        excluded_ids = tuple(item.matter_id for item in excluded_containers)
        source_snapshot = _source_snapshot(
            database=args.database,
            evidence_root=args.evidence_root,
            evidence=evidence,
            city=city,
            code_revision=args.code_revision,
            selected_ids=selected_ids,
            eligible_ids=eligible_ids,
            raw_eligible_ids=raw_eligible_ids,
            excluded_ids=excluded_ids,
            candidate_matters=candidates,
        )
        reviewer_items: list[dict[str, object]] = []
        answer_items: list[dict[str, object]] = []
        for raw_matter in selected:
            case = load_matter_case(records, city, raw_matter.matter_id, args.evidence_root)
            if raw_matter.is_candidate:
                reason_values: list[str] = []
                for pair in raw_matter.candidate_pairs:
                    raw_reasons = pair.get("reasons")
                    if isinstance(raw_reasons, list):
                        reason_values.extend(
                            reason for reason in raw_reasons if isinstance(reason, str)
                        )
                reasons = tuple(dict.fromkeys(reason_values))
                pairs = raw_matter.candidate_pairs
                role = "candidate"
            else:
                reasons = ("mechanical_control",)
                pairs = ()
                role = "control"
            review_pair, answer_review_pair = _review_pair_for_matter(raw_matter)
            reviewer_items.append(
                _reviewer_item(
                    city=city,
                    case=case,
                    review_pair=review_pair,
                )
            )
            answer_items.append(
                _answer_item(
                    city=city,
                    case=case,
                    role=role,
                    selection_reasons=reasons,
                    selected_pairs=pairs,
                    review_pair=answer_review_pair,
                )
            )

    reviewer_snapshot = {
        field: source_snapshot[field]
        for field in (
            "code_revision",
            "created_at_utc",
            "database_sha256",
            "evidence_manifest_sha256",
            "evidence_chain_sha256",
            "evidence_integrity_root",
        )
    }
    output: dict[str, object] = {
        "schema_version": 2,
        "city": city,
        "status": "awaiting_independent_labels",
        "source_snapshot": reviewer_snapshot,
        "blind_review": {
            "answer_key_withheld": True,
            "shuffle_seed": args.seed,
            "order": (
                "Items are shuffled after sampling with the recorded seed; item order carries "
                "no cohort meaning."
            ),
            "review_unit": (
                "Each item has one fixed adjacent appearance pair for one matter-level label. "
                "The same review_pair shape is present for every item."
            ),
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
                "This is a blind, mechanically selected historical challenge cohort, not a "
                "prevalence sample or representative accuracy estimate."
            ),
        },
        "items": reviewer_items,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    answer_key: dict[str, object] = {
        "schema_version": 1,
        "artifact": "page47_historical_challenge_answer_key",
        "status": "withheld_from_reviewers",
        "city": city,
        "review_packet_sha256": _sha256_file(args.output),
        "source_snapshot": source_snapshot,
        "selection": {
            "seed": args.seed,
            "minimum_appearances": minimum_appearances,
            "candidate_count": candidate_count,
            "control_count": control_count,
            "raw_eligible_repeated_matters": len(raw_matters),
            "excluded_recurring_container_count": len(excluded_containers),
            "excluded_recurring_containers": [
                {
                    "matter_id": matter.matter_id,
                    "reason": matter.container_exclusion_reason,
                }
                for matter in excluded_containers
            ],
            "eligible_review_matters": len(eligible_matters),
            "candidate_pool_size": len(candidates),
            "control_pool_size": len(controls),
            "order": "sampled candidates and controls are shuffled together with the seed",
            "review_unit": "one fixed adjacent appearance pair per matter",
            "rules": [
                "candidate: adjacent title text changed",
                "candidate: adjacent supported agenda placement changed",
                "candidate: adjacent attachment identity set changed",
                "candidate: a retained attachment target has multiple successful content hashes",
                (
                    "exclude: at least three appearances whose titles are the same recurring "
                    "agenda, minutes, or calendar container"
                ),
                "control: no candidate rule matched any adjacent pair after exclusions",
            ],
            "page47_result_used_for_selection": False,
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
                "items": len(reviewer_items),
                "candidates": candidate_count,
                "controls": control_count,
                "excluded_containers": len(excluded_containers),
                "status": output["status"],
                "output": str(args.output),
                "answer_key": str(args.answer_key),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
