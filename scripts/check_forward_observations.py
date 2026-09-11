#!/usr/bin/env python3
"""Check whether the collector has earned a forward-observed positive case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.evaluation.forward import scan_forward_observations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a directional result was based on two Page 47 captures"
    )
    parser.add_argument("--city", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--require",
        action="store_true",
        help="Return status 2 when no forward-observed positive case exists yet",
    )
    args = parser.parse_args()
    result = scan_forward_observations(
        city=args.city,
        database=args.database,
        evidence_root=args.evidence_root,
        presentation_path=args.presentation,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if args.require and result["candidate_count"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
