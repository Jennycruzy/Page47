# Independently reviewed historical challenge cohort

This directory is the browser-friendly view of Page 47's corrected historical
challenge cohort: 37 real Seattle matters with two retained independent human
reviews for every matter.

The [case index](index.json) links to one JSON file per matter. The [complete
packet](../historical-challenge-cohort.json) is the canonical audit artifact;
it is intended for download rather than browser rendering. The [public answer
key](../historical-challenge-answer-key.json) records the mechanical selection
roles and source snapshot now that review is complete. The [review record](../historical-challenge-review.md)
explains the unit, labels, evidence requirements, and correction history.

The cohort contains 5 mechanically selected raw-change candidates and 32
controls. Three recurring container records were removed before the completed
reviews were imported: matter IDs 15756, 16819, and 16820. These were recurring
agenda or minutes containers whose routine weekly changes were not suitable
tests of matter presentation drift.

The original review files were retained. The corrected packet removes only
those three records, removes selection metadata from the reviewer-facing case
material, preserves both reviewer slots, and records matching labels as the
adjudicated result. This is an independently reviewed historical challenge
cohort, not a prevalence sample or a representative accuracy estimate.

Every item uses one fixed adjacent appearance pair as its review unit. The
allowed labels are:

- `clearer`: supported presentation became more representative or visible;
- `less_clear`: supported presentation became less representative or visible;
- `mixed`: supported dimensions moved in opposite directions;
- `unchanged`: comparable presentation dimensions stayed neutral;
- `cannot_determine`: the retained public record is insufficient to establish a
  direction.

The packet retains primary source URLs, capture times, and page numbers where a
review used a PDF page. The answer key also retains the database, evidence, and
code fingerprints needed to reproduce the selection and scoring inputs.
