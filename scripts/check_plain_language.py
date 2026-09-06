"""Check the committed resident-facing text and rendered console copy."""

from __future__ import annotations

import re
from pathlib import Path

from page47.notifications.delivery import BANNED_HUMAN_WORDS
from page47.web.app import _index_page


def _check(text: str, context: str) -> None:
    lowered = text.casefold()
    found = sorted(
        word
        for word in BANNED_HUMAN_WORDS
        if (
            re.search(rf"\b{re.escape(word)}\b", lowered) is not None
            if " " not in word
            else word in lowered
        )
    )
    if found:
        raise SystemExit(f"{context} contains prohibited wording: {', '.join(found)}")


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    for relative in ("README.md", "docs/AWS.md"):
        path = repository_root / relative
        _check(path.read_text(encoding="utf-8"), relative)
    rendered_console = _index_page("Page 47", "Seattle, Washington", "/page47")
    _check(rendered_console, "rendered console")


if __name__ == "__main__":
    main()
