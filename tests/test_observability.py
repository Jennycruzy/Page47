from __future__ import annotations

import json
from pathlib import Path

import yaml


def test_cloudwatch_configuration_matches_the_collector_heartbeat() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = yaml.safe_load(
        (root / "config/observability.yaml").read_text(encoding="utf-8")
    )
    agent = json.loads(
        (root / "deploy/cloudwatch/page47-agent.json").read_text(encoding="utf-8")
    )
    observability = settings["observability"]
    files = agent["logs"]["logs_collected"]["files"]["collect_list"]
    journald = agent["logs"]["logs_collected"]["journald"]["collect_list"]

    assert observability["snapshot_log_group"] == files[0]["log_group_name"]
    assert observability["web_log_group"] == journald[0]["log_group_name"]
    assert observability["log_retention_days"] == files[0]["retention_in_days"]
    assert observability["log_retention_days"] == journald[0]["retention_in_days"]
    assert observability["success_metric_filter"].strip('"') == "Page47SnapshotRunSuccess"
