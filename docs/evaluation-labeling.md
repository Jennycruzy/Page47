# Hand labels for the comparison set

The comparison uses real Seattle matters exported from the stored public record. The checked-in [export](evaluation-set.json) contains 100 matters with at least two recorded appearances. The first 30 in ascending matter ID order are the smaller hand-labelled set. The completed human audit records all 30 as `cannot_determine` because the available public records are insufficient.

Open each gold matter in the Page 47 console or inspect the linked city records. Compare the appearances in order. In the matching item in `docs/evaluation-set.json`, fill in:

- `gold_label`: `yes` if the way the matter was presented changed meaningfully, `no` if it did not, or `cannot_determine` if the stored public record is insufficient.
- `gold_label_reason`: one plain sentence explaining the label.
- `gold_evidence`: at least one primary-record object containing `url` and `captured_at`; include a `page_number` when the judgment relies on a PDF page.

Do not label motive, legality, or whether anyone acted improperly. The label concerns only the recorded presentation across appearances. Do not change the selected matter IDs or the gold subset after the comparison arms have run.

The human audit is complete. Verify the finalized export shape:

```sh
python scripts/validate_evaluation_set.py \
  --input docs/evaluation-set.json
```

The validator refuses to pass until every gold item has a valid label, reason,
and primary evidence. `cannot_determine` items remain listed as exclusions
rather than being silently removed. This gate does not calculate or publish
comparison metrics.
