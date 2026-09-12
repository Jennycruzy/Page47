# Historical challenge cohort review

This is a blind review packet for real Seattle records retained by Page 47.
It tests whether the detector behaves correctly on historical transitions that
are mechanically selected from raw record changes, without using Page 47's
classification or output to choose cases.

## Reviewer materials

Use the [browser-friendly packet](historical-challenge/README.md), beginning
with its [compact index](historical-challenge/index.json). The complete
[canonical packet](historical-challenge-cohort.json) is preserved for download
and audit, but is too large for comfortable browser rendering.

The reviewer-facing packet contains 40 cases in a shuffled order. Every item
has the same fields: a case ID, city, matter ID, one fixed adjacent
`review_pair`, the complete retained case payload, and empty review slots. It
does not contain candidate/control roles, selection reasons, selected-pair
metadata, or comparator output. The individual case files contain the same
neutral fields.

The separate selection answer key is held outside the repository. Do not give
it to either reviewer before both independent labels are complete. It records
the candidate/control composition, exclusions, selection rules, selected raw
pairs, and source hashes needed for later scoring.

## What is being labelled

The unit is one matter-level judgment for the fixed adjacent pair shown in
`review_pair`. Review that pair against the complete case payload and the
retained primary evidence. Do not combine multiple transitions into one
judgment. The same unit applies to every case, including controls.

Use exactly one of these five states:

- `clearer`: supported presentation became more representative or visible;
- `less_clear`: supported presentation became less representative or visible;
- `mixed`: supported dimensions moved in opposite directions;
- `unchanged`: comparable presentation dimensions stayed neutral;
- `cannot_determine`: the retained public record is insufficient to establish a
  direction.

Do not label motive, legality, policy merits, or whether anyone acted
improperly. A raw title, placement, or attachment change is a reason to inspect
a case, not a directional label by itself.

## Reviewer record

Each reviewer records:

- one state;
- one plain-language reason;
- at least one primary source URL and capture time;
- a PDF page number when the judgment relies on a page.

Reviewer A and Reviewer B must work from separate copies and must not inspect
Page 47 comparator output or the withheld answer key. Keep their original
labels unchanged. After both are retained, adjudicate disagreements in a third
field with the evidence and reason for the decision.

## Validation

Before labelling, validate the neutral packet:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge.py \
  --input docs/historical-challenge-cohort.json
```

The validator rejects candidate/control fields, non-uniform item shapes,
missing review-pair fields, duplicate case IDs, and invalid review slots.

After both independent labels and adjudications are complete, set the packet
status to `labels_complete` and run:

```sh
PYTHONPATH=src python scripts/validate_historical_challenge.py \
  --input docs/historical-challenge-cohort.json \
  --require-labels
```

Score only with the withheld answer key generated alongside the packet and
kept outside the repository:

```sh
PYTHONPATH=src python scripts/score_historical_challenge.py \
  --cohort docs/historical-challenge-cohort.json \
  --answer-key /path/outside/repository/page47-historical-challenge-answer-key.json \
  --database runtime/records/seattle.sqlite3 \
  --evidence-root runtime/evidence/seattle \
  --presentation config/presentation.yaml \
  --output docs/historical-challenge-results.json \
  --code-revision <scoring-code-revision>
```

The scorer verifies the packet hash, database hash, evidence chain, and
integrity root before calculating the five-way confusion matrix, per-state
precision and recall, surfaced-positive precision, abstention correctness,
reviewer agreement, evidence coverage, and provenance validity.

## Selection boundary after review

The withheld answer key is the place to inspect the counts and exclusions. The
current construction starts with 470 repeated Seattle matters, excludes
recurring agenda/minutes containers, and selects all remaining mechanical
candidates plus randomly sampled controls. The exact post-exclusion counts,
candidate IDs, and selection reasons remain withheld until labelling is
complete so that the review remains blind.

This is a mechanically selected historical challenge cohort, not a prevalence
sample and not a representative accuracy estimate. Its purpose is to test
behavior on real retained records while keeping the evidence boundary
inspectable.
