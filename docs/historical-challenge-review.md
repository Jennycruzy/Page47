# Historical challenge cohort review

This artifact is a mechanically selected historical challenge cohort for Page
47. It is designed to test the detector on real stored records where a raw
record change is present, while keeping a control group that did not match any
selection rule.

The checked-in packet is
[`docs/historical-challenge-cohort.json`](historical-challenge-cohort.json).
It contains 40 Seattle matters:

- 7 candidates: all matters in the retained dataset that met the mechanical
  change rules;
- 33 controls: matters with at least two appearances where no candidate rule
  matched.

The candidate pool could not honestly support the originally suggested 35
candidate cases. The packet therefore includes every available candidate and
states the limitation in its selection metadata. The controls bring the cohort
to 40 cases; they must not be presented as additional positive cases.

## Selection boundary

The builder uses only raw stored record fields and the evidence manifest. It
does not import Page 47's comparator, read its output, or select cases because
they look alarming.

A matter enters the candidate pool when an adjacent pair has at least one of
these properties:

- title text changed;
- supported agenda placement changed between `regular` and `consent`;
- the attachment identity set changed;
- a retained attachment target has more than one successful captured content
  hash.

Controls have at least two recorded appearances and match none of those rules.
The selection seed is 47 and the source snapshot records the database hash,
evidence-chain hash, integrity root, candidate-pool hash, selected-ID hash, and
builder revision.

## Independent labelling

Do not open Page 47's comparison output while labelling. The packet contains no
comparator result, but the selection metadata is included for auditability. If
the strongest possible blind review is required, give each reviewer a copy with
`cohort_role`, `selection_reasons`, and `selected_pairs` removed while retaining
`case_id` and `case_payload`.

Two reviewers label every case independently. Each reviewer records:

- one state;
- one plain-language reason;
- at least one primary source URL and capture time;
- a PDF page number when the judgment relies on a page.

Use only these states:

- `clearer`: supported presentation became more representative or visible;
- `less_clear`: supported presentation became less representative or visible;
- `mixed`: supported dimensions moved in opposite directions;
- `unchanged`: comparable presentation dimensions stayed neutral;
- `cannot_determine`: the retained public record is insufficient to establish a
  direction.

Do not label motive, legality, policy merits, or whether anyone acted
improperly. A changed attachment or title is a reason to inspect a case, not a
directional label by itself.

After both labels are retained, adjudicate disagreements. Keep both original
labels, the adjudicated state, the evidence, and the reason. Never overwrite an
original reviewer label.

## Validation gates

Before review:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge.py \
  --input docs/historical-challenge-cohort.json
```

After all independent labels and adjudications are complete, change the packet
status to `labels_complete` and run:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge.py \
  --input docs/historical-challenge-cohort.json \
  --require-labels
```

Only then should a separate scoring script calculate a five-way confusion
matrix, per-state precision and recall, surfaced-positive precision,
abstention correctness, reviewer agreement, evidence coverage, and provenance
validity. Until that gate passes, the packet is a review input, not an
evaluation result.

Run the scoring gate with the same database and evidence root recorded in the
packet:

```sh
PYTHONPATH=src python scripts/score_historical_challenge.py \
  --cohort docs/historical-challenge-cohort.json \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output docs/historical-challenge-results.json \
  --code-revision <scoring-code-revision>
```

The scorer refuses to run if the labels are incomplete or if the database or
evidence chain no longer matches the packet's source snapshot. Its output stays
`review_required` until the results receive an independent check.

This is a mechanically selected challenge cohort, not a representative sample
of Seattle public records. Its purpose is to test behavior on real retained
transitions and to make the evidence boundary inspectable.
