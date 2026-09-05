#!/usr/bin/env python3
"""Apply captured-agenda placement results to stored appearances."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.records.placement_runner import apply_pdf_placements  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply PDF-backed consent placement to stored appearances"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    result = apply_pdf_placements(args.config, args.database, args.evidence_root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
