#!/usr/bin/env python3
"""Run the four transparent Page 47 comparison arms."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.evaluation.comparison import run_comparison  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Page 47 four-arm comparison")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_comparison(
        input_path=args.input,
        database=args.database,
        evidence_root=args.evidence_root,
        presentation_path=args.presentation,
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "city": result["city"],
                "cases": result["case_count"],
                "output": str(args.output),
                "status": result["status"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
