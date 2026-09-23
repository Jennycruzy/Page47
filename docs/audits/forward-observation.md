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

## Live scan — 23 September 2026

A read-only scan of the VPS records found three qualifying Seattle candidates
and no Denver candidates. Seattle reported `forward_positive_case_found` after
checking 8,476 matters and skipping 57 orphaned appearances; its evidence
integrity root was
`cf46e4ab8b1ec77220218643bee393afc9ce66a5fce1ab1fea52e526329bd4b4`. Denver
reported `awaiting_real_transition` after checking 18 matters and skipping 76
orphaned appearances; its integrity root was
`df923e39b946d04eaad4f1ea9c86510cb3a0fd874df9dccc1e4ca8c2f572b5d2`.

One named Seattle candidate is matter `17316`, an ordinance amending the
Seattle Comprehensive Plan as part of the 2026 annual amendment process. The
Page 47 comparator labels the transition `less_clear` between event items
`125807` and `126048`. Its evidence links carry distinct capture keys,
response hashes, ordered capture times, and scheduled collector-run IDs:

| Captured state | Capture key | Captured at (UTC) | Collector run | Response SHA-256 | Source |
|---|---|---|---|---|---|
| Earlier committee agenda | `5e82deebbde0c5941dfd660f89d1e8b64f0d462c6ed34736eb13bac31e9ac5d9` | `2026-09-15T20:31:32.233538Z` | `2026-09-15T20:30:10.356465Z` | `5b39f707a5afdf0a73d0306d1f3b03c4374fb09b490b8e32a60a8893d6dfafc5` | [Seattle Land Use and Sustainability Committee agenda](https://legistar2.granicus.com/seattle/meetings/2026/9/6887_A_Land_Use_and_Sustainability_Committee_26-09-16_Committee_Agenda.pdf) |
| Later City Council agenda | `5f724c1b7613f49c2aad02e4256153db7ea0801ced982442627c8c7748378828` | `2026-09-22T10:31:11.010299Z` | `2026-09-22T10:30:15.381224Z` | `705862e690f7a3a815c388bdaa546f2f822d0f73143df1ab0b3492aa1ae373c0` | [Seattle City Council full meeting agenda](https://legistar2.granicus.com/seattle/meetings/2026/9/6894_A_City_Council_26-09-22_Full_Council_Meeting_Agenda.pdf) |

This establishes a Page 47 forward-observed transition. It does not yet
establish a resident-facing finding: at the time of the scan, matter `17316`
had no saved investigation or finding and no notification outcome. Investigate
this matter and retain the resulting run and finding before claiming the full
watch-to-finding path.
