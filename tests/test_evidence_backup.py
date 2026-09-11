from __future__ import annotations

from pathlib import Path

from page47.snapshotter.backup import backup_evidence
from page47.snapshotter.http import FetchResult
from page47.snapshotter.store import SnapshotStore


class FakeS3:
    def __init__(self) -> None:
        self.objects: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> object:
        self.objects.append(kwargs)
        return {}


def response() -> FetchResult:
    return FetchResult(
        target="event:1",
        url="https://records.example/event/1",
        captured_at="2026-09-11T00:00:00Z",
        status=200,
        headers={},
        body=b"captured public record",
        error_type=None,
        error=None,
        not_modified=False,
    )


def test_backup_copies_bytes_and_integrity_manifests(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "evidence")
    store.capture(response(), "event_detail", {"parse_status": "parsed"})
    client = FakeS3()

    result = backup_evidence(store, client, bucket="page47-test", prefix="evidence")

    assert result.capture_count == 1
    assert result.uploaded_objects == 3
    assert result.integrity_root is not None
    keys = {item["Key"] for item in client.objects}
    assert any(
        isinstance(key, str) and key.startswith("evidence/bodies/")
        for key in keys
    )
    assert "evidence/manifest.jsonl" in keys
    assert "evidence/manifest-chain.jsonl" in keys


def test_backup_refuses_tampered_capture_manifest(tmp_path: Path) -> None:
    store = SnapshotStore(tmp_path / "evidence")
    store.capture(response(), "event_detail", {"parse_status": "parsed"})
    manifest = store.manifest_path.read_text(encoding="utf-8")
    store.manifest_path.write_text(
        manifest.replace("event_detail", "tampered", 1), encoding="utf-8"
    )

    client = FakeS3()
    try:
        backup_evidence(store, client, bucket="page47-test")
    except ValueError as error:
        assert "integrity chain" in str(error)
    else:
        raise AssertionError("Tampered evidence should not be backed up")
