# Independent evaluation review

Date: 12 September 2026.

This review checks the generated evaluation artifacts and their deterministic
invariants. It does not reopen or relabel the 30 historical cases whose human
review is already complete.

## Review scope

The checked-in exports were validated with:

```sh
.venv/bin/python scripts/validate_evaluation_set.py \
  --input docs/evaluation-set.json
.venv/bin/python scripts/validate_comparison.py \
  --input docs/comparison-results.json
```

The evaluation export passed with 100 matters, 30 gold items, and 30 completed
labels. Every gold label is `cannot_determine`, matching the completed human
audit. No gold case or label was changed during this review.

The four-arm comparison passed with 100 cases and 400 arm results. The schema 2
artifact records the code revision `3ef76ece820df4bbf71c0beb0c7e31d8033af108`
and SHA-256 fingerprints for the manifest, presentation configuration, SQLite
database, evidence manifest, evidence chain, and matter-ID list. An independent
per-row check confirmed:

- each arm has exactly 100 results;
- all four arms are present once per case;
- every result has a non-empty reason and valid HTTP(S) evidence fields;
- all four arms surfaced zero cases in this real Seattle export; and
- Page 47 returned `cannot_determine` for all 100 cases, including all 30 gold
  cases, producing zero historical overclaims.

The new diagnostics explain the abstentions: 623 adjacent pairs had comparable
titles, but all 623 titles were exact matches; no pair had comparable agenda
placement; no stored attachment in the cohort had readable extracted substance;
and publication timing remained unavailable. Meeting-date ordering was trusted
for the recorded sequence. These are evidence-coverage results, not directional
accuracy claims.

The real comparison remains descriptive. Because the 30 gold labels contain no
`yes` or `no` cases, no directional accuracy percentage is published.

## Controlled directional fixture

The controlled run contains 28 frozen transformations. The independent output
check found:

- Page 47 comparator states: 28/28 correct;
- keyword-arm surface expectations: 28/28 correct;
- directional reversal pairs: 2/2 correct;
- Page 47 comparator misses: none;
- Skeptic annotations: 1 reject, 2 abstain, and 25 not applicable.

The deterministic fixture runner does not invoke Bedrock or the Skeptic. The
Skeptic counts are therefore review targets, not model-accuracy measurements.
The fixture is evidence that the comparator handles direction, reversal,
mixed states, abstention, replacement hashes, and adversarial document text;
it is not a real-world accuracy claim.

## Verification gates

The repository checks completed successfully after the artifact review:

```text
53 tests passed
ruff: All checks passed!
mypy --strict: Success: no issues found in 48 source files
```

The generated JSON artifacts intentionally retain `status:
"review_required"`. That status prevents their descriptive results from being
mistaken for a published real-world accuracy claim. The independent output
review is complete; no unsupported benchmark percentage should be added.
