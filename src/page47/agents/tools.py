"""Narrow, typed tools used by the investigation agents."""

from __future__ import annotations

import json
from io import BytesIO

from pypdf import PdfReader
from strands import ToolContext, tool

from page47.analysis.case import InvestigationContext


def _context(tool_context: ToolContext) -> InvestigationContext:
    value = tool_context.invocation_state.get("page47_context")
    if not isinstance(value, InvestigationContext):
        raise ValueError("Page 47 investigation context was missing")
    return value


@tool(context=True)
def read_record(tool_context: ToolContext) -> str:
    """Return the stored matter history and public-record source details."""

    context = _context(tool_context)
    return json.dumps(context.case.structural_payload(), sort_keys=True)


@tool(context=True)
def read_presentation_record(tool_context: ToolContext) -> str:
    """Return only structural presentation details for the Process reader."""

    context = _context(tool_context)
    appearances = []
    for appearance in context.case.appearances:
        value = appearance.as_json()
        raw_attachments = value["attachments"]
        if not isinstance(raw_attachments, list):
            raise ValueError("Matter appearance attachments were not a list")
        value["attachments"] = [
            {
                "attachment_id": item["attachment_id"],
                "name": item["name"],
                "version": item["version"],
                "last_modified_utc": item["last_modified_utc"],
                "source": item["source"],
            }
            for item in raw_attachments
            if isinstance(item, dict)
        ]
        appearances.append(value)
    payload = {
        "city": context.case.city,
        "matter_id": context.case.matter_id,
        "matter_source": context.case.matter.source.as_json(),
        "appearances": appearances,
    }
    return json.dumps(payload, sort_keys=True)


@tool(context=True)
def read_presentation_comparison(tool_context: ToolContext) -> str:
    """Return Page 47's deterministic comparison for the Skeptic to review."""

    context = _context(tool_context)
    comparison = context.presentation_comparison
    if comparison is None:
        return json.dumps({"state": "cannot_determine", "observations": []})
    raw_observations = comparison.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("Page 47 presentation comparison observations were invalid")
    observations: list[dict[str, object]] = []
    for item in raw_observations:
        if not isinstance(item, dict):
            raise ValueError("Page 47 presentation comparison observation was invalid")
        key = item.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("Page 47 presentation comparison observation had no key")
        observations.append({"observation_id": f"record-{key}", **item})
    return json.dumps(
        {
            "state": comparison.get("state"),
            "previous_event_item_id": comparison.get("previous_event_item_id"),
            "current_event_item_id": comparison.get("current_event_item_id"),
            "observations": observations,
        },
        sort_keys=True,
    )


@tool(context=True)
def list_attachment_documents(tool_context: ToolContext) -> str:
    """List captured document IDs and page counts without structural fields."""

    context = _context(tool_context)
    documents = []
    for attachment in context.case.unique_attachments():
        capture = (
            context.document_captures.get(attachment.attachment_id)
            if context.document_captures is not None
            else None
        )
        if capture is None:
            capture = attachment.document_capture()
        if capture is None:
            continue
        _, source = capture
        documents.append(
            {
                "attachment_id": attachment.attachment_id,
                "document_name": attachment.name,
                "page_count": attachment.page_count,
                "reading_status": attachment.reading_status,
                "source": source.as_json(),
            }
        )
    return json.dumps({"documents": documents}, sort_keys=True)


@tool(context=True)
def read_attachment_document(attachment_id: int, tool_context: ToolContext) -> str:
    """Read captured PDF pages for one attachment ID from the investigation."""

    context = _context(tool_context)
    attachment = next(
        (
            item
            for item in context.case.unique_attachments()
            if item.attachment_id == attachment_id
        ),
        None,
    )
    if attachment is None:
        raise ValueError(f"Attachment {attachment_id} is not part of this matter")
    capture = (
        context.document_captures.get(attachment_id)
        if context.document_captures is not None
        else None
    )
    if capture is None:
        capture = attachment.document_capture()
    if capture is None:
        raise ValueError(f"No captured PDF bytes are available for attachment {attachment_id}")
    pdf_bytes, source = capture
    reader = PdfReader(BytesIO(pdf_bytes))
    pages: list[dict[str, object]] = []
    for page_number, page in enumerate(reader.pages, start=1):
        if page_number > context.models.max_document_pages:
            break
        text = page.extract_text()
        if not isinstance(text, str) or not text.strip():
            continue
        pages.append(
            {
                "page_number": page_number,
                "text": text[: context.models.max_page_characters],
            }
        )
    return json.dumps(
        {
            "attachment_id": attachment_id,
            "source": source.as_json(),
            "pages": pages,
        },
        sort_keys=True,
    )
