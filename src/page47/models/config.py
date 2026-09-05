"""Validate the Bedrock model choices made from the live discovery record."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ModelRoute:
    name: str
    model_id: str


@dataclass(frozen=True, slots=True)
class ModelSettings:
    region: str
    triage: ModelRoute
    document: ModelRoute
    agents: tuple[ModelRoute, ...]
    temperature: float
    streaming: bool
    triage_max_output_tokens: int
    document_max_output_tokens: int
    agent_max_output_tokens: int
    max_document_pages: int
    max_page_characters: int
    render_scale: float

    def agent_model(self, name: str) -> ModelRoute:
        for route in self.agents:
            if route.name == name:
                return route
        raise ValueError(f"No model route configured for agent {name}")


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Model configuration keys must be text")
            output[key] = _json_value(item)
        return output
    raise ValueError(f"Unsupported model configuration value: {type(value).__name__}")


def _object(value: JSONValue | None, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def _text(value: JSONObject, key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{context}.{key} must be non-empty text")
    return item


def _integer(value: JSONObject, key: str, context: str, minimum: int) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer of at least {minimum}")
    return item


def _number(value: JSONObject, key: str, context: str, minimum: float, maximum: float) -> float:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        raise ValueError(f"{context}.{key} must be a number")
    number = float(item)
    if number < minimum or number > maximum:
        raise ValueError(f"{context}.{key} must be between {minimum} and {maximum}")
    return number


def _boolean(value: JSONObject, key: str, context: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"{context}.{key} must be a boolean")
    return item


def _route(value: JSONObject, key: str, context: str) -> ModelRoute:
    return ModelRoute(name=key, model_id=_text(value, "model_id", context))


def load_model_settings(path: Path) -> ModelSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _object(_json_value(decoded), "model configuration")
    region = _text(root, "region", "model configuration")
    triage = _route(_object(root.get("triage"), "triage"), "triage", "triage")
    document = _route(_object(root.get("document"), "document"), "document", "document")
    raw_agents = _object(root.get("agents"), "agents")
    agents: list[ModelRoute] = []
    for name, raw_value in raw_agents.items():
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"agents.{name} must be non-empty text")
        agents.append(ModelRoute(name=name, model_id=raw_value))
    expected = {"archivist", "substance", "process", "skeptic", "brief_writer"}
    if {route.name for route in agents} != expected:
        raise ValueError("agents must configure exactly the five named Page 47 agents")
    inference = _object(root.get("inference"), "inference")
    return ModelSettings(
        region=region,
        triage=triage,
        document=document,
        agents=tuple(agents),
        temperature=_number(inference, "temperature", "inference", 0.0, 1.0),
        streaming=_boolean(inference, "streaming", "inference"),
        triage_max_output_tokens=_integer(
            inference, "triage_max_output_tokens", "inference", 1
        ),
        document_max_output_tokens=_integer(
            inference, "document_max_output_tokens", "inference", 1
        ),
        agent_max_output_tokens=_integer(inference, "agent_max_output_tokens", "inference", 1),
        max_document_pages=_integer(inference, "max_document_pages", "inference", 1),
        max_page_characters=_integer(inference, "max_page_characters", "inference", 1),
        render_scale=_number(inference, "render_scale", "inference", 0.5, 4.0),
    )
