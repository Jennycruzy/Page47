#!/usr/bin/env python3
"""Export a deterministic, real-record set for the four comparison arms."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.analysis.case import load_matter_case  # noqa: E402, I001
from page47.records.store import RecordStore  # noqa: E402, I001
from page47.snapshotter.config import JSONObject, as_json_value  # noqa: E402, I001


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _config(path: Path) -> tuple[str, int, int, int]:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = as_json_value(decoded)
    if not isinstance(root, dict):
        raise ValueError("Evaluation configuration must be an object")
    city = root.get("city")
    if not isinstance(city, str) or not city.strip():
        raise ValueError("evaluation.city must be non-empty text")
    minimum = _positive_integer(root.get("minimum_appearances"), "evaluation.minimum_appearances")
    sample = _positive_integer(root.get("sample_size"), "evaluation.sample_size")
    gold = _positive_integer(root.get("gold_size"), "evaluation.gold_size")
    if gold > sample:
        raise ValueError("evaluation.gold_size must not exceed evaluation.sample_size")
    order = root.get("selection_order")
    if order != "matter_id":
        raise ValueError("evaluation.selection_order must be matter_id")
    return city, minimum, sample, gold


def _source(source: object) -> JSONObject:
    if not isinstance(source, dict):
        raise ValueError("Evaluation source was not an object")
    url = source.get("url")
    captured_at = source.get("captured_at")
    if not isinstance(url, str) or not url or not isinstance(captured_at, str) or not captured_at:
        raise ValueError("Evaluation source was incomplete")
    return {"url": url, "captured_at": captured_at}


def _appearance(case: object) -> JSONObject:
    if not hasattr(case, "event_item_id"):
        raise ValueError("Evaluation appearance was not a stored appearance")
    # The typed MatterCase records are converted through their public JSON shape so the
    # export contains only fields already present in the record store.
    raw = case.as_json()  # type: ignore[attr-defined]
    if not isinstance(raw, dict):
        raise ValueError("Evaluation appearance did not produce an object")
    attachments = raw.get("attachments")
    if not isinstance(attachments, list):
        raise ValueError("Evaluation appearance attachments were not a list")
    compact_attachments: list[JSONObject] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            raise ValueError("Evaluation attachment was not an object")
        compact_attachments.append(
            {
                "attachment_id": attachment.get("attachment_id"),
                "name": attachment.get("name"),
                "url": attachment.get("url"),
                "reading_status": attachment.get("reading_status"),
                "page_count": attachment.get("page_count"),
                "source": _source(attachment.get("source")),
                "reading_source": (
                    _source(attachment["reading_source"])
                    if attachment.get("reading_source") is not None
                    else None
                ),
            }
        )
    return {
        "event_item_id": raw.get("event_item_id"),
        "event_id": raw.get("event_id"),
        "event_date": raw.get("event_date"),
        "title_as_presented": raw.get("title_as_presented"),
        "pdf_placement": raw.get("pdf_placement"),
        "agenda_sequence": raw.get("agenda_sequence"),
        "source": _source(raw.get("source")),
        "attachments": compact_attachments,
    }


def _item(city: str, case: object) -> JSONObject:
    if not hasattr(case, "matter_id") or not hasattr(case, "matter"):
        raise ValueError("Evaluation case was incomplete")
    matter = case.matter  # type: ignore[attr-defined]
    appearances = case.appearances  # type: ignore[attr-defined]
    matter_json = matter.as_json()
    if not isinstance(matter_json, dict):
        raise ValueError("Evaluation matter did not produce an object")
    matter_id = matter_json.get("matter_id")
    if isinstance(matter_id, bool) or not isinstance(matter_id, int) or matter_id < 1:
        raise ValueError("Evaluation matter ID was invalid")
    return {
        "case_id": f"{city}:{matter_id}",
        "city": city,
        "matter_id": matter_id,
        "file_number": matter_json.get("file_number"),
        "current_title": matter_json.get("current_title"),
        "body_name": matter_json.get("body_name"),
        "matter_source": _source(matter_json.get("source")),
        "appearances": [_appearance(appearance) for appearance in appearances],
        "gold_label": None,
        "gold_label_reason": None,
        "gold_evidence": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export real matters for hand-labelled comparison")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    city, minimum, sample_size, gold_size = _config(args.config)
    with RecordStore(args.database) as records:
        rows = records.connection.execute(
            "SELECT matter_id FROM appearances WHERE matter_id IS NOT NULL "
            "GROUP BY matter_id HAVING COUNT(*) >= ? ORDER BY matter_id LIMIT ?",
            (minimum, sample_size),
        ).fetchall()
        matter_ids: list[int] = []
        for row in rows:
            matter_id = row[0]
            if isinstance(matter_id, bool) or not isinstance(matter_id, int) or matter_id < 1:
                raise ValueError("Stored evaluation matter ID was invalid")
            matter_ids.append(matter_id)
        if len(matter_ids) < sample_size:
            raise ValueError(
                f"Only {len(matter_ids)} matters met the minimum appearance count; "
                f"need {sample_size}"
            )
        items = [
            _item(city, load_matter_case(records, city, matter_id, args.evidence_root))
            for matter_id in matter_ids
        ]
    gold_items = items[:gold_size]
    output: JSONObject = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "city": city,
        "selection": {
            "minimum_appearances": minimum,
            "sample_size": sample_size,
            "gold_size": gold_size,
            "order": "matter_id ascending",
            "gold_subset": "the first gold_size records in that deterministic order",
        },
        "label_rule": (
            "Mark yes only when comparing the stored appearances shows a meaningful change "
            "in how the matter was presented, no when the presentation did not meaningfully "
            "change, and cannot_determine when the public record is insufficient. Add a "
            "primary-record URL and capture time for every label."
        ),
        "gold_case_ids": [item["case_id"] for item in gold_items],
        "items": items,
        "status": "awaiting_human_labels",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"city": city, "items": len(items), "gold_items": len(gold_items)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
