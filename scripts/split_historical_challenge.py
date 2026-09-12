#!/usr/bin/env python3
"""Create browser-friendly case files from the complete challenge packet."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

WITHHELD_FIELDS = frozenset(
    {"cohort_role", "selection_reasons", "selected_pairs", "selection_index"}
)


def _load(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"{path} must contain an object")
    return decoded


def _filename(case_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", case_id).strip("-")
    if not safe:
        raise ValueError(f"Could not create a safe filename for {case_id!r}")
    return f"{safe}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Split a Page 47 challenge packet into case files")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cases-dir", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    args = parser.parse_args()

    packet = _load(args.input)
    raw_items = packet.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Challenge packet items must be a non-empty list")
    args.cases_dir.mkdir(parents=True, exist_ok=True)
    index_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Challenge packet item must be an object")
        leaked = sorted(WITHHELD_FIELDS.intersection(raw_item))
        if leaked:
            raise ValueError(f"Reviewer packet exposes withheld fields: {leaked}")
        case_id = raw_item.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen_ids:
            raise ValueError("Challenge packet case IDs must be unique non-empty text")
        seen_ids.add(case_id)
        filename = _filename(case_id)
        case_path = args.cases_dir / filename
        case_path.write_text(
            json.dumps(raw_item, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        index_items.append(
            {
                "case_id": case_id,
                "matter_id": raw_item.get("matter_id"),
                "file": str(case_path.relative_to(args.index.parent)),
            }
        )

    index = {
        "schema_version": 1,
        "status": packet.get("status"),
        "city": packet.get("city"),
        "source_packet": str(args.input),
        "source_snapshot": packet.get("source_snapshot"),
        "blind_review": packet.get("blind_review"),
        "items": index_items,
        "note": (
            "Each linked case file contains the same neutral retained case payload, one fixed "
            "review pair, and review slots. The complete packet remains the canonical audit file."
        ),
    }
    args.index.parent.mkdir(parents=True, exist_ok=True)
    args.index.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "cases": len(index_items),
                "index": str(args.index),
                "cases_dir": str(args.cases_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
