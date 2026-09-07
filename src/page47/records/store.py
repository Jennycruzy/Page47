"""A repeatable SQLite record store with field-level source references."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Final

from page47.snapshotter.config import JSONObject, JSONValue, as_json_value

type SQLValue = int | str | None

SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY,
    event_date TEXT,
    body_id INTEGER,
    body_name TEXT,
    agenda_file TEXT,
    agenda_last_published_utc TEXT,
    agenda_status_name TEXT,
    in_site_url TEXT,
    comment TEXT,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS matters (
    matter_id INTEGER PRIMARY KEY,
    file_number TEXT,
    matter_name TEXT,
    current_title TEXT,
    type_name TEXT,
    status_name TEXT,
    body_id INTEGER,
    body_name TEXT,
    intro_date TEXT,
    agenda_date TEXT,
    version TEXT,
    last_modified_utc TEXT,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appearances (
    event_item_id INTEGER PRIMARY KEY,
    matter_id INTEGER,
    event_id INTEGER NOT NULL,
    event_date TEXT,
    body_id INTEGER,
    body_name TEXT,
    title_as_presented TEXT,
    consent_value INTEGER,
    pdf_placement TEXT,
    pdf_evidence_pages_json TEXT,
    pdf_placement_reason TEXT,
    agenda_sequence INTEGER,
    agenda_number TEXT,
    action_taken TEXT,
    action_text TEXT,
    passed_flag_name TEXT,
    matter_version_at_event TEXT,
    agenda_note TEXT,
    minutes_note TEXT,
    item_last_modified_utc TEXT,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id INTEGER PRIMARY KEY,
    matter_id INTEGER,
    name TEXT,
    url TEXT,
    version TEXT,
    last_modified_utc TEXT,
    first_observed_by_us TEXT NOT NULL,
    content_hash TEXT,
    supporting_document INTEGER,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appearance_attachments (
    event_item_id INTEGER NOT NULL,
    attachment_id INTEGER NOT NULL,
    matter_id INTEGER,
    name TEXT,
    url TEXT,
    version TEXT,
    last_modified_utc TEXT,
    supporting_document INTEGER,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    PRIMARY KEY (event_item_id, attachment_id)
);

CREATE TABLE IF NOT EXISTS attachment_readings (
    attachment_id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    references_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_extractions (
    attachment_id INTEGER PRIMARY KEY,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    model_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots (
    capture_key TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    status INTEGER,
    response_sha256 TEXT NOT NULL,
    content_sha256 TEXT,
    storage_key TEXT NOT NULL,
    source_kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS parse_failures (
    failure_key TEXT PRIMARY KEY,
    target TEXT NOT NULL,
    source_url TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    response_sha256 TEXT,
    error TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    counts_json TEXT NOT NULL,
    structural_fingerprint TEXT NOT NULL,
    issues_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS investigation_runs (
    run_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    matter_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    graph_result_json TEXT NOT NULL,
    policy_json TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    finding_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    matter_id INTEGER NOT NULL,
    state TEXT NOT NULL,
    publish INTEGER NOT NULL,
    supported_count INTEGER NOT NULL,
    rejected_count INTEGER NOT NULL,
    decision_json TEXT NOT NULL,
    brief_json TEXT,
    norms_json TEXT,
    fingerprint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watches (
    watch_id TEXT PRIMARY KEY,
    city TEXT NOT NULL,
    bodies_json TEXT NOT NULL,
    address TEXT,
    neighbourhood TEXT,
    email TEXT NOT NULL,
    active INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL,
    city TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    status TEXT NOT NULL,
    area_status TEXT NOT NULL,
    area_reason TEXT NOT NULL,
    provider_message_id TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (watch_id, finding_id)
);

CREATE INDEX IF NOT EXISTS findings_by_matter ON findings (matter_id, updated_at);
CREATE INDEX IF NOT EXISTS findings_by_city ON findings (city, updated_at);
CREATE INDEX IF NOT EXISTS watches_by_city ON watches (city, active);
CREATE INDEX IF NOT EXISTS notifications_by_finding ON notifications (finding_id, status);

CREATE INDEX IF NOT EXISTS appearances_by_matter
    ON appearances (matter_id);
CREATE INDEX IF NOT EXISTS appearances_by_event
    ON appearances (event_id);
CREATE INDEX IF NOT EXISTS attachments_by_matter
    ON attachments (matter_id);
CREATE INDEX IF NOT EXISTS attachment_readings_by_content
    ON attachment_readings (content_hash);
"""


@dataclass(frozen=True, slots=True)
class SourceReference:
    """The record location and time that support one or more stored values."""

    kind: str
    url: str
    captured_at: str

    def as_json(self) -> JSONObject:
        return {
            "kind": self.kind,
            "url": self.url,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True, slots=True)
class EventObservation:
    event_id: int
    event_date: str | None
    body_id: int | None
    body_name: str | None
    agenda_file: str | None
    agenda_last_published_utc: str | None
    agenda_status_name: str | None
    in_site_url: str | None
    comment: str | None
    source: SourceReference
    provenance: JSONObject


@dataclass(frozen=True, slots=True)
class MatterObservation:
    matter_id: int
    file_number: str | None
    matter_name: str | None
    current_title: str | None
    type_name: str | None
    status_name: str | None
    body_id: int | None
    body_name: str | None
    intro_date: str | None
    agenda_date: str | None
    version: str | None
    last_modified_utc: str | None
    source: SourceReference
    provenance: JSONObject


@dataclass(frozen=True, slots=True)
class AppearanceObservation:
    event_item_id: int
    matter_id: int | None
    event_id: int
    event_date: str | None
    body_id: int | None
    body_name: str | None
    title_as_presented: str | None
    consent_value: int | None
    pdf_placement: str | None
    pdf_evidence_pages_json: str | None
    pdf_placement_reason: str | None
    agenda_sequence: int | None
    agenda_number: str | None
    action_taken: str | None
    action_text: str | None
    passed_flag_name: str | None
    matter_version_at_event: str | None
    agenda_note: str | None
    minutes_note: str | None
    item_last_modified_utc: str | None
    source: SourceReference
    provenance: JSONObject


@dataclass(frozen=True, slots=True)
class PlacementHistoryItem:
    event_item_id: int
    event_date: str | None
    title_as_presented: str | None
    placement: str | None
    evidence_pages: tuple[int, ...]
    source: SourceReference | None


@dataclass(frozen=True, slots=True)
class EventAppearanceTitle:
    event_item_id: int
    title_as_presented: str


@dataclass(frozen=True, slots=True)
class EventAgenda:
    event_id: int
    agenda_file: str


@dataclass(frozen=True, slots=True)
class AttachmentObservation:
    attachment_id: int
    matter_id: int | None
    name: str | None
    url: str | None
    version: str | None
    last_modified_utc: str | None
    first_observed_by_us: str
    content_hash: str | None
    supporting_document: bool | None
    source: SourceReference
    provenance: JSONObject
    content_source: SourceReference | None


@dataclass(frozen=True, slots=True)
class StoredAttachmentSource:
    """A stored attachment URL eligible for a later evidence capture."""

    attachment_id: int
    matter_id: int | None
    name: str | None
    url: str | None
    version: str | None
    last_modified_utc: str | None


@dataclass(frozen=True, slots=True)
class AttachmentReadingObservation:
    attachment_id: int
    content_hash: str
    status: str
    page_count: int
    references: JSONObject
    reason: str
    source: SourceReference


@dataclass(frozen=True, slots=True)
class DocumentExtractionObservation:
    attachment_id: int
    content_hash: str
    status: str
    changes: JSONValue
    reason: str
    model_id: str
    source: SourceReference


@dataclass(frozen=True, slots=True)
class InvestigationRunObservation:
    run_id: str
    city: str
    matter_id: int
    started_at: str
    finished_at: str
    status: str
    graph_result: JSONValue
    policy: JSONObject | None
    error: str | None


@dataclass(frozen=True, slots=True)
class FindingObservation:
    finding_id: str
    city: str
    matter_id: int
    state: str
    publish: bool
    supported_count: int
    rejected_count: int
    decision: JSONObject
    brief: JSONObject | None
    norms: JSONObject | None
    fingerprint: str
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class WatchObservation:
    watch_id: str
    city: str
    bodies: JSONValue
    address: str | None
    neighbourhood: str | None
    email: str
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class NotificationObservation:
    notification_id: str
    watch_id: str
    city: str
    finding_id: str
    status: str
    area_status: str
    area_reason: str
    provider_message_id: str | None
    error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class SnapshotObservation:
    capture_key: str
    target: str
    kind: str
    source_url: str
    captured_at: str
    status: int | None
    response_sha256: str
    content_sha256: str | None
    storage_key: str
    source_kind: str


def stable_json(value: JSONValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def provenance_json(value: JSONObject) -> str:
    return stable_json(value)


def json_object(value: object, context: str) -> JSONObject:
    validated = as_json_value(value)
    if not isinstance(validated, dict):
        raise ValueError(f"Expected an object for {context}")
    return validated


def parse_provenance(value: object, context: str) -> JSONObject:
    if not isinstance(value, str):
        raise ValueError(f"Stored provenance for {context} was not text")
    try:
        decoded: object = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Stored provenance for {context} was not valid JSON") from error
    return json_object(decoded, context)


def bool_as_integer(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def value_is_present(value: SQLValue) -> bool:
    return value is not None


class RecordStore:
    """Store normalized records while retaining the source for each value."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SCHEMA)
        columns = {
            row[1]
            for row in self.connection.execute("PRAGMA table_info(appearances)").fetchall()
        }
        for name, definition in (
            ("pdf_placement", "TEXT"),
            ("pdf_evidence_pages_json", "TEXT"),
            ("pdf_placement_reason", "TEXT"),
        ):
            if name not in columns:
                self.connection.execute(f"ALTER TABLE appearances ADD COLUMN {name} {definition}")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> RecordStore:
        return self

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        self.close()

    def add_snapshot(self, observation: SnapshotObservation) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO snapshots
            (capture_key, target, kind, source_url, captured_at, status,
             response_sha256, content_sha256, storage_key, source_kind)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.capture_key,
                observation.target,
                observation.kind,
                observation.source_url,
                observation.captured_at,
                observation.status,
                observation.response_sha256,
                observation.content_sha256,
                observation.storage_key,
                observation.source_kind,
            ),
        )

    def has_snapshot(self, capture_key: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM snapshots WHERE capture_key = ?", (capture_key,)
        ).fetchone()
        return row is not None

    def add_parse_failure(
        self,
        target: str,
        source_url: str,
        captured_at: str,
        response_sha256: str | None,
        error: str,
    ) -> None:
        material: JSONObject = {
            "target": target,
            "source_url": source_url,
            "captured_at": captured_at,
            "response_sha256": response_sha256,
            "error": error,
        }
        failure_key = sha256(stable_json(material).encode("utf-8")).hexdigest()
        self.connection.execute(
            """
            INSERT OR IGNORE INTO parse_failures
            (failure_key, target, source_url, captured_at, response_sha256, error)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (failure_key, target, source_url, captured_at, response_sha256, error),
        )

    def upsert_event(self, observation: EventObservation) -> None:
        values: dict[str, SQLValue] = {
            "event_date": observation.event_date,
            "body_id": observation.body_id,
            "body_name": observation.body_name,
            "agenda_file": observation.agenda_file,
            "agenda_last_published_utc": observation.agenda_last_published_utc,
            "agenda_status_name": observation.agenda_status_name,
            "in_site_url": observation.in_site_url,
            "comment": observation.comment,
        }
        self._merge_row(
            table="events",
            key_column="event_id",
            key_value=observation.event_id,
            values=values,
            source=observation.source,
            provenance=observation.provenance,
        )

    def upsert_matter(self, observation: MatterObservation) -> None:
        values: dict[str, SQLValue] = {
            "file_number": observation.file_number,
            "matter_name": observation.matter_name,
            "current_title": observation.current_title,
            "type_name": observation.type_name,
            "status_name": observation.status_name,
            "body_id": observation.body_id,
            "body_name": observation.body_name,
            "intro_date": observation.intro_date,
            "agenda_date": observation.agenda_date,
            "version": observation.version,
            "last_modified_utc": observation.last_modified_utc,
        }
        self._merge_row(
            table="matters",
            key_column="matter_id",
            key_value=observation.matter_id,
            values=values,
            source=observation.source,
            provenance=observation.provenance,
        )

    def upsert_appearance(self, observation: AppearanceObservation) -> None:
        values: dict[str, SQLValue] = {
            "matter_id": observation.matter_id,
            "event_id": observation.event_id,
            "event_date": observation.event_date,
            "body_id": observation.body_id,
            "body_name": observation.body_name,
            "title_as_presented": observation.title_as_presented,
            "consent_value": observation.consent_value,
            "pdf_placement": observation.pdf_placement,
            "pdf_evidence_pages_json": observation.pdf_evidence_pages_json,
            "pdf_placement_reason": observation.pdf_placement_reason,
            "agenda_sequence": observation.agenda_sequence,
            "agenda_number": observation.agenda_number,
            "action_taken": observation.action_taken,
            "action_text": observation.action_text,
            "passed_flag_name": observation.passed_flag_name,
            "matter_version_at_event": observation.matter_version_at_event,
            "agenda_note": observation.agenda_note,
            "minutes_note": observation.minutes_note,
            "item_last_modified_utc": observation.item_last_modified_utc,
        }
        self._merge_row(
            table="appearances",
            key_column="event_item_id",
            key_value=observation.event_item_id,
            values=values,
            source=observation.source,
            provenance=observation.provenance,
        )

    def set_pdf_placement(
        self,
        event_item_id: int,
        placement: str,
        evidence_pages: tuple[int, ...],
        reason: str,
        source: SourceReference,
    ) -> None:
        if placement not in {"consent", "regular", "cannot_determine"}:
            raise ValueError(f"Unsupported PDF placement {placement}")
        row = self.connection.execute(
            "SELECT provenance_json FROM appearances WHERE event_item_id = ?",
            (event_item_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Cannot add PDF placement to missing appearance {event_item_id}")
        provenance = parse_provenance(row[0], "appearances.provenance")
        placement_source = source.as_json()
        provenance["pdf_placement"] = placement_source
        provenance["pdf_evidence_pages_json"] = placement_source
        provenance["pdf_placement_reason"] = placement_source
        self.connection.execute(
            """
            UPDATE appearances
            SET pdf_placement = ?, pdf_evidence_pages_json = ?,
                pdf_placement_reason = ?, provenance_json = ?
            WHERE event_item_id = ?
            """,
            (
                placement,
                stable_json(list(evidence_pages)),
                reason,
                provenance_json(provenance),
                event_item_id,
            ),
        )

    def consent_placement_inputs(self) -> tuple[tuple[int, int, SourceReference], ...]:
        """Return recorded API placement values with their field sources."""

        rows = self.connection.execute(
            "SELECT event_item_id, consent_value, provenance_json FROM appearances "
            "WHERE consent_value IS NOT NULL ORDER BY event_item_id"
        ).fetchall()
        output: list[tuple[int, int, SourceReference]] = []
        for row in rows:
            event_item_id = row[0]
            consent_value = row[1]
            if (
                isinstance(event_item_id, bool)
                or not isinstance(event_item_id, int)
                or isinstance(consent_value, bool)
                or not isinstance(consent_value, int)
            ):
                raise ValueError("Stored API placement input was invalid")
            provenance = parse_provenance(row[2], "appearances.provenance")
            source = self._source_from_json(provenance.get("consent_value"), "consent value")
            output.append((event_item_id, consent_value, source))
        return tuple(output)

    def upsert_attachment(
        self,
        observation: AttachmentObservation,
    ) -> None:
        existing = self.connection.execute(
            "SELECT first_observed_by_us FROM attachments WHERE attachment_id = ?",
            (observation.attachment_id,),
        ).fetchone()
        first_observed = observation.first_observed_by_us
        if existing is not None:
            existing_first = existing[0]
            if not isinstance(existing_first, str) or not existing_first:
                raise ValueError(
                    f"Attachment {observation.attachment_id} has an invalid first observation"
                )
            if existing_first < first_observed:
                first_observed = existing_first
        preserve_provenance: frozenset[str] = frozenset()
        if existing is not None:
            existing_first = existing[0]
            if isinstance(existing_first, str) and existing_first <= first_observed:
                preserve_provenance = frozenset({"first_observed_by_us"})
        values: dict[str, SQLValue] = {
            "matter_id": observation.matter_id,
            "name": observation.name,
            "url": observation.url,
            "version": observation.version,
            "last_modified_utc": observation.last_modified_utc,
            "first_observed_by_us": first_observed,
            "content_hash": observation.content_hash,
            "supporting_document": bool_as_integer(observation.supporting_document),
        }
        self._merge_row(
            table="attachments",
            key_column="attachment_id",
            key_value=observation.attachment_id,
            values=values,
            source=observation.source,
            provenance=observation.provenance,
            preserve_provenance=preserve_provenance,
        )
        if observation.content_source is not None and observation.content_hash is not None:
            self._merge_provenance(
                "attachments",
                "attachment_id",
                observation.attachment_id,
                {"content_hash": observation.content_source.as_json()},
            )

    def attachment_sources(self) -> tuple[StoredAttachmentSource, ...]:
        """Return attachment URLs recovered from the normalized public record."""

        rows = self.connection.execute(
            "SELECT attachment_id, matter_id, name, url, version, last_modified_utc "
            "FROM attachments ORDER BY attachment_id"
        ).fetchall()
        output: list[StoredAttachmentSource] = []
        for row in rows:
            attachment_id = row["attachment_id"]
            matter_id = row["matter_id"]
            name = row["name"]
            url = row["url"]
            version = row["version"]
            last_modified_utc = row["last_modified_utc"]
            if isinstance(attachment_id, bool) or not isinstance(attachment_id, int):
                raise ValueError("Stored attachment ID was invalid")
            if matter_id is not None and (
                isinstance(matter_id, bool) or not isinstance(matter_id, int)
            ):
                raise ValueError(f"Stored attachment {attachment_id} matter ID was invalid")
            for value, label in (
                (name, "name"),
                (url, "url"),
                (version, "version"),
                (last_modified_utc, "last modified time"),
            ):
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"Stored attachment {attachment_id} {label} was invalid")
            output.append(
                StoredAttachmentSource(
                    attachment_id=attachment_id,
                    matter_id=matter_id,
                    name=name,
                    url=url,
                    version=version,
                    last_modified_utc=last_modified_utc,
                )
            )
        return tuple(output)

    def upsert_attachment_reading(self, observation: AttachmentReadingObservation) -> None:
        if observation.status not in {"candidate", "absent", "unreadable"}:
            raise ValueError(f"Unsupported attachment reading status {observation.status}")
        if observation.page_count < 0:
            raise ValueError("Attachment reading page count must not be negative")
        values: dict[str, SQLValue] = {
            "content_hash": observation.content_hash,
            "status": observation.status,
            "page_count": observation.page_count,
            "references_json": provenance_json(observation.references),
            "reason": observation.reason,
        }
        provenance: JSONObject = {
            "content_hash": observation.source.as_json(),
            "status": observation.source.as_json(),
            "page_count": observation.source.as_json(),
            "references_json": observation.source.as_json(),
            "reason": observation.source.as_json(),
        }
        self._merge_row(
            table="attachment_readings",
            key_column="attachment_id",
            key_value=observation.attachment_id,
            values=values,
            source=observation.source,
            provenance=provenance,
        )

    def upsert_document_extraction(
        self, observation: DocumentExtractionObservation
    ) -> None:
        if observation.status not in {"read", "absent", "unreadable", "failed"}:
            raise ValueError(f"Unsupported document extraction status {observation.status}")
        if not observation.content_hash:
            raise ValueError("Document extraction content hash must not be empty")
        if not observation.reason.strip():
            raise ValueError("Document extraction reason must not be empty")
        if not observation.model_id.strip():
            raise ValueError("Document extraction model ID must not be empty")
        changes = as_json_value(observation.changes)
        values: dict[str, SQLValue] = {
            "content_hash": observation.content_hash,
            "status": observation.status,
            "changes_json": stable_json(changes),
            "reason": observation.reason,
            "model_id": observation.model_id,
        }
        provenance: JSONObject = {
            "content_hash": observation.source.as_json(),
            "status": observation.source.as_json(),
            "changes_json": observation.source.as_json(),
            "reason": observation.source.as_json(),
            "model_id": observation.source.as_json(),
        }
        self._merge_row(
            table="document_extractions",
            key_column="attachment_id",
            key_value=observation.attachment_id,
            values=values,
            source=observation.source,
            provenance=provenance,
        )

    def attachment_reading_hash(self, attachment_id: int) -> str | None:
        row = self.connection.execute(
            "SELECT content_hash FROM attachment_readings WHERE attachment_id = ?",
            (attachment_id,),
        ).fetchone()
        if row is None:
            return None
        content_hash = row[0]
        if not isinstance(content_hash, str) or not content_hash:
            raise ValueError(
                f"Stored attachment reading {attachment_id} has an invalid content hash"
            )
        return content_hash

    def document_extraction_hash(self, attachment_id: int) -> str | None:
        row = self.connection.execute(
            "SELECT content_hash FROM document_extractions WHERE attachment_id = ?",
            (attachment_id,),
        ).fetchone()
        if row is None:
            return None
        content_hash = row[0]
        if not isinstance(content_hash, str) or not content_hash:
            raise ValueError(
                f"Stored document extraction {attachment_id} has an invalid content hash"
            )
        return content_hash

    def attachment_reading(self, attachment_id: int) -> AttachmentReadingObservation | None:
        row = self.connection.execute(
            "SELECT * FROM attachment_readings WHERE attachment_id = ?", (attachment_id,)
        ).fetchone()
        if row is None:
            return None
        status = row["status"]
        content_hash = row["content_hash"]
        page_count = row["page_count"]
        reason = row["reason"]
        if not isinstance(status, str) or not isinstance(content_hash, str):
            raise ValueError("Stored attachment reading had invalid status or hash")
        if isinstance(page_count, bool) or not isinstance(page_count, int):
            raise ValueError("Stored attachment reading had invalid page count")
        if not isinstance(reason, str):
            raise ValueError("Stored attachment reading had invalid reason")
        raw_references = row["references_json"]
        if not isinstance(raw_references, str):
            raise ValueError("Stored attachment reading references were not text")
        try:
            decoded_references: object = json.loads(raw_references)
        except json.JSONDecodeError as error:
            raise ValueError("Stored attachment reading references were invalid JSON") from error
        return AttachmentReadingObservation(
            attachment_id=attachment_id,
            content_hash=content_hash,
            status=status,
            page_count=page_count,
            references=json_object(decoded_references, "attachment reading references"),
            reason=reason,
            source=SourceReference(
                kind="snapshot",
                url=str(row["source_url"]),
                captured_at=str(row["observed_at"]),
            ),
        )

    def upsert_appearance_attachment(
        self,
        event_item_id: int,
        observation: AttachmentObservation,
    ) -> None:
        values: dict[str, SQLValue] = {
            "matter_id": observation.matter_id,
            "name": observation.name,
            "url": observation.url,
            "version": observation.version,
            "last_modified_utc": observation.last_modified_utc,
            "supporting_document": bool_as_integer(observation.supporting_document),
        }
        self._merge_row(
            table="appearance_attachments",
            key_column="event_item_id",
            key_value=event_item_id,
            values=values,
            source=observation.source,
            provenance=observation.provenance,
            composite_key_column="attachment_id",
            composite_key_value=observation.attachment_id,
        )

    def _merge_row(
        self,
        table: str,
        key_column: str,
        key_value: int,
        values: dict[str, SQLValue],
        source: SourceReference,
        provenance: JSONObject,
        composite_key_column: str | None = None,
        composite_key_value: int | None = None,
        preserve_provenance: frozenset[str] = frozenset(),
    ) -> None:
        if composite_key_column is None and composite_key_value is not None:
            raise ValueError("A composite key column is required with a composite key value")
        if composite_key_column is not None and composite_key_value is None:
            raise ValueError("A composite key value is required with a composite key column")
        where = f"{key_column} = ?"
        parameters: list[SQLValue] = [key_value]
        if composite_key_column is not None and composite_key_value is not None:
            where = f"{where} AND {composite_key_column} = ?"
            parameters.append(composite_key_value)
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE {where}", parameters
        ).fetchone()
        source_values = dict(provenance)
        for column, value in values.items():
            if value_is_present(value) and column not in source_values:
                source_values[column] = source.as_json()
        if row is None:
            columns = [key_column]
            insert_values: list[SQLValue] = [key_value]
            if composite_key_column is not None and composite_key_value is not None:
                columns.append(composite_key_column)
                insert_values.append(composite_key_value)
            for column, value in values.items():
                columns.append(column)
                insert_values.append(value)
            columns.extend(["source_url", "observed_at", "provenance_json"])
            insert_values.extend(
                [source.url, source.captured_at, provenance_json(source_values)]
            )
            placeholders = ", ".join("?" for _ in columns)
            self.connection.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                insert_values,
            )
            return
        existing_provenance = parse_provenance(
            row["provenance_json"], f"{table}.provenance"
        )
        merged_provenance = dict(existing_provenance)
        updates: dict[str, SQLValue] = {}
        for column, value in values.items():
            if value_is_present(value) or row[column] is None:
                updates[column] = value
            if value_is_present(value) and column not in preserve_provenance:
                provenance_value = source_values.get(column)
                if provenance_value is None:
                    provenance_value = source.as_json()
                merged_provenance[column] = provenance_value
        updates["source_url"] = source.url
        updates["observed_at"] = source.captured_at
        updates["provenance_json"] = provenance_json(merged_provenance)
        assignments = ", ".join(f"{column} = ?" for column in updates)
        update_parameters = list(updates.values()) + parameters
        self.connection.execute(
            f"UPDATE {table} SET {assignments} WHERE {where}", update_parameters
        )

    def _merge_provenance(
        self,
        table: str,
        key_column: str,
        key_value: int,
        additions: JSONObject,
    ) -> None:
        row = self.connection.execute(
            f"SELECT provenance_json FROM {table} WHERE {key_column} = ?", (key_value,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Cannot add provenance to missing {table} row {key_value}")
        existing = parse_provenance(row[0], f"{table}.provenance")
        existing.update(additions)
        self.connection.execute(
            f"UPDATE {table} SET provenance_json = ? WHERE {key_column} = ?",
            (provenance_json(existing), key_value),
        )

    def commit(self) -> None:
        self.connection.commit()

    def save_investigation_run(self, observation: InvestigationRunObservation) -> None:
        if not observation.run_id.strip():
            raise ValueError("Investigation run ID must not be empty")
        if not observation.city.strip():
            raise ValueError("Investigation run city must not be empty")
        if observation.matter_id < 1:
            raise ValueError("Investigation run matter ID must be positive")
        if not observation.started_at or not observation.finished_at:
            raise ValueError("Investigation run timestamps must not be empty")
        if not observation.status.strip():
            raise ValueError("Investigation run status must not be empty")
        policy_json = stable_json(observation.policy) if observation.policy is not None else None
        self.connection.execute(
            """
            INSERT OR REPLACE INTO investigation_runs
            (run_id, city, matter_id, started_at, finished_at, status,
             graph_result_json, policy_json, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.run_id,
                observation.city,
                observation.matter_id,
                observation.started_at,
                observation.finished_at,
                observation.status,
                stable_json(observation.graph_result),
                policy_json,
                observation.error,
            ),
        )

    def save_finding(self, observation: FindingObservation) -> None:
        if not observation.finding_id.strip():
            raise ValueError("Finding ID must not be empty")
        if not observation.city.strip():
            raise ValueError("Finding city must not be empty")
        if observation.matter_id < 1:
            raise ValueError("Finding matter ID must be positive")
        if observation.supported_count < 0 or observation.rejected_count < 0:
            raise ValueError("Finding counts must not be negative")
        if not observation.state.strip() or not observation.fingerprint.strip():
            raise ValueError("Finding state and fingerprint must not be empty")
        brief_json = stable_json(observation.brief) if observation.brief is not None else None
        norms_json = stable_json(observation.norms) if observation.norms is not None else None
        self.connection.execute(
            """
            INSERT OR REPLACE INTO findings
            (finding_id, city, matter_id, state, publish, supported_count,
             rejected_count, decision_json, brief_json, norms_json, fingerprint,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.finding_id,
                observation.city,
                observation.matter_id,
                observation.state,
                bool_as_integer(observation.publish),
                observation.supported_count,
                observation.rejected_count,
                stable_json(observation.decision),
                brief_json,
                norms_json,
                observation.fingerprint,
                observation.created_at,
                observation.updated_at,
            ),
        )

    def finding_rows(self, city: str | None = None, limit: int = 100) -> list[JSONObject]:
        if limit < 1:
            raise ValueError("Finding limit must be positive")
        if city is None:
            rows = self.connection.execute(
                "SELECT * FROM findings ORDER BY updated_at DESC, finding_id LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            if not city.strip():
                raise ValueError("Finding city filter must not be empty")
            rows = self.connection.execute(
                "SELECT * FROM findings WHERE city = ? "
                "ORDER BY updated_at DESC, finding_id LIMIT ?",
                (city, limit),
            ).fetchall()
        output: list[JSONObject] = []
        for row in rows:
            decision = json_object(json.loads(row["decision_json"]), "finding decision")
            brief_raw = row["brief_json"]
            norms_raw = row["norms_json"]
            brief = (
                json_object(json.loads(brief_raw), "finding brief")
                if isinstance(brief_raw, str)
                else None
            )
            norms = (
                json_object(json.loads(norms_raw), "finding norms")
                if isinstance(norms_raw, str)
                else None
            )
            publish_value = row["publish"]
            if isinstance(publish_value, bool) or not isinstance(publish_value, int):
                raise ValueError("Stored finding publish flag was invalid")
            output.append(
                {
                    "finding_id": row["finding_id"],
                    "city": row["city"],
                    "matter_id": row["matter_id"],
                    "state": row["state"],
                    "publish": bool(publish_value),
                    "supported_count": row["supported_count"],
                    "rejected_count": row["rejected_count"],
                    "decision": decision,
                    "brief": brief,
                    "norms": norms,
                    "fingerprint": row["fingerprint"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return output

    def save_watch(self, observation: WatchObservation) -> None:
        if not observation.watch_id.strip() or not observation.city.strip():
            raise ValueError("Watch ID and city must not be empty")
        if not observation.email.strip():
            raise ValueError("Watch email must not be empty")
        if not observation.created_at or not observation.updated_at:
            raise ValueError("Watch timestamps must not be empty")
        self.connection.execute(
            """
            INSERT OR REPLACE INTO watches
            (watch_id, city, bodies_json, address, neighbourhood, email, active,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                observation.watch_id,
                observation.city,
                stable_json(observation.bodies),
                observation.address,
                observation.neighbourhood,
                observation.email,
                bool_as_integer(observation.active),
                observation.created_at,
                observation.updated_at,
            ),
        )

    def watch_rows(self, city: str | None = None) -> list[JSONObject]:
        if city is None:
            rows = self.connection.execute(
                "SELECT * FROM watches WHERE active = 1 ORDER BY created_at, watch_id"
            ).fetchall()
        else:
            if not city.strip():
                raise ValueError("Watch city filter must not be empty")
            rows = self.connection.execute(
                "SELECT * FROM watches WHERE city = ? AND active = 1 "
                "ORDER BY created_at, watch_id",
                (city,),
            ).fetchall()
        return [self._watch_row(row) for row in rows]

    def watch_row(self, watch_id: str) -> JSONObject | None:
        if not watch_id.strip():
            raise ValueError("Watch ID must not be empty")
        row = self.connection.execute(
            "SELECT * FROM watches WHERE watch_id = ?", (watch_id,)
        ).fetchone()
        return self._watch_row(row) if row is not None else None

    def deactivate_watch(self, watch_id: str, updated_at: str) -> None:
        if not watch_id.strip():
            raise ValueError("Watch ID must not be empty")
        if not updated_at:
            raise ValueError("Watch update time must not be empty")
        cursor = self.connection.execute(
            "UPDATE watches SET active = 0, updated_at = ? WHERE watch_id = ?",
            (updated_at, watch_id),
        )
        if cursor.rowcount != 1:
            raise LookupError(f"Watch {watch_id} was not found")

    @staticmethod
    def _watch_row(row: sqlite3.Row) -> JSONObject:
        active_value = row["active"]
        if isinstance(active_value, bool) or not isinstance(active_value, int):
            raise ValueError("Stored watch active flag was invalid")
        bodies = as_json_value(json.loads(row["bodies_json"]))
        if not isinstance(bodies, list):
            raise ValueError("Stored watch bodies were not a list")
        return {
            "watch_id": row["watch_id"],
            "city": row["city"],
            "bodies": bodies,
            "address": row["address"],
            "neighbourhood": row["neighbourhood"],
            "email": row["email"],
            "active": bool(active_value),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def notification_sent(self, watch_id: str, finding_id: str) -> bool:
        row = self.connection.execute(
            "SELECT status FROM notifications WHERE watch_id = ? AND finding_id = ?",
            (watch_id, finding_id),
        ).fetchone()
        if row is None:
            return False
        status = row[0]
        if not isinstance(status, str):
            raise ValueError("Stored notification status was not text")
        return status == "sent"

    def save_notification(self, observation: NotificationObservation) -> None:
        if not observation.notification_id.strip() or not observation.watch_id.strip():
            raise ValueError("Notification IDs must not be empty")
        if not observation.city.strip() or not observation.finding_id.strip():
            raise ValueError("Notification city and finding ID must not be empty")
        if observation.status not in {"sent", "failed", "skipped"}:
            raise ValueError(f"Unsupported notification status {observation.status}")
        if not observation.area_status.strip() or not observation.area_reason.strip():
            raise ValueError("Notification area details must not be empty")
        if not observation.created_at or not observation.updated_at:
            raise ValueError("Notification timestamps must not be empty")
        self.connection.execute(
            """
            INSERT INTO notifications
            (notification_id, watch_id, city, finding_id, status, area_status,
             area_reason, provider_message_id, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (watch_id, finding_id) DO UPDATE SET
                notification_id = excluded.notification_id,
                status = excluded.status,
                area_status = excluded.area_status,
                area_reason = excluded.area_reason,
                provider_message_id = excluded.provider_message_id,
                error = excluded.error,
                updated_at = excluded.updated_at
            """,
            (
                observation.notification_id,
                observation.watch_id,
                observation.city,
                observation.finding_id,
                observation.status,
                observation.area_status,
                observation.area_reason,
                observation.provider_message_id,
                observation.error,
                observation.created_at,
                observation.updated_at,
            ),
        )

    def notification_rows(self, city: str | None = None, limit: int = 100) -> list[JSONObject]:
        if limit < 1:
            raise ValueError("Notification limit must be positive")
        if city is None:
            rows = self.connection.execute(
                "SELECT * FROM notifications ORDER BY updated_at DESC, notification_id LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            if not city.strip():
                raise ValueError("Notification city filter must not be empty")
            rows = self.connection.execute(
                "SELECT * FROM notifications WHERE city = ? "
                "ORDER BY updated_at DESC, notification_id LIMIT ?",
                (city, limit),
            ).fetchall()
        output: list[JSONObject] = []
        for row in rows:
            output.append(
                {
                    "notification_id": row["notification_id"],
                    "watch_id": row["watch_id"],
                    "city": row["city"],
                    "finding_id": row["finding_id"],
                    "status": row["status"],
                    "area_status": row["area_status"],
                    "area_reason": row["area_reason"],
                    "provider_message_id": row["provider_message_id"],
                    "error": row["error"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )
        return output

    def add_collection_run(
        self,
        run_id: str,
        started_at: str,
        finished_at: str,
        status: str,
        counts: JSONObject,
        structural_fingerprint: str,
        issues: list[JSONValue],
    ) -> None:
        self.connection.execute(
            """
            INSERT OR REPLACE INTO collection_runs
            (run_id, started_at, finished_at, status, counts_json,
             structural_fingerprint, issues_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                started_at,
                finished_at,
                status,
                stable_json(counts),
                structural_fingerprint,
                stable_json(issues),
            ),
        )

    def counts(self) -> JSONObject:
        counts: JSONObject = {}
        for table, label in (
            ("events", "events"),
            ("matters", "matters"),
            ("appearances", "appearances"),
            ("attachments", "attachments"),
            ("attachment_readings", "attachment_readings"),
            ("document_extractions", "document_extractions"),
            ("snapshots", "snapshots"),
            ("parse_failures", "parse_failures"),
            ("investigation_runs", "investigation_runs"),
            ("findings", "findings"),
            ("watches", "watches"),
            ("notifications", "notifications"),
        ):
            row = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            if row is None or not isinstance(row[0], int):
                raise ValueError(f"Could not count {table}")
            counts[label] = row[0]
        return counts

    def repeated_matter_count(self, minimum_appearances: int) -> int:
        if minimum_appearances < 1:
            raise ValueError("minimum_appearances must be positive")
        row = self.connection.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT matter_id
                FROM appearances
                WHERE matter_id IS NOT NULL
                GROUP BY matter_id
                HAVING COUNT(*) >= ?
            )
            """,
            (minimum_appearances,),
        ).fetchone()
        if row is None or not isinstance(row[0], int):
            raise ValueError("Could not count repeated matters")
        return row[0]

    def placement_history(self, matter_id: int) -> tuple[PlacementHistoryItem, ...]:
        rows = self.connection.execute(
            """
            SELECT event_item_id, event_date, title_as_presented, pdf_placement,
                   pdf_evidence_pages_json, provenance_json
            FROM appearances
            WHERE matter_id = ?
            ORDER BY event_date, event_item_id
            """,
            (matter_id,),
        ).fetchall()
        history: list[PlacementHistoryItem] = []
        for row in rows:
            item_id = row[0]
            if not isinstance(item_id, int):
                raise ValueError("Stored appearance had an invalid item ID")
            event_date = row[1] if isinstance(row[1], str) else None
            title = row[2] if isinstance(row[2], str) else None
            placement = row[3] if isinstance(row[3], str) else None
            pages = self._page_numbers(row[4])
            provenance = parse_provenance(row[5], "appearances.provenance")
            history.append(
                PlacementHistoryItem(
                    event_item_id=item_id,
                    event_date=event_date,
                    title_as_presented=title,
                    placement=placement,
                    evidence_pages=pages,
                    source=self._placement_source(provenance),
                )
            )
        return tuple(history)

    def matter_appearance_titles(self, event_id: int) -> tuple[EventAppearanceTitle, ...]:
        rows = self.connection.execute(
            """
            SELECT event_item_id, title_as_presented
            FROM appearances
            WHERE event_id = ? AND matter_id IS NOT NULL AND title_as_presented IS NOT NULL
            ORDER BY event_item_id
            """,
            (event_id,),
        ).fetchall()
        output: list[EventAppearanceTitle] = []
        for row in rows:
            item_id = row[0]
            title = row[1]
            if not isinstance(item_id, int) or not isinstance(title, str) or not title:
                raise ValueError("Stored matter appearance title was invalid")
            output.append(EventAppearanceTitle(item_id, title))
        return tuple(output)

    def event_agendas(self) -> tuple[EventAgenda, ...]:
        rows = self.connection.execute(
            "SELECT event_id, agenda_file FROM events "
            "WHERE agenda_file IS NOT NULL ORDER BY event_id"
        ).fetchall()
        output: list[EventAgenda] = []
        for row in rows:
            event_id = row[0]
            agenda_file = row[1]
            if not isinstance(event_id, int) or not isinstance(agenda_file, str) or not agenda_file:
                raise ValueError("Stored event agenda was invalid")
            output.append(EventAgenda(event_id, agenda_file))
        return tuple(output)

    @staticmethod
    def _page_numbers(value: object) -> tuple[int, ...]:
        if value is None:
            return ()
        if not isinstance(value, str):
            raise ValueError("Stored PDF evidence pages were not text")
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError as error:
            raise ValueError("Stored PDF evidence pages were not valid JSON") from error
        if not isinstance(decoded, list):
            raise ValueError("Stored PDF evidence pages were not a list")
        pages: list[int] = []
        for page in decoded:
            if isinstance(page, bool) or not isinstance(page, int) or page < 1:
                raise ValueError("Stored PDF evidence pages contained an invalid page number")
            pages.append(page)
        return tuple(pages)

    @staticmethod
    def _source_from_json(value: object, context: str) -> SourceReference:
        raw_source = value
        if not isinstance(raw_source, dict):
            raise ValueError(f"Stored {context} source was not an object")
        kind = raw_source.get("kind")
        url = raw_source.get("url")
        captured_at = raw_source.get("captured_at")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"Stored {context} source was incomplete")
        if not isinstance(url, str) or not url:
            raise ValueError(f"Stored {context} source was incomplete")
        if not isinstance(captured_at, str) or not captured_at:
            raise ValueError(f"Stored {context} source was incomplete")
        return SourceReference(kind=kind, url=url, captured_at=captured_at)

    @staticmethod
    def _placement_source(provenance: JSONObject) -> SourceReference | None:
        raw_source = provenance.get("pdf_placement")
        if raw_source is None:
            return None
        return RecordStore._source_from_json(raw_source, "PDF placement")

    def date_bounds(self) -> tuple[str | None, str | None]:
        row = self.connection.execute(
            "SELECT MIN(event_date), MAX(event_date) FROM events WHERE event_date IS NOT NULL"
        ).fetchone()
        if row is None:
            raise ValueError("Could not read event date bounds")
        oldest = row[0] if isinstance(row[0], str) else None
        newest = row[1] if isinstance(row[1], str) else None
        return oldest, newest

    def structural_fingerprint(self) -> str:
        payload: JSONObject = {
            "events": self._structural_rows(
                "events",
                (
                    "event_id",
                    "event_date",
                    "body_id",
                    "body_name",
                    "agenda_file",
                    "agenda_last_published_utc",
                    "agenda_status_name",
                    "in_site_url",
                    "comment",
                ),
                "event_id",
            ),
            "matters": self._structural_rows(
                "matters",
                (
                    "matter_id",
                    "file_number",
                    "matter_name",
                    "current_title",
                    "type_name",
                    "status_name",
                    "body_id",
                    "body_name",
                    "intro_date",
                    "agenda_date",
                    "version",
                    "last_modified_utc",
                ),
                "matter_id",
            ),
            "appearances": self._structural_rows(
                "appearances",
                (
                    "event_item_id",
                    "matter_id",
                    "event_id",
                    "event_date",
                    "body_id",
                    "body_name",
                    "title_as_presented",
                    "consent_value",
                    "pdf_placement",
                    "pdf_evidence_pages_json",
                    "agenda_sequence",
                    "agenda_number",
                    "action_taken",
                    "action_text",
                    "passed_flag_name",
                    "matter_version_at_event",
                    "agenda_note",
                    "minutes_note",
                    "item_last_modified_utc",
                ),
                "event_item_id",
            ),
            "attachments": self._structural_rows(
                "attachments",
                (
                    "attachment_id",
                    "matter_id",
                    "name",
                    "url",
                    "version",
                    "last_modified_utc",
                    "content_hash",
                    "supporting_document",
                ),
                "attachment_id",
            ),
            "attachment_readings": self._structural_rows(
                "attachment_readings",
                (
                    "attachment_id",
                    "content_hash",
                    "status",
                    "page_count",
                    "references_json",
                    "reason",
                ),
                "attachment_id",
            ),
            "appearance_attachments": self._structural_rows(
                "appearance_attachments",
                (
                    "event_item_id",
                    "attachment_id",
                    "matter_id",
                    "name",
                    "url",
                    "version",
                    "last_modified_utc",
                    "supporting_document",
                ),
                "event_item_id, attachment_id",
            ),
        }
        return sha256(stable_json(payload).encode("utf-8")).hexdigest()

    def _structural_rows(
        self,
        table: str,
        columns: tuple[str, ...],
        order_by: str,
    ) -> list[JSONValue]:
        rows = self.connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} ORDER BY {order_by}"
        ).fetchall()
        output: list[JSONValue] = []
        for row in rows:
            output.append({column: row[column] for column in columns})
        return output

    def parse_failure_rows(self) -> list[JSONObject]:
        rows = self.connection.execute(
            """
            SELECT target, source_url, captured_at, response_sha256, error
            FROM parse_failures ORDER BY captured_at, failure_key
            """
        ).fetchall()
        output: list[JSONObject] = []
        for row in rows:
            output.append(
                {
                    "target": row[0],
                    "source_url": row[1],
                    "captured_at": row[2],
                    "response_sha256": row[3],
                    "error": row[4],
                }
            )
        return output

    def commit_and_counts(self) -> JSONObject:
        self.connection.commit()
        return self.counts()
