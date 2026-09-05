"""Compute plain, per-body comparisons from the stored public record."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import yaml

from page47.records.store import SourceReference, stable_json

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class NormSettings:
    short_document_page_limit: int
    maximum_source_links: int


def load_norm_settings(path: Path) -> NormSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Norm configuration must be an object")
    raw = decoded.get("norms")
    if not isinstance(raw, dict):
        raise ValueError("Norm configuration lacks norms settings")
    short_limit = raw.get("short_document_page_limit")
    source_limit = raw.get("maximum_source_links")
    if (
        isinstance(short_limit, bool)
        or not isinstance(short_limit, int)
        or short_limit < 1
    ):
        raise ValueError("short_document_page_limit must be a positive integer")
    if (
        isinstance(source_limit, bool)
        or not isinstance(source_limit, int)
        or source_limit < 1
    ):
        raise ValueError("maximum_source_links must be a positive integer")
    return NormSettings(short_limit, source_limit)


@dataclass(frozen=True, slots=True)
class HistoricalNorm:
    body_name: str
    meeting_count: int
    appearance_count: int
    title_comparison_count: int
    retitled_count: int
    retitled_rate: float | None
    known_placement_count: int
    consent_appearance_count: int
    regular_appearance_count: int
    consent_documents_count: int
    short_consent_documents_count: int
    short_consent_document_share: float | None
    timing_observation_count: int
    median_attachment_lead_hours: float | None
    unknown_timing_count: int
    source_links: tuple[SourceReference, ...]

    def as_json(self) -> JSONObject:
        return {
            "body_name": self.body_name,
            "meeting_count": self.meeting_count,
            "appearance_count": self.appearance_count,
            "title_comparison_count": self.title_comparison_count,
            "retitled_count": self.retitled_count,
            "retitled_rate": self.retitled_rate,
            "known_placement_count": self.known_placement_count,
            "consent_appearance_count": self.consent_appearance_count,
            "regular_appearance_count": self.regular_appearance_count,
            "consent_documents_count": self.consent_documents_count,
            "short_consent_documents_count": self.short_consent_documents_count,
            "short_consent_document_share": self.short_consent_document_share,
            "timing_observation_count": self.timing_observation_count,
            "median_attachment_lead_hours": self.median_attachment_lead_hours,
            "unknown_timing_count": self.unknown_timing_count,
            "source_links": [source.as_json() for source in self.source_links],
        }

    @property
    def fingerprint(self) -> str:
        return sha256(stable_json(self.as_json()).encode("utf-8")).hexdigest()

    def timing_sentence(self, observed_lead_hours: float | None) -> str:
        if observed_lead_hours is None:
            return "The attachment timing could not be compared with this body's stored records."
        if self.median_attachment_lead_hours is None:
            return (
                "This body's stored records do not yet contain enough attachment timestamps "
                "for a timing comparison."
            )
        usual_days = self.median_attachment_lead_hours / 24.0
        observed_days = observed_lead_hours / 24.0
        return (
            f"For {self.meeting_count} recorded {self.body_name} meetings, attachments had a "
            f"median lead time of {usual_days:.1f} days. This item had {observed_days:.1f} days."
        )


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _source(row: sqlite3.Row) -> SourceReference:
    url = row["source_url"]
    captured_at = row["observed_at"]
    if not isinstance(url, str) or not url:
        raise ValueError("Norm source URL was missing")
    if not isinstance(captured_at, str) or not captured_at:
        raise ValueError("Norm source capture time was missing")
    return SourceReference("api", url, captured_at)


def _add_source(
    sources: dict[str, SourceReference], row: sqlite3.Row, limit: int
) -> None:
    source = _source(row)
    if source.url not in sources and len(sources) < limit:
        sources[source.url] = source


def _body_names(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT DISTINCT body_name FROM events "
        "WHERE body_name IS NOT NULL ORDER BY body_name"
    ).fetchall()
    output: list[str] = []
    for row in rows:
        name = row[0]
        if not isinstance(name, str) or not name:
            raise ValueError("Stored event body name was invalid")
        output.append(name)
    return tuple(output)


def compute_historical_norms(
    connection: sqlite3.Connection, settings: NormSettings
) -> tuple[HistoricalNorm, ...]:
    """Compute norms from rows already stored; no external call is made here."""

    norms: list[HistoricalNorm] = []
    for body_name in _body_names(connection):
        source_links: dict[str, SourceReference] = {}
        meetings = connection.execute(
            "SELECT event_id, source_url, observed_at FROM events "
            "WHERE body_name = ? ORDER BY event_date, event_id",
            (body_name,),
        ).fetchall()
        for row in meetings:
            _add_source(source_links, row, settings.maximum_source_links)

        appearances = connection.execute(
            "SELECT event_item_id, matter_id, event_date, title_as_presented, "
            "pdf_placement, source_url, observed_at FROM appearances "
            "WHERE body_name = ? ORDER BY event_date, event_item_id",
            (body_name,),
        ).fetchall()
        previous_titles: dict[int, str | None] = {}
        title_comparison_count = 0
        retitled_count = 0
        consent_count = 0
        regular_count = 0
        for row in appearances:
            _add_source(source_links, row, settings.maximum_source_links)
            matter_id = row["matter_id"]
            title = row["title_as_presented"]
            if matter_id is not None:
                if isinstance(matter_id, bool) or not isinstance(matter_id, int):
                    raise ValueError("Stored appearance matter ID was invalid")
                if matter_id in previous_titles:
                    title_comparison_count += 1
                    previous = previous_titles[matter_id]
                    if isinstance(previous, str) and isinstance(title, str):
                        if previous.strip().casefold() != title.strip().casefold():
                            retitled_count += 1
                previous_titles[matter_id] = title if isinstance(title, str) else None
            placement = row["pdf_placement"]
            if placement == "consent":
                consent_count += 1
            elif placement == "regular":
                regular_count += 1

        attachment_rows = connection.execute(
            "SELECT a.event_item_id, a.event_date, a.pdf_placement, a.source_url, "
            "a.observed_at, aa.last_modified_utc, ar.page_count "
            "FROM appearances a JOIN appearance_attachments aa "
            "ON aa.event_item_id = a.event_item_id "
            "LEFT JOIN attachment_readings ar ON ar.attachment_id = aa.attachment_id "
            "WHERE a.body_name = ? ORDER BY a.event_date, a.event_item_id, aa.attachment_id",
            (body_name,),
        ).fetchall()
        timing_values: list[float] = []
        unknown_timing_count = 0
        consent_documents_count = 0
        short_consent_documents_count = 0
        for row in attachment_rows:
            _add_source(source_links, row, settings.maximum_source_links)
            event_date = _parse_datetime(row["event_date"])
            modified = _parse_datetime(row["last_modified_utc"])
            if event_date is None or modified is None:
                unknown_timing_count += 1
            else:
                timing_values.append((event_date - modified).total_seconds() / 3600.0)
            if row["pdf_placement"] == "consent":
                consent_documents_count += 1
                page_count = row["page_count"]
                if (
                    isinstance(page_count, int)
                    and not isinstance(page_count, bool)
                    and page_count < settings.short_document_page_limit
                ):
                    short_consent_documents_count += 1

        known_placement_count = consent_count + regular_count
        retitled_rate = (
            retitled_count / title_comparison_count if title_comparison_count else None
        )
        short_share = (
            short_consent_documents_count / consent_documents_count
            if consent_documents_count
            else None
        )
        norms.append(
            HistoricalNorm(
                body_name=body_name,
                meeting_count=len(meetings),
                appearance_count=len(appearances),
                title_comparison_count=title_comparison_count,
                retitled_count=retitled_count,
                retitled_rate=retitled_rate,
                known_placement_count=known_placement_count,
                consent_appearance_count=consent_count,
                regular_appearance_count=regular_count,
                consent_documents_count=consent_documents_count,
                short_consent_documents_count=short_consent_documents_count,
                short_consent_document_share=short_share,
                timing_observation_count=len(timing_values),
                median_attachment_lead_hours=_median(timing_values),
                unknown_timing_count=unknown_timing_count,
                source_links=tuple(source_links.values()),
            )
        )
    return tuple(norms)


def norms_json(norms: tuple[HistoricalNorm, ...]) -> str:
    return json.dumps([norm.as_json() for norm in norms], sort_keys=True, separators=(",", ":"))
