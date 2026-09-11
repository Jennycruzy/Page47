# Forward-observed positive case

Page 47 does not manufacture a positive case from historical records. The
collector must capture an earlier public state and a later public state itself.
Only then can a directional comparison be labeled `Observed by Page 47`.

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
primary evidence links carrying two distinct Page 47 capture keys and capture
times. When that happens it becomes `forward_positive_case_found` and records
the matter, comparison, hashes already retained by the capture store, and the
evidence links ready for the normal investigation path.

This is intentionally a live operational result, not a fixture or a claim made
from two historical records that happen to be available today.
