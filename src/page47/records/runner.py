"""Backfill Seattle's public record into the normalized record store."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from page47.records.pdf_consent import AgendaPage, classify_item, extract_pages
from page47.records.store import (
    AppearanceObservation,
    AttachmentObservation,
    EventObservation,
    MatterObservation,
    RecordStore,
    SnapshotObservation,
    SourceReference,
)
from page47.snapshotter.client import LegistarClient, as_object, as_objects, parse_json
from page47.snapshotter.config import (
    CityConfig,
    JSONObject,
    JSONValue,
    field_name,
    load_city_config,
)
from page47.snapshotter.http import FetchResult, utc_now
from page47.snapshotter.store import SnapshotStore, text_value

HTTP_OK = 200


@dataclass(frozen=True, slots=True)
class EventCandidate:
    event: JSONObject
    source: SourceReference


@dataclass(slots=True)
class RunState:
    issues: list[JSONValue]
    details_attempted: int = 0
    details_parsed: int = 0
    event_pages: int = 0
    matter_pages: int = 0
    event_page_end_found: bool = False
    matter_page_end_found: bool = False
    event_page_failed: bool = False
    matter_page_failed: bool = False


def required_integer(record: JSONObject, fields: JSONObject, key: str, context: str) -> int:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}.{source_key} must be an integer")
    return value


def optional_integer(record: JSONObject, fields: JSONObject, key: str, context: str) -> int | None:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context}.{source_key} must be an integer or null")
    return value


def optional_text(record: JSONObject, fields: JSONObject, key: str, context: str) -> str | None:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context}.{source_key} must be text or null")
    return value


def optional_boolean(
    record: JSONObject, fields: JSONObject, key: str, context: str
) -> bool | None:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{context}.{source_key} must be boolean or null")
    return value


def required_objects(
    record: JSONObject, fields: JSONObject, key: str, context: str
) -> list[JSONObject]:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if value is None:
        raise ValueError(f"{context}.{source_key} was absent")
    return as_objects(value, f"{context}.{source_key}")


def source_for_capture(capture: JSONObject, kind: str = "api") -> SourceReference:
    target = text_value(capture, "target")
    source_url = text_value(capture, "source_url")
    captured_at = text_value(capture, "captured_at")
    if target is None or source_url is None or captured_at is None:
        raise ValueError("A stored capture lacked its target, URL, or capture time")
    return SourceReference(kind=kind, url=source_url, captured_at=captured_at)


def response_hash(capture: JSONObject) -> str | None:
    return text_value(capture, "response_sha256")


def agenda_snapshot(
    snapshot_store: SnapshotStore,
    event_id: int,
    agenda_url: str | None,
) -> JSONObject | None:
    """Return the newest capture for an agenda target or matching source URL."""

    capture = snapshot_store.latest(f"agenda:{event_id}")
    if capture is not None or agenda_url is None:
        return capture
    matching_records = [
        record
        for record in snapshot_store.records
        if record.get("kind") == "agenda_pdf" and record.get("source_url") == agenda_url
    ]
    if not matching_records:
        return None
    return matching_records[-1]


def capture_observation(capture: JSONObject) -> SnapshotObservation:
    capture_key = text_value(capture, "capture_key")
    target = text_value(capture, "target")
    kind = text_value(capture, "kind")
    source_url = text_value(capture, "source_url")
    captured_at = text_value(capture, "captured_at")
    response_sha256 = text_value(capture, "response_sha256")
    storage_key = text_value(capture, "storage_key")
    source_kind = "api"
    if capture_key is None or target is None or kind is None or source_url is None:
        raise ValueError("A stored capture lacked its identifying fields")
    if captured_at is None or response_sha256 is None or storage_key is None:
        raise ValueError("A stored capture lacked its content fields")
    status_value = capture.get("status")
    if status_value is not None and (
        isinstance(status_value, bool) or not isinstance(status_value, int)
    ):
        raise ValueError("A stored capture had an invalid HTTP status")
    content_sha256 = text_value(capture, "content_sha256")
    return SnapshotObservation(
        capture_key=capture_key,
        target=target,
        kind=kind,
        source_url=source_url,
        captured_at=captured_at,
        status=status_value,
        response_sha256=response_sha256,
        content_sha256=content_sha256,
        storage_key=storage_key,
        source_kind=source_kind,
    )


def add_issue(state: RunState, kind: str, details: JSONObject) -> None:
    state.issues.append({"kind": kind, "details": details})


def parse_captured_json(
    snapshot_store: SnapshotStore,
    record_store: RecordStore,
    response: FetchResult,
    kind: str,
    fields: JSONObject,
) -> tuple[JSONValue | None, JSONObject | None]:
    previous = snapshot_store.latest(response.target)
    if response.not_modified:
        if previous is None:
            reason = "received 304 without a prior stored response"
            capture, _ = snapshot_store.capture(
                response,
                kind,
                {"parse_status": "unparsed", "parse_error": reason, **fields},
            )
            record_store.add_snapshot(capture_observation(capture))
            record_store.add_parse_failure(
                response.target,
                response.url,
                response.captured_at,
                response_hash(capture),
                reason,
            )
            return None, capture
        body = snapshot_store.body(previous)
        capture = previous
    elif response.status != HTTP_OK:
        reason = f"HTTP status {response.status} did not provide a usable JSON response"
        capture, _ = snapshot_store.capture(
            response,
            kind,
            {"parse_status": "unparsed", "parse_error": reason, **fields},
        )
        record_store.add_snapshot(capture_observation(capture))
        record_store.add_parse_failure(
            response.target,
            response.url,
            response.captured_at,
            response_hash(capture),
            reason,
        )
        return None, capture
    else:
        body = response.body
        capture = None
    try:
        decoded = parse_json(body)
    except (ValueError, UnicodeDecodeError) as error:
        reason = f"{type(error).__name__}: {error}"
        if capture is None:
            capture, _ = snapshot_store.capture(
                response,
                kind,
                {"parse_status": "unparsed", "parse_error": reason, **fields},
            )
        record_store.add_snapshot(capture_observation(capture))
        record_store.add_parse_failure(
            response.target,
            response.url,
            response.captured_at,
            response_hash(capture),
            reason,
        )
        return None, capture
    if capture is None:
        capture, _ = snapshot_store.capture(
            response,
            kind,
            {"parse_status": "parsed", **fields},
        )
    record_store.add_snapshot(capture_observation(capture))
    return decoded, capture


def source_values(source: SourceReference, values: Mapping[str, object]) -> JSONObject:
    output: JSONObject = {}
    for key, value in values.items():
        if value is not None:
            output[key] = source.as_json()
    return output


def matter_observation(
    matter: JSONObject,
    source: SourceReference,
    config: CityConfig,
) -> MatterObservation:
    matter_id = required_integer(matter, config.matter_fields, "id", "matter")
    file_number = optional_text(matter, config.matter_fields, "file_number", "matter")
    matter_name = optional_text(matter, config.matter_fields, "name", "matter")
    current_title = optional_text(matter, config.matter_fields, "title", "matter")
    type_name = optional_text(matter, config.matter_fields, "type", "matter")
    status_name = optional_text(matter, config.matter_fields, "status", "matter")
    body_id = optional_integer(matter, config.matter_fields, "body_id", "matter")
    body_name = optional_text(matter, config.matter_fields, "body_name", "matter")
    intro_date = optional_text(matter, config.matter_fields, "intro_date", "matter")
    agenda_date = optional_text(matter, config.matter_fields, "agenda_date", "matter")
    version = optional_text(matter, config.matter_fields, "version", "matter")
    last_modified_utc = optional_text(matter, config.matter_fields, "last_modified", "matter")
    values: dict[str, object] = {
        "file_number": file_number,
        "matter_name": matter_name,
        "current_title": current_title,
        "type_name": type_name,
        "status_name": status_name,
        "body_id": body_id,
        "body_name": body_name,
        "intro_date": intro_date,
        "agenda_date": agenda_date,
        "version": version,
        "last_modified_utc": last_modified_utc,
    }
    return MatterObservation(
        matter_id=matter_id,
        file_number=file_number,
        matter_name=matter_name,
        current_title=current_title,
        type_name=type_name,
        status_name=status_name,
        body_id=body_id,
        body_name=body_name,
        intro_date=intro_date,
        agenda_date=agenda_date,
        version=version,
        last_modified_utc=last_modified_utc,
        source=source,
        provenance=source_values(source, values),
    )


def event_observation(
    event: JSONObject,
    source: SourceReference,
    config: CityConfig,
) -> EventObservation:
    event_id = required_integer(event, config.event_fields, "id", "event")
    event_date = optional_text(event, config.event_fields, "date", "event")
    body_id = optional_integer(event, config.event_fields, "body_id", "event")
    body_name = optional_text(event, config.event_fields, "body_name", "event")
    agenda_file = optional_text(event, config.event_fields, "agenda_file", "event")
    agenda_last_published_utc = optional_text(
        event, config.event_fields, "agenda_last_published", "event"
    )
    agenda_status_name = optional_text(event, config.event_fields, "agenda_status", "event")
    in_site_url = optional_text(event, config.event_fields, "in_site_url", "event")
    comment = optional_text(event, config.event_fields, "comment", "event")
    values: dict[str, object] = {
        "event_date": event_date,
        "body_id": body_id,
        "body_name": body_name,
        "agenda_file": agenda_file,
        "agenda_last_published_utc": agenda_last_published_utc,
        "agenda_status_name": agenda_status_name,
        "in_site_url": in_site_url,
        "comment": comment,
    }
    return EventObservation(
        event_id=event_id,
        event_date=event_date,
        body_id=body_id,
        body_name=body_name,
        agenda_file=agenda_file,
        agenda_last_published_utc=agenda_last_published_utc,
        agenda_status_name=agenda_status_name,
        in_site_url=in_site_url,
        comment=comment,
        source=source,
        provenance=source_values(source, values),
    )


def value_from_detail_or_list(
    detail: JSONObject,
    listing: JSONObject,
    fields: JSONObject,
    key: str,
    context: str,
    detail_source: SourceReference,
    listing_source: SourceReference,
) -> tuple[object, SourceReference]:
    source_key = field_name(fields, key)
    detail_value = detail.get(source_key)
    listing_value = listing.get(source_key)
    if detail_value is not None:
        return detail_value, detail_source
    return listing_value, listing_source


def optional_integer_value(value: object, context: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer or null")
    return value


def optional_text_value(value: object, context: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{context} must be text or null")
    return value


def appearance_observation(
    item: JSONObject,
    event_id: int,
    event_date: object,
    body_id: object,
    body_name: object,
    detail_source: SourceReference,
    event_source: SourceReference,
    config: CityConfig,
) -> AppearanceObservation:
    item_id = required_integer(item, config.item_fields, "id", "event item")
    item_event_id = required_integer(item, config.item_fields, "event_id", "event item")
    if item_event_id != event_id:
        raise ValueError(
            f"event item {item_id} referred to event {item_event_id}, expected {event_id}"
        )
    matter_id = optional_integer(item, config.item_fields, "matter_id", "event item")
    event_date_value = optional_text_value(event_date, "event date")
    body_id_value = optional_integer_value(body_id, "event body ID")
    body_name_value = optional_text_value(body_name, "event body name")
    title_as_presented = optional_text(item, config.item_fields, "title", "event item")
    consent_value = optional_integer(item, config.item_fields, "consent", "event item")
    agenda_sequence = optional_integer(item, config.item_fields, "agenda_sequence", "event item")
    agenda_number = optional_text(item, config.item_fields, "agenda_number", "event item")
    action_taken = optional_text(item, config.item_fields, "action_name", "event item")
    action_text = optional_text(item, config.item_fields, "action_text", "event item")
    passed_flag_name = optional_text(item, config.item_fields, "passed_flag_name", "event item")
    matter_version_at_event = optional_text(item, config.item_fields, "version", "event item")
    agenda_note = optional_text(item, config.item_fields, "agenda_note", "event item")
    minutes_note = optional_text(item, config.item_fields, "minutes_note", "event item")
    item_last_modified_utc = optional_text(
        item, config.item_fields, "last_modified", "event item"
    )
    values: dict[str, object] = {
        "matter_id": matter_id,
        "event_id": event_id,
        "event_date": event_date_value,
        "body_id": body_id_value,
        "body_name": body_name_value,
        "title_as_presented": title_as_presented,
        "consent_value": consent_value,
        "agenda_sequence": agenda_sequence,
        "agenda_number": agenda_number,
        "action_taken": action_taken,
        "action_text": action_text,
        "passed_flag_name": passed_flag_name,
        "matter_version_at_event": matter_version_at_event,
        "agenda_note": agenda_note,
        "minutes_note": minutes_note,
        "item_last_modified_utc": item_last_modified_utc,
    }
    provenance: JSONObject = source_values(detail_source, values)
    for key in ("event_date", "body_id", "body_name"):
        if values[key] is not None:
            selected_source = detail_source
            if key == "event_date" and detail_source == event_source:
                selected_source = event_source
            provenance[key] = selected_source.as_json()
    return AppearanceObservation(
        event_item_id=item_id,
        matter_id=matter_id,
        event_id=event_id,
        event_date=event_date_value,
        body_id=body_id_value,
        body_name=body_name_value,
        title_as_presented=title_as_presented,
        consent_value=consent_value,
        pdf_placement=None,
        pdf_evidence_pages_json=None,
        pdf_placement_reason=None,
        agenda_sequence=agenda_sequence,
        agenda_number=agenda_number,
        action_taken=action_taken,
        action_text=action_text,
        passed_flag_name=passed_flag_name,
        matter_version_at_event=matter_version_at_event,
        agenda_note=agenda_note,
        minutes_note=minutes_note,
        item_last_modified_utc=item_last_modified_utc,
        source=detail_source,
        provenance=provenance,
    )


def attachment_observation(
    attachment: JSONObject,
    item_matter_id: int | None,
    source: SourceReference,
    config: CityConfig,
    content_hash: str | None,
    content_source: SourceReference | None,
) -> AttachmentObservation:
    attachment_id = required_integer(attachment, config.attachment_fields, "id", "attachment")
    name = optional_text(attachment, config.attachment_fields, "name", "attachment")
    url = optional_text(attachment, config.attachment_fields, "url", "attachment")
    version = optional_text(
        attachment, config.attachment_fields, "matter_version", "attachment"
    )
    last_modified_utc = optional_text(
        attachment, config.attachment_fields, "last_modified", "attachment"
    )
    supporting_document = optional_boolean(
        attachment, config.attachment_fields, "supporting_document", "attachment"
    )
    values: dict[str, object] = {
        "matter_id": item_matter_id,
        "name": name,
        "url": url,
        "version": version,
        "last_modified_utc": last_modified_utc,
        "supporting_document": supporting_document,
    }
    provenance = source_values(source, values)
    if content_hash is not None and content_source is not None:
        provenance["content_hash"] = content_source.as_json()
    return AttachmentObservation(
        attachment_id=attachment_id,
        matter_id=item_matter_id,
        name=name,
        url=url,
        version=version,
        last_modified_utc=last_modified_utc,
        first_observed_by_us=source.captured_at,
        content_hash=content_hash,
        supporting_document=supporting_document,
        source=source,
        provenance=provenance,
        content_source=content_source,
    )


def content_capture(
    snapshot_store: SnapshotStore,
    attachment_id: int,
) -> tuple[str | None, SourceReference | None]:
    capture = snapshot_store.latest(f"attachment:{attachment_id}")
    if capture is None:
        return None, None
    status = capture.get("status")
    content_hash = text_value(capture, "content_sha256")
    if status != HTTP_OK or content_hash is None:
        return None, None
    return content_hash, source_for_capture(capture)


def agenda_capture(
    snapshot_store: SnapshotStore,
    event_id: int,
    agenda_url: str | None,
) -> tuple[tuple[AgendaPage, ...], SourceReference] | None:
    """Read an agenda only when its captured bytes are available locally."""

    capture = agenda_snapshot(snapshot_store, event_id, agenda_url)
    if capture is None:
        return None
    status = capture.get("status")
    if status != HTTP_OK:
        raise ValueError(f"Captured agenda response had HTTP status {status!r}, not 200")
    if text_value(capture, "content_sha256") is None:
        raise ValueError("Captured agenda response had no content hash")
    try:
        pages = extract_pages(snapshot_store.body(capture))
    except Exception as error:
        raise ValueError(
            f"Could not read captured agenda PDF: {type(error).__name__}: {error}"
        ) from error
    return pages, source_for_capture(capture, "snapshot")


def read_matter_pages(
    client: LegistarClient,
    config: CityConfig,
    snapshot_store: SnapshotStore,
    record_store: RecordStore,
    state: RunState,
    start_page: int = 0,
) -> None:
    if start_page < 0 or start_page >= config.backfill.max_matter_pages:
        raise ValueError("start_page must be within the configured matter page range")
    for page_number in range(start_page, config.backfill.max_matter_pages):
        state.matter_pages += 1
        response = client.fetch_matter_page(page_number, config.backfill.matter_page_size)
        decoded, capture = parse_captured_json(
            snapshot_store,
            record_store,
            response,
            "matter_page",
            {"page_number": page_number},
        )
        if decoded is None or capture is None:
            state.matter_page_failed = True
            add_issue(
                state,
                "matter_page_unavailable",
                {"page_number": page_number, "url": response.url},
            )
            break
        source = source_for_capture(capture)
        try:
            matters = as_objects(decoded, f"matter page {page_number}")
        except ValueError as error:
            state.matter_page_failed = True
            add_issue(
                state,
                "matter_page_unreadable",
                {"page_number": page_number, "error": f"{type(error).__name__}: {error}"},
            )
            record_store.add_parse_failure(
                response.target,
                response.url,
                source.captured_at,
                response_hash(capture),
                f"{type(error).__name__}: {error}",
            )
            break
        if not matters:
            state.matter_page_end_found = True
            break
        for index, matter in enumerate(matters):
            try:
                record_store.upsert_matter(matter_observation(matter, source, config))
            except ValueError as error:
                message = f"{type(error).__name__}: {error}"
                add_issue(
                    state,
                    "matter_record_unreadable",
                    {"page_number": page_number, "record_index": index, "error": message},
                )
                record_store.add_parse_failure(
                    response.target,
                    response.url,
                    source.captured_at,
                    response_hash(capture),
                    message,
                )
        if len(matters) < config.backfill.matter_page_size:
            state.matter_page_end_found = True
            break
    else:
        add_issue(
            state,
            "matter_page_limit_reached",
            {"limit": config.backfill.max_matter_pages},
        )


def read_event_pages(
    client: LegistarClient,
    config: CityConfig,
    snapshot_store: SnapshotStore,
    record_store: RecordStore,
    state: RunState,
) -> list[EventCandidate]:
    watched_ids = {body.body_id for body in config.watched_bodies}
    candidates: list[EventCandidate] = []
    seen_event_ids: set[int] = set()
    for page_number in range(config.backfill.max_event_pages):
        state.event_pages += 1
        response = client.fetch_event_page(page_number, config.backfill.event_page_size)
        decoded, capture = parse_captured_json(
            snapshot_store,
            record_store,
            response,
            "event_page",
            {"page_number": page_number},
        )
        if decoded is None or capture is None:
            state.event_page_failed = True
            add_issue(
                state,
                "event_page_unavailable",
                {"page_number": page_number, "url": response.url},
            )
            break
        source = source_for_capture(capture)
        try:
            events = as_objects(decoded, f"event page {page_number}")
        except ValueError as error:
            state.event_page_failed = True
            message = f"{type(error).__name__}: {error}"
            add_issue(
                state,
                "event_page_unreadable",
                {"page_number": page_number, "error": message},
            )
            record_store.add_parse_failure(
                response.target,
                response.url,
                source.captured_at,
                response_hash(capture),
                message,
            )
            break
        if not events:
            state.event_page_end_found = True
            break
        for index, event in enumerate(events):
            try:
                event_id = required_integer(event, config.event_fields, "id", "event")
                body_id = required_integer(event, config.event_fields, "body_id", "event")
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                if body_id not in watched_ids:
                    continue
                record_store.upsert_event(event_observation(event, source, config))
                candidates.append(EventCandidate(event=event, source=source))
            except ValueError as error:
                message = f"{type(error).__name__}: {error}"
                add_issue(
                    state,
                    "event_record_unreadable",
                    {"page_number": page_number, "record_index": index, "error": message},
                )
                record_store.add_parse_failure(
                    response.target,
                    response.url,
                    source.captured_at,
                    response_hash(capture),
                    message,
                )
        if len(events) < config.backfill.event_page_size:
            state.event_page_end_found = True
            break
    else:
        add_issue(
            state,
            "event_page_limit_reached",
            {"limit": config.backfill.max_event_pages},
        )
    return candidates


def read_event_detail(
    candidate: EventCandidate,
    client: LegistarClient,
    config: CityConfig,
    snapshot_store: SnapshotStore,
    record_store: RecordStore,
    state: RunState,
) -> None:
    event_id = required_integer(candidate.event, config.event_fields, "id", "event")
    state.details_attempted += 1
    response = client.fetch_event_detail(event_id)
    decoded, capture = parse_captured_json(
        snapshot_store,
        record_store,
        response,
        "event_detail",
        {"event_id": event_id},
    )
    if decoded is None or capture is None:
        add_issue(
            state,
            "event_detail_unavailable",
            {"event_id": event_id, "url": response.url},
        )
        return
    try:
        detail = as_object(decoded, f"event detail {event_id}")
        detail_id = required_integer(detail, config.event_fields, "id", "event detail")
        if detail_id != event_id:
            raise ValueError(f"event detail returned ID {detail_id}, expected {event_id}")
        detail_source = source_for_capture(capture)
        event_source = candidate.source
        record_store.upsert_event(event_observation(detail, detail_source, config))
        event_date, event_date_source = value_from_detail_or_list(
            detail,
            candidate.event,
            config.event_fields,
            "date",
            "event date",
            detail_source,
            event_source,
        )
        body_id, body_id_source = value_from_detail_or_list(
            detail,
            candidate.event,
            config.event_fields,
            "body_id",
            "event body ID",
            detail_source,
            event_source,
        )
        body_name, body_name_source = value_from_detail_or_list(
            detail,
            candidate.event,
            config.event_fields,
            "body_name",
            "event body name",
            detail_source,
            event_source,
        )
        items = required_objects(detail, config.event_fields, "items", f"event detail {event_id}")
        agenda_file = optional_text(detail, config.event_fields, "agenda_file", "event detail")
        agenda: tuple[tuple[AgendaPage, ...], SourceReference] | None = None
        agenda_source: SourceReference | None = None
        agenda_issue: str | None = None
        agenda_record = agenda_snapshot(snapshot_store, event_id, agenda_file)
        if agenda_record is not None:
            try:
                agenda = agenda_capture(snapshot_store, event_id, agenda_file)
            except ValueError as error:
                agenda_issue = f"{type(error).__name__}: {error}"
                agenda_source = source_for_capture(agenda_record, "snapshot")
                agenda_target = text_value(agenda_record, "target")
                if agenda_target is None:
                    raise ValueError("A stored agenda capture lacked its target")
                record_store.add_parse_failure(
                    agenda_target,
                    agenda_source.url,
                    agenda_source.captured_at,
                    response_hash(agenda_record),
                    agenda_issue,
                )
                add_issue(
                    state,
                    "agenda_unreadable",
                    {"event_id": event_id, "error": agenda_issue},
                )
        for index, item in enumerate(items):
            try:
                appearance = appearance_observation(
                    item,
                    event_id,
                    event_date,
                    body_id,
                    body_name,
                    detail_source,
                    event_source,
                    config,
                )
                appearance_provenance = dict(appearance.provenance)
                appearance_provenance["event_date"] = event_date_source.as_json()
                appearance_provenance["body_id"] = body_id_source.as_json()
                appearance_provenance["body_name"] = body_name_source.as_json()
                appearance = AppearanceObservation(
                    event_item_id=appearance.event_item_id,
                    matter_id=appearance.matter_id,
                    event_id=appearance.event_id,
                    event_date=appearance.event_date,
                    body_id=appearance.body_id,
                    body_name=appearance.body_name,
                    title_as_presented=appearance.title_as_presented,
                    consent_value=appearance.consent_value,
                    pdf_placement=appearance.pdf_placement,
                    pdf_evidence_pages_json=appearance.pdf_evidence_pages_json,
                    pdf_placement_reason=appearance.pdf_placement_reason,
                    agenda_sequence=appearance.agenda_sequence,
                    agenda_number=appearance.agenda_number,
                    action_taken=appearance.action_taken,
                    action_text=appearance.action_text,
                    passed_flag_name=appearance.passed_flag_name,
                    matter_version_at_event=appearance.matter_version_at_event,
                    agenda_note=appearance.agenda_note,
                    minutes_note=appearance.minutes_note,
                    item_last_modified_utc=appearance.item_last_modified_utc,
                    source=appearance.source,
                    provenance=appearance_provenance,
                )
                record_store.upsert_appearance(appearance)
                if (
                    agenda is not None
                    and appearance.matter_id is not None
                    and appearance.title_as_presented is not None
                ):
                    agenda_pages, agenda_source = agenda
                    placement = classify_item(agenda_pages, appearance.title_as_presented)
                    record_store.set_pdf_placement(
                        appearance.event_item_id,
                        placement.placement,
                        placement.evidence_pages,
                        placement.reason,
                        agenda_source,
                    )
                elif (
                    agenda_source is not None
                    and agenda_issue is not None
                    and appearance.matter_id is not None
                ):
                    record_store.set_pdf_placement(
                        appearance.event_item_id,
                        "cannot_determine",
                        (),
                        agenda_issue,
                        agenda_source,
                    )
                raw_attachments = item.get(field_name(config.item_fields, "attachments"))
                if raw_attachments is None:
                    raise ValueError("event item attachments were absent")
                attachments = as_objects(raw_attachments, f"event item {appearance.event_item_id}")
                for attachment in attachments:
                    attachment_id = required_integer(
                        attachment, config.attachment_fields, "id", "attachment"
                    )
                    content_hash, content_source = content_capture(snapshot_store, attachment_id)
                    observed_attachment = attachment_observation(
                        attachment,
                        appearance.matter_id,
                        detail_source,
                        config,
                        content_hash,
                        content_source,
                    )
                    if observed_attachment.attachment_id != attachment_id:
                        raise ValueError("attachment ID changed while parsing")
                    record_store.upsert_attachment(observed_attachment)
                    record_store.upsert_appearance_attachment(
                        appearance.event_item_id, observed_attachment
                    )
            except ValueError as error:
                message = f"{type(error).__name__}: {error}"
                add_issue(
                    state,
                    "event_item_unreadable",
                    {"event_id": event_id, "item_index": index, "error": message},
                )
                record_store.add_parse_failure(
                    response.target,
                    response.url,
                    detail_source.captured_at,
                    response_hash(capture),
                    message,
                )
        state.details_parsed += 1
    except ValueError as error:
        message = f"{type(error).__name__}: {error}"
        add_issue(state, "event_detail_unreadable", {"event_id": event_id, "error": message})
        record_store.add_parse_failure(
            response.target,
            response.url,
            source_for_capture(capture).captured_at,
            response_hash(capture),
            message,
        )


def run_backfill(
    config_path: Path,
    database_path: Path,
    evidence_root: Path,
    matter_start_page: int = 0,
    matters_only: bool = False,
) -> JSONObject:
    config = load_city_config(config_path)
    started_at = utc_now()
    snapshot_store = SnapshotStore(evidence_root)
    state = RunState(issues=[])
    with RecordStore(database_path) as record_store:
        client = LegistarClient(config, snapshot_store)
        read_matter_pages(
            client, config, snapshot_store, record_store, state, start_page=matter_start_page
        )
        if matters_only:
            candidates: list[EventCandidate] = []
        else:
            candidates = read_event_pages(client, config, snapshot_store, record_store, state)
        if len(candidates) > config.backfill.max_detail_events:
            add_issue(
                state,
                "event_detail_limit_reached",
                {
                    "available": len(candidates),
                    "limit": config.backfill.max_detail_events,
                },
            )
        for candidate in candidates[: config.backfill.max_detail_events]:
            read_event_detail(candidate, client, config, snapshot_store, record_store, state)
        counts = record_store.commit_and_counts()
        repeated = record_store.repeated_matter_count(
            config.backfill.minimum_appearances_per_repeated_matter
        )
        if repeated < config.backfill.minimum_repeated_matters:
            add_issue(
                state,
                "not_enough_repeated_matters",
                {
                    "found": repeated,
                    "required": config.backfill.minimum_repeated_matters,
                    "appearances_required_per_matter": (
                        config.backfill.minimum_appearances_per_repeated_matter
                    ),
                },
            )
        oldest_date, newest_date = record_store.date_bounds()
        structural_fingerprint = record_store.structural_fingerprint()
        status = "complete" if not state.issues else "incomplete"
        finished_at = utc_now()
        record_store.add_collection_run(
            run_id=finished_at,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            counts=counts,
            structural_fingerprint=structural_fingerprint,
            issues=state.issues,
        )
        record_store.commit()
        summary: JSONObject = {
            "status": status,
            "city": config.city,
            "client": config.client,
            "event_pages_read": state.event_pages,
            "matter_pages_read": state.matter_pages,
            "event_details_attempted": state.details_attempted,
            "event_details_parsed": state.details_parsed,
            "events_reused": matters_only,
            "event_page_end_found": state.event_page_end_found,
            "matter_page_end_found": state.matter_page_end_found,
            "record_counts": counts,
            "repeated_matters_with_at_least_configured_appearances": repeated,
            "oldest_event_date": oldest_date,
            "newest_event_date": newest_date,
            "structural_fingerprint": structural_fingerprint,
            "issues": state.issues,
            "database": str(database_path),
            "evidence_root": str(evidence_root),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill a configured public record source")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--matter-start-page", type=int, default=0)
    parser.add_argument(
        "--matters-only",
        action="store_true",
        help="Retry the matter listing while reusing already stored meeting records",
    )
    args = parser.parse_args()
    summary = run_backfill(
        args.config,
        args.database,
        args.evidence_root,
        matter_start_page=args.matter_start_page,
        matters_only=args.matters_only,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
