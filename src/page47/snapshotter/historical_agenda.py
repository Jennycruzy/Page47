"""Capture a specified city's published agenda through its event record."""

from __future__ import annotations

from pathlib import Path

from page47.snapshotter.client import LegistarClient, as_object
from page47.snapshotter.config import CityConfig, load_city_config, text_field
from page47.snapshotter.runner import (
    HTTP_OK,
    binary_capture,
    parse_response,
    response_is_pdf,
    source_url_is_usable,
)
from page47.snapshotter.store import SnapshotStore


def capture_historical_agenda(
    config_path: Path,
    evidence_root: Path,
    event_id: int,
) -> dict[str, int | str]:
    """Capture one event's agenda URL obtained from its configured API record."""

    if event_id < 1:
        raise ValueError("event_id must be positive")
    config: CityConfig = load_city_config(config_path)
    store = SnapshotStore(evidence_root)
    client = LegistarClient(config, store)
    detail_response = client.fetch_event_detail(event_id)
    previous_detail = store.latest(f"event:{event_id}")
    decoded, _capture, error = parse_response(
        store, detail_response, previous_detail, "event_detail"
    )
    if decoded is None:
        raise ValueError(f"Event {event_id} could not be read: {error}")
    detail = as_object(decoded, f"event {event_id} detail")
    agenda_url = text_field(detail, config.event_fields, "agenda_file")
    if agenda_url is None or not source_url_is_usable(agenda_url):
        raise ValueError(f"Event {event_id} has no usable published agenda URL")
    event_date = text_field(detail, config.event_fields, "date")
    published = text_field(detail, config.event_fields, "agenda_last_published")
    target = f"agenda:{event_id}"
    previous_agenda = store.latest(target)
    response = client.http.fetch(target, agenda_url, previous_agenda)
    if response.not_modified:
        if previous_agenda is None:
            raise ValueError(f"Event {event_id} returned 304 without a prior agenda capture")
        return {"event_id": event_id, "status": "reused", "agenda_captured": 0}
    if response.status != HTTP_OK:
        store.capture(
            response,
            "agenda_pdf",
            {
                "parse_status": "unparsed",
                "parse_error": "agenda download did not return HTTP 200",
                "event_id": event_id,
            },
        )
        raise ValueError(f"Event {event_id} agenda download returned HTTP {response.status}")
    if not response_is_pdf(response):
        content_type = response.headers.get("content-type", "unknown")
        raise ValueError(
            f"Event {event_id} agenda URL returned non-PDF content ({content_type})"
        )
    _record, inserted = binary_capture(
        store,
        response,
        "agenda_pdf",
        {
            "parse_status": "binary",
            "event_id": event_id,
            "event_date": event_date,
            "agenda_last_published": published,
        },
    )
    return {
        "event_id": event_id,
        "status": "captured" if inserted else "reused",
        "agenda_captured": 1 if inserted else 0,
    }
