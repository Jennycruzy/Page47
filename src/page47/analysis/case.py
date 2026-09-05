"""Load one matter and its primary evidence without losing source details."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from page47.models.config import ModelSettings
from page47.records.store import RecordStore, SourceReference
from page47.snapshotter.store import SnapshotStore

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class PageAnchor:
    kind: str
    value: str
    page_number: int
    start_character: int
    end_character: int
    excerpt: str
    source: SourceReference

    def as_json(self) -> JSONObject:
        return {
            "kind": self.kind,
            "value": self.value,
            "page_number": self.page_number,
            "start_character": self.start_character,
            "end_character": self.end_character,
            "excerpt": self.excerpt,
            "source": self.source.as_json(),
        }


@dataclass(frozen=True, slots=True)
class AttachmentRecord:
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
    reading_status: str | None
    page_count: int | None
    anchors: tuple[PageAnchor, ...]
    reading_source: SourceReference | None
    evidence_root: Path

    def document_capture(self) -> tuple[bytes, SourceReference] | None:
        snapshots = SnapshotStore(self.evidence_root)
        capture = snapshots.latest(f"attachment:{self.attachment_id}")
        if capture is None or capture.get("status") != 200:
            return None
        source_url = capture.get("source_url")
        captured_at = capture.get("captured_at")
        if not isinstance(source_url, str) or not source_url:
            raise ValueError(f"Attachment {self.attachment_id} capture had no source URL")
        if not isinstance(captured_at, str) or not captured_at:
            raise ValueError(f"Attachment {self.attachment_id} capture had no capture time")
        return snapshots.body(capture), SourceReference("snapshot", source_url, captured_at)

    def as_index_json(self) -> JSONObject:
        return {
            "attachment_id": self.attachment_id,
            "name": self.name,
            "version": self.version,
            "last_modified_utc": self.last_modified_utc,
            "content_hash": self.content_hash,
            "reading_status": self.reading_status,
            "page_count": self.page_count,
            "anchors": [anchor.as_json() for anchor in self.anchors],
            "source": self.source.as_json(),
        }


@dataclass(frozen=True, slots=True)
class AppearanceRecord:
    event_item_id: int
    matter_id: int | None
    event_id: int
    event_date: str | None
    body_id: int | None
    body_name: str | None
    title_as_presented: str | None
    consent_value: int | None
    pdf_placement: str | None
    pdf_evidence_pages: tuple[int, ...]
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
    pdf_source: SourceReference | None
    attachments: tuple[AttachmentRecord, ...]

    def as_json(self) -> JSONObject:
        return {
            "event_item_id": self.event_item_id,
            "matter_id": self.matter_id,
            "event_id": self.event_id,
            "event_date": self.event_date,
            "body_id": self.body_id,
            "body_name": self.body_name,
            "title_as_presented": self.title_as_presented,
            "consent_value": self.consent_value,
            "pdf_placement": self.pdf_placement,
            "pdf_evidence_pages": list(self.pdf_evidence_pages),
            "pdf_placement_reason": self.pdf_placement_reason,
            "agenda_sequence": self.agenda_sequence,
            "agenda_number": self.agenda_number,
            "action_taken": self.action_taken,
            "action_text": self.action_text,
            "passed_flag_name": self.passed_flag_name,
            "matter_version_at_event": self.matter_version_at_event,
            "agenda_note": self.agenda_note,
            "minutes_note": self.minutes_note,
            "item_last_modified_utc": self.item_last_modified_utc,
            "source": self.source.as_json(),
            "pdf_source": self.pdf_source.as_json() if self.pdf_source is not None else None,
            "attachments": [attachment.as_index_json() for attachment in self.attachments],
        }


@dataclass(frozen=True, slots=True)
class MatterRecord:
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

    def as_json(self) -> JSONObject:
        return {
            "matter_id": self.matter_id,
            "file_number": self.file_number,
            "matter_name": self.matter_name,
            "current_title": self.current_title,
            "type_name": self.type_name,
            "status_name": self.status_name,
            "body_id": self.body_id,
            "body_name": self.body_name,
            "intro_date": self.intro_date,
            "agenda_date": self.agenda_date,
            "version": self.version,
            "last_modified_utc": self.last_modified_utc,
            "source": self.source.as_json(),
        }


@dataclass(frozen=True, slots=True)
class MatterCase:
    city: str
    matter: MatterRecord
    appearances: tuple[AppearanceRecord, ...]

    @property
    def matter_id(self) -> int:
        return self.matter.matter_id

    def unique_attachments(self) -> tuple[AttachmentRecord, ...]:
        seen: set[int] = set()
        output: list[AttachmentRecord] = []
        for appearance in self.appearances:
            for attachment in appearance.attachments:
                if attachment.attachment_id not in seen:
                    seen.add(attachment.attachment_id)
                    output.append(attachment)
        return tuple(output)

    def structural_payload(self) -> JSONObject:
        return {
            "city": self.city,
            "matter": self.matter.as_json(),
            "appearances": [appearance.as_json() for appearance in self.appearances],
            "record_limit": (
                "This record contains only public material returned by the city service."
            ),
        }

    def document_index_payload(self) -> JSONObject:
        return {
            "city": self.city,
            "matter_id": self.matter_id,
            "documents": [attachment.as_index_json() for attachment in self.unique_attachments()],
        }


@dataclass(frozen=True, slots=True)
class InvestigationContext:
    case: MatterCase
    evidence_root: Path
    models: ModelSettings


def _source(row: sqlite3.Row) -> SourceReference:
    source_url = row["source_url"]
    observed_at = row["observed_at"]
    if not isinstance(source_url, str) or not source_url:
        raise ValueError("Stored record source URL was missing")
    if not isinstance(observed_at, str) or not observed_at:
        raise ValueError("Stored record observation time was missing")
    return SourceReference(kind="api", url=source_url, captured_at=observed_at)


def _text(row: sqlite3.Row, key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Stored {key} was not text")
    return value


def _integer(row: sqlite3.Row, key: str) -> int | None:
    value = row[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Stored {key} was not an integer")
    return value


def _required_integer(row: sqlite3.Row, key: str) -> int:
    value = _integer(row, key)
    if value is None:
        raise ValueError(f"Stored {key} was missing")
    return value


def _pages(value: object, context: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, str):
        raise ValueError(f"Stored {context} was not text")
    decoded: object = json.loads(value)
    if not isinstance(decoded, list):
        raise ValueError(f"Stored {context} was not a list")
    output: list[int] = []
    for item in decoded:
        if isinstance(item, bool) or not isinstance(item, int) or item < 1:
            raise ValueError(f"Stored {context} contained an invalid page")
        output.append(item)
    return tuple(output)


def _source_from_json(value: object, context: str) -> SourceReference:
    if not isinstance(value, dict):
        raise ValueError(f"Stored {context} source was not an object")
    kind: object = value.get("kind")
    url: object = value.get("url")
    captured_at: object = value.get("captured_at")
    if (
        not isinstance(kind, str)
        or not kind
        or not isinstance(url, str)
        or not url
        or not isinstance(captured_at, str)
        or not captured_at
    ):
        raise ValueError(f"Stored {context} source was incomplete")
    return SourceReference(kind=kind, url=url, captured_at=captured_at)


def _provenance_source(row: sqlite3.Row, key: str) -> SourceReference | None:
    raw = row["provenance_json"]
    if not isinstance(raw, str):
        raise ValueError("Stored provenance was not text")
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("Stored provenance was not an object")
    value = decoded.get(key)
    if value is None:
        return None
    return _source_from_json(value, key)


def _anchors(row: sqlite3.Row, source: SourceReference) -> tuple[PageAnchor, ...]:
    raw = row["references_json"]
    if not isinstance(raw, str):
        raise ValueError("Stored attachment references were not text")
    decoded: object = json.loads(raw)
    if not isinstance(decoded, dict):
        raise ValueError("Stored attachment references were not an object")
    references = decoded.get("references")
    if not isinstance(references, list):
        raise ValueError("Stored attachment references list was missing")
    anchors: list[PageAnchor] = []
    for index, item in enumerate(references):
        if not isinstance(item, dict):
            raise ValueError(f"Stored attachment reference {index} was not an object")
        kind: object = item.get("kind")
        value: object = item.get("value")
        page: object = item.get("page_number")
        start: object = item.get("start_character")
        end: object = item.get("end_character")
        excerpt: object = item.get("excerpt")
        if not isinstance(kind, str) or not kind:
            raise ValueError(f"Stored attachment reference {index} had no kind")
        if not isinstance(value, str) or not value:
            raise ValueError(f"Stored attachment reference {index} had no value")
        if any(
            isinstance(bound, bool) or not isinstance(bound, int)
            for bound in (page, start, end)
        ):
            raise ValueError(f"Stored attachment reference {index} had invalid character bounds")
        if not isinstance(page, int) or not isinstance(start, int) or not isinstance(end, int):
            raise ValueError(f"Stored attachment reference {index} had invalid character bounds")
        if page < 1 or start < 0 or end < start:
            raise ValueError(f"Stored attachment reference {index} had invalid bounds")
        if not isinstance(excerpt, str) or not excerpt:
            raise ValueError(f"Stored attachment reference {index} had no excerpt")
        anchors.append(PageAnchor(kind, value, page, start, end, excerpt, source))
    return tuple(anchors)


def _attachment(
    row: sqlite3.Row,
    reading: sqlite3.Row | None,
    evidence_root: Path,
) -> AttachmentRecord:
    reading_source = _source(reading) if reading is not None else None
    anchors = _anchors(reading, reading_source) if reading is not None and reading_source else ()
    return AttachmentRecord(
        attachment_id=_required_integer(row, "attachment_id"),
        matter_id=_integer(row, "matter_id"),
        name=_text(row, "name"),
        url=_text(row, "url"),
        version=_text(row, "version"),
        last_modified_utc=_text(row, "last_modified_utc"),
        first_observed_by_us=str(row["first_observed_by_us"]),
        content_hash=_text(row, "content_hash"),
        supporting_document=bool(row["supporting_document"])
        if row["supporting_document"] is not None
        else None,
        source=_source(row),
        reading_status=_text(reading, "status") if reading is not None else None,
        page_count=_integer(reading, "page_count") if reading is not None else None,
        anchors=anchors,
        reading_source=reading_source,
        evidence_root=evidence_root,
    )


def load_matter_case(
    store: RecordStore,
    city: str,
    matter_id: int,
    evidence_root: Path,
) -> MatterCase:
    if matter_id < 1:
        raise ValueError("matter_id must be positive")
    matter_row = store.connection.execute(
        "SELECT * FROM matters WHERE matter_id = ?", (matter_id,)
    ).fetchone()
    if matter_row is None:
        raise LookupError(f"Matter {matter_id} was not found in the record store")
    matter = MatterRecord(
        matter_id=_required_integer(matter_row, "matter_id"),
        file_number=_text(matter_row, "file_number"),
        matter_name=_text(matter_row, "matter_name"),
        current_title=_text(matter_row, "current_title"),
        type_name=_text(matter_row, "type_name"),
        status_name=_text(matter_row, "status_name"),
        body_id=_integer(matter_row, "body_id"),
        body_name=_text(matter_row, "body_name"),
        intro_date=_text(matter_row, "intro_date"),
        agenda_date=_text(matter_row, "agenda_date"),
        version=_text(matter_row, "version"),
        last_modified_utc=_text(matter_row, "last_modified_utc"),
        source=_source(matter_row),
    )
    appearance_rows = store.connection.execute(
        "SELECT * FROM appearances WHERE matter_id = ? ORDER BY event_date, event_item_id",
        (matter_id,),
    ).fetchall()
    appearances: list[AppearanceRecord] = []
    for appearance_row in appearance_rows:
        item_id = _required_integer(appearance_row, "event_item_id")
        attachment_rows = store.connection.execute(
            """
            SELECT aa.*, a.content_hash, a.first_observed_by_us
            FROM appearance_attachments aa
            JOIN attachments a ON a.attachment_id = aa.attachment_id
            WHERE aa.event_item_id = ?
            ORDER BY aa.attachment_id
            """,
            (item_id,),
        ).fetchall()
        attachments: list[AttachmentRecord] = []
        for attachment_row in attachment_rows:
            attachment_id = _required_integer(attachment_row, "attachment_id")
            reading_row = store.connection.execute(
                "SELECT * FROM attachment_readings WHERE attachment_id = ?",
                (attachment_id,),
            ).fetchone()
            attachments.append(_attachment(attachment_row, reading_row, evidence_root))
        appearances.append(
            AppearanceRecord(
                event_item_id=item_id,
                matter_id=_integer(appearance_row, "matter_id"),
                event_id=_required_integer(appearance_row, "event_id"),
                event_date=_text(appearance_row, "event_date"),
                body_id=_integer(appearance_row, "body_id"),
                body_name=_text(appearance_row, "body_name"),
                title_as_presented=_text(appearance_row, "title_as_presented"),
                consent_value=_integer(appearance_row, "consent_value"),
                pdf_placement=_text(appearance_row, "pdf_placement"),
                pdf_evidence_pages=_pages(
                    appearance_row["pdf_evidence_pages_json"],
                    "PDF evidence pages",
                ),
                pdf_placement_reason=_text(appearance_row, "pdf_placement_reason"),
                agenda_sequence=_integer(appearance_row, "agenda_sequence"),
                agenda_number=_text(appearance_row, "agenda_number"),
                action_taken=_text(appearance_row, "action_taken"),
                action_text=_text(appearance_row, "action_text"),
                passed_flag_name=_text(appearance_row, "passed_flag_name"),
                matter_version_at_event=_text(appearance_row, "matter_version_at_event"),
                agenda_note=_text(appearance_row, "agenda_note"),
                minutes_note=_text(appearance_row, "minutes_note"),
                item_last_modified_utc=_text(appearance_row, "item_last_modified_utc"),
                source=_source(appearance_row),
                pdf_source=_provenance_source(appearance_row, "pdf_placement"),
                attachments=tuple(attachments),
            )
        )
    return MatterCase(city=city, matter=matter, appearances=tuple(appearances))
