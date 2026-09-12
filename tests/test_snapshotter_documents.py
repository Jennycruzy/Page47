from __future__ import annotations

from page47.snapshotter.http import FetchResult
from page47.snapshotter.runner import response_is_pdf


def response(body: bytes, content_type: str) -> FetchResult:
    return FetchResult(
        target="attachment:1",
        url="https://records.example/document",
        captured_at="2026-09-12T06:00:00Z",
        status=200,
        headers={"content-type": content_type},
        body=body,
        error_type=None,
        error=None,
        not_modified=False,
    )


def test_pdf_detection_uses_file_signature_not_server_label() -> None:
    assert response_is_pdf(response(b"%PDF-1.7\ncontent", "application/octet-stream"))


def test_dynamic_html_is_not_accepted_as_a_document() -> None:
    assert not response_is_pdf(
        response(b"<!doctype html><title>City Council</title>", "text/html")
    )
