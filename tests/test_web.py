from __future__ import annotations

from pathlib import Path

from page47.web.app import _index_page
from page47.web.config import load_web_settings


def test_console_configuration_has_a_public_path() -> None:
    settings = load_web_settings(Path("config/web.yaml"))
    assert settings.public_path == "/page47"


def test_console_links_use_the_configured_public_path() -> None:
    page = _index_page("Page 47", "Seattle, Washington", "/page47")
    assert 'href="/page47/"' in page
    assert 'const publicPath = "/page47"' in page
    assert "internal('/api/cities')" in page
    assert "internal(`/matter/" in page
    assert "Manage this private watch" in page
