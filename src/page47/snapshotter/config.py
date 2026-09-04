"""Validated city configuration for the public-record snapshotter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class WatchedBody:
    body_id: int
    name: str


@dataclass(frozen=True, slots=True)
class BackfillConfig:
    event_page_size: int
    max_event_pages: int
    matter_page_size: int
    max_matter_pages: int
    max_detail_events: int
    minimum_repeated_matters: int
    minimum_appearances_per_repeated_matter: int


@dataclass(frozen=True, slots=True)
class CityConfig:
    city: str
    client: str
    base_url: str
    accept_header: str
    page_size: int
    max_pages: int
    timeout_seconds: int
    lookahead_days: int
    include_cancelled: bool
    watched_bodies: tuple[WatchedBody, ...]
    event_fields: JSONObject
    item_fields: JSONObject
    matter_fields: JSONObject
    attachment_fields: JSONObject
    detail_parameters: JSONObject
    storage_root: Path
    backfill: BackfillConfig


def as_json_value(value: object) -> JSONValue:
    """Validate YAML data before it enters typed application code."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [as_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("City configuration keys must be text")
            output[key] = as_json_value(item)
        return output
    raise ValueError(f"Unsupported city configuration value: {type(value).__name__}")


def as_object(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def required_text(value: JSONObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return item


def required_integer(value: JSONObject, key: str, minimum: int | None = None) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise ValueError(f"{key} must be an integer")
    if minimum is not None and item < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    return item


def required_boolean(value: JSONObject, key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{key} must be a boolean")
    return item


def required_mapping(value: JSONObject, key: str) -> JSONObject:
    return as_object(value.get(key), key)


def load_city_config(path: Path) -> CityConfig:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = as_object(as_json_value(decoded), "city configuration")
    api = required_mapping(root, "api")
    watched_value = root.get("watched_bodies")
    if not isinstance(watched_value, list):
        raise ValueError("watched_bodies must be a list")
    watched: list[WatchedBody] = []
    for index, raw_body in enumerate(watched_value):
        body = as_object(raw_body, f"watched_bodies[{index}]")
        watched.append(
            WatchedBody(
                body_id=required_integer(body, "id", minimum=1),
                name=required_text(body, "name"),
            )
        )
    if not watched:
        raise ValueError("watched_bodies must not be empty")
    storage = required_mapping(root, "storage")
    backfill = required_mapping(root, "backfill")
    detail_parameters = required_mapping(api, "detail_parameters")
    for key, item in detail_parameters.items():
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"api.detail_parameters.{key} must be an integer")
    return CityConfig(
        city=required_text(root, "city"),
        client=required_text(root, "client"),
        base_url=required_text(api, "base_url").rstrip("/"),
        accept_header=required_text(api, "accept_header"),
        page_size=required_integer(api, "page_size", minimum=1),
        max_pages=required_integer(api, "max_pages", minimum=1),
        timeout_seconds=required_integer(api, "timeout_seconds", minimum=1),
        lookahead_days=required_integer(api, "lookahead_days", minimum=0),
        include_cancelled=required_boolean(api, "include_cancelled"),
        watched_bodies=tuple(watched),
        event_fields=required_mapping(root, "event_fields"),
        item_fields=required_mapping(root, "item_fields"),
        matter_fields=required_mapping(root, "matter_fields"),
        attachment_fields=required_mapping(root, "attachment_fields"),
        detail_parameters=detail_parameters,
        storage_root=Path(required_text(storage, "root")),
        backfill=BackfillConfig(
            event_page_size=required_integer(backfill, "event_page_size", minimum=1),
            max_event_pages=required_integer(backfill, "max_event_pages", minimum=1),
            matter_page_size=required_integer(backfill, "matter_page_size", minimum=1),
            max_matter_pages=required_integer(backfill, "max_matter_pages", minimum=1),
            max_detail_events=required_integer(backfill, "max_detail_events", minimum=1),
            minimum_repeated_matters=required_integer(
                backfill, "minimum_repeated_matters", minimum=1
            ),
            minimum_appearances_per_repeated_matter=required_integer(
                backfill, "minimum_appearances_per_repeated_matter", minimum=2
            ),
        ),
    )


def field_name(fields: JSONObject, key: str) -> str:
    """Return a configured source field name without assuming a site label."""

    return required_text(fields, key)


def integer_field(record: JSONObject, fields: JSONObject, key: str) -> int | None:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def text_field(record: JSONObject, fields: JSONObject, key: str) -> str | None:
    source_key = field_name(fields, key)
    value = record.get(source_key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def object_field(record: JSONObject, fields: JSONObject, key: str) -> JSONValue | None:
    source_key = field_name(fields, key)
    return record.get(source_key)


def configured_integer(value: JSONValue, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} must be an integer")
    return value


def body_ids(config: CityConfig) -> set[int]:
    return {body.body_id for body in config.watched_bodies}
