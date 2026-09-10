from __future__ import annotations

from datetime import UTC, datetime

from page47.notifications.delivery import (
    _parameter_value,
    _plain_language,
    render_finding_email,
)
from page47.snapshotter.config import JSONObject


class ParameterClient:
    def get_parameter(self, *, Name: str, WithDecryption: bool) -> object:
        assert Name == "/page47/email/sender"
        assert WithDecryption is True
        return {
            "Parameter": {
                "Value": "sender@example.test",
                "LastModifiedDate": datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
            }
        }


def finding() -> JSONObject:
    return {
        "finding_id": "seattle-7",
        "city": "Seattle, Washington",
        "decision": {"state": "less_clear"},
        "brief": {
            "heading": "Worth a look",
            "lines": [
                {
                    "text": "The item moved to the consent calendar.",
                    "evidence": [
                        {
                            "label": "Agenda PDF",
                            "url": "https://records.example/agenda.pdf",
                            "captured_at": "2026-09-06T00:00:00Z",
                            "page_number": 3,
                        }
                    ],
                }
            ],
            "limitation": "Page 47 does not determine why these changes were made.",
        },
    }


def test_email_contains_review_and_private_watch_links() -> None:
    payload = finding()
    payload["manage_url"] = "https://page47.example/watch/watch-1"
    message = render_finding_email(payload, "https://page47.example")

    assert "https://page47.example/finding/Seattle%2C%20Washington/seattle-7" in message.text
    assert "https://page47.example/watch/watch-1" in message.text
    assert "Manage or stop this watch" in message.html


def test_email_rejects_non_http_watch_links() -> None:
    payload = finding()
    payload["manage_url"] = "javascript:alert(1)"

    try:
        render_finding_email(payload, "https://page47.example")
    except ValueError as error:
        assert "HTTP(S) URL" in str(error)
    else:
        raise AssertionError("A non-HTTP watch link was accepted")


def test_parameter_value_accepts_boto_datetime_metadata() -> None:
    assert _parameter_value(ParameterClient(), "/page47/email/sender") == "sender@example.test"


def test_plain_language_matches_words_without_rejecting_identity() -> None:
    assert _plain_language("The deployment identity is recorded.", "test")
    try:
        _plain_language("The record names an entity.", "test")
    except ValueError as error:
        assert "entity" in str(error)
    else:
        raise AssertionError("A prohibited whole word was accepted")
