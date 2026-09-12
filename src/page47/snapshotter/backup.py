"""Optional durable backup for the local evidence store."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from page47.snapshotter.config import JSONObject
from page47.snapshotter.store import SnapshotStore, text_value


class S3PutClient(Protocol):
    def put_object(self, **kwargs: object) -> object: ...

    def head_object(self, **kwargs: object) -> object: ...


@dataclass(frozen=True, slots=True)
class EvidenceBackup:
    bucket: str
    prefix: str
    uploaded_objects: int
    skipped_objects: int
    capture_count: int
    integrity_root: str | None

    def as_json(self) -> JSONObject:
        return {
            "bucket": self.bucket,
            "prefix": self.prefix,
            "uploaded_objects": self.uploaded_objects,
            "skipped_objects": self.skipped_objects,
            "capture_count": self.capture_count,
            "integrity_root": self.integrity_root,
        }


def _object_key(prefix: str, relative_path: str) -> str:
    clean_prefix = prefix.strip("/")
    clean_path = relative_path.lstrip("/")
    if (
        (".." in Path(clean_prefix).parts if clean_prefix else False)
        or not clean_path
        or ".." in Path(clean_path).parts
    ):
        raise ValueError("Evidence backup path was invalid")
    return f"{clean_prefix}/{clean_path}" if clean_prefix else clean_path


def _put(
    client: S3PutClient,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str,
    metadata: dict[str, str],
) -> None:
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType=content_type,
        Metadata=metadata,
    )


def _remote_hash(
    client: S3PutClient,
    bucket: str,
    key: str,
) -> str | None:
    try:
        result = client.head_object(Bucket=bucket, Key=key)
    except Exception as error:
        response = getattr(error, "response", None)
        if isinstance(response, dict):
            details = response.get("Error")
            if isinstance(details, dict) and str(details.get("Code")) in {
                "404",
                "NoSuchKey",
                "NotFound",
            }:
                return None
        raise
    if not isinstance(result, dict):
        return None
    metadata = result.get("Metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("sha256")
    return value if isinstance(value, str) and value else None


def _put_if_changed(
    client: S3PutClient,
    bucket: str,
    key: str,
    body: bytes,
    content_type: str,
    metadata: dict[str, str],
) -> bool:
    digest = hashlib.sha256(body).hexdigest()
    if _remote_hash(client, bucket, key) == digest:
        return False
    _put(
        client,
        bucket,
        key,
        body,
        content_type,
        {**metadata, "sha256": digest},
    )
    return True


def backup_evidence(
    store: SnapshotStore,
    client: S3PutClient,
    *,
    bucket: str,
    prefix: str = "page47-evidence",
) -> EvidenceBackup:
    """Copy capture bytes and manifests after verifying local integrity."""

    if not bucket.strip():
        raise ValueError("Evidence backup bucket must not be empty")
    integrity_root = store.verify_integrity()
    uploaded = 0
    skipped = 0
    seen_storage_keys: set[str] = set()
    for record in store.records:
        capture_key = text_value(record, "capture_key")
        storage_key = text_value(record, "storage_key")
        response_hash = text_value(record, "response_sha256")
        if capture_key is None or storage_key is None or response_hash is None:
            raise ValueError("Capture manifest was incomplete")
        if storage_key in seen_storage_keys:
            continue
        seen_storage_keys.add(storage_key)
        body = store.body(record)
        changed = _put_if_changed(
            client,
            bucket,
            _object_key(prefix, storage_key),
            body,
            "application/octet-stream",
            {"capture-key": capture_key, "response-sha256": response_hash},
        )
        uploaded += int(changed)
        skipped += int(not changed)

    for relative_path, content_type in (
        ("manifest.jsonl", "application/x-ndjson"),
        ("manifest-chain.jsonl", "application/x-ndjson"),
        ("runs.jsonl", "application/x-ndjson"),
        ("changes.jsonl", "application/x-ndjson"),
    ):
        path = store.root / relative_path
        if not path.exists():
            continue
        body = path.read_bytes()
        changed = _put_if_changed(
            client,
            bucket,
            _object_key(prefix, relative_path),
            body,
            content_type,
            {"integrity-root": integrity_root or "empty"},
        )
        uploaded += int(changed)
        skipped += int(not changed)
    return EvidenceBackup(
        bucket=bucket,
        prefix=prefix.strip("/"),
        uploaded_objects=uploaded,
        skipped_objects=skipped,
        capture_count=len(store.records),
        integrity_root=integrity_root,
    )
