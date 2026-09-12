from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from page47.snapshotter.http import FetchResult
from page47.snapshotter.runner import compare_document
from page47.snapshotter.store import SnapshotStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_INDEX = REPOSITORY_ROOT / "docs/evidence/preflight/index.json"


def recorded_capture(url_fragment: str) -> tuple[FetchResult, bytes]:
    index = json.loads(PREFLIGHT_INDEX.read_text(encoding="utf-8"))
    capture = next(
        item
        for item in index["captures"]
        if url_fragment in item["url"] and item["status"] == 200
    )
    body_path = REPOSITORY_ROOT / "docs" / capture["storage_key"]
    body = body_path.read_bytes()
    assert sha256(body).hexdigest() == capture["sha256"]
    return (
        FetchResult(
            target="recorded-attachment",
            url=capture["url"],
            captured_at=capture["captured_at"],
            status=capture["status"],
            headers=capture["headers"],
            body=body,
            error_type=None,
            error=None,
            not_modified=False,
        ),
        body,
    )


def test_replaying_the_same_record_does_not_add_a_duplicate_row(tmp_path: Path) -> None:
    response, _ = recorded_capture("/v1/seattle/events/")
    store = SnapshotStore(tmp_path / "evidence")
    fields = {"parse_status": "parsed"}

    first, first_inserted = store.capture(
        response,
        "event_detail",
        fields,
        collector_run_id="2026-09-04T18:00:00Z",
    )
    second, second_inserted = store.capture(
        response,
        "event_detail",
        fields,
        collector_run_id="2026-09-04T18:15:00Z",
    )

    assert first_inserted
    assert not second_inserted
    assert first == second
    assert first["collector_run_id"] == "2026-09-04T18:00:00Z"
    assert store.count_manifest_rows() == 1


def test_a_changed_stored_copy_is_reported(tmp_path: Path) -> None:
    response, body = recorded_capture("/v1/seattle/events/")
    response = replace(response, target="recorded-event")
    store = SnapshotStore(tmp_path / "evidence")
    fields = {"parse_status": "parsed"}
    previous, previous_inserted = store.capture(response, "event_detail", fields)
    changed_response = replace(
        response,
        captured_at="2026-09-04T18:30:00Z",
        body=body + b"\nPage 47 test change\n",
    )
    current, current_inserted = store.capture(changed_response, "event_detail", fields)

    assert previous_inserted
    assert current_inserted
    assert previous["content_sha256"] != current["content_sha256"]
    assert compare_document(
        store,
        "2026-09-04T18:30:00Z",
        "recorded-event",
        previous,
        current,
        "event",
    ) == 1
    assert store.changes_path.read_text(encoding="utf-8").count("content_changed") == 1


def test_capture_history_records_versions_and_integrity_root(tmp_path: Path) -> None:
    response, body = recorded_capture("/v1/seattle/events/")
    response = replace(response, target="forward-observed-event")
    store = SnapshotStore(tmp_path / "evidence")
    previous, _ = store.capture(response, "event_detail", {"parse_status": "parsed"})
    current, _ = store.capture(
        replace(
            response,
            captured_at="2026-09-06T00:00:00Z",
            body=body + b"\nForward observation\n",
        ),
        "event_detail",
        {"parse_status": "parsed"},
    )

    history = store.capture_history("forward-observed-event", successful_only=True)
    window = store.observation_window("forward-observed-event")
    transition = store.observed_transition("forward-observed-event")

    assert [item["capture_key"] for item in history] == [
        previous["capture_key"],
        current["capture_key"],
    ]
    assert window["first_seen_at"] == response.captured_at
    assert window["last_seen_at"] == "2026-09-06T00:00:00Z"
    assert window["distinct_content_hashes"] == 2
    assert transition is not None
    assert transition[0]["content_sha256"] != transition[1]["content_sha256"]
    assert store.verify_integrity() is not None


def test_tampered_manifest_fails_integrity_verification(tmp_path: Path) -> None:
    response, _ = recorded_capture("/v1/seattle/events/")
    store = SnapshotStore(tmp_path / "evidence")
    store.capture(response, "event_detail", {"parse_status": "parsed"})
    integrity = store.integrity_path.read_text(encoding="utf-8")
    store.integrity_path.write_text(
        integrity.replace("capture_key", "tamper_key", 1), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="integrity chain"):
        SnapshotStore(tmp_path / "evidence")


def test_tampered_capture_body_fails_integrity_verification(tmp_path: Path) -> None:
    response, _ = recorded_capture("/v1/seattle/events/")
    store = SnapshotStore(tmp_path / "evidence")
    record, _ = store.capture(response, "event_detail", {"parse_status": "parsed"})
    storage_key = record["storage_key"]
    assert isinstance(storage_key, str)
    (tmp_path / "evidence" / storage_key).write_bytes(b"tampered evidence")

    with pytest.raises(ValueError, match="body hash"):
        store.verify_integrity()
