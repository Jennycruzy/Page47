"""Store newly captured event details without re-reading historical listings."""

from __future__ import annotations

from pathlib import Path

from page47.records.pdf_consent import AgendaPage, classify_item
from page47.records.runner import (
    HTTP_OK,
    agenda_capture,
    agenda_snapshot,
    appearance_observation,
    attachment_observation,
    capture_observation,
    content_capture,
    event_observation,
    required_integer,
    response_hash,
    source_for_capture,
)
from page47.records.store import RecordStore, SourceReference
from page47.snapshotter.client import as_object, as_objects, parse_json
from page47.snapshotter.config import field_name, load_city_config
from page47.snapshotter.store import SnapshotStore, text_value


def apply_captured_events(
    config_path: Path,
    database_path: Path,
    evidence_root: Path,
) -> dict[str, int]:
    """Apply event-detail captures not yet recorded in the local database."""

    config = load_city_config(config_path)
    snapshot_store = SnapshotStore(evidence_root)
    result = {"new_details": 0, "appearances": 0, "failures": 0}
    with RecordStore(database_path) as record_store:
        for capture in snapshot_store.records:
            if capture.get("kind") != "event_detail" or capture.get("status") != HTTP_OK:
                continue
            capture_key = text_value(capture, "capture_key")
            if capture_key is None:
                raise ValueError("Stored event-detail capture has no capture key")
            if record_store.has_snapshot(capture_key):
                continue
            source = source_for_capture(capture)
            response_sha256 = text_value(capture, "response_sha256")
            complete = True
            try:
                detail = as_object(
                    parse_json(snapshot_store.body(capture)),
                    f"captured event detail {capture_key}",
                )
                event_id = required_integer(detail, config.event_fields, "id", "event detail")
                record_store.upsert_event(event_observation(detail, source, config))
                raw_items = detail.get(field_name(config.event_fields, "items"))
                items = as_objects(raw_items, f"captured event {event_id} items")
                agenda_file = detail.get(field_name(config.event_fields, "agenda_file"))
                if agenda_file is not None and not isinstance(agenda_file, str):
                    raise ValueError("Captured event agenda URL was not text")
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
                            raise ValueError("A stored agenda capture lacked its target") from error
                        record_store.add_parse_failure(
                            agenda_target,
                            agenda_source.url,
                            agenda_source.captured_at,
                            response_hash(agenda_record),
                            agenda_issue,
                        )
                        result["failures"] += 1
                event_date = detail.get(field_name(config.event_fields, "date"))
                body_id = detail.get(field_name(config.event_fields, "body_id"))
                body_name = detail.get(field_name(config.event_fields, "body_name"))
                for index, item in enumerate(items):
                    try:
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
                        record_store.upsert_appearance(appearance)
                        if (
                            agenda is not None
                            and appearance.matter_id is not None
                            and appearance.title_as_presented is not None
                        ):
                            pages, agenda_source = agenda
                            placement = classify_item(pages, appearance.title_as_presented)
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
                        attachments = as_objects(
                            raw_attachments,
                            f"captured event item {appearance.event_item_id} attachments",
                        )
                        for attachment in attachments:
                            attachment_id = required_integer(
                                attachment, config.attachment_fields, "id", "attachment"
                            )
                            content_hash, content_source = content_capture(
                                snapshot_store, attachment_id
                            )
                            observed = attachment_observation(
                                attachment,
                                appearance.matter_id,
                                source,
                                config,
                                content_hash,
                                content_source,
                            )
                            record_store.upsert_attachment(observed)
                            record_store.upsert_appearance_attachment(
                                appearance.event_item_id, observed
                            )
                        result["appearances"] += 1
                    except ValueError as error:
                        complete = False
                        result["failures"] += 1
                        record_store.add_parse_failure(
                            f"captured-event:{event_id}:{index}",
                            source.url,
                            source.captured_at,
                            response_sha256,
                            f"{type(error).__name__}: {error}",
                        )
                if complete:
                    record_store.add_snapshot(capture_observation(capture))
                    result["new_details"] += 1
            except (UnicodeDecodeError, ValueError) as error:
                result["failures"] += 1
                record_store.add_parse_failure(
                    capture_key,
                    source.url,
                    source.captured_at,
                    response_sha256,
                    f"{type(error).__name__}: {error}",
                )
        record_store.commit()
    return result
