#!/usr/bin/env python3
"""Run one real public-record capture for a configured city."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from page47.snapshotter.runner import main  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture upcoming public meeting records")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--store", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    raise SystemExit(main(arguments.config, arguments.store))
