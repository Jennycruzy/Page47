from __future__ import annotations

from pathlib import Path

from page47.web.app import _finding_page, _index_page, _internal_url, _watch_page
from page47.web.config import load_web_settings


def test_console_configuration_has_a_public_path() -> None:
    settings = load_web_settings(Path("config/web.yaml"))
    # The configured domain root is represented internally by an empty prefix.
    assert settings.public_path == ""


def test_console_links_use_the_configured_public_path() -> None:
    page = _index_page("Page 47", "Seattle, Washington", "/page47")
    assert 'href="/page47/"' in page
    assert 'const publicPath = "/page47"' in page
    assert "internal('/api/cities')" in page
    assert "internal(`/matter/" in page
    assert "Manage this private watch" in page


def test_console_supports_a_domain_root_public_path() -> None:
    assert _internal_url("/", "/api/cities") == "/api/cities"
    assert _internal_url("/", "/watch/watch-1") == "/watch/watch-1"
    page = _index_page("Page 47", "Seattle, Washington", "/")
    assert 'href="/"' in page
    assert "publicPath === '/'" in page


def test_homepage_leads_with_resident_promise() -> None:
    page = _index_page("Page 47", "Seattle, Washington", "/")
    assert "City packets change." in page
    assert "Page 47 watches what you care about." in page
    assert "You do not need to keep this page open." in page
    assert "Advanced options — public bodies" in page
    assert "See what survived review." in page
    assert "Replay captured case" in page


def test_finding_page_exposes_dimensions_provenance_and_rejections() -> None:
    data = {
        "matter_id": 17394,
        "decision": {
            "state": "mixed",
            "reason": (
                "The finding met the configured count of independently supported "
                "observations after review."
            ),
            "accepted": [
                {
                    "observation_id": "substance:height",
                    "text": "The document records height: 35 feet to 75 feet.",
                    "evidence": [
                        {
                            "label": "captured packet",
                            "url": "https://records.example/packet.pdf",
                            "captured_at": "2026-09-11T10:00:00Z",
                            "page_number": 47,
                        }
                    ],
                }
            ],
            "rejected": [
                {
                    "observation_id": "process:timing",
                    "reason": "The record establishes timing but not its effect.",
                }
            ],
        },
        "brief": {
            "lines": [],
            "questions": ["What changed?"],
            "limitation": "Page 47 does not determine why these changes were made.",
        },
        "case": {
            "matter": {"current_title": "Central Avenue matter"},
            "appearances": [
                {
                    "event_item_id": 1,
                    "title_as_presented": "Central Avenue Height Increase",
                    "pdf_placement": "regular",
                },
                {
                    "event_item_id": 2,
                    "title_as_presented": "Administrative Amendments",
                    "pdf_placement": "consent",
                },
            ],
        },
        "drift": {
            "comparisons": [
                {
                    "previous_event_item_id": 1,
                    "current_event_item_id": 2,
                    "observations": [
                        {
                            "key": "title_changed",
                            "direction": "less_clear",
                            "evidence": [
                                    {
                                        "label": "earlier title",
                                        "url": "https://records.example/old",
                                        "captured_at": "2026-09-01",
                                        "origin": "observed_by_page47",
                                    },
                                    {
                                        "label": "later title",
                                        "url": "https://records.example/new",
                                        "captured_at": "2026-09-02",
                                        "origin": "observed_by_page47",
                                    },
                            ],
                        },
                        {
                            "key": "moved_to_consent",
                            "direction": "less_clear",
                            "evidence": [
                                {
                                    "label": "agenda",
                                    "url": "https://records.example/agenda.pdf",
                                    "captured_at": "2026-09-02",
                                    "page_number": 47,
                                }
                            ],
                        },
                    ],
                }
            ]
        },
    }
    page = _finding_page("Page 47", "Seattle, Washington", data, "/")
    assert "This matter changed in mixed directions" in page
    assert "Title" in page
    assert "Agenda placement" in page
    assert "Document substance" in page
    assert "Observed by Page 47" in page
    assert "Rejected interpretation" in page
    assert "The record establishes timing but not its effect." in page
    replay_page = _finding_page("Page 47", "Seattle, Washington", data, "/", replay=True)
    assert "Captured-case replay" in replay_page
    assert "not a live event" in replay_page


def test_watch_page_shows_background_status_and_stop_control() -> None:
    data = {
        "watch_id": "watch-1",
        "city": "Seattle, Washington",
        "bodies": ["Full Council"],
        "neighbourhood": "Capitol Hill",
        "address": None,
        "active": True,
        "created_at": "2026-09-11T10:00:00Z",
        "last_successful_check": "2026-09-11T10:15:00Z",
        "reviews_delivered": 1,
    }
    page = _watch_page("Page 47", data, "/")
    assert "Page 47 is watching." in page
    assert "You do not need to keep this page open." in page
    assert "Last successful collector check" in page
    assert "Reviews delivered" in page
    assert "Stop this watch" in page
