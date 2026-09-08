# Denver attachment coverage follow-up

Date: 8 September 2026.

The initial historical Denver attachment capture produced 1,024 manifest rows
covering 473 attachment records. Four attachment URLs returned HTTP 404 during
that run. A follow-up on 8 September 2026 re-fetched all four URLs; each now
returns HTTP 200. The latest capture for every one of the 473 attachment IDs is
therefore HTTP 200, while the four earlier 404 responses remain preserved in
the append-only manifest.

Evidence hashes from the Lightsail store:

- `runtime/evidence/denver/manifest.jsonl` —
  `b9269037900cfff652e715e6bfe9afe4df551192c83279d239441efb9c678b1f`
- `runtime/records/denver.sqlite3` —
  `4fd4333378504788bdcb413d6c11b9c09419d46b8bbde8c0ebb2eba937308e07`

## HTTP 404 records

These initial failures are preserved as explicit failed captures rather than
being deleted or treated as missing data:

| Attachment | Matter | Captured | Source |
|---:|---:|---|---|
| 188353 | 56381 | 2026-09-07T01:07:12.839280Z | [DOCX attachment](https://denver.legistar1.com/denver/attachments/4f3d1230-dda7-450c-8c3a-930206a7cec5.docx) |
| 188535 | 56280 | 2026-09-07T01:07:13.280025Z | [PDF attachment](https://denver.legistar1.com/denver/attachments/5ec49ae9-23e2-4520-a572-9b2ba2de663b.pdf) |
| 188568 | 56327 | 2026-09-07T01:07:13.725458Z | [DOCX attachment](https://denver.legistar1.com/denver/attachments/3c55d8ba-43cb-4ccd-a770-94c04178a2d4.docx) |
| 189770 | 56603 | 2026-09-07T01:10:06.005734Z | [PDF attachment](https://denver.legistar1.com/denver/attachments/88d7cf94-f611-49b3-8fbd-1f9d7de74b3d.pdf) |

The stored response status for each is 404, with no content hash. The public
record still retains the attachment metadata and source URL.

## Recovery captures

The follow-up captured new bodies for all four URLs. The two PDFs were then
triaged and extracted with the configured document reader:

| Attachment | Follow-up capture | Content SHA-256 | Reading | Extraction |
|---:|---|---|---|---|
| 188353 | 2026-09-08T10:19:36.051990Z | `cc1f6fa2e6f5c5fb48fa0af4b72b2e732f47fa9eced1fdbe568d29bf390e7dc3` | non-PDF | not applicable |
| 188535 | 2026-09-08T10:19:36.798855Z | `a050fc3d5a90d746e2eceaedf4c60097e7ba1be2bee4f62f79ca195ab4038c44` | candidate, 1 page | read |
| 188568 | 2026-09-08T10:19:37.652972Z | `1b0f8b7015230b8c188697def6f61bf96f55c7fa2e8922e39a1aa956b3d9e576` | non-PDF | not applicable |
| 189770 | 2026-09-08T10:19:38.301453Z | `9131eb16c10a5ba4524f2cd2d8e0cb9c8a19a751835058365e58736e2072ae89` | candidate, 1 page | read |

## Unreadable PDF

Attachment `191179` belongs to the captured Denver record and points to the
[stored source PDF](https://denver.legistar1.com/denver/attachments/7ed93406-85ac-437a-8dcd-73e4deefcc0b.pdf).
Its reading result is:

- observed: `2026-09-07T01:12:13.634576Z`;
- content SHA-256: `30ab44201519815fe29249a9a2a087aa7cc2565651494fba4a9ef5b2de90a67e`;
- page count: `0`; and
- reason: `PdfStreamError: Stream has ended unexpectedly`.

## Reader coverage

The current PDF reader has a stored result for all 270 successful attachment
URLs whose names identify them as PDFs:

- 259 `candidate` readings;
- 10 `absent` readings where no configured reference was found; and
- 1 `unreadable` reading, recorded above.

The other 203 successful attachment URLs are non-PDF records. They remain
captured, but the current PDF reader does not claim to have read them. No
Denver comparison or completeness percentage is published from this audit.
