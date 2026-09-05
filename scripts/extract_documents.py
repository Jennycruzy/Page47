#!/usr/bin/env python3
"""Run the expensive document reader only for text-triaged PDF candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.models.config import load_model_settings  # noqa: E402
from page47.records.runner import source_for_capture  # noqa: E402
from page47.records.store import (  # noqa: E402
    DocumentExtractionObservation,
    RecordStore,
)
from page47.snapshotter.store import SnapshotStore, text_value  # noqa: E402
from page47.substance.model_reader import extract_document  # noqa: E402
from page47.substance.reader import AttachmentReading, PageReference  # noqa: E402


def _attachment_id(capture: dict[str, object]) -> int:
    target = capture.get("target")
    if not isinstance(target, str) or not target.startswith("attachment:"):
        raise ValueError("Captured attachment had an invalid target")
    raw_id = target.removeprefix("attachment:")
    try:
        attachment_id = int(raw_id)
    except ValueError as error:
        raise ValueError("Captured attachment target had a non-integer ID") from error
    if attachment_id < 1:
        raise ValueError("Captured attachment ID must be positive")
    return attachment_id


def _reading(store: RecordStore, attachment_id: int) -> AttachmentReading | None:
    observation = store.attachment_reading(attachment_id)
    if observation is None:
        return None
    raw = observation.references.get("references")
    if not isinstance(raw, list):
        raise ValueError(f"Attachment reading {attachment_id} had no references list")
    references: list[PageReference] = []
    for index, value in enumerate(raw):
        if not isinstance(value, dict):
            raise ValueError(
                f"Attachment reading {attachment_id} reference {index} was not an object"
            )
        kind = value.get("kind")
        match_value = value.get("value")
        page = value.get("page_number")
        start = value.get("start_character")
        end = value.get("end_character")
        excerpt = value.get("excerpt")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"Attachment reading {attachment_id} reference had no kind")
        if not isinstance(match_value, str) or not match_value:
            raise ValueError(f"Attachment reading {attachment_id} reference had no value")
        if any(isinstance(item, bool) or not isinstance(item, int) for item in (page, start, end)):
            raise ValueError(f"Attachment reading {attachment_id} reference had invalid bounds")
        if page < 1 or start < 0 or end < start:
            raise ValueError(f"Attachment reading {attachment_id} reference had invalid bounds")
        if not isinstance(excerpt, str) or not excerpt:
            raise ValueError(f"Attachment reading {attachment_id} reference had no excerpt")
        references.append(PageReference(kind, match_value, page, start, end, excerpt))
    return AttachmentReading(
        status=observation.status,
        page_count=observation.page_count,
        references=tuple(references),
        reason=observation.reason,
    )


def _capture_map(snapshots: SnapshotStore) -> dict[int, dict[str, object]]:
    output: dict[int, dict[str, object]] = {}
    for raw_capture in snapshots.records:
        capture = dict(raw_capture)
        if capture.get("kind") != "attachment" or capture.get("status") != 200:
            continue
        source_url = text_value(capture, "source_url")
        content_hash = text_value(capture, "content_sha256")
        if source_url is None or content_hash is None or not source_url.casefold().endswith(".pdf"):
            continue
        output[_attachment_id(capture)] = capture
    return output


def _failure_reason(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract changes from candidate PDF attachments")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rerun an extraction even when the content hash is already stored",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=None,
        help="Stop after this many candidate documents; omit for all candidates",
    )
    parser.add_argument(
        "--attachment-id",
        type=int,
        default=None,
        help="Read only this captured attachment ID",
    )
    args = parser.parse_args()
    if args.max_candidates is not None and args.max_candidates < 1:
        raise ValueError("--max-candidates must be positive when supplied")
    if args.attachment_id is not None and args.attachment_id < 1:
        raise ValueError("--attachment-id must be positive when supplied")
    settings = load_model_settings(args.models)
    snapshots = SnapshotStore(args.evidence_root)
    captures = _capture_map(snapshots)
    result = {"candidates": 0, "read": 0, "absent": 0, "failed": 0, "reused": 0}
    with RecordStore(args.database) as records:
        processed = 0
        for attachment_id, capture in sorted(captures.items()):
            if args.attachment_id is not None and attachment_id != args.attachment_id:
                continue
            reading = _reading(records, attachment_id)
            if reading is None or reading.status != "candidate":
                continue
            if args.max_candidates is not None and processed >= args.max_candidates:
                break
            processed += 1
            result["candidates"] += 1
            content_hash = text_value(capture, "content_sha256")
            if content_hash is None:
                raise ValueError(f"Attachment {attachment_id} capture had no content hash")
            if not args.force and records.document_extraction_hash(attachment_id) == content_hash:
                result["reused"] += 1
                continue
            source = source_for_capture(capture, "snapshot")
            try:
                extraction = extract_document(
                    attachment_id,
                    content_hash,
                    snapshots.body(capture),
                    reading,
                    source,
                    settings,
                )
                changes = [change.as_json() for change in extraction.changes]
                records.upsert_document_extraction(
                    DocumentExtractionObservation(
                        attachment_id=attachment_id,
                        content_hash=content_hash,
                        status=extraction.status,
                        changes=changes,
                        reason=extraction.reason,
                        model_id=extraction.model_id,
                        source=source,
                    )
                )
                result[extraction.status] += 1
            except Exception as error:
                records.upsert_document_extraction(
                    DocumentExtractionObservation(
                        attachment_id=attachment_id,
                        content_hash=content_hash,
                        status="failed",
                        changes=[],
                        reason=_failure_reason(error),
                        model_id=settings.document.model_id,
                        source=source,
                    )
                )
                result["failed"] += 1
        records.commit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
