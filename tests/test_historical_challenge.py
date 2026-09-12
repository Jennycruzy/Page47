from scripts.score_historical_challenge import _metrics, _reviewer_agreement


def test_historical_metrics_keep_the_five_states_separate() -> None:
    actual = ["clearer", "less_clear", "mixed", "unchanged", "cannot_determine"]
    predicted = ["clearer", "mixed", "mixed", "unchanged", "cannot_determine"]

    metrics = _metrics(actual, predicted)

    assert metrics["cases"] == 5
    assert metrics["confusion_matrix"]["less_clear"]["mixed"] == 1
    assert metrics["per_state"]["clearer"]["recall"] == 1.0
    assert metrics["abstention"]["correct"] == 1


def test_reviewer_agreement_reports_exact_rate_and_distributions() -> None:
    items = [
        {
            "review": {
                "reviewer_a": {"label": "clearer"},
                "reviewer_b": {"label": "clearer"},
            }
        },
        {
            "review": {
                "reviewer_a": {"label": "cannot_determine"},
                "reviewer_b": {"label": "less_clear"},
            }
        },
    ]

    agreement = _reviewer_agreement(items)

    assert agreement["cases"] == 2
    assert agreement["exact_agreement"] == 1
    assert agreement["agreement_rate"] == 0.5
    assert agreement["reviewer_a_distribution"] == {
        "cannot_determine": 1,
        "clearer": 1,
    }
