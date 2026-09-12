#!/usr/bin/env python3
"""Store page-linked readings for captured PDF attachments."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.records.runner import source_for_capture  # noqa: E402, I001
from page47.records.store import AttachmentReadingObservation, RecordStore  # noqa: E402, I001
from page47.snapshotter.store import (  # noqa: E402, I001
    SnapshotStore,
    body_is_pdf,
    text_value,
)
from page47.substance.reader import (  # noqa: E402, I001
    AttachmentReading,
    load_substance_config,
    read_pdf_attachment,
    reading_references,
)


def attachment_id(capture: Mapping[str, object]) -> int:
    target = capture.get("target")
    if not isinstance(target, str) or not target.startswith("attachment:"):
        raise ValueError("Captured attachment has an invalid target")
    value = target.removeprefix("attachment:")
    try:
        result = int(value)
    except ValueError as error:
        raise ValueError("Captured attachment target has a non-integer ID") from error
    if result < 1:
        raise ValueError("Captured attachment ID must be positive")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Read captured PDF attachments")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--substance-config", type=Path, required=True)
    args = parser.parse_args()
    config = load_substance_config(args.substance_config)
    snapshots = SnapshotStore(args.evidence_root)
    result = {"read": 0, "reused": 0, "candidate": 0, "absent": 0, "unreadable": 0}
    with RecordStore(args.database) as records:
        for capture in snapshots.records:
            if capture.get("kind") != "attachment" or capture.get("status") != 200:
                continue
            source_url = text_value(capture, "source_url")
            content_hash = text_value(capture, "content_sha256")
            if source_url is None or content_hash is None:
                raise ValueError("Captured attachment has no source URL or content hash")
            body = snapshots.body(capture)
            if not body_is_pdf(body):
                continue
            item_id = attachment_id(capture)
            if records.attachment_reading_hash(item_id) == content_hash:
                result["reused"] += 1
                continue
            try:
                reading = read_pdf_attachment(body, config)
            except Exception as error:
                reading = AttachmentReading(
                    status="unreadable",
                    page_count=0,
                    references=(),
                    reason=f"{type(error).__name__}: {error}",
                )
            records.upsert_attachment_reading(
                AttachmentReadingObservation(
                    attachment_id=item_id,
                    content_hash=content_hash,
                    status=reading.status,
                    page_count=reading.page_count,
                    references=reading_references(reading),
                    reason=reading.reason,
                    source=source_for_capture(capture, "snapshot"),
                )
            )
            records.commit()
            result["read"] += 1
            result[reading.status] += 1
        records.commit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
