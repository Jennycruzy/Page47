#!/usr/bin/env python3
"""Read one captured PDF attachment by its Legistar attachment ID."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.snapshotter.store import SnapshotStore, text_value  # noqa: E402, I001
from page47.substance.reader import load_substance_config, read_pdf_attachment  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="Read one captured PDF attachment")
    parser.add_argument("--attachment-id", type=int, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--substance-config", type=Path, required=True)
    args = parser.parse_args()
    if args.attachment_id < 1:
        raise ValueError("attachment_id must be positive")
    store = SnapshotStore(args.evidence_root)
    capture = store.latest(f"attachment:{args.attachment_id}")
    if capture is None:
        raise ValueError(f"No captured attachment exists for {args.attachment_id}")
    source_url = text_value(capture, "source_url")
    if source_url is None or not source_url.casefold().endswith(".pdf"):
        raise ValueError(f"Attachment {args.attachment_id} is not a captured PDF")
    reading = read_pdf_attachment(store.body(capture), load_substance_config(args.substance_config))
    print(
        json.dumps(
            {
                "attachment_id": args.attachment_id,
                "source_url": source_url,
                "status": reading.status,
                "page_count": reading.page_count,
                "reason": reading.reason,
                "references": [
                    {
                        "kind": reference.kind,
                        "value": reference.value,
                        "page_number": reference.page_number,
                        "start_character": reference.start_character,
                        "end_character": reference.end_character,
                        "excerpt": reference.excerpt,
                    }
                    for reference in reading.references
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if reading.status != "unreadable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
