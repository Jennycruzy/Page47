#!/usr/bin/env python3
"""Capture attachment bytes referenced by the normalized public record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.records.runner import capture_observation, source_for_capture  # noqa: E402, I001
from page47.records.store import (  # noqa: E402, I001
    RecordStore,
    StoredAttachmentSource,
)
from page47.snapshotter.config import (  # noqa: E402, I001
    CityConfig,
    JSONObject,
    load_city_config,
)
from page47.snapshotter.http import (  # noqa: E402, I001
    ConditionalHttpClient,
    FetchResult,
    utc_now,
)
from page47.snapshotter.runner import (  # noqa: E402, I001
    HTTP_OK,
    compare_document,
    source_url_is_usable,
)
from page47.snapshotter.store import SnapshotStore  # noqa: E402, I001


def _fields(attachment: StoredAttachmentSource) -> JSONObject:
    return {
        "parse_status": "binary",
        "attachment_id": attachment.attachment_id,
        "matter_id": attachment.matter_id,
        "name": attachment.name,
        "last_modified": attachment.last_modified_utc,
        "matter_version": attachment.version,
        "capture_reason": "historical attachment capture from normalized public record",
    }


def _unparsed_fields(attachment: StoredAttachmentSource, reason: str) -> JSONObject:
    fields = _fields(attachment)
    fields["parse_status"] = "unparsed"
    fields["parse_error"] = reason
    return fields


def _same_host(url: str, configured_hosts: tuple[str, ...]) -> bool:
    url_host = urlparse(url).hostname
    return url_host is not None and url_host.casefold() in configured_hosts


def _fetchable(attachment: StoredAttachmentSource, configured_hosts: tuple[str, ...]) -> bool:
    """Require a stored HTTP URL and the configured Legistar API host."""

    return attachment.url is not None and source_url_is_usable(attachment.url) and _same_host(
        attachment.url, configured_hosts
    )


def _capture(
    store: SnapshotStore,
    client: ConditionalHttpClient,
    attachment: StoredAttachmentSource,
    config: CityConfig,
    run_id: str,
) -> tuple[str, int | None, str | None, JSONObject | None]:
    if not _fetchable(attachment, config.attachment_hosts):
        return (
            "invalid",
            None,
            "attachment URL was missing or outside the configured Legistar attachment hosts",
            None,
        )
    url = attachment.url
    if url is None:
        raise ValueError(f"Attachment {attachment.attachment_id} URL disappeared during validation")
    target = f"attachment:{attachment.attachment_id}"
    previous = store.latest(target)
    response: FetchResult = client.fetch(target, url, previous)
    if response.not_modified:
        if previous is None:
            return "invalid", response.status, "received 304 without a prior capture", None
        return "reused", response.status, None, previous
    if response.status != HTTP_OK:
        reason = f"attachment download returned HTTP status {response.status!r}"
        failed, _ = store.capture(response, "attachment", _unparsed_fields(attachment, reason))
        return "failed", response.status, reason, failed
    current, inserted = store.capture(response, "attachment", _fields(attachment))
    compare_document(store, run_id, target, previous, current, "attachment")
    if inserted:
        return "captured", response.status, None, current
    return "unchanged", response.status, None, current


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Capture attachment bytes referenced by a stored city record"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--attachment-id", type=int)
    parser.add_argument("--max-attachments", type=int)
    args = parser.parse_args()
    if args.attachment_id is not None and args.attachment_id < 1:
        raise ValueError("--attachment-id must be positive")
    if args.max_attachments is not None and args.max_attachments < 1:
        raise ValueError("--max-attachments must be positive")

    config = load_city_config(args.config)
    store = SnapshotStore(args.evidence_root)
    client = ConditionalHttpClient(config.timeout_seconds, config.accept_header)
    run_id = utc_now()
    selected = 0
    counts = {
        "selected": 0,
        "captured": 0,
        "reused": 0,
        "unchanged": 0,
        "failed": 0,
        "invalid": 0,
    }
    issues: list[str] = []
    with RecordStore(args.database) as records:
        attachments = records.attachment_sources()
    captured: list[tuple[int, JSONObject]] = []
    for attachment in attachments:
        if args.attachment_id is not None and attachment.attachment_id != args.attachment_id:
            continue
        if args.max_attachments is not None and selected >= args.max_attachments:
            break
        selected += 1
        counts["selected"] += 1
        status, http_status, issue, capture = _capture(store, client, attachment, config, run_id)
        counts[status] += 1
        if capture is not None:
            captured.append((attachment.attachment_id, capture))
        if issue is not None:
            issues.append(
                f"attachment {attachment.attachment_id}: {issue} (status {http_status})"
            )
    with RecordStore(args.database) as records:
        for attachment_id, capture in captured:
            records.add_snapshot(capture_observation(capture, "snapshot"))
            content_hash = capture.get("content_sha256")
            if isinstance(content_hash, str) and content_hash:
                records.record_attachment_content(
                    attachment_id,
                    content_hash,
                    source_for_capture(capture, "snapshot"),
                )
        records.commit()
    run: JSONObject = {
        "run_id": run_id,
        "status": "complete" if not issues else "complete_with_issues",
        "city": config.city,
        "mode": "normalized_record_attachments",
        "counts": counts,
        "issues": issues,
    }
    store.append_run(run)
    print(json.dumps(run, indent=2, sort_keys=True))
    return 0 if not issues else 2


if __name__ == "__main__":
    raise SystemExit(main())
