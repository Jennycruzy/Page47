#!/usr/bin/env python3
"""Back up a Page 47 evidence store to an S3 bucket."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import boto3

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.snapshotter.backup import backup_evidence  # noqa: E402
from page47.snapshotter.store import SnapshotStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up Page 47 evidence to S3")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="page47-evidence")
    parser.add_argument("--region", default=None)
    args = parser.parse_args()
    store = SnapshotStore(args.evidence_root)
    client = boto3.client("s3", region_name=args.region)
    result = backup_evidence(store, client, bucket=args.bucket, prefix=args.prefix)
    print(json.dumps(result.as_json(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
