# Phase 2 audit — record model and history

Status: complete for the selected Seattle bodies. One failed network attempt is retained as evidence and is listed below; the subsequent retry reached the end of both public listings.

## Evidence

- `src/page47/records/store.py` creates the SQLite record store. It has tables for events, matters, appearances, attachments, the attachment-to-appearance relationship, raw captures, parse failures, and collection runs.
- `src/page47/records/runner.py` reads the configured API fields, writes one appearance for each returned event item, preserves the integer consent value exactly as returned, and records a source URL and capture time for every present stored field. It does not interpret the consent value.
- `config/cities/seattle.yaml` records the verified field names and the collection bounds: 100 event pages, 250 matter pages, 10,000 detail requests, and a requirement for twenty matters with at least three appearances each. These are configuration values, not source assumptions.
- The first wide collection command was:

  ```text
  .venv/bin/python scripts/backfill.py --config config/cities/seattle.yaml --database runtime/records/seattle.sqlite3 --evidence-root runtime/evidence/seattle
  ```

- The first wide read reached event history but received no HTTP status while requesting matter page 74. That attempt is stored as `matters-page:74` with response hash `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` and error text `HTTP status None did not provide a usable JSON response`.
- The retry command started at page 74 and reused the meeting records already collected:

  ```text
  .venv/bin/python scripts/backfill.py --config config/cities/seattle.yaml --database runtime/records/seattle.sqlite3 --evidence-root runtime/evidence/seattle --matter-start-page 74 --matters-only
  ```

- The completed retry reported `13,750` matters, `1,332` watched meetings, `24,047` appearances, `25,640` attachment records, `51,969` attachment-to-appearance rows, `1,511` stored captures, and `1` retained failed attempt. The event date range is `2015-02-09` through `2026-09-11`.
- The listing reached its end at `40` event pages and `138` matter pages. There were `0` appearance references to a matter missing from the normalized matter table.
- The database reported `81` matters with at least three appearances, exceeding the required twenty.
- The source-coverage check returned zero rows without a source reference for every table checked:

  ```text
  events rows 1332 rows_without_source_for_present_fields 0
  matters rows 13750 rows_without_source_for_present_fields 0
  appearances rows 24047 rows_without_source_for_present_fields 0
  attachments rows 25640 rows_without_source_for_present_fields 0
  appearance_attachments rows 51969 rows_without_source_for_present_fields 0
  ```

- The structural fingerprint was `c662582bc520bb43cea085aa1147c05da6cbb83597ca634c6d6763d8d7c9080f`. Computing it twice over the stored rows returned the same value.
- The normalized database is on Lightsail at `/home/ubuntu/page47-preflight/runtime/records/seattle.sqlite3`; the evidence is at `/home/ubuntu/page47-preflight/runtime/evidence/seattle`. The database is intentionally not copied into the repository because the live file is hundreds of megabytes and remains an operational record store.
- The recorded-response suite now has `7` passing tests. `ruff check` passed, and strict mypy passed across `12` source files in the Python 3.12 environment.

## Gaps

- The first record store is SQLite on Lightsail. The deployment specification calls for PostgreSQL; a PostgreSQL-backed deployment or migration is still required before the public console is called complete.
- Only `30` of the `25,640` attachment rows have a content hash at this point. Those hashes come from the running snapshotter's captured documents. Historical attachment metadata is preserved, but a document is not claimed to have been captured when it was not.
- The historical boundary is the oldest public Seattle record reached by the API listing, not a claim that older or removed records never existed.
- The API can expose only records marked public and viewable on the city's site. It cannot restore an item or document that was never published or was removed before capture began.

## Blockers

- Consent placement has not been used. The raw `EventItemConsent` integers are stored, but a meeting PDF must be compared with its event items and the Seattle mapping must be confirmed by a human before any later finding depends on it.
- Terms-of-use review for Seattle remains a human task.
- The AWS role still cannot list Bedrock models or AgentCore runtimes, so model-dependent work remains disabled.

## Exit criteria

The selected Seattle bodies have a repeatable historical record from the oldest public listing reached through the current API. Matters, meetings, appearances, and attachment relationships are stored with field-level source references. Failed reads are itemized, the required repeated-matter count is met, and the stored structural fingerprint is stable. The next human decision is consent calibration; no consent-based code has been enabled.
