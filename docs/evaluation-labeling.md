# Hand labels for the comparison set

The comparison uses real Seattle matters exported from the stored public record. The export contains 100 matters with at least two recorded appearances. The first 30 in ascending matter ID order are the smaller hand-labelled set.

Open each gold matter in the Page 47 console or inspect the linked city records. Compare the appearances in order. In the matching item in `docs/evaluation-set.json`, fill in:

- `gold_label`: `yes` if the way the matter was presented changed meaningfully, `no` if it did not, or `cannot_determine` if the stored public record is insufficient.
- `gold_label_reason`: one plain sentence explaining the label.
- `gold_evidence`: at least one primary-record object containing `url` and `captured_at`; include a `page_number` when the judgment relies on a PDF page.

Do not label motive, legality, or whether anyone acted improperly. The label concerns only the recorded presentation across appearances. Do not change the selected matter IDs or the gold subset after the comparison arms have run.

The evaluation runner must refuse to report recall until every gold item has a label and evidence. Unlabeled or `cannot_determine` items remain listed as exclusions rather than being silently removed.
