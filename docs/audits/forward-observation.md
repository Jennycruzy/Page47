# Forward-observed positive case

Page 47 does not manufacture a positive case from historical records. The
collector must capture an earlier public state and a later public state itself.
Only then can a directional comparison be labeled `Observed by Page 47`.
The production baseline is `2026-09-12T09:34:44Z`, immediately after the first
complete collector cycle carrying collector-run provenance and rejecting
non-PDF attachment responses. Captures before that boundary remain
`Reconstructed from public record` even when Page 47 retained their bytes.

The repository now includes a verifier for that exact condition:

```bash
PYTHONPATH=src python scripts/check_forward_observations.py \
  --city "Seattle, Washington" \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output /tmp/page47-forward-observation.json
```

The report is `awaiting_real_transition` until a directional comparison has
primary evidence links carrying two distinct Page 47 capture keys, ordered
capture times, and qualifying scheduled collector-run provenance after the
baseline. When that happens it becomes `forward_positive_case_found` and records
the matter, comparison, hashes already retained by the capture store, and the
evidence links ready for the normal investigation path.

This is intentionally a live operational result, not a fixture or a claim made
from two historical records that happen to be available today.

## Live operating note

The deployed collector is scheduled from the `ubuntu` crontab every fifteen
minutes. The corrected baseline run completed at `2026-09-12T09:34:44Z` with
no issues. It also skipped 11 successful HTTP responses whose bytes were not
PDFs instead of treating those changing web pages as document revisions. The
collector must remain running; a positive case
cannot be created by editing a database or by relabeling two historical
records.

Two apparent placement candidates discovered during hardening were rejected:
their supposed later states had actually been captured before their earlier
states. That reverse chronology is historical reconstruction, not a witnessed
transition. A recurring city-agenda HTML page was also rejected as an
attachment after its content type and PDF signature failed validation. These
cases show why hashes alone are not sufficient proof of a forward-observed
document change.

The verifier joins appearances to their stored matter rows before loading a
case. If an incomplete old appearance has no corresponding matter row, the
scan skips it and reports `skipped_orphan_matter_count` rather than stopping
the entire audit. That is a data-quality warning, not evidence of a forward
transition.

When the collector has recorded a real directional transition, run the check
on the host and retain its JSON output with the audit materials:

```bash
cd /home/ubuntu/page47-preflight
.venv/bin/python scripts/check_forward_observations.py \
  --city "Seattle, Washington" \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output /tmp/page47-forward-observation.json \
  --require
```

The returned candidate is ready for the normal investigation endpoint. Keep
the candidate's two capture keys, hashes, capture times, and source links with
the resulting investigation and finding. Until the report says
`forward_positive_case_found`, describe the real-data result as abstention or
awaiting observation.
