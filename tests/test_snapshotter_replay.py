from __future__ import annotations

import json
from pathlib import Path

from page47.snapshotter.client import as_objects, parse_json
from page47.snapshotter.config import load_city_config, object_field


def test_recorded_event_detail_replays_as_public_items() -> None:
    root = Path(__file__).resolve().parents[1]
    index = json.loads(
        (root / "docs/evidence/preflight/index.json").read_text(encoding="utf-8")
    )
    capture = next(
        item
        for item in index["captures"]
        if "/v1/seattle/events/" in item["url"] and item["status"] == 200
    )
    body = (root / "docs" / capture["storage_key"]).read_bytes()
    detail = parse_json(body)
    config = load_city_config(root / "config/cities/seattle.yaml")
    assert isinstance(detail, dict)
    raw_items = object_field(detail, config.event_fields, "items")
    assert raw_items is not None
    items = as_objects(raw_items, "recorded event items")
    assert len(items) > 0
