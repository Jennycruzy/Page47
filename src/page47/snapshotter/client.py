"""Legistar requests whose field and paging choices come from city config."""

from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import quote, urlencode

from page47.snapshotter.config import CityConfig, JSONObject, JSONValue, configured_integer
from page47.snapshotter.http import ConditionalHttpClient, FetchResult
from page47.snapshotter.store import SnapshotStore


def parse_json(body: bytes) -> JSONValue:
    decoded: object = json.loads(body)
    return _as_json_value(decoded)


def _as_json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_as_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Legistar JSON keys must be text")
            output[key] = _as_json_value(item)
        return output
    raise ValueError(f"Unsupported Legistar JSON value: {type(value).__name__}")


def as_object(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def as_objects(value: JSONValue, context: str) -> list[JSONObject]:
    if not isinstance(value, list):
        raise ValueError(f"Expected a list for {context}")
    output: list[JSONObject] = []
    for index, item in enumerate(value):
        output.append(as_object(item, f"{context}[{index}]"))
    return output


class LegistarClient:
    def __init__(
        self,
        config: CityConfig,
        store: SnapshotStore,
        http: ConditionalHttpClient | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.http = (
            http
            if http is not None
            else ConditionalHttpClient(config.timeout_seconds, config.accept_header)
        )

    def url(self, resource: str, parameters: Mapping[str, str]) -> str:
        path = "/".join(
            (
                quote(self.config.client, safe=""),
                *(quote(part, safe="") for part in resource.strip("/").split("/")),
            )
        )
        query = urlencode(parameters)
        return f"{self.config.base_url}/{path}?{query}"

    def fetch(self, target: str, resource: str, parameters: Mapping[str, str]) -> FetchResult:
        request_url = self.url(resource, parameters)
        return self.http.fetch(target, request_url, self.store.latest(target))

    def fetch_event_page(self, page_number: int, page_size: int | None = None) -> FetchResult:
        if page_number < 0:
            raise ValueError("page_number must not be negative")
        requested_page_size = self.config.page_size if page_size is None else page_size
        if requested_page_size < 1:
            raise ValueError("page_size must be positive")
        skip = page_number * requested_page_size
        parameters = {
            "$top": str(requested_page_size),
            "$skip": str(skip),
            "$orderby": "EventId desc",
        }
        return self.fetch(f"events-page:{page_number}", "events", parameters)

    def fetch_matter_page(self, page_number: int, page_size: int) -> FetchResult:
        if page_number < 0:
            raise ValueError("page_number must not be negative")
        if page_size < 1:
            raise ValueError("page_size must be positive")
        skip = page_number * page_size
        parameters = {
            "$top": str(page_size),
            "$skip": str(skip),
            "$orderby": "MatterId asc",
        }
        return self.fetch(f"matters-page:{page_number}", "matters", parameters)

    def fetch_event_detail(self, event_id: int) -> FetchResult:
        if event_id < 1:
            raise ValueError("event_id must be positive")
        parameters: dict[str, str] = {}
        for key, value in self.config.detail_parameters.items():
            parameters[key] = str(configured_integer(value, f"detail_parameters.{key}"))
        return self.fetch(f"event:{event_id}", f"events/{event_id}", parameters)
