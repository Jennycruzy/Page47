# Four-arm comparison audit

Date: 13 September 2026.

The comparison was rerun over the checked-in 100-matter Seattle manifest with
the current comparator. The selected matter IDs and labels were unchanged. The
first 30 cases remain the completed historical evidence-sufficiency audit; all
30 are `cannot_determine`. The remaining 70 cases are intentionally unlabeled
and are reported as descriptive evidence coverage, not accuracy.

The run used the stored Seattle record database and evidence root. It recorded
the exact code revision and input fingerprints in the generated artifact:

```sh
.venv/bin/python scripts/run_comparison.py \
  --input docs/evaluation-set.json \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output docs/comparison-results.json \
  --code-revision 7b0cfab
```

The artifact is schema version 2 and passes
`scripts/validate_comparison.py`. It contains 400 arm results for 100 matters.
The input record includes the SHA-256 digests for the evaluation manifest,
presentation configuration, SQLite database, evidence manifest, evidence chain,
and matter-ID list, along with the evidence integrity root.

## Result

All four arms surfaced zero cases. Page 47 returned `cannot_determine` for all
100 matters, including all 30 historical gold cases. The historical abstention
audit therefore has zero Page 47 overclaims. No directional accuracy
percentage is published because the gold set contains no `clearer`,
`less_clear`, `mixed`, or `unchanged` labels.

The diagnostics explain the result rather than hiding it:

| Coverage signal | Result across the 100 matters |
| --- | ---: |
| Recorded appearances | 723 |
| Adjacent appearance pairs | 623 |
| Pairs with comparable titles | 623 |
| Pairs with a directional title signal | 0 |
| Pairs with comparable agenda placement | 0 |
| Readable captured attachments | 0 of 1,047 unique attachments |
| Attachments with retained substance anchors | 0 |
| Trustworthy publication timing | 0 pairs |
| Meeting-sequence chronology | Trusted for all 623 pairs |

The title dimension was comparable for every adjacent pair, but all 623 title
pairs were exact matches. Agenda placement was unavailable for every pair, and
the stored attachment set had no readable extracted substance for this cohort.
Timing remains intentionally unavailable because city last-modified fields do
not prove when material became public.

The resulting abstention coverage codes were:

| Code | Matters |
| --- | ---: |
| `placement_unavailable` | 100 |
| `substance_not_readable` | 100 |
| `timing_unavailable` | 100 |
| `no_directional_signal` | 100 |

These are separate causes, not a combined risk score. The comparator was not
made more aggressive after seeing the result.

## Four arms

- Keyword alerts flag explicit title or attachment-name lexical changes only.
- Search sees the latest public record and has no retained presentation history.
- Latest-document reading sees the latest document set and has no earlier comparison.
- Page 47 compares adjacent recorded appearances and abstains when the available
  dimensions are insufficient.

This artifact demonstrates a conservative evidence boundary on a random
historical cohort. It does not claim that Page 47 has directional accuracy on
real-world cases. The controlled directional fixture and the separately
labelled historical challenge cohort provide the complementary behavior check;
the challenge-cohort score is preserved in
[`docs/historical-challenge-results.json`](historical-challenge-results.json).

The generated four-arm comparison artifact retains `review_required` as its
schema status. That status is a machine-readable guard against treating this
descriptive random-cohort run as an accuracy benchmark. The independent review
above cites this exact artifact and its input fingerprints.
