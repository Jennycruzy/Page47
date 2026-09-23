"""Validate the JSON request sent from the record service to AgentCore."""

from __future__ import annotations

import base64
import binascii
import json
from hashlib import sha256
from pathlib import Path

from page47.analysis.case import InvestigationContext, MatterCase, case_from_structural_payload
from page47.analysis.drift import compare_all_appearances, load_presentation_config
from page47.models.config import load_model_settings
from page47.records.store import SourceReference
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value


def request_from_case(case: MatterCase) -> JSONObject:
    """Build a checked AgentCore request from one stored public matter."""

    documents: list[JSONValue] = []
    for attachment in case.unique_attachments():
        capture = attachment.document_capture()
        if capture is None:
            continue
        content, source = capture
        content_hash = sha256(content).hexdigest()
        if attachment.content_hash is not None and attachment.content_hash != content_hash:
            raise ValueError(
                f"Captured attachment {attachment.attachment_id} did not match the record hash"
            )
        documents.append(
            {
                "attachment_id": attachment.attachment_id,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "content_sha256": content_hash,
                "source": source.as_json(),
            }
        )
    return {
        "city": case.city,
        "matter_id": case.matter_id,
        "case": case.structural_payload(),
        "documents": documents,
    }


def request_bytes(case: MatterCase) -> bytes:
    """Encode a runtime request deterministically for the data-plane call."""

    return json.dumps(request_from_case(case), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _object(value: object, context: str) -> JSONObject:
    decoded = as_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"Runtime request {context} was not an object")
    return decoded


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Runtime request {context} was not non-empty text")
    return value


def _integer(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"Runtime request {context} was not a positive integer")
    return value


def _source(value: object, context: str) -> SourceReference:
    item = _object(value, context)
    return SourceReference(
        kind=_text(item.get("kind"), f"{context}.kind"),
        url=_text(item.get("url"), f"{context}.url"),
        captured_at=_text(item.get("captured_at"), f"{context}.captured_at"),
    )


def _decode_documents(
    value: object,
    case: MatterCase,
) -> dict[int, tuple[bytes, SourceReference]]:
    if not isinstance(value, list):
        raise ValueError("Runtime request documents was not a list")
    known = {attachment.attachment_id: attachment for attachment in case.unique_attachments()}
    output: dict[int, tuple[bytes, SourceReference]] = {}
    for index, raw in enumerate(value):
        item = _object(raw, f"documents[{index}]")
        attachment_id = _integer(item.get("attachment_id"), f"documents[{index}].attachment_id")
        if attachment_id not in known:
            raise ValueError(f"Runtime document {attachment_id} was not part of the case")
        if attachment_id in output:
            raise ValueError(f"Runtime document {attachment_id} was supplied twice")
        encoded = _text(item.get("content_base64"), f"documents[{index}].content_base64")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError(f"Runtime document {attachment_id} was not valid base64") from error
        expected_hash = _text(
            item.get("content_sha256"), f"documents[{index}].content_sha256"
        )
        actual_hash = sha256(content).hexdigest()
        if actual_hash != expected_hash:
            raise ValueError(f"Runtime document {attachment_id} failed its SHA-256 check")
        known_hash = known[attachment_id].content_hash
        if known_hash is not None and known_hash != actual_hash:
            raise ValueError(f"Runtime document {attachment_id} did not match the case record")
        output[attachment_id] = (content, _source(item.get("source"), f"documents[{index}].source"))
    return output


def context_from_request(
    payload: object,
    models_path: Path,
    working_directory: Path,
) -> InvestigationContext:
    root = _object(payload, "root")
    case = case_from_structural_payload(root.get("case"), working_directory)
    request_city = _text(root.get("city"), "city")
    request_matter_id = _integer(root.get("matter_id"), "matter_id")
    if request_city != case.city or request_matter_id != case.matter_id:
        raise ValueError("Runtime request identity did not match the supplied case")
    captures = _decode_documents(root.get("documents"), case)
    presentation_config = load_presentation_config(models_path.with_name("presentation.yaml"))
    comparisons = compare_all_appearances(case, presentation_config).comparisons
    return InvestigationContext(
        case=case,
        evidence_root=working_directory,
        models=load_model_settings(models_path),
        document_captures=captures,
        presentation_comparison=comparisons[-1].as_json() if comparisons else None,
    )
