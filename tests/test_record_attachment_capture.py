from __future__ import annotations

from page47.records.store import StoredAttachmentSource
from scripts.capture_record_attachments import _fetchable


def test_record_attachment_capture_only_accepts_configured_host() -> None:
    attachment = StoredAttachmentSource(
        attachment_id=12,
        matter_id=34,
        name="Agenda",
        url="https://denver.legistar1.com/denver/attachments/agenda.pdf",
        version="1",
        last_modified_utc="2026-09-01T00:00:00Z",
    )

    assert _fetchable(attachment, ("denver.legistar1.com",))
    assert not _fetchable(attachment, ("legistar2.granicus.com",))
