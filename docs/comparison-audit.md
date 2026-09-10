# Four-arm comparison audit

Date: 10 September 2026.

The comparison was run over the checked-in 100-matter Seattle manifest without
changing its selected matters or labels. The first 30 cases remain the completed
historical evidence-sufficiency audit; all 30 are `cannot_determine`. The other
70 cases are intentionally unlabeled and are reported only as descriptive
coverage, not accuracy.

The host run used the stored Seattle record database and evidence root:

```sh
.venv/bin/python scripts/run_comparison.py \
  --input docs/evaluation-set.json \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output docs/comparison-results.json
```

The four arms were kept separate:

- Keyword alerts flag explicit title or attachment-name lexical changes only.
- Search sees the latest public record and has no retained presentation history.
- Latest-document reading sees the latest document set and has no earlier comparison.
- Page 47 compares adjacent recorded appearances and abstains when the available
  dimensions are insufficient.

The artifact contains 400 arm results for 100 cases and passes
`scripts/validate_comparison.py`. Page 47 abstained on all 100 cases, including
all 30 historical gold cases; the historical abstention audit has zero Page 47
overclaims. No directional accuracy percentage is published because the gold
set contains no `yes` or `no` cases.

This artifact is evidence that the abstention boundary is working. It is not a
claim that Page 47 wins a directional benchmark. A separate controlled
directional fixture set is required before publishing accuracy, reversal, mixed
case, or baseline-performance claims.

The generated per-case results remain `review_required` until every output and
any future controlled-evaluation miss has been checked.
