from __future__ import annotations

from pathlib import Path

from page47.snapshotter.config import load_city_config


def test_seattle_configuration_uses_the_verified_bodies_and_detail_switches() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config/cities/seattle.yaml"
    config = load_city_config(config_path)

    assert config.city == "Seattle, Washington"
    assert config.client == "seattle"
    assert {body.body_id for body in config.watched_bodies} == {
        138,
        211,
        268,
        270,
        278,
        279,
        280,
        282,
        283,
    }
    assert config.detail_parameters == {
        "EventItems": 1,
        "AgendaNote": 1,
        "MinutesNote": 1,
        "EventItemAttachments": 1,
    }
    assert config.backfill.max_event_pages == 100
    assert config.backfill.max_matter_pages == 250
    assert config.backfill.minimum_repeated_matters == 20
    assert config.backfill.minimum_appearances_per_repeated_matter == 3
