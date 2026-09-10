# Page 47 — controlled directional evaluation

This artifact runs the deterministic comparator over 28 frozen transformations in
[`config/evaluation-controlled.json`](../config/evaluation-controlled.json). The
fixture is intentionally separate from the completed 30-case historical audit:
its cases have known expected outcomes because the presentation dimensions are
controlled.

Run it with:

```bash
.venv/bin/python scripts/run_controlled_evaluation.py \
  --fixture config/evaluation-controlled.json \
  --presentation config/presentation.yaml \
  --output docs/controlled-evaluation-results.json
```

The current run is preserved in
[`controlled-evaluation-results.json`](controlled-evaluation-results.json).
It contains 28/28 correct Page 47 comparator states, 28/28 keyword-arm
surface expectations, and 2/2 directional reversal pairs. The artifact remains
marked `review_required` so those numbers are not presented as real-world
accuracy: they measure behavior on controlled transformations only.

The fixture covers:

- clearer and less-clear title transitions in both directions;
- consent/regular placement transitions in both directions;
- mixed title/placement directions;
- unchanged and neutral wording edits;
- missing history and insufficient evidence;
- attachment-name changes, duplicate copies, and same-URL replacement hashes;
- a substantive change that is annotated for Skeptic rejection;
- an unsupported-motive case annotated for Skeptic abstention; and
- instruction-like text embedded in document evidence, treated as data.

The deterministic run does not invoke Bedrock or the Skeptic. The two
`skeptic_expected` annotations are therefore review targets, not measured
Skeptic accuracy. No claim of model accuracy is made from this artifact.
