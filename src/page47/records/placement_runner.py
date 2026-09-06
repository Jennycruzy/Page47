"""Apply PDF-backed consent placement to already stored appearances."""

from __future__ import annotations

from pathlib import Path

from page47.records.pdf_consent import classify_item
from page47.records.runner import (
    agenda_capture,
    agenda_snapshot,
    response_hash,
    source_for_capture,
)
from page47.records.store import RecordStore, SourceReference
from page47.snapshotter.config import CityConfig, load_city_config
from page47.snapshotter.store import SnapshotStore, text_value


def pdf_reader_enabled(config: CityConfig) -> bool:
    calibration = config.consent_calibration
    reader = calibration.get("pdf_reader")
    return isinstance(reader, dict) and reader.get("enabled") is True


def apply_pdf_placements(
    config_path: Path,
    database_path: Path,
    evidence_root: Path,
) -> dict[str, int]:
    """Update only appearances supported by locally captured agenda PDFs."""

    config = load_city_config(config_path)
    if not pdf_reader_enabled(config):
        raise ValueError(f"PDF placement reader is not enabled for {config.city}")
    snapshot_store = SnapshotStore(evidence_root)
    result = {
        "agendas_available": 0,
        "agendas_unavailable": 0,
        "agendas_unreadable": 0,
        "appearances_updated": 0,
        "cannot_determine": 0,
    }
    with RecordStore(database_path) as record_store:
        for event in record_store.event_agendas():
            agenda_record = agenda_snapshot(snapshot_store, event.event_id, event.agenda_file)
            agenda = None
            agenda_issue: str | None = None
            agenda_source: SourceReference | None = None
            if agenda_record is not None:
                try:
                    agenda = agenda_capture(snapshot_store, event.event_id, event.agenda_file)
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
                    if agenda_record.get("status") == 200:
                        result["agendas_unreadable"] += 1
                    else:
                        result["agendas_unavailable"] += 1
            if agenda is None and agenda_source is not None and agenda_issue is not None:
                for appearance in record_store.matter_appearance_titles(event.event_id):
                    record_store.set_pdf_placement(
                        appearance.event_item_id,
                        "cannot_determine",
                        (),
                        agenda_issue,
                        agenda_source,
                    )
                    result["appearances_updated"] += 1
                    result["cannot_determine"] += 1
            if agenda is None:
                continue
            result["agendas_available"] += 1
            pages, source = agenda
            for appearance in record_store.matter_appearance_titles(event.event_id):
                placement = classify_item(pages, appearance.title_as_presented)
                record_store.set_pdf_placement(
                    appearance.event_item_id,
                    placement.placement,
                    placement.evidence_pages,
                    placement.reason,
                    source,
                )
                result["appearances_updated"] += 1
                if placement.placement == "cannot_determine":
                    result["cannot_determine"] += 1
        record_store.commit()
    return result
