from page47.records.pdf_consent import AgendaPage, classify_item


def test_seattle_august_11_consent_item_is_found_under_heading() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 579\nBills: CB 121271"),
        AgendaPage(12, "I. ITEMS REMOVED FROM CONSENT CALENDAR\nCF 314550"),
    )
    result = classify_item(pages, "CB 121271")
    assert result.placement == "consent"
    assert result.evidence_pages == (3,)


def test_seattle_august_4_regular_item_is_outside_consent_section() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 578\nBills: CB 121265"),
        AgendaPage(8, "I. ITEMS REMOVED FROM CONSENT CALENDAR\n10. CF 314530"),
    )
    result = classify_item(pages, "CF 314530")
    assert result.placement == "regular"
    assert result.evidence_pages == (8,)


def test_missing_title_is_not_labeled() -> None:
    pages = (
        AgendaPage(3, "G. APPROVAL OF CONSENT CALENDAR\nJournal: Min 578"),
        AgendaPage(8, "I. ITEMS REMOVED FROM CONSENT CALENDAR"),
    )
    result = classify_item(pages, "An item that is not in this agenda")
    assert result.placement == "cannot_determine"
    assert result.evidence_pages == ()
