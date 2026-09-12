# Historical challenge cohort review record

This record describes the completed review of real Seattle records retained by
Page 47. It is a challenge cohort, not a prevalence sample. Cases were selected
from mechanical record-change signals rather than from Page 47's classification
or published result.

## What is included

The corrected packet contains 37 matters: 5 candidate matters and 32 controls.
Each matter has one fixed adjacent appearance pair and one matter-level label.
Three recurring container records from the previously reviewed packet were
removed before import:

- 15756
- 16819
- 16820

The two supplied human review files were retained as Reviewer A and Reviewer B.
Both reviewers supplied a label, reason, and evidence reference for every
retained matter. Where the labels matched, that label is recorded as the
adjudicated result. No case was sent back for relabelling.

The original packet exposed selection information. The corrected public packet
does not expose that information in its case payloads, and the correction is
recorded here rather than being described as a blind re-review. This keeps the
record accurate while preserving the independent work already completed.

## Labels

Exactly one of these five labels is used for each matter:

- `clearer`: supported presentation became more representative or visible;
- `less_clear`: supported presentation became less representative or visible;
- `mixed`: supported dimensions moved in opposite directions;
- `unchanged`: comparable presentation dimensions stayed neutral;
- `cannot_determine`: the retained public record is insufficient to establish a
  direction.

Reviewers were asked not to label motive, legality, policy merits, or whether
anyone acted improperly. A raw title, placement, or attachment change is a
reason to inspect a case, not a directional label by itself.

## Evidence rule

Each completed review retains at least one primary source URL and capture time,
with a PDF page number when the judgment relies on a page. The importer maps
the evidence references in the supplied review files to the matching captured
primary records in each retained case.

## Validation and scoring

Validate the completed packet with:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge.py \
  --input docs/historical-challenge-cohort.json \
  --require-labels
```

Validate the public answer key with:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge_answer_key.py \
  --input docs/historical-challenge-answer-key.json \
  --packet docs/historical-challenge-cohort.json
```

Score the current comparator against the pinned records with:

```sh
PYTHONPATH=src python scripts/score_historical_challenge.py \
  --cohort docs/historical-challenge-cohort.json \
  --answer-key docs/historical-challenge-answer-key.json \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output docs/historical-challenge-results.json \
  --code-revision <scoring-code-revision>
```

The scorer reports a five-way confusion matrix, per-label precision and recall,
surfaced-positive precision, abstention correctness, reviewer agreement,
evidence coverage, and provenance validity. Results from this cohort must be
described as challenge-cohort results, not representative Seattle accuracy.
