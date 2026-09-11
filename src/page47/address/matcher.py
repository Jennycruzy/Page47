"""Resolve an address with the Census service and match only public text fields."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

from page47.analysis.case import MatterCase
from page47.records.store import SourceReference
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value

AreaMatchStatus = Literal["confirmed", "may_affect"]
AreaMatchBasis = Literal["direct_public_text", "inferred_relevance"]


@dataclass(frozen=True, slots=True)
class AddressSettings:
    endpoint: str
    benchmark: str
    response_format: str
    timeout_seconds: int
    cache_directory: str


def load_address_settings(path: Path) -> AddressSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = as_json_value(decoded)
    if not isinstance(root, dict):
        raise ValueError("Address configuration must be an object")
    raw = root.get("geocoder")
    if not isinstance(raw, dict):
        raise ValueError("Address configuration lacks geocoder settings")

    def text(key: str) -> str:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"geocoder.{key} must be non-empty text")
        return value

    timeout = raw.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ValueError("geocoder.timeout_seconds must be a positive integer")
    return AddressSettings(
        endpoint=text("endpoint"),
        benchmark=text("benchmark"),
        response_format=text("format"),
        timeout_seconds=timeout,
        cache_directory=text("cache_directory"),
    )


@dataclass(frozen=True, slots=True)
class CensusAddress:
    requested: str
    matched_address: str
    street_name: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    source: SourceReference

    def as_json(self) -> JSONObject:
        return {
            "requested": self.requested,
            "matched_address": self.matched_address,
            "street_name": self.street_name,
            "city": self.city,
            "state": self.state,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source.as_json(),
        }


@dataclass(frozen=True, slots=True)
class AreaMatch:
    status: AreaMatchStatus
    reason: str
    matched_terms: tuple[str, ...]
    evidence: tuple[SourceReference, ...]
    address: CensusAddress | None
    basis: AreaMatchBasis = "inferred_relevance"
    matched_fields: tuple[str, ...] = ()

    def as_json(self) -> JSONObject:
        return {
            "status": self.status,
            "reason": self.reason,
            "matched_terms": list(self.matched_terms),
            "basis": self.basis,
            "matched_fields": list(self.matched_fields),
            "evidence": [item.as_json() for item in self.evidence],
            "address": self.address.as_json() if self.address is not None else None,
        }


def _config_value(value: object, context: str) -> JSONValue:
    try:
        return as_json_value(value)
    except ValueError as error:
        raise ValueError(f"Invalid {context}") from error


def _cached_json(
    query: str, settings: AddressSettings, cache_root: Path
) -> tuple[JSONObject, SourceReference]:
    params = urlencode(
        {
            "address": query,
            "benchmark": settings.benchmark,
            "format": settings.response_format,
        }
    )
    url = f"{settings.endpoint}?{params}"
    key = sha256(url.encode("utf-8")).hexdigest()
    directory = cache_root / settings.cache_directory
    directory.mkdir(parents=True, exist_ok=True)
    body_path = directory / f"{key}.json"
    metadata_path = directory / f"{key}.meta.json"
    if body_path.exists() != metadata_path.exists():
        raise ValueError(
            "Geocoder cache was incomplete; body and metadata must be present together"
        )
    if body_path.exists() and metadata_path.exists():
        body = body_path.read_text(encoding="utf-8")
        metadata_value = _config_value(
            json.loads(metadata_path.read_text(encoding="utf-8")),
            "cached geocoder metadata",
        )
        if not isinstance(metadata_value, dict):
            raise ValueError("Cached geocoder metadata was not an object")
        captured_at = metadata_value.get("captured_at")
        if not isinstance(captured_at, str) or not captured_at:
            raise ValueError("Cached geocoder metadata had no capture time")
        etag = metadata_value.get("etag")
        if etag is not None and not isinstance(etag, str):
            raise ValueError("Cached geocoder metadata had an invalid ETag")
        decoded = _config_value(json.loads(body), "cached geocoder response")
        if not isinstance(decoded, dict):
            raise ValueError("Cached geocoder response was not an object")
        return decoded, SourceReference("snapshot", url, captured_at)

    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=settings.timeout_seconds) as response:
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        body_bytes = response.read()
    body = body_bytes.decode("utf-8")
    decoded = _config_value(json.loads(body), "geocoder response")
    if not isinstance(decoded, dict):
        raise ValueError("Geocoder response was not an object")
    from datetime import UTC, datetime

    captured_at = datetime.now(UTC).isoformat()
    body_path.write_text(body, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "captured_at": captured_at,
                "url": url,
                "content_sha256": sha256(body_bytes).hexdigest(),
                "etag": etag,
                "last_modified": last_modified,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return decoded, SourceReference("snapshot", url, captured_at)


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def census_lookup(query: str, settings: AddressSettings, cache_root: Path) -> CensusAddress | None:
    if not query.strip():
        raise ValueError("Address query must not be empty")
    decoded, source = _cached_json(query, settings, cache_root)
    raw_matches = decoded.get("result")
    if not isinstance(raw_matches, dict):
        raise ValueError("Geocoder response lacked result object")
    matches = raw_matches.get("addressMatches")
    if not isinstance(matches, list):
        raise ValueError("Geocoder response lacked addressMatches list")
    if not matches:
        return None
    first = matches[0]
    if not isinstance(first, dict):
        raise ValueError("Geocoder address match was not an object")
    matched_address = _text(first.get("matchedAddress"))
    components = first.get("addressComponents")
    coordinates = first.get("coordinates")
    if matched_address is None or not isinstance(components, dict):
        raise ValueError("Geocoder address match lacked required fields")
    street = _text(components.get("streetName"))
    city = _text(components.get("city"))
    state = _text(components.get("state"))
    latitude: float | None = None
    longitude: float | None = None
    if coordinates is not None:
        if not isinstance(coordinates, dict):
            raise ValueError("Geocoder coordinates were not an object")
        raw_latitude = coordinates.get("y")
        raw_longitude = coordinates.get("x")
        if isinstance(raw_latitude, (int, float)) and not isinstance(raw_latitude, bool):
            latitude = float(raw_latitude)
        if isinstance(raw_longitude, (int, float)) and not isinstance(raw_longitude, bool):
            longitude = float(raw_longitude)
    return CensusAddress(query, matched_address, street, city, state, latitude, longitude, source)


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9]+", value) if len(token) > 1}


def _case_fields(case: MatterCase) -> tuple[
    tuple[tuple[str, str], ...], tuple[tuple[str, str], ...], tuple[SourceReference, ...]
]:
    direct_fields: list[tuple[str, str]] = []
    inferred_fields: list[tuple[str, str]] = []
    sources: dict[str, SourceReference] = {}
    for field, value in (
        ("matter.current_title", case.matter.current_title),
        ("matter.matter_name", case.matter.matter_name),
        ("matter.file_number", case.matter.file_number),
    ):
        if isinstance(value, str):
            direct_fields.append((field, value))
    sources[case.matter.source.url] = case.matter.source
    for appearance in case.appearances:
        for field, value in (
            ("appearance.title_as_presented", appearance.title_as_presented),
            ("appearance.agenda_note", appearance.agenda_note),
            ("appearance.minutes_note", appearance.minutes_note),
        ):
            if isinstance(value, str):
                direct_fields.append((field, value))
        if isinstance(appearance.body_name, str):
            inferred_fields.append(("appearance.body_name", appearance.body_name))
        sources[appearance.source.url] = appearance.source
        for attachment in appearance.attachments:
            if attachment.name is not None:
                direct_fields.append(("attachment.name", attachment.name))
            sources[attachment.source.url] = attachment.source
    return tuple(direct_fields), tuple(inferred_fields), tuple(sources.values())


def _field_matches(
    fields: tuple[tuple[str, str], ...], requested_terms: tuple[str, ...]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    matched_terms: list[str] = []
    matched_fields: list[str] = []
    for field, text in fields:
        hits = tuple(term for term in requested_terms if term in _tokens(text))
        if not hits:
            continue
        matched_fields.append(field)
        for term in hits:
            if term not in matched_terms:
                matched_terms.append(term)
    return tuple(matched_terms), tuple(matched_fields)


def match_case_to_area(
    case: MatterCase,
    address: CensusAddress | None,
    neighbourhood: str | None,
) -> AreaMatch:
    if address is None and (neighbourhood is None or not neighbourhood.strip()):
        raise ValueError("An address or neighbourhood is required")
    direct_fields, inferred_fields, sources = _case_fields(case)
    requested_terms: list[str] = []
    if address is not None and address.street_name is not None:
        requested_terms.extend(sorted(_tokens(address.street_name)))
    if neighbourhood is not None and neighbourhood.strip():
        requested_terms.extend(sorted(_tokens(neighbourhood)))
    terms = tuple(dict.fromkeys(requested_terms))
    matched, matched_fields = _field_matches(direct_fields, terms)
    if matched:
        return AreaMatch(
            "confirmed",
            "The requested area appears in the stored public record's direct text "
            f"({', '.join(matched_fields)}).",
            matched,
            sources,
            address,
            "direct_public_text",
            matched_fields,
        )
    inferred_terms, inferred_fields_matched = _field_matches(inferred_fields, terms)
    if inferred_terms:
        return AreaMatch(
            "may_affect",
            "The record matches a public-body or jurisdiction term, but the requested "
            "area was not identified directly in the matter text.",
            inferred_terms,
            sources,
            address,
            "inferred_relevance",
            inferred_fields_matched,
        )
    return AreaMatch(
        "may_affect",
        "May affect your area — no direct street or neighbourhood text match was found.",
        (),
        sources,
        address,
        "inferred_relevance",
        (),
    )
