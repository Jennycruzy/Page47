"""Run one immutable capture of upcoming meetings and their documents."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from page47.snapshotter.client import LegistarClient, as_object, as_objects, parse_json
from page47.snapshotter.config import (
    CityConfig,
    JSONObject,
    JSONValue,
    body_ids,
    field_name,
    integer_field,
    load_city_config,
    object_field,
    text_field,
)
from page47.snapshotter.http import ConditionalHttpClient, FetchResult, utc_now
from page47.snapshotter.store import SnapshotStore, text_value

HTTP_OK = 200
HTTP_NOT_MODIFIED = 304


def json_list(values: Iterable[JSONValue]) -> list[JSONValue]:
    return list(values)


def parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def parse_date(value: str | None) -> date | None:
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return parsed.date()


def error_text(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"


def response_body(
    response: FetchResult,
    store: SnapshotStore,
    previous: JSONObject | None,
) -> bytes | None:
    if response.not_modified:
        if previous is None:
            return None
        return store.body(previous)
    if response.status != HTTP_OK:
        return None
    return response.body


def capture_unparsed(
    store: SnapshotStore,
    response: FetchResult,
    kind: str,
    reason: str,
) -> JSONObject:
    record, _ = store.capture(
        response,
        kind,
        {"parse_status": "unparsed", "parse_error": reason},
    )
    return record


def parse_response(
    store: SnapshotStore,
    response: FetchResult,
    previous: JSONObject | None,
    kind: str,
) -> tuple[JSONValue | None, JSONObject | None, str | None]:
    body = response_body(response, store, previous)
    if body is None:
        if response.not_modified:
            reason = "received 304 without a prior stored response"
        elif response.status is None:
            reason = "request did not return an HTTP status"
        else:
            reason = f"HTTP status {response.status} did not provide a usable JSON response"
        record = capture_unparsed(store, response, kind, reason)
        return None, record, reason
    try:
        decoded = parse_json(body)
    except (ValueError, UnicodeDecodeError) as error:
        reason = error_text(error)
        record = capture_unparsed(store, response, kind, reason)
        return None, record, reason
    if response.not_modified:
        return decoded, previous, None
    return decoded, None, None


def binary_capture(
    store: SnapshotStore,
    response: FetchResult,
    kind: str,
    fields: JSONObject,
) -> tuple[JSONObject, bool]:
    return store.capture(response, kind, fields)


def source_url_is_usable(value: str | None) -> bool:
    if value is None:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def event_is_in_window(event: JSONObject, config: CityConfig, now: datetime) -> bool:
    event_date = parse_date(text_field(event, config.event_fields, "date"))
    if event_date is None:
        return False
    last_day = (now + timedelta(days=config.lookahead_days)).date()
    return now.date() <= event_date <= last_day


def event_is_cancelled(event: JSONObject, config: CityConfig) -> bool:
    status = text_field(event, config.event_fields, "agenda_status")
    return status is not None and status.casefold() == "cancelled"


def attachment_views(
    items: Iterable[JSONObject], config: CityConfig
) -> tuple[dict[int, JSONObject], list[str]]:
    attachments: dict[int, JSONObject] = {}
    issues: list[str] = []
    attachment_field = field_name(config.item_fields, "attachments")
    for item in items:
        raw_attachments = item.get(attachment_field)
        if raw_attachments is None:
            continue
        parsed = as_objects(raw_attachments, "event item attachments")
        matter_id = integer_field(item, config.item_fields, "matter_id")
        for attachment in parsed:
            attachment_id = integer_field(attachment, config.attachment_fields, "id")
            attachment_url = text_field(attachment, config.attachment_fields, "url")
            if attachment_id is None:
                if attachment_url is None:
                    issues.append("An attachment had neither an ID nor a URL")
                    continue
                issues.append(f"Attachment at {attachment_url} had no attachment ID")
                continue
            view: JSONObject = {
                "attachment_id": attachment_id,
                "matter_id": matter_id,
                "name": text_field(attachment, config.attachment_fields, "name"),
                "url": attachment_url,
                "last_modified": text_field(
                    attachment, config.attachment_fields, "last_modified"
                ),
                "matter_version": text_field(
                    attachment, config.attachment_fields, "matter_version"
                ),
            }
            previous = attachments.get(attachment_id)
            if previous is not None and previous != view:
                raise ValueError(f"Attachment {attachment_id} had conflicting metadata")
            attachments[attachment_id] = view
    return attachments, issues


def detail_fields(
    detail: JSONObject,
    event_id: int,
    event: JSONObject,
    attachments: Mapping[int, JSONObject],
    config: CityConfig,
) -> JSONObject:
    event_date = text_field(detail, config.event_fields, "date")
    if event_date is None:
        event_date = text_field(event, config.event_fields, "date")
    return {
        "parse_status": "parsed",
        "event_id": event_id,
        "event_date": event_date,
        "body_id": integer_field(detail, config.event_fields, "body_id"),
        "body_name": text_field(detail, config.event_fields, "body_name"),
        "agenda_last_published": text_field(
            detail, config.event_fields, "agenda_last_published"
        ),
        "agenda_status": text_field(detail, config.event_fields, "agenda_status"),
        "attachment_ids": json_list(sorted(attachments)),
    }


def optional_value(record: JSONObject, key: str) -> JSONValue | None:
    return record.get(key)


def append_change(
    store: SnapshotStore,
    run_id: str,
    kind: str,
    target: str,
    details: JSONObject,
) -> None:
    change: JSONObject = {
        "observed_at": run_id,
        "kind": kind,
        "target": target,
        "details": details,
    }
    store.append_change(change)


def compare_event(
    store: SnapshotStore,
    run_id: str,
    event_id: int,
    previous: JSONObject | None,
    current: JSONObject,
) -> int:
    if previous is None:
        return 0
    changes = 0
    old_published = text_value(previous, "agenda_last_published")
    new_published = text_value(current, "agenda_last_published")
    if old_published is not None and new_published is not None and old_published != new_published:
        append_change(
            store,
            run_id,
            "agenda_publication_time_moved",
            f"event:{event_id}",
            {
                "before": old_published,
                "after": new_published,
                "evidence_target": f"event:{event_id}",
            },
        )
        changes += 1
    old_ids = store.attachment_ids(previous)
    new_ids = store.attachment_ids(current)
    for attachment_id in sorted(new_ids - old_ids):
        append_change(
            store,
            run_id,
            "attachment_appeared",
            f"event:{event_id}",
            {"attachment_id": attachment_id, "evidence_target": f"attachment:{attachment_id}"},
        )
        changes += 1
    for attachment_id in sorted(old_ids - new_ids):
        append_change(
            store,
            run_id,
            "attachment_vanished",
            f"event:{event_id}",
            {"attachment_id": attachment_id, "evidence_target": f"event:{event_id}"},
        )
        changes += 1
    return changes


def compare_document(
    store: SnapshotStore,
    run_id: str,
    target: str,
    previous: JSONObject | None,
    current: JSONObject,
    kind: str,
) -> int:
    if previous is None:
        return 0
    old_hash = text_value(previous, "content_sha256")
    new_hash = text_value(current, "content_sha256")
    changes = 0
    if old_hash is not None and new_hash is not None and old_hash != new_hash:
        append_change(
            store,
            run_id,
            f"{kind}_content_changed",
            target,
            {"before_sha256": old_hash, "after_sha256": new_hash, "evidence_target": target},
        )
        changes += 1
    old_url = text_value(previous, "source_url")
    new_url = text_value(current, "source_url")
    if old_url is not None and new_url is not None and old_url != new_url:
        append_change(
            store,
            run_id,
            f"{kind}_url_changed",
            target,
            {"before": old_url, "after": new_url, "evidence_target": target},
        )
        changes += 1
    return changes


def run_once(config: CityConfig, store: SnapshotStore, now: datetime | None = None) -> JSONObject:
    reference_time = now if now is not None else datetime.now(UTC)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    run_id = utc_now()
    watched = body_ids(config)
    issues: list[str] = []
    event_map: dict[int, JSONObject] = {}
    pages_fetched = 0
    pages_reused = 0
    client = LegistarClient(
        config,
        store,
        ConditionalHttpClient(config.timeout_seconds, config.accept_header),
    )
    for page_number in range(config.max_pages):
        response = client.fetch_event_page(page_number)
        pages_fetched += 1
        previous = store.latest(f"events-page:{page_number}")
        decoded, _, parse_issue = parse_response(
            store, response, previous, "event_page"
        )
        if response.not_modified:
            pages_reused += 1
        if parse_issue is not None:
            issues.append(f"events page {page_number}: {parse_issue}")
            continue
        if decoded is None:
            issues.append(f"events page {page_number}: no decoded response")
            continue
        try:
            events = as_objects(decoded, f"events page {page_number}")
        except ValueError as error:
            issues.append(f"events page {page_number}: {error_text(error)}")
            capture_unparsed(store, response, "event_page", error_text(error))
            continue
        if not response.not_modified:
            store.capture(
                response,
                "event_page",
                {"parse_status": "parsed", "record_count": len(events)},
            )
        for event in events:
            event_id = integer_field(event, config.event_fields, "id")
            if event_id is None:
                issues.append(f"events page {page_number}: event without an ID")
                continue
            event_map[event_id] = event
        if len(events) < config.page_size:
            break
    selected_events: list[tuple[int, JSONObject]] = []
    for event in event_map.values():
        event_id = integer_field(event, config.event_fields, "id")
        if event_id is None:
            issues.append("event map contained an event without an ID")
            continue
        if (
            integer_field(event, config.event_fields, "body_id") in watched
            and event_is_in_window(event, config, reference_time)
            and (config.include_cancelled or not event_is_cancelled(event, config))
        ):
            selected_events.append((event_id, event))
    selected_events.sort(key=lambda item: item[0])
    detail_count = 0
    agenda_count = 0
    agenda_reused = 0
    attachment_count = 0
    attachment_reused = 0
    changes_count = 0
    for event_id, event in selected_events:
        detail_target = f"event:{event_id}"
        previous_detail = store.latest(detail_target)
        response = client.fetch_event_detail(event_id)
        decoded, _, parse_issue = parse_response(
            store, response, previous_detail, "event_detail"
        )
        if parse_issue is not None:
            issues.append(f"event {event_id}: {parse_issue}")
            continue
        if decoded is None:
            issues.append(f"event {event_id}: no decoded detail response")
            continue
        try:
            detail = as_object(decoded, f"event {event_id} detail")
            raw_items = object_field(detail, config.event_fields, "items")
            if raw_items is None:
                raise ValueError("configured event-items field was absent")
            items = as_objects(raw_items, f"event {event_id} items")
            attachments, attachment_issues = attachment_views(items, config)
            issues.extend(f"event {event_id}: {issue}" for issue in attachment_issues)
        except ValueError as error:
            reason = error_text(error)
            issues.append(f"event {event_id}: {reason}")
            capture_unparsed(store, response, "event_detail", reason)
            continue
        current_fields = detail_fields(detail, event_id, event, attachments, config)
        if response.not_modified:
            current_detail = previous_detail
            if current_detail is None:
                issues.append(f"event {event_id}: 304 response had no stored detail")
                continue
        else:
            current_detail, inserted = store.capture(response, "event_detail", current_fields)
            if inserted:
                detail_count += 1
        if current_detail is None:
            raise ValueError(f"event {event_id}: detail capture was not available")
        changes_count += compare_event(
            store, run_id, event_id, previous_detail, current_detail
        )
        event_date = text_field(detail, config.event_fields, "date")
        published = text_field(detail, config.event_fields, "agenda_last_published")
        agenda_url = text_field(detail, config.event_fields, "agenda_file")
        if agenda_url is None:
            agenda_url = text_field(event, config.event_fields, "agenda_file")
        if agenda_url is None or not source_url_is_usable(agenda_url):
            issues.append(f"event {event_id}: agenda URL is missing or unusable")
        else:
            agenda_target = f"agenda:{event_id}"
            previous_agenda = store.latest(agenda_target)
            agenda_response = client.http.fetch(
                agenda_target, agenda_url, previous_agenda
            )
            if agenda_response.not_modified:
                agenda_record = previous_agenda
                if agenda_record is None:
                    issues.append(f"event {event_id}: agenda returned 304 without a prior capture")
                else:
                    agenda_reused += 1
                    changes_count += compare_document(
                        store, run_id, agenda_target, previous_agenda, agenda_record, "agenda"
                    )
            elif agenda_response.status == HTTP_OK:
                agenda_record, inserted = binary_capture(
                    store,
                    agenda_response,
                    "agenda_pdf",
                    {
                        "parse_status": "binary",
                        "event_id": event_id,
                        "event_date": event_date,
                        "agenda_last_published": published,
                    },
                )
                if inserted:
                    agenda_count += 1
                changes_count += compare_document(
                    store, run_id, agenda_target, previous_agenda, agenda_record, "agenda"
                )
            else:
                capture_unparsed(
                    store,
                    agenda_response,
                    "agenda_pdf",
                    "agenda download did not return HTTP 200",
                )
                issues.append(f"event {event_id}: agenda download failed")
        for attachment_id, attachment in sorted(attachments.items()):
            attachment_url = text_value(attachment, "url")
            if attachment_url is None or not source_url_is_usable(attachment_url):
                issues.append(f"attachment {attachment_id}: URL is missing or unusable")
                continue
            attachment_target = f"attachment:{attachment_id}"
            previous_attachment = store.latest(attachment_target)
            attachment_response = client.http.fetch(
                attachment_target, attachment_url, previous_attachment
            )
            if attachment_response.not_modified:
                attachment_record = previous_attachment
                if attachment_record is None:
                    issues.append(
                        f"attachment {attachment_id}: returned 304 without a prior capture"
                    )
                else:
                    attachment_reused += 1
                    changes_count += compare_document(
                        store,
                        run_id,
                        attachment_target,
                        previous_attachment,
                        attachment_record,
                        "attachment",
                    )
            elif attachment_response.status == HTTP_OK:
                attachment_record, inserted = binary_capture(
                    store,
                    attachment_response,
                    "attachment",
                    {
                        "parse_status": "binary",
                        "attachment_id": attachment_id,
                        "matter_id": optional_value(attachment, "matter_id"),
                        "name": text_value(attachment, "name"),
                        "last_modified": text_value(attachment, "last_modified"),
                        "matter_version": text_value(attachment, "matter_version"),
                    },
                )
                if inserted:
                    attachment_count += 1
                changes_count += compare_document(
                    store,
                    run_id,
                    attachment_target,
                    previous_attachment,
                    attachment_record,
                    "attachment",
                )
            else:
                capture_unparsed(
                    store,
                    attachment_response,
                    "attachment",
                    "attachment download did not return HTTP 200",
                )
                issues.append(f"attachment {attachment_id}: download failed")
    status = "complete" if not issues else "complete_with_issues"
    summary: JSONObject = {
        "run_id": run_id,
        "status": status,
        "city": config.city,
        "events_pages_fetched": pages_fetched,
        "events_pages_reused": pages_reused,
        "upcoming_events_selected": len(selected_events),
        "event_details_captured": detail_count,
        "agendas_captured": agenda_count,
        "agendas_reused": agenda_reused,
        "attachments_captured": attachment_count,
        "attachments_reused": attachment_reused,
        "changes_observed": changes_count,
        "issues": json_list(issues),
    }
    store.append_run(summary)
    return summary


def main(config_path: Path, store_path: Path | None = None) -> int:
    config = load_city_config(config_path)
    configured_root = config.storage_root
    if store_path is None:
        if not configured_root.is_absolute():
            configured_root = config_path.parent.parent / configured_root
        store_path = configured_root
    store = SnapshotStore(store_path)
    summary = run_once(config, store)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["status"] == "complete" else 2
