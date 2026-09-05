"""Run document-specific page reading only after text triage selects a PDF."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Literal, Self, cast

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator
from strands import Agent
from strands.models import BedrockModel
from strands.types.content import ContentBlock

from page47.models.config import ModelSettings
from page47.records.store import SourceReference
from page47.substance.reader import AttachmentReading

ExtractionStatus = Literal["read", "absent", "unreadable", "failed"]


class BoundingBox(BaseModel):
    left: float = Field(ge=0.0, le=1.0)
    top: float = Field(ge=0.0, le=1.0)
    right: float = Field(ge=0.0, le=1.0)
    bottom: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def has_ordered_edges(self) -> Self:
        if self.right < self.left or self.bottom < self.top:
            raise ValueError("Bounding box edges must be ordered")
        return self


class DocumentChange(BaseModel):
    subject: str = Field(min_length=1)
    before: str | None = Field(default=None, min_length=1)
    after: str | None = Field(default=None, min_length=1)
    value: str | None = Field(default=None, min_length=1)
    unit: str | None = None
    page_number: int = Field(ge=1)
    bounding_box: BoundingBox
    excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def has_value_or_explicit_change(self) -> Self:
        has_before = self.before is not None
        has_after = self.after is not None
        has_value = self.value is not None
        if has_before != has_after:
            raise ValueError("before and after must be supplied together")
        if not has_value and not (has_before and has_after):
            raise ValueError("A provision needs a stated value or an explicit change")
        return self


class DocumentChangeReport(BaseModel):
    provisions: list[DocumentChange]
    no_substantive_change: bool
    note: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class ExtractedDocumentChange:
    subject: str
    before: str | None
    after: str | None
    value: str | None
    unit: str | None
    page_number: int
    bounding_box: BoundingBox
    excerpt: str
    source: SourceReference

    def as_json(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "before": self.before,
            "after": self.after,
            "value": self.value,
            "unit": self.unit,
            "page_number": self.page_number,
            "bounding_box": self.bounding_box.model_dump(mode="json"),
            "excerpt": self.excerpt,
            "source": self.source.as_json(),
        }


@dataclass(frozen=True, slots=True)
class DocumentExtraction:
    attachment_id: int
    content_hash: str
    status: ExtractionStatus
    changes: tuple[ExtractedDocumentChange, ...]
    reason: str
    source: SourceReference
    model_id: str


def _render_page(pdf_bytes: bytes, page_number: int, scale: float) -> bytes:
    document = pdfium.PdfDocument(pdf_bytes)
    try:
        page_count = len(document)
        if page_number < 1 or page_number > page_count:
            raise ValueError(f"Requested page {page_number} outside PDF page count {page_count}")
        page = document.get_page(page_number - 1)
        try:
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil()
                output = BytesIO()
                image.save(output, format="PNG")
                return output.getvalue()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()


def _candidate_pages(reading: AttachmentReading, max_pages: int) -> tuple[int, ...]:
    pages = tuple(dict.fromkeys(reference.page_number for reference in reading.references))
    if pages:
        return pages[:max_pages]
    return tuple(range(1, min(reading.page_count, max_pages) + 1))


@lru_cache(maxsize=1)
def _agent(settings: ModelSettings) -> Agent:
    model = BedrockModel(
        model_id=settings.document.model_id,
        region_name=settings.region,
        temperature=settings.temperature,
        max_tokens=settings.document_max_output_tokens,
    )
    return Agent(
        model=model,
        name="document_reader",
        callback_handler=None,
        system_prompt=(
            "Read the supplied public-record PDF page images as one attachment, not as a "
            "before-and-after pair. Extract concrete provisions that could matter to a resident: "
            "numbers with units, dollar amounts, dates, parcel or street references, permissions "
            "granted or removed, and other specific limits or obligations. If the page explicitly "
            "states a change such as 35 feet to 75 feet, fill before and after. Otherwise record "
            "the stated current provision in value and leave before and after empty. Never invent "
            "a prior value, a current value, a location, or a reason. Every entry must include the "
            "supplied PDF page number, a normalized bounding box for the visible passage, and a "
            "short exact excerpt. Use the field named provisions for specific rules, quantities, "
            "dates, locations, or obligations found in the pages; do not use an empty result "
            "merely because this is not a before-and-after comparison. If no concrete provision "
            "is visible, "
            "return an empty provisions list and set no_substantive_change to true. Never infer "
            "purpose or motive."
        ),
        structured_output_model=DocumentChangeReport,
    )


def extract_document(
    attachment_id: int,
    content_hash: str,
    pdf_bytes: bytes,
    reading: AttachmentReading,
    source: SourceReference,
    settings: ModelSettings,
) -> DocumentExtraction:
    """Read candidate pages with the verified multimodal model."""

    if attachment_id < 1:
        raise ValueError("attachment_id must be positive")
    if not content_hash:
        raise ValueError("content_hash must not be empty")
    if reading.status != "candidate":
        return DocumentExtraction(
            attachment_id,
            content_hash,
            "absent",
            (),
            "Text triage did not identify a configured substantive reference.",
            source,
            settings.document.model_id,
        )
    pages = _candidate_pages(reading, settings.max_document_pages)
    if not pages:
        return DocumentExtraction(
            attachment_id,
            content_hash,
            "absent",
            (),
            "The candidate PDF had no readable pages to send for document-specific reading.",
            source,
            settings.document.model_id,
        )
    references_by_page: dict[int, list[str]] = {}
    for reference in reading.references:
        if reference.page_number in pages:
            references_by_page.setdefault(reference.page_number, []).append(reference.excerpt)
    content: list[dict[str, object]] = [
        {
            "text": (
                "The following page images belong to one public-record attachment. "
                "Page numbers are supplied in the labels. Report only what is visible."
            )
        }
    ]
    for page_number in pages:
        image_bytes = _render_page(pdf_bytes, page_number, settings.render_scale)
        content.append({"text": f"PDF page {page_number}."})
        excerpts = references_by_page.get(page_number, [])
        if excerpts:
            context = "\n".join(dict.fromkeys(excerpts))
            content.append(
                {
                    "text": (
                        "Text extracted from this page is provided only to help locate visible "
                        "words; verify every entry against the image:\n"
                        f"{context[:settings.max_page_characters]}"
                    )
                }
            )
        content.append({"image": {"format": "png", "source": {"bytes": image_bytes}}})
    result = _agent(settings)(cast(list[ContentBlock], content))
    structured = result.structured_output
    if not isinstance(structured, DocumentChangeReport):
        raise ValueError("Document reader returned no validated structured result")
    page_set = set(pages)
    for change in structured.provisions:
        if change.page_number not in page_set:
            raise ValueError(
                f"Document reader cited page {change.page_number} outside supplied pages"
            )
    normalized_changes: list[ExtractedDocumentChange] = []
    for change in structured.provisions:
        before = change.before
        after = change.after
        value = change.value
        if before is not None and after is not None and before.strip() == after.strip():
            value = after
            before = None
            after = None
        normalized_changes.append(
            ExtractedDocumentChange(
                subject=change.subject,
                before=before,
                after=after,
                value=value,
                unit=change.unit,
                page_number=change.page_number,
                bounding_box=change.bounding_box,
                excerpt=change.excerpt,
                source=source,
            )
        )
    changes = tuple(normalized_changes)
    status: ExtractionStatus = "absent" if not changes else "read"
    reason = structured.note
    return DocumentExtraction(
        attachment_id,
        content_hash,
        status,
        changes,
        reason,
        source,
        settings.document.model_id,
    )
