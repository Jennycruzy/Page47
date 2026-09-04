#!/usr/bin/env python3
"""Command-line entry point for the Phase 0 discovery."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from page47.preflight.runner import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
