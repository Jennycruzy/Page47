#!/usr/bin/env python3
"""Run the configured historical public-record collection."""

from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.records.runner import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())
