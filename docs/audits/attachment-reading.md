# Captured attachment reading

## Evidence

`scripts/read_captured_attachments.py` was run against the immutable Seattle evidence store and `runtime/records/seattle.sqlite3` on Lightsail.

- Twenty PDF attachments were marked `candidate` because configured numbers, units, dates, or parcel references occurred on pages containing configured public-record terms.
- Two PDF attachments were marked `absent`: no configured reference was found in their readable text.
- No PDF was marked unreadable in this run.
- A second run read zero files and reused 23 stored captures by content hash.

Each result keeps the source URL, capture time, PDF page, character location in extracted page text, and an excerpt. For example, attachment `49284` is a two-page public-hearing notice. It has a page-1 reference to `September 11, 2026` and a page-2 reference to the written-comment deadline. The primary PDF is [the City of Seattle notice](https://legistar2.granicus.com/seattle/attachments/5acd0a72-89a6-4b25-b000-bd8c6ee5cd14.pdf).

## Limits

This reading step identifies documents worth document-specific review; it does not state that a number changed, what a provision means, or why a document was written. Those statements require the later document-specific reading stage and its page evidence.

Page 47 does not determine why these changes were made.
