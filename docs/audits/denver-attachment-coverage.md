# Denver attachment coverage follow-up

Date: 8 September 2026.

The historical Denver attachment capture produced 1,024 manifest rows covering
473 attachment records. At the time of this audit, 469 attachment downloads
returned HTTP 200 and four returned HTTP 404. The manifest and normalized
database were not modified while this audit was prepared.

Evidence hashes from the Lightsail store:

- `runtime/evidence/denver/manifest.jsonl` —
  `674127ff1414d1befb464c1abe90e22206c4ffe6eae29f2249061dd5a934bf7b`
- `runtime/records/denver.sqlite3` —
  `99793bdba38c92946814c16cf4044c2a8d504fed90eda3698e887b974bbca013`

## HTTP 404 records

These are preserved as explicit failed captures rather than being treated as
missing data:

| Attachment | Matter | Captured | Source |
|---:|---:|---|---|
| 188353 | 56381 | 2026-09-07T01:07:12.839280Z | [DOCX attachment](https://denver.legistar1.com/denver/attachments/4f3d1230-dda7-450c-8c3a-930206a7cec5.docx) |
| 188535 | 56280 | 2026-09-07T01:07:13.280025Z | [PDF attachment](https://denver.legistar1.com/denver/attachments/5ec49ae9-23e2-4520-a572-9b2ba2de663b.pdf) |
| 188568 | 56327 | 2026-09-07T01:07:13.725458Z | [DOCX attachment](https://denver.legistar1.com/denver/attachments/3c55d8ba-43cb-4ccd-a770-94c04178a2d4.docx) |
| 189770 | 56603 | 2026-09-07T01:10:06.005734Z | [PDF attachment](https://denver.legistar1.com/denver/attachments/88d7cf94-f611-49b3-8fbd-1f9d7de74b3d.pdf) |

The stored response status for each is 404, with no content hash. The public
record still retains the attachment metadata and source URL.

## Unreadable PDF

Attachment `191179` belongs to the captured Denver record and points to the
[stored source PDF](https://denver.legistar1.com/denver/attachments/7ed93406-85ac-437a-8dcd-73e4deefcc0b.pdf).
Its reading result is:

- observed: `2026-09-07T01:12:13.634576Z`;
- content SHA-256: `30ab44201519815fe29249a9a2a087aa7cc2565651494fba4a9ef5b2de90a67e`;
- page count: `0`; and
- reason: `PdfStreamError: Stream has ended unexpectedly`.

## Reader coverage

The current PDF reader has a stored result for all 268 successful attachment
URLs whose names identify them as PDFs:

- 257 `candidate` readings;
- 10 `absent` readings where no configured reference was found; and
- 1 `unreadable` reading, recorded above.

The other 201 successful attachment URLs are non-PDF records. They remain
captured, but the current reader does not claim to have read them. No Denver
comparison or completeness percentage is published from this audit.
