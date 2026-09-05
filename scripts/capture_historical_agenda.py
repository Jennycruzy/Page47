#!/usr/bin/env python3
"""Capture a specified published agenda using a configured Legistar city."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.snapshotter.historical_agenda import capture_historical_agenda  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture one published historical agenda")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--event-id", type=int, required=True)
    args = parser.parse_args()
    result = capture_historical_agenda(args.config, args.evidence_root, args.event_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
