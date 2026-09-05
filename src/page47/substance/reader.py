"""Read captured PDF attachments and return page-linked references."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import yaml
from pypdf import PdfReader

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class ReferenceRule:
    name: str
    expression: str


@dataclass(frozen=True, slots=True)
class SubstanceConfig:
    minimum_references: int
    context_characters: int
    terms: tuple[str, ...]
    references: tuple[ReferenceRule, ...]


@dataclass(frozen=True, slots=True)
class PageReference:
    kind: str
    value: str
    page_number: int
    start_character: int
    end_character: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class AttachmentReading:
    status: str
    page_count: int
    references: tuple[PageReference, ...]
    reason: str


def reading_references(reading: AttachmentReading) -> JSONObject:
    return {
        "references": [
            {
                "kind": reference.kind,
                "value": reference.value,
                "page_number": reference.page_number,
                "start_character": reference.start_character,
                "end_character": reference.end_character,
                "excerpt": reference.excerpt,
            }
            for reference in reading.references
        ]
    }


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        result: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("Substance configuration keys must be text")
            result[key] = _json_value(item)
        return result
    raise ValueError(f"Unsupported substance configuration value: {type(value).__name__}")


def _object(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def _text(value: JSONObject, key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} must be non-empty text")
    return item


def _integer(value: JSONObject, key: str, minimum: int) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{key} must be an integer of at least {minimum}")
    return item


def load_substance_config(path: Path) -> SubstanceConfig:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _object(_json_value(decoded), "substance configuration")
    triage = _object(root.get("triage"), "triage")
    raw_terms = triage.get("terms")
    raw_references = triage.get("references")
    if not isinstance(raw_terms, list) or not raw_terms:
        raise ValueError("triage.terms must be a non-empty list")
    if not isinstance(raw_references, list) or not raw_references:
        raise ValueError("triage.references must be a non-empty list")
    terms = tuple(
        item if isinstance(item, str) and item.strip() else _invalid_text("triage.terms")
        for item in raw_terms
    )
    rules: list[ReferenceRule] = []
    for index, item in enumerate(raw_references):
        rule = _object(item, f"triage.references[{index}]")
        expression = _text(rule, "expression")
        try:
            re.compile(expression, re.IGNORECASE)
        except re.error as error:
            raise ValueError(f"Invalid reference expression {rule.get('name')}: {error}") from error
        rules.append(ReferenceRule(name=_text(rule, "name"), expression=expression))
    return SubstanceConfig(
        minimum_references=_integer(triage, "minimum_references", 1),
        context_characters=_integer(triage, "context_characters", 1),
        terms=terms,
        references=tuple(rules),
    )


def _invalid_text(context: str) -> str:
    raise ValueError(f"{context} must contain non-empty text")


def read_pdf_attachment(pdf_bytes: bytes, config: SubstanceConfig) -> AttachmentReading:
    """Return only references whose page also contains a configured subject term."""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except (OSError, ValueError) as error:
        return AttachmentReading("unreadable", 0, (), f"{type(error).__name__}: {error}")
    references: list[PageReference] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text()
        except (OSError, ValueError) as error:
            return AttachmentReading(
                "unreadable", len(reader.pages), (), f"{type(error).__name__}: {error}"
            )
        if not isinstance(text, str) or not text.strip():
            continue
        lower_text = text.casefold()
        if not any(term.casefold() in lower_text for term in config.terms):
            continue
        for rule in config.references:
            for match in re.finditer(rule.expression, text, re.IGNORECASE):
                start = max(0, match.start() - config.context_characters)
                end = min(len(text), match.end() + config.context_characters)
                references.append(
                    PageReference(
                        kind=rule.name,
                        value=match.group(0),
                        page_number=page_number,
                        start_character=match.start(),
                        end_character=match.end(),
                        excerpt=" ".join(text[start:end].split()),
                    )
                )
    if len(references) < config.minimum_references:
        return AttachmentReading(
            "absent",
            len(reader.pages),
            (),
            "No configured substantive reference was identified in the readable PDF text.",
        )
    return AttachmentReading(
        "candidate",
        len(reader.pages),
        tuple(references),
        "Configured references were identified and require document-specific reading.",
    )
