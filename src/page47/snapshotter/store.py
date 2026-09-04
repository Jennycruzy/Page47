"""Append-only local evidence storage for snapshotter runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from page47.snapshotter.config import JSONObject, JSONValue
from page47.snapshotter.http import FetchResult


def as_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [as_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Stored JSON object keys must be text")
            output[key] = as_json_value(item)
        return output
    raise ValueError(f"Unsupported stored value: {type(value).__name__}")


def as_object(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def text_value(record: JSONObject, key: str) -> str | None:
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def stable_json(value: JSONObject) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SnapshotStore:
    """Keep immutable bytes and metadata, deduplicated by observed content."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.body_dir = root / "bodies"
        self.manifest_path = root / "manifest.jsonl"
        self.runs_path = root / "runs.jsonl"
        self.changes_path = root / "changes.jsonl"
        self.body_dir.mkdir(parents=True, exist_ok=True)
        self.records = self._load_records()
        self.capture_keys = {
            key
            for record in self.records
            if (key := text_value(record, "capture_key")) is not None
        }

    def _load_records(self) -> list[JSONObject]:
        if not self.manifest_path.exists():
            return []
        records: list[JSONObject] = []
        for line_number, line in enumerate(
            self.manifest_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                raise ValueError(f"Blank line in {self.manifest_path} at line {line_number}")
            decoded: object = json.loads(line)
            records.append(as_object(as_json_value(decoded), f"manifest line {line_number}"))
        return records

    def latest(self, target: str) -> JSONObject | None:
        for record in reversed(self.records):
            if record.get("target") == target:
                return record
        return None

    def body(self, record: JSONObject) -> bytes:
        storage_key = text_value(record, "storage_key")
        if storage_key is None:
            raise ValueError("Capture has no storage key")
        path = self.root / storage_key
        if not path.exists():
            raise FileNotFoundError(path)
        return path.read_bytes()

    def capture(
        self,
        response: FetchResult,
        kind: str,
        fields: JSONObject,
    ) -> tuple[JSONObject, bool]:
        response_hash = hashlib.sha256(response.body).hexdigest()
        fingerprint_fields: JSONObject = {
            "target": response.target,
            "status": response.status,
            "response_sha256": response_hash,
            "fields": fields,
        }
        capture_key = hashlib.sha256(stable_json(fingerprint_fields).encode("utf-8")).hexdigest()
        existing = next(
            (record for record in self.records if record.get("capture_key") == capture_key),
            None,
        )
        if existing is not None:
            return existing, False
        body_path = self.body_dir / f"{response_hash}.body"
        if not body_path.exists():
            body_path.write_bytes(response.body)
        record: JSONObject = {
            "capture_key": capture_key,
            "target": response.target,
            "kind": kind,
            "source_url": response.url,
            "captured_at": response.captured_at,
            "status": response.status,
            "response_sha256": response_hash,
            "content_sha256": response_hash if response.status == 200 else None,
            "storage_key": str(body_path.relative_to(self.root)),
            "etag": response.headers.get("etag"),
            "http_last_modified": response.headers.get("last-modified"),
            "error_type": response.error_type,
            "error": response.error,
        }
        for key, value in fields.items():
            if key in record:
                raise ValueError(f"Capture field conflicts with reserved key: {key}")
            record[key] = value
        with self.manifest_path.open("a", encoding="utf-8") as manifest:
            manifest.write(json.dumps(record, sort_keys=True) + "\n")
        self.records.append(record)
        self.capture_keys.add(capture_key)
        return record, True

    def append_run(self, run: JSONObject) -> None:
        with self.runs_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(run, sort_keys=True) + "\n")

    def append_change(self, change: JSONObject) -> None:
        with self.changes_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(change, sort_keys=True) + "\n")

    def attachment_ids(self, record: JSONObject) -> set[int]:
        raw = record.get("attachment_ids")
        if raw is None:
            return set()
        if not isinstance(raw, list):
            raise ValueError("Capture attachment_ids must be a list")
        output: set[int] = set()
        for value in raw:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError("Capture attachment_ids must contain integers")
            output.add(value)
        return output

    def count_manifest_rows(self) -> int:
        return len(self.records)

    def iter_target(self, target: str) -> Iterable[JSONObject]:
        return (record for record in self.records if record.get("target") == target)
