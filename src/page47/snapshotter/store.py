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
        self.integrity_path = root / "manifest-chain.jsonl"
        self.runs_path = root / "runs.jsonl"
        self.changes_path = root / "changes.jsonl"
        self.body_dir.mkdir(parents=True, exist_ok=True)
        self.records = self._load_records()
        self._ensure_integrity_chain()
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

    @staticmethod
    def _record_hash(record: JSONObject) -> str:
        return hashlib.sha256(stable_json(record).encode("utf-8")).hexdigest()

    @staticmethod
    def _chain_hash(previous: str, record_hash: str) -> str:
        return hashlib.sha256(f"{previous}:{record_hash}".encode()).hexdigest()

    def _load_integrity_entries(self) -> list[JSONObject]:
        if not self.integrity_path.exists():
            return []
        entries: list[JSONObject] = []
        for line_number, line in enumerate(
            self.integrity_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                raise ValueError(f"Blank line in {self.integrity_path} at line {line_number}")
            decoded: object = json.loads(line)
            entries.append(
                as_object(as_json_value(decoded), f"integrity line {line_number}")
            )
        return entries

    def _chain_for_records(self, records: list[JSONObject]) -> list[JSONObject]:
        previous = "0" * 64
        entries: list[JSONObject] = []
        for index, record in enumerate(records, start=1):
            record_hash = self._record_hash(record)
            chain_hash = self._chain_hash(previous, record_hash)
            capture_key = text_value(record, "capture_key")
            if capture_key is None:
                raise ValueError(f"Manifest record {index} had no capture key")
            entries.append(
                {
                    "manifest_index": index,
                    "capture_key": capture_key,
                    "record_sha256": record_hash,
                    "previous_chain_sha256": previous,
                    "chain_sha256": chain_hash,
                }
            )
            previous = chain_hash
        return entries

    def _write_integrity_entries(self, entries: list[JSONObject]) -> None:
        payload = "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries)
        self.integrity_path.write_text(payload, encoding="utf-8")

    def _ensure_integrity_chain(self) -> None:
        if not self.records:
            if self.integrity_path.exists() and self._load_integrity_entries():
                raise ValueError("Evidence integrity chain existed without manifest records")
            return
        if not self.integrity_path.exists():
            self._write_integrity_entries(self._chain_for_records(self.records))
            self.verify_integrity()
            return
        self.verify_integrity()

    def verify_integrity(self) -> str | None:
        """Verify the append-only hash chain and return its current root."""

        disk_records = self._load_records()
        if disk_records != self.records:
            raise ValueError(
                "Evidence integrity chain cannot verify a capture manifest that changed "
                "after the store was loaded"
            )
        entries = self._load_integrity_entries()
        if len(entries) != len(disk_records):
            raise ValueError(
                "Evidence integrity chain length did not match the capture manifest"
            )
        expected_entries = self._chain_for_records(disk_records)
        for index, (actual, expected) in enumerate(
            zip(entries, expected_entries, strict=True), start=1
        ):
            if actual != expected:
                raise ValueError(f"Evidence integrity chain failed at manifest record {index}")
        for record in disk_records:
            self.body(record)
        if not entries:
            return None
        root = entries[-1].get("chain_sha256")
        if not isinstance(root, str) or not root:
            raise ValueError("Evidence integrity chain had no root")
        return root

    def latest(self, target: str) -> JSONObject | None:
        for record in reversed(self.records):
            if record.get("target") == target:
                return record
        return None

    def body(self, record: JSONObject) -> bytes:
        storage_key = text_value(record, "storage_key")
        if storage_key is None:
            raise ValueError("Capture has no storage key")
        root = self.root.resolve()
        path = (self.root / storage_key).resolve()
        if path != root and root not in path.parents:
            raise ValueError("Capture storage path escaped the evidence root")
        if not path.exists():
            raise FileNotFoundError(path)
        body = path.read_bytes()
        expected_hash = text_value(record, "response_sha256")
        if expected_hash is None:
            raise ValueError("Capture has no response hash")
        actual_hash = hashlib.sha256(body).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(
                f"Capture body hash did not match its manifest for {storage_key}"
            )
        return body

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
        elif hashlib.sha256(body_path.read_bytes()).hexdigest() != response_hash:
            raise ValueError(f"Existing capture body did not match hash {response_hash}")
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
        self._append_integrity_entry(record)
        self.capture_keys.add(capture_key)
        return record, True

    def _append_integrity_entry(self, record: JSONObject) -> None:
        entries = self._load_integrity_entries()
        previous = entries[-1].get("chain_sha256") if entries else "0" * 64
        if not isinstance(previous, str):
            raise ValueError("Evidence integrity chain had an invalid previous root")
        capture_key = text_value(record, "capture_key")
        if capture_key is None:
            raise ValueError("Cannot chain a capture without a capture key")
        record_hash = self._record_hash(record)
        entry: JSONObject = {
            "manifest_index": len(entries) + 1,
            "capture_key": capture_key,
            "record_sha256": record_hash,
            "previous_chain_sha256": previous,
            "chain_sha256": self._chain_hash(previous, record_hash),
        }
        with self.integrity_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(entry, sort_keys=True) + "\n")

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

    def capture_history(
        self,
        target: str,
        *,
        successful_only: bool = False,
    ) -> tuple[JSONObject, ...]:
        records = [record for record in self.records if record.get("target") == target]
        if successful_only:
            records = [
                record
                for record in records
                if record.get("status") == 200 and text_value(record, "content_sha256") is not None
            ]
        return tuple(sorted(records, key=lambda record: text_value(record, "captured_at") or ""))

    def observation_window(self, target: str) -> JSONObject:
        """Summarize the observed versions of one public target."""

        records = self.capture_history(target, successful_only=True)
        versions: dict[str, JSONObject] = {}
        for record in records:
            content_hash = text_value(record, "content_sha256")
            captured_at = text_value(record, "captured_at")
            capture_key = text_value(record, "capture_key")
            if content_hash is None or captured_at is None or capture_key is None:
                continue
            version = versions.get(content_hash)
            if version is None:
                versions[content_hash] = {
                    "content_sha256": content_hash,
                    "first_seen_at": captured_at,
                    "last_seen_at": captured_at,
                    "capture_count": 1,
                    "capture_keys": [capture_key],
                }
            else:
                version["last_seen_at"] = captured_at
                count = version.get("capture_count")
                if isinstance(count, int):
                    version["capture_count"] = count + 1
                keys = version.get("capture_keys")
                if isinstance(keys, list):
                    keys.append(capture_key)
        return {
            "target": target,
            "first_seen_at": text_value(records[0], "captured_at") if records else None,
            "last_seen_at": text_value(records[-1], "captured_at") if records else None,
            "distinct_content_hashes": len(versions),
            "versions": list(versions.values()),
        }

    def observed_transition(self, target: str) -> tuple[JSONObject, JSONObject] | None:
        """Return the first two distinct successful versions Page 47 captured."""

        records = self.capture_history(target, successful_only=True)
        seen_hashes: set[str] = set()
        versions: list[JSONObject] = []
        for record in records:
            content_hash = text_value(record, "content_sha256")
            if content_hash is None or content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)
            versions.append(record)
            if len(versions) == 2:
                return versions[0], versions[1]
        return None
