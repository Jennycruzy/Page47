from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from page47.analysis.case import load_matter_case
from page47.records.runner import (
    appearance_observation,
    attachment_observation,
    matter_observation,
)
from page47.records.store import (
    AppearanceObservation,
    MatterObservation,
    NotificationObservation,
    RecordStore,
    SnapshotObservation,
    SourceReference,
    WatchObservation,
)
from page47.snapshotter.client import as_object, as_objects, parse_json
from page47.snapshotter.config import JSONObject, JSONValue, field_name, load_city_config

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = REPOSITORY_ROOT / "docs/evidence/preflight/index.json"
CONFIG_PATH = REPOSITORY_ROOT / "config/cities/seattle.yaml"


def recorded_json(url_fragment: str) -> tuple[JSONValue, SourceReference]:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    capture = next(
        item
        for item in index["captures"]
        if url_fragment in item["url"] and item["status"] == 200
    )
    body = (REPOSITORY_ROOT / "docs" / capture["storage_key"]).read_bytes()
    return (
        parse_json(body),
        SourceReference(kind="api", url=capture["url"], captured_at=capture["captured_at"]),
    )


def recorded_detail_with_matter() -> tuple[JSONObject, SourceReference, JSONObject]:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    for capture in index["captures"]:
        if "/v1/seattle/events/" not in capture["url"] or capture["status"] != 200:
            continue
        body = (REPOSITORY_ROOT / "docs" / capture["storage_key"]).read_bytes()
        decoded = parse_json(body)
        if not isinstance(decoded, dict):
            continue
        raw_items = decoded.get("EventItems")
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if isinstance(item, dict) and isinstance(item.get("EventItemMatterId"), int):
                return (
                    decoded,
                    SourceReference(
                        kind="api", url=capture["url"], captured_at=capture["captured_at"]
                    ),
                    item,
                )
    raise AssertionError("The recorded preflight set had no matter-bearing event item")


def recorded_snapshot_observation() -> SnapshotObservation:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    capture = next(
        item
        for item in index["captures"]
        if "/v1/seattle/events/" in item["url"] and item["status"] == 200
    )
    return SnapshotObservation(
        capture_key=capture["capture_id"],
        target="recorded-event-detail",
        kind="event_detail",
        source_url=capture["url"],
        captured_at=capture["captured_at"],
        status=capture["status"],
        response_sha256=capture["sha256"],
        content_sha256=capture["sha256"],
        storage_key=capture["storage_key"],
        source_kind="api",
    )


def test_recorded_matters_upsert_without_fingerprint_drift(tmp_path: Path) -> None:
    config = load_city_config(CONFIG_PATH)
    decoded, source = recorded_json("/v1/seattle/matters?")
    matters = as_objects(decoded, "recorded matters")
    with RecordStore(tmp_path / "records.sqlite3") as store:
        for matter in matters:
            store.upsert_matter(matter_observation(matter, source, config))
        first = store.structural_fingerprint()
        store.commit()
        for matter in matters:
            store.upsert_matter(matter_observation(matter, source, config))
        second = store.structural_fingerprint()
        counts = store.commit_and_counts()

        assert first == second
        assert counts["matters"] == len(matters)
        row = store.connection.execute(
            "SELECT provenance_json FROM matters ORDER BY matter_id LIMIT 1"
        ).fetchone()
        assert row is not None
        provenance = json.loads(row[0])
        assert "current_title" in provenance
        assert provenance["current_title"]["url"] == source.url


def test_recorded_appearance_and_attachment_keep_primary_source(tmp_path: Path) -> None:
    config = load_city_config(CONFIG_PATH)
    detail, source, item = recorded_detail_with_matter()
    event_id = detail.get(field_name(config.event_fields, "id"))
    event_date = detail.get(field_name(config.event_fields, "date"))
    body_id = detail.get(field_name(config.event_fields, "body_id"))
    body_name = detail.get(field_name(config.event_fields, "body_name"))
    if not isinstance(event_id, int):
        raise AssertionError("Recorded event had no integer ID")
    appearance = appearance_observation(
        item,
        event_id,
        event_date,
        body_id,
        body_name,
        source,
        source,
        config,
    )
    raw_attachments = item.get(field_name(config.item_fields, "attachments"))
    attachments = as_objects(raw_attachments, "recorded attachments")
    if not attachments:
        raise AssertionError("Recorded matter-bearing item had no attachment")
    attachment = attachment_observation(
        attachments[0], appearance.matter_id, source, config, None, None
    )
    with RecordStore(tmp_path / "records.sqlite3") as store:
        store.upsert_appearance(appearance)
        store.upsert_attachment(attachment)
        store.upsert_appearance_attachment(appearance.event_item_id, attachment)
        later_observation = replace(
            attachment,
            first_observed_by_us="2026-09-06T00:00:00Z",
            source=SourceReference(
                kind="api", url=source.url, captured_at="2026-09-05T00:00:00Z"
            ),
        )
        store.upsert_attachment(later_observation)
        store.commit()
        first_row = store.connection.execute(
            "SELECT first_observed_by_us, provenance_json FROM attachments LIMIT 1"
        ).fetchone()
        assert first_row is not None
        assert first_row[0] == source.captured_at
        assert json.loads(first_row[1])["first_observed_by_us"]["captured_at"] == source.captured_at
        row = store.connection.execute(
            "SELECT provenance_json FROM appearance_attachments LIMIT 1"
        ).fetchone()
        assert row is not None
        provenance = json.loads(row[0])
        assert provenance["url"]["url"] == source.url
        assert store.counts()["appearances"] == 1
        assert store.counts()["attachments"] == 1


def test_recorded_detail_can_be_read_as_a_typed_object() -> None:
    decoded, _source, _item = recorded_detail_with_matter()
    detail = as_object(decoded, "recorded event detail")
    items = as_objects(detail["EventItems"], "recorded event items")
    assert len(items) > 0


def test_forward_capture_metadata_survives_record_roundtrip(tmp_path: Path) -> None:
    matter_source = SourceReference(
        kind="api",
        url="https://records.example/matters/7",
        captured_at="2026-09-10T00:00:00Z",
        observed_by_page47=True,
        capture_key="matter-capture-1",
        response_sha256="matter-response-1",
        content_sha256="matter-content-1",
    )
    appearance_source = SourceReference(
        kind="api",
        url="https://records.example/items/7",
        captured_at="2026-09-11T00:00:00Z",
        observed_by_page47=True,
        capture_key="item-capture-2",
        response_sha256="item-response-2",
        content_sha256="item-content-2",
    )
    with RecordStore(tmp_path / "records.sqlite3") as store:
        store.upsert_matter(
            MatterObservation(
                matter_id=7,
                file_number="AB-7",
                matter_name=None,
                current_title="Pine Street improvements",
                type_name=None,
                status_name=None,
                body_id=1,
                body_name="Full Council",
                intro_date=None,
                agenda_date=None,
                version=None,
                last_modified_utc=None,
                source=matter_source,
                provenance={"current_title": matter_source.as_json()},
            )
        )
        store.upsert_appearance(
            AppearanceObservation(
                event_item_id=7,
                matter_id=7,
                event_id=7,
                event_date="2026-09-11T00:00:00Z",
                body_id=1,
                body_name="Full Council",
                title_as_presented="Pine Street improvements",
                consent_value=None,
                pdf_placement="regular",
                pdf_evidence_pages_json="[1]",
                pdf_placement_reason="Captured agenda page",
                agenda_sequence=1,
                agenda_number="1",
                action_taken=None,
                action_text=None,
                passed_flag_name=None,
                matter_version_at_event=None,
                agenda_note=None,
                minutes_note=None,
                item_last_modified_utc=None,
                source=appearance_source,
                provenance={
                    "title_as_presented": appearance_source.as_json(),
                    "pdf_placement": appearance_source.as_json(),
                },
            )
        )
        store.commit()

        loaded = load_matter_case(store, "Seattle, Washington", 7, tmp_path / "evidence")

    assert loaded.matter.source.is_forward_capture is True
    assert loaded.matter.source.capture_key == "matter-capture-1"
    assert loaded.appearances[0].source.is_forward_capture is True
    assert loaded.appearances[0].source.capture_key == "item-capture-2"


def test_recorded_snapshot_marks_a_detail_as_applied(tmp_path: Path) -> None:
    observation = recorded_snapshot_observation()
    with RecordStore(tmp_path / "records.sqlite3") as store:
        assert store.has_snapshot(observation.capture_key) is False
        store.add_snapshot(observation)
        assert store.has_snapshot(observation.capture_key) is True


def test_notification_delivery_is_unique_per_watch_and_finding(tmp_path: Path) -> None:
    with RecordStore(tmp_path / "records.sqlite3") as store:
        store.save_watch(
            WatchObservation(
                watch_id="watch-1",
                city="Seattle, Washington",
                bodies=["City Council"],
                address=None,
                neighbourhood="Central",
                email="resident@example.org",
                active=True,
                created_at="2026-09-05T00:00:00Z",
                updated_at="2026-09-05T00:00:00Z",
            )
        )
        store.save_notification(
            NotificationObservation(
                notification_id="delivery-1",
                watch_id="watch-1",
                city="Seattle, Washington",
                finding_id="seattle-1",
                status="failed",
                area_status="confirmed",
                area_reason="The stored record contained the requested neighbourhood.",
                provider_message_id=None,
                error="delivery failed",
                created_at="2026-09-05T00:00:00Z",
                updated_at="2026-09-05T00:00:00Z",
            )
        )
        store.save_notification(
            NotificationObservation(
                notification_id="delivery-2",
                watch_id="watch-1",
                city="Seattle, Washington",
                finding_id="seattle-1",
                status="sent",
                area_status="confirmed",
                area_reason="The stored record contained the requested neighbourhood.",
                provider_message_id="ses-message-1",
                error=None,
                created_at="2026-09-05T00:00:00Z",
                updated_at="2026-09-05T00:01:00Z",
            )
        )
        store.commit()
        assert store.notification_sent("watch-1", "seattle-1") is True
        assert store.counts()["notifications"] == 1
        assert store.notification_rows("Seattle, Washington")[0]["status"] == "sent"


def test_watch_private_link_can_stop_a_watch(tmp_path: Path) -> None:
    observation = WatchObservation(
        watch_id="watch-private",
        city="Seattle, Washington",
        bodies=["City Council"],
        address=None,
        neighbourhood="Central",
        email="resident@example.org",
        active=True,
        created_at="2026-09-05T00:00:00Z",
        updated_at="2026-09-05T00:00:00Z",
    )
    with RecordStore(tmp_path / "records.sqlite3") as store:
        store.save_watch(observation)
        store.commit()
        saved = store.watch_row("watch-private")
        assert saved is not None
        assert saved["active"] is True
        store.deactivate_watch("watch-private", "2026-09-06T00:00:00Z")
        store.commit()
        stopped = store.watch_row("watch-private")
        assert stopped is not None
        assert stopped["active"] is False
        assert store.watch_rows("Seattle, Washington") == []
