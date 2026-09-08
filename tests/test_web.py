from __future__ import annotations

from pathlib import Path

from page47.web.app import _index_page, _internal_url
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
