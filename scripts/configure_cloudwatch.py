"""Create the Page 47 log metric and missed-run alarm from checked-in settings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Protocol, cast

import yaml

from page47.snapshotter.config import JSONValue, as_json_value


class LogsClient(Protocol):
    def describe_log_groups(self, **kwargs: object) -> object: ...

    def put_metric_filter(self, **kwargs: object) -> object: ...


class CloudWatchClient(Protocol):
    def put_metric_alarm(self, **kwargs: object) -> object: ...


class AwsSession(Protocol):
    def client(self, service_name: str, *, region_name: str) -> object: ...


def _object(value: object, context: str) -> dict[str, JSONValue]:
    decoded = as_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{context} must be an object")
    return decoded


def _text(value: JSONValue | None, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be non-empty text")
    return value


def _integer(value: JSONValue | None, context: str, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{context} must be an integer of at least {minimum}")
    return value


def _settings(path: Path) -> dict[str, str | int]:
    decoded = _object(yaml.safe_load(path.read_text(encoding="utf-8")), "observability")
    values = _object(decoded.get("observability"), "observability")
    return {
        "region": _text(values.get("region"), "observability.region"),
        "snapshot_log_group": _text(
            values.get("snapshot_log_group"), "observability.snapshot_log_group"
        ),
        "success_metric_namespace": _text(
            values.get("success_metric_namespace"),
            "observability.success_metric_namespace",
        ),
        "success_metric_name": _text(
            values.get("success_metric_name"), "observability.success_metric_name"
        ),
        "success_metric_filter": _text(
            values.get("success_metric_filter"), "observability.success_metric_filter"
        ),
        "missed_run_alarm_name": _text(
            values.get("missed_run_alarm_name"), "observability.missed_run_alarm_name"
        ),
        "alarm_period_seconds": _integer(
            values.get("alarm_period_seconds"), "observability.alarm_period_seconds", 60
        ),
        "alarm_evaluation_periods": _integer(
            values.get("alarm_evaluation_periods"),
            "observability.alarm_evaluation_periods",
            1,
        ),
        "alarm_threshold": _integer(
            values.get("alarm_threshold"), "observability.alarm_threshold", 1
        ),
    }


def _log_group_exists(client: LogsClient, name: str) -> bool:
    response = _object(
        client.describe_log_groups(logGroupNamePrefix=name),
        "CloudWatch Logs response",
    )
    groups = response.get("logGroups")
    if not isinstance(groups, list):
        raise ValueError("CloudWatch Logs response lacked logGroups")
    for index, raw_group in enumerate(groups):
        group = _object(raw_group, f"CloudWatch Logs logGroups[{index}]")
        if group.get("logGroupName") == name:
            return True
    return False


def configure(path: Path) -> dict[str, str | int]:
    settings = _settings(path)
    try:
        import boto3
    except ImportError as error:
        raise RuntimeError("boto3 is required to configure CloudWatch") from error
    session = cast(AwsSession, boto3.Session())
    logs = cast(LogsClient, session.client("logs", region_name=str(settings["region"])))
    cloudwatch = cast(
        CloudWatchClient,
        session.client("cloudwatch", region_name=str(settings["region"])),
    )
    log_group = str(settings["snapshot_log_group"])
    if not _log_group_exists(logs, log_group):
        raise RuntimeError(
            f"CloudWatch log group {log_group} does not exist; start the log collector first"
        )
    logs.put_metric_filter(
        logGroupName=log_group,
        filterName="Page47SnapshotRunSuccess",
        filterPattern=str(settings["success_metric_filter"]),
        metricTransformations=[
            {
                "metricName": str(settings["success_metric_name"]),
                "metricNamespace": str(settings["success_metric_namespace"]),
                "metricValue": "1",
                "defaultValue": 0,
            }
        ],
    )
    cloudwatch.put_metric_alarm(
        AlarmName=str(settings["missed_run_alarm_name"]),
        AlarmDescription=(
            "Page 47 collector has not recorded a successful scheduled run in the "
            "configured evaluation window."
        ),
        Namespace=str(settings["success_metric_namespace"]),
        MetricName=str(settings["success_metric_name"]),
        Statistic="Sum",
        Period=int(settings["alarm_period_seconds"]),
        EvaluationPeriods=int(settings["alarm_evaluation_periods"]),
        DatapointsToAlarm=int(settings["alarm_evaluation_periods"]),
        Threshold=int(settings["alarm_threshold"]),
        ComparisonOperator="LessThanThreshold",
        TreatMissingData="breaching",
    )
    return {
        "region": str(settings["region"]),
        "log_group": log_group,
        "metric": f"{settings['success_metric_namespace']}/{settings['success_metric_name']}",
        "alarm": str(settings["missed_run_alarm_name"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure Page 47 CloudWatch monitoring")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(configure(args.config), sort_keys=True))


if __name__ == "__main__":
    main()
