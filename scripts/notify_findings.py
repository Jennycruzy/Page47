#!/usr/bin/env python3
"""Deliver all saved publishable reviews that have not already been sent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from page47.notifications.delivery import deliver_finding  # noqa: E402, I001
from page47.records.store import RecordStore  # noqa: E402, I001
from page47.snapshotter.config import as_json_value  # noqa: E402, I001
from page47.web.config import load_web_settings  # noqa: E402, I001


def main() -> int:
    parser = argparse.ArgumentParser(description="Deliver saved Page 47 reviews")
    parser.add_argument(
        "--web-config",
        type=Path,
        default=REPOSITORY_ROOT / "config" / "web.yaml",
    )
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
    settings = load_web_settings(args.web_config)
    results: list[object] = []
    for city in settings.cities:
        with RecordStore(city.database) as store:
            findings = store.finding_rows(city.name, 10000)
            for finding in findings:
                if finding.get("publish") is not True:
                    continue
                finding_id = finding.get("finding_id")
                if not isinstance(finding_id, str) or not finding_id:
                    raise ValueError("Stored publishable finding had no finding ID")
                result = deliver_finding(
                    store=store,
                    city=city.name,
                    finding_id=finding_id,
                    evidence_root=city.evidence_root,
                    address_config=args.address_config,
                    notification_config=args.notification_config,
                )
                results.append(result)
    value = as_json_value(results)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
