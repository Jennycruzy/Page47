"""Load the city data locations used by the web service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from page47.snapshotter.config import JSONValue, as_json_value


@dataclass(frozen=True, slots=True)
class CityRuntime:
    name: str
    city_config: Path
    database: Path
    evidence_root: Path


@dataclass(frozen=True, slots=True)
class WebSettings:
    title: str
    default_city: str
    public_path: str
    cities: tuple[CityRuntime, ...]
    repository_root: Path

    def city(self, name: str) -> CityRuntime:
        for item in self.cities:
            if item.name == name:
                return item
        raise LookupError(f"City {name} is not configured")


def _object(value: JSONValue | None, context: str) -> dict[str, JSONValue]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def _text(value: dict[str, JSONValue], key: str, context: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{context}.{key} must be non-empty text")
    return raw


def load_web_settings(path: Path) -> WebSettings:
    repository_root = path.resolve().parent.parent
    decoded = as_json_value(yaml.safe_load(path.read_text(encoding="utf-8")))
    root = _object(decoded, "web configuration")
    web = _object(root.get("web"), "web")
    title = _text(web, "title", "web")
    default_city = _text(web, "default_city", "web")
    public_path = _text(web, "public_path", "web").rstrip("/")
    if not public_path.startswith("/"):
        raise ValueError("web.public_path must start with '/'")
    raw_cities = _object(web.get("city_configs"), "web.city_configs")
    cities: list[CityRuntime] = []
    for name, raw_value in raw_cities.items():
        city = _object(raw_value, f"web.city_configs.{name}")
        city_config = repository_root / _text(city, "city_config", name)
        database = repository_root / _text(city, "database", name)
        evidence_root = repository_root / _text(city, "evidence_root", name)
        if not city_config.exists():
            raise FileNotFoundError(city_config)
        cities.append(CityRuntime(name, city_config, database, evidence_root))
    if not cities:
        raise ValueError("web.city_configs must not be empty")
    if default_city not in {city.name for city in cities}:
        raise ValueError("web.default_city is not configured")
    return WebSettings(title, default_city, public_path, tuple(cities), repository_root)
