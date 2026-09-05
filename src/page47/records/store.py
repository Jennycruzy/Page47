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

CREATE INDEX IF NOT EXISTS appearances_by_matter
    ON appearances (matter_id);
CREATE INDEX IF NOT EXISTS appearances_by_event
    ON appearances (event_id);
CREATE INDEX IF NOT EXISTS attachments_by_matter
    ON attachments (matter_id);
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
            ("snapshots", "snapshots"),
            ("parse_failures", "parse_failures"),
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
    def _placement_source(provenance: JSONObject) -> SourceReference | None:
        raw_source = provenance.get("pdf_placement")
        if raw_source is None:
            return None
        if not isinstance(raw_source, dict):
            raise ValueError("Stored PDF placement source was not an object")
        kind = raw_source.get("kind")
        url = raw_source.get("url")
        captured_at = raw_source.get("captured_at")
        if not isinstance(kind, str) or not kind:
            raise ValueError("Stored PDF placement source was incomplete")
        if not isinstance(url, str) or not url:
            raise ValueError("Stored PDF placement source was incomplete")
        if not isinstance(captured_at, str) or not captured_at:
            raise ValueError("Stored PDF placement source was incomplete")
        return SourceReference(kind=kind, url=url, captured_at=captured_at)

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
