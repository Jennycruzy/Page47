#!/usr/bin/env python3
"""Deliver one saved review to matching active watches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.notifications.delivery import deliver_finding  # noqa: E402, I001
from page47.records.store import RecordStore  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver one saved Page 47 review")
    parser.add_argument("--city", required=True)
    parser.add_argument("--finding-id", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument(
        "--address-config",
        type=Path,
        default=REPOSITORY_ROOT / "config" / "address.yaml",
    )
    parser.add_argument(
        "--notification-config",
        type=Path,
        default=REPOSITORY_ROOT / "config" / "notifications.yaml",
    )
    args = parser.parse_args()
    with RecordStore(args.database) as store:
        result = deliver_finding(
            store=store,
            city=args.city,
            finding_id=args.finding_id,
            evidence_root=args.evidence_root,
            address_config=args.address_config,
            notification_config=args.notification_config,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
