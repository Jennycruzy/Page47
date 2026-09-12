#!/usr/bin/env python3
"""Import completed human review CSVs into a corrected challenge packet."""

from __future__ import annotations

import argparse
import csv
import json
import re
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

ALLOWED_LABELS = frozenset({"clearer", "less_clear", "mixed", "unchanged", "cannot_determine"})
EVENT_PATTERN = re.compile(r"\b(?:event|events)\s+(\d+)\b", re.IGNORECASE)
PAGE_PATTERN = re.compile(r"\b(?:p|page)\s*(\d+)\b", re.IGNORECASE)


def _load_packet(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Could not read packet {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError("Packet must contain an object")
    return decoded


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _load_reviews(path: Path) -> dict[int, dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as error:
        raise ValueError(f"Could not read review file {path}: {error}") from error
    required = {"matter_id", "label", "reason", "evidence_key"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Review file {path} is missing required columns {sorted(required)}")
    output: dict[int, dict[str, str]] = {}
    for index, row in enumerate(rows, start=2):
        raw_matter_id = row.get("matter_id", "").strip()
        try:
            matter_id = int(raw_matter_id)
        except ValueError as error:
            raise ValueError(f"{path}:{index} has an invalid matter_id") from error
        label = row.get("label", "").strip()
        if label not in ALLOWED_LABELS:
            raise ValueError(f"{path}:{index} has an invalid label {label!r}")
        reason = row.get("reason", "").strip()
        evidence_key = row.get("evidence_key", "").strip()
        if not reason or not evidence_key:
            raise ValueError(f"{path}:{index} needs both reason and evidence_key")
        if matter_id in output:
            raise ValueError(f"{path} contains duplicate matter_id {matter_id}")
        output[matter_id] = {
            "label": label,
            "reason": reason,
            "evidence_key": evidence_key,
            "confidence": row.get("confidence", "").strip(),
        }
    return output


def _source_for_appearance(appearance: dict[str, Any]) -> dict[str, str] | None:
    source = appearance.get("source")
    if isinstance(source, dict):
        url = source.get("url")
        captured_at = source.get("captured_at")
        if isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(
            captured_at, str
        ):
            return {"url": url, "captured_at": captured_at}
    for attachment in appearance.get("attachments", []):
        if not isinstance(attachment, dict):
            continue
        for source_key in ("source", "reading_source"):
            source = attachment.get(source_key)
            if not isinstance(source, dict):
                continue
            url = source.get("url")
            captured_at = source.get("captured_at")
            if isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(
                captured_at, str
            ):
                return {"url": url, "captured_at": captured_at}
    return None


def _evidence_for_review(item: dict[str, Any], evidence_key: str) -> list[dict[str, object]]:
    payload = item.get("case_payload")
    appearances = payload.get("appearances") if isinstance(payload, dict) else None
    if not isinstance(appearances, list):
        raise ValueError(f"{item.get('case_id')} has no appearances")
    event_ids = {int(value) for value in EVENT_PATTERN.findall(evidence_key)}
    selected: list[dict[str, str]] = []
    for appearance in appearances:
        if not isinstance(appearance, dict):
            continue
        if event_ids and appearance.get("event_id") not in event_ids:
            continue
        source = _source_for_appearance(appearance)
        if source is not None:
            selected.append(source)
    if not selected:
        for appearance in appearances:
            if not isinstance(appearance, dict):
                continue
            source = _source_for_appearance(appearance)
            if source is not None:
                selected.append(source)
            if len(selected) >= 2:
                break
    if not selected:
        raise ValueError(f"{item.get('case_id')} has no usable primary source")
    page_match = PAGE_PATTERN.search(evidence_key)
    page_number = int(page_match.group(1)) if page_match else None
    output: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for index, source in enumerate(selected):
        identity = (source["url"], source["captured_at"])
        if identity in seen:
            continue
        seen.add(identity)
        evidence: dict[str, object] = dict(source)
        if page_number is not None and index == 0:
            evidence["page_number"] = page_number
        output.append(evidence)
    return output


def _slot(item: dict[str, Any], review: dict[str, str]) -> dict[str, object]:
    slot: dict[str, object] = {
        "label": review["label"],
        "reason": review["reason"],
        "evidence": _evidence_for_review(item, review["evidence_key"]),
        "evidence_key": review["evidence_key"],
    }
    if review["confidence"]:
        slot["confidence"] = review["confidence"]
    return slot


def main() -> int:
    parser = argparse.ArgumentParser(description="Import two completed Page 47 human review CSVs")
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--answer-key", type=Path)
    parser.add_argument("--ignore-matter-ids", required=True)
    args = parser.parse_args()

    packet = _load_packet(args.packet)
    raw_items = packet.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Packet items must be a non-empty list")
    reviewer_a = _load_reviews(args.reviewer_a)
    reviewer_b = _load_reviews(args.reviewer_b)
    ignored = {int(value.strip()) for value in args.ignore_matter_ids.split(",") if value.strip()}
    packet_ids: set[int] = set()
    items_by_matter: dict[int, dict[str, Any]] = {}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict) or not isinstance(raw_item.get("matter_id"), int):
            raise ValueError("Packet contains an invalid item")
        matter_id = raw_item["matter_id"]
        packet_ids.add(matter_id)
        items_by_matter[matter_id] = raw_item
    expected_ids = packet_ids | ignored
    for name, reviews in (("reviewer_a", reviewer_a), ("reviewer_b", reviewer_b)):
        missing = sorted(packet_ids - set(reviews))
        extra = sorted(set(reviews) - expected_ids)
        if missing:
            raise ValueError(f"{name} is missing packet matters {missing}")
        if extra:
            raise ValueError(f"{name} contains unexpected matters {extra}")

    completed = True
    output = deepcopy(packet)
    output["review_provenance"] = {
        "source": "two completed human review CSVs supplied for the prior cohort",
        "packet_correction": "three recurring container matters were removed before import",
        "note": (
            "The prior review files were retained rather than discarded. This corrected packet "
            "does not claim that the prior packet was blind to its selection metadata."
        ),
    }
    for raw_item in output["items"]:
        if not isinstance(raw_item, dict):
            raise ValueError("Packet item is invalid")
        matter_id = raw_item["matter_id"]
        source_item = items_by_matter[matter_id]
        slot_a = _slot(source_item, reviewer_a[matter_id])
        slot_b = _slot(source_item, reviewer_b[matter_id])
        raw_item["review"] = {
            "reviewer_a": slot_a,
            "reviewer_b": slot_b,
            "adjudicated": {},
        }
        if slot_a["label"] == slot_b["label"]:
            raw_item["review"]["adjudicated"] = {
                **slot_a,
                "adjudication_basis": "Both independent reviewers supplied the same label.",
            }
        else:
            completed = False
    output["status"] = "labels_complete" if completed else "awaiting_adjudication"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.answer_key is not None:
        answer_key = _load_packet(args.answer_key)
        answer_key["review_packet_sha256"] = _sha256_file(args.output)
        answer_key["status"] = (
            "published_after_review" if completed else "withheld_from_reviewers"
        )
        args.answer_key.write_text(
            json.dumps(answer_key, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {"items": len(packet_ids), "status": output["status"], "ignored": sorted(ignored)},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
