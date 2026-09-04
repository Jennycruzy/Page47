# Phase 1 audit — snapshotter

Status: complete for Seattle, with the source's recorded non-PDF failures retained.

## Evidence

- `src/page47/snapshotter/` contains the validated city loader, conditional HTTP client, append-only store, and capture runner.
- `config/cities/seattle.yaml` records the client, nine bodies observed in the live response, page settings, detail switches, field names, and storage location. The four integer detail switches were verified against the cached official API help response before this code was used.
- `deploy/run_snapshotter.sh` runs the real capture on Lightsail with a non-overlapping file lock. `deploy/cron/page47-snapshotter` is installed in the `ubuntu` crontab as `*/15 * * * *`; `systemctl is-active cron` returned `active`.
- The wrapper passed `sh -n`, `/usr/bin/flock` is executable, and the scheduled job wrote a successful run at `2026-09-04T18:42:17.434262Z` UTC.
- The first live attempt recorded eleven HTTP 406 responses for DOC/DOCX links. The client then used the configured `Accept: */*` value. The next run at `2026-09-04T18:21:13.818130Z` returned no issues and captured the eleven previously failing documents.
- The final clean run at `2026-09-04T18:32:49.459134Z` selected five upcoming meetings, reused five agendas and thirty attachments, observed zero changes, and reported no issues. The scheduled run at `2026-09-04T19:00:01.316461Z` found one changed event response, saved it as a new immutable row, and still reported no presentation-field or document change.
- The remote store currently contains `72` immutable manifest rows, `62` content-addressed bodies, and `7` run records. Its current disk use is `68M` on the 40 GB Lightsail instance. The incremental storage cost is included in the selected fixed-size instance; a separate object-storage price has not been claimed.
- Before the deliberate repeat run the manifest had `71` rows. After it, the manifest still had `71` rows; the run reused all thirty attachments and added no changes. This proves the same stored observation is not written twice.
- `tests/test_snapshotter_store.py` replays a recorded real Legistar detail response and applies a permitted synthetic change to a stored copy. `tests/test_snapshotter_replay.py` replays the recorded response into the configured item collection. `tests/test_snapshotter_config.py` checks the live-derived city configuration. The suite passed with `4` tests.
- Python 3.12 `mypy --strict` passed for `9` source files, and `ruff check` passed for the source and command wrappers on Lightsail.

## Gaps

- Several source documents are DOC or DOCX rather than PDF. The server initially rejected the narrower content request with HTTP 406; the successful retry is stored as evidence. A later document reader must support these formats or report them as unavailable.
- Legistar event responses did not provide ETag values in the preflight. The snapshotter sends validators whenever the source supplies them and always compares SHA-256 content when a new response arrives. API pages without validators must still be checked on each scheduled run.
- The current store is append-only filesystem evidence on the Lightsail instance. Durable backup and object-storage lifecycle policy are still deployment work.
- No document text extraction has been attempted yet. The snapshotter preserves bytes and source metadata only.

## Blockers

- The AWS role still cannot list Bedrock models or AgentCore runtimes, so no model-dependent work is enabled.
- Seattle terms-of-use review remains a human task before treating the schedule as production coverage.

## Exit criteria

The selected bodies are being captured on Lightsail every fifteen minutes. Event responses, agenda files, and attachment bytes are stored with capture time, source URL, response hash, content hash where available, and HTTP validators. A repeat run adds no duplicate manifest rows; a changed stored copy is detected by a passing test; and every source failure is retained in the run record. The store is ready for record backfill while the AWS and terms blockers remain visible.
