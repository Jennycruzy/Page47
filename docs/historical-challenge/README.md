# Historical challenge packet

This directory is the browser-friendly view of the 40-case historical
challenge cohort.

Open the [compact case index](index.json) to see the shuffled case order and
the link to each retained case file. The index and case files contain neutral
review material only. They do not expose candidate/control roles, selection
reasons, or Page 47 comparator results.

The [complete packet](../historical-challenge-cohort.json) is the canonical
audit artifact. It contains the same retained case payloads and independent
review slots in one JSON file. It is intended for download rather than browser
rendering. The [review protocol](../historical-challenge-review.md) defines
the blind labelling and adjudication rules.

The selection answer key is withheld outside the repository until independent
labelling is complete. It records the candidate and control counts, the
recurring-container exclusions, the mechanical selection rules, and the
reproducibility hashes. This keeps the reviewer packet blind while preserving
the audit trail for later scoring.

Every item uses one fixed adjacent appearance pair as its review unit. The
same `review_pair` shape is present for every case, including controls. Review
the pair in context of the complete retained case payload, then record one of:
`clearer`, `less_clear`, `mixed`, `unchanged`, or `cannot_determine`.
