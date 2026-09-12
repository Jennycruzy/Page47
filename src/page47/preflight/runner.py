"""Run source discovery without assuming a city's field meanings."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]


class AwsClient(Protocol):
    """The small, validated surface used from an AWS service client."""

    def list_foundation_models(self) -> object: ...

    def list_agent_runtimes(self, *, maxResults: int) -> object: ...


class AwsSession(Protocol):
    """The small, typed surface used from a boto3 session."""

    def client(self, service_name: str, *, region_name: str) -> AwsClient: ...

    def get_available_services(self) -> list[str]: ...

    def get_available_regions(self, service_name: str) -> list[str]: ...

EVENT_FIELDS: Final[tuple[str, ...]] = (
    "EventId",
    "EventDate",
    "EventBodyId",
    "EventBodyName",
    "EventAgendaFile",
    "EventAgendaLastPublishedUTC",
    "EventAgendaStatusName",
    "EventInSiteURL",
    "EventComment",
)
EVENT_ITEM_FIELDS: Final[tuple[str, ...]] = (
    "EventItemId",
    "EventItemEventId",
    "EventItemMatterId",
    "EventItemTitle",
    "EventItemConsent",
    "EventItemAgendaSequence",
    "EventItemAgendaNumber",
    "EventItemActionName",
    "EventItemActionText",
    "EventItemPassedFlagName",
    "EventItemVersion",
    "EventItemAgendaNote",
    "EventItemMinutesNote",
    "EventItemLastModifiedUtc",
    "EventItemMatterAttachments",
)
ATTACHMENT_FIELDS: Final[tuple[str, ...]] = (
    "MatterAttachmentId",
    "MatterAttachmentName",
    "MatterAttachmentHyperlink",
    "MatterAttachmentLastModifiedUtc",
    "MatterAttachmentMatterVersion",
    "MatterAttachmentIsSupportingDocument",
)
MATTER_FIELDS: Final[tuple[str, ...]] = (
    "MatterId",
    "MatterFile",
    "MatterName",
    "MatterTitle",
    "MatterTypeName",
    "MatterStatusName",
    "MatterBodyName",
    "MatterIntroDate",
    "MatterAgendaDate",
    "MatterVersion",
    "MatterLastModifiedUtc",
)
USER_AGENT: Final[str] = "Page47-preflight/0.1 (public-record research)"
CAPTURED_HEADERS: Final[frozenset[str]] = frozenset(
    {"etag", "last-modified", "content-type", "retry-after", "content-length"}
)
AWS_ACCOUNT_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{12}(?!\d)")
AWS_ARN_PATTERN: Final[re.Pattern[str]] = re.compile(r"arn:aws:[^\s,]+")


def utc_now() -> str:
    """Return an ISO timestamp with an explicit UTC offset."""

    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def as_json_value(value: object) -> JSONValue:
    """Validate the object returned by a JSON decoder."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [as_json_value(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object key was not text")
            result[key] = as_json_value(item)
        return result
    raise ValueError(f"Unsupported decoded JSON value: {type(value).__name__}")


def parse_json(body: bytes) -> JSONValue:
    """Parse and validate a JSON response without allowing unchecked values onward."""

    decoded: object = json.loads(body)
    return as_json_value(decoded)


def as_object(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}, got {type(value).__name__}")
    return value


def as_objects(value: JSONValue, context: str) -> list[JSONObject]:
    if not isinstance(value, list):
        raise ValueError(f"Expected a list for {context}, got {type(value).__name__}")
    objects: list[JSONObject] = []
    for index, item in enumerate(value):
        objects.append(as_object(item, f"{context}[{index}]"))
    return objects


def json_list(values: Sequence[JSONValue]) -> list[JSONValue]:
    """Widen a typed sequence before placing it inside a JSON value."""

    return list(values)


def json_object(values: Mapping[str, JSONValue]) -> JSONObject:
    """Widen a typed mapping before placing it inside a JSON object."""

    output: JSONObject = {}
    for key, value in values.items():
        output[key] = value
    return output


def nonempty(value: JSONValue | object) -> bool:
    """Treat null and empty containers/text as absent, while preserving numeric zero."""

    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def text_value(value: JSONValue | object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def event_is_current_or_past(event: JSONObject, reference: datetime) -> bool:
    """Prefer meetings that have already occurred, without dropping unknown dates."""

    raw_date = text_value(event.get("EventDate"))
    if raw_date is None:
        return True
    try:
        parsed = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed <= reference


def integer_value(value: JSONValue | object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def number_value(value: JSONValue | object, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Expected a number for {context}")
    return float(value)


def redacted_error(error: Exception) -> str:
    message = str(error)
    message = AWS_ARN_PATTERN.sub("<aws-arn-redacted>", message)
    return AWS_ACCOUNT_PATTERN.sub("<aws-account-redacted>", message)


@dataclass(frozen=True, slots=True)
class FetchResult:
    """A captured HTTP attempt."""

    url: str
    captured_at: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    error_type: str | None
    error: str | None


class EvidenceCache:
    """Persist every attempted response as immutable bytes plus an index record."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.response_dir = root / "responses"
        self.response_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[JSONObject] = []

    def add(self, result: FetchResult) -> None:
        body_hash = hashlib.sha256(result.body).hexdigest()
        url_hash = hashlib.sha256(result.url.encode("utf-8")).hexdigest()[:16]
        timestamp = result.captured_at.replace(":", "").replace("-", "")
        capture_id = f"{timestamp}_{url_hash}_{body_hash[:16]}"
        body_path = self.response_dir / f"{capture_id}.body"
        if not body_path.exists():
            body_path.write_bytes(result.body)
        record: JSONObject = {
            "capture_id": capture_id,
            "url": result.url,
            "captured_at": result.captured_at,
            "status": result.status,
            "sha256": body_hash,
            "bytes": len(result.body),
            "storage_key": str(body_path.relative_to(self.root.parent.parent)),
            "headers": json_object(result.headers),
        }
        if result.error_type is not None:
            record["error_type"] = result.error_type
        if result.error is not None:
            record["error"] = result.error
        self.records.append(record)

    def write_index(self) -> None:
        index_path = self.root / "index.json"
        index_path.write_text(
            json.dumps({"captures": self.records}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def fetch(url: str, timeout_seconds: float, cache: EvidenceCache) -> FetchResult:
    """Fetch one public URL and record both successes and failures."""

    captured_at = utc_now()
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html"},
    )
    status: int | None = None
    headers: dict[str, str] = {}
    body = b""
    error_type: str | None = None
    error_message: str | None = None
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = response.status
            headers = {
                key.lower(): value
                for key, value in response.headers.items()
                if key.lower() in CAPTURED_HEADERS
            }
            body = response.read()
    except HTTPError as error:
        status = error.code
        headers = {
            key.lower(): value
            for key, value in error.headers.items()
            if key.lower() in CAPTURED_HEADERS
        }
        body = error.read()
        error_type = type(error).__name__
        error_message = redacted_error(error)
    except (URLError, TimeoutError, OSError) as error:
        error_type = type(error).__name__
        error_message = redacted_error(error)
    result = FetchResult(url, captured_at, status, headers, body, error_type, error_message)
    cache.add(result)
    return result


def fetch_json(
    url: str, timeout_seconds: float, cache: EvidenceCache
) -> tuple[FetchResult, JSONValue | None]:
    result = fetch(url, timeout_seconds, cache)
    if result.status != 200:
        return result, None
    try:
        return result, parse_json(result.body)
    except (ValueError, json.JSONDecodeError) as error:
        result = FetchResult(
            result.url,
            result.captured_at,
            result.status,
            result.headers,
            result.body,
            "ParseError",
            redacted_error(error),
        )
        return result, None


def api_url(base_url: str, client: str, resource: str, **query: str) -> str:
    path = f"{base_url.rstrip('/')}/{client}/{resource.lstrip('/')}"
    return f"{path}?{urlencode(query)}" if query else path


def count_fields(records: Sequence[JSONObject], fields: Sequence[str]) -> JSONObject:
    return {
        field: {
            "present": sum(1 for record in records if nonempty(record.get(field))),
            "sample_records": len(records),
        }
        for field in fields
    }


def values_for(records: Sequence[JSONObject], field: str) -> list[JSONValue]:
    return [value for record in records if (value := record.get(field)) is not None]


def range_for(records: Sequence[JSONObject], field: str) -> JSONObject:
    values = values_for(records, field)
    numeric = [value for value in values if isinstance(value, int) and not isinstance(value, bool)]
    text = [value for value in values if isinstance(value, str) and value]
    output: JSONObject = {"field": field, "sample_count": len(values)}
    if numeric:
        output["minimum"] = min(numeric)
        output["maximum"] = max(numeric)
    if text:
        output["lexical_minimum"] = min(text)
        output["lexical_maximum"] = max(text)
    return output


def extract_nested_items(detail: JSONObject) -> list[JSONObject]:
    raw_items = detail.get("EventItems")
    if raw_items is None:
        raw_items = detail.get("EventItem")
    if raw_items is None:
        return []
    return as_objects(raw_items, "event detail items")


def extract_attachments(items: Sequence[JSONObject]) -> list[JSONObject]:
    attachments: list[JSONObject] = []
    for item in items:
        raw = item.get("EventItemMatterAttachments")
        if raw is None:
            raw = item.get("MatterAttachments")
        if raw is None:
            continue
        attachments.extend(as_objects(raw, "event item attachments"))
    return attachments


def public_hosts(events: Sequence[JSONObject]) -> list[str]:
    hosts: set[str] = set()
    for event in events:
        for field in ("EventInSiteURL", "EventAgendaFile"):
            value = text_value(event.get(field))
            if value is not None:
                host = urlparse(value).netloc
                if host:
                    hosts.add(host)
    return sorted(hosts)


def probe_rate_limit(
    base_url: str,
    client: str,
    count: int,
    delay_seconds: float,
    timeout_seconds: float,
    cache: EvidenceCache,
) -> JSONObject:
    attempts: list[JSONValue] = []
    throttled_after: int | None = None
    for attempt in range(1, count + 1):
        url = api_url(base_url, client, "events", **{"$top": "1"})
        started = time.monotonic()
        result = fetch(url, timeout_seconds, cache)
        elapsed_ms = round((time.monotonic() - started) * 1000, 2)
        retry_after = result.headers.get("retry-after")
        attempts.append(
            {
                "attempt": attempt,
                "status": result.status,
                "elapsed_ms": elapsed_ms,
                "retry_after": retry_after,
                "error_type": result.error_type,
            }
        )
        if throttled_after is None and (result.status == 429 or retry_after is not None):
            throttled_after = attempt
        if attempt < count:
            time.sleep(delay_seconds)
    return {
        "requests_attempted": count,
        "throttled_after_request": throttled_after,
        "attempts": attempts,
        "interpretation": (
            "throttling observed"
            if throttled_after is not None
            else "no throttling observed within the bounded probe"
        ),
    }


def probe_city(
    candidate: JSONObject,
    legistar: JSONObject,
    cache: EvidenceCache,
) -> JSONObject:
    slug = text_value(candidate.get("slug"))
    name = text_value(candidate.get("name"))
    if slug is None or name is None:
        raise ValueError("Each Legistar candidate needs a non-empty slug and name")
    base_url = text_value(legistar.get("base_url"))
    if base_url is None:
        raise ValueError("Legistar base_url is missing")
    sample_size = integer_value(legistar.get("sample_size"))
    event_scan_size = integer_value(legistar.get("event_scan_size"))
    event_detail_sample_size = integer_value(legistar.get("event_detail_sample_size"))
    rate_count = integer_value(legistar.get("rate_limit_probe_requests"))
    delay_value = legistar.get("rate_limit_probe_delay_seconds")
    timeout_value = legistar.get("timeout_seconds")
    if (
        sample_size is None
        or event_scan_size is None
        or event_detail_sample_size is None
        or rate_count is None
        or not isinstance(delay_value, (int, float))
    ):
        raise ValueError("Legistar numeric probe settings are incomplete")
    if not isinstance(timeout_value, (int, float)):
        raise ValueError("Legistar timeout_seconds is incomplete")
    timeout_seconds = float(timeout_value)

    result: JSONObject = {"slug": slug, "name": name, "status": "unverified"}
    events_url = api_url(
        base_url,
        slug,
        "events",
        **{"$top": str(event_scan_size), "$orderby": "EventId desc"},
    )
    events_result, events_value = fetch_json(events_url, timeout_seconds, cache)
    result["events_request"] = {
        "status": events_result.status,
        "error_type": events_result.error_type,
        "error": events_result.error,
    }
    if events_value is None:
        result["status"] = "unavailable"
        return result
    try:
        events = as_objects(events_value, "events")
    except ValueError as error:
        result["status"] = "unparseable"
        result["parse_error"] = str(error)
        return result
    if not events:
        result["status"] = "empty"
        return result

    matters_url = api_url(
        base_url,
        slug,
        "matters",
        **{"$top": str(sample_size), "$orderby": "MatterId desc"},
    )
    matters_result, matters_value = fetch_json(matters_url, timeout_seconds, cache)
    matters: list[JSONObject] = []
    if matters_value is not None:
        try:
            matters = as_objects(matters_value, "matters")
        except ValueError as error:
            result["matters_parse_error"] = str(error)
    result["matters_request"] = {
        "status": matters_result.status,
        "error_type": matters_result.error_type,
        "error": matters_result.error,
    }

    detail_items: list[JSONObject] = []
    detail_events_with_items = 0
    detail_requests: list[JSONObject] = []
    reference_time = datetime.now(UTC)
    ordered_events = [
        *[event for event in events if event_is_current_or_past(event, reference_time)],
        *[event for event in events if not event_is_current_or_past(event, reference_time)],
    ]
    for event in ordered_events:
        event_id = integer_value(event.get("EventId"))
        if event_id is None:
            detail_requests.append({"event_id": event.get("EventId"), "status": "missing_event_id"})
            continue
        detail_url = api_url(
            base_url,
            slug,
            f"events/{event_id}",
            EventItems="1",
            AgendaNote="1",
            MinutesNote="1",
            EventItemAttachments="1",
        )
        detail_result, detail_value = fetch_json(detail_url, timeout_seconds, cache)
        detail_record: JSONObject = {"event_id": event_id, "status": detail_result.status}
        if detail_result.error_type is not None:
            detail_record["error_type"] = detail_result.error_type
        if detail_value is not None:
            try:
                detail = as_object(detail_value, f"event {event_id} detail")
                items = extract_nested_items(detail)
                detail_items.extend(items)
                detail_record["item_count"] = len(items)
                if items:
                    detail_events_with_items += 1
            except ValueError as error:
                detail_record["parse_error"] = str(error)
        detail_requests.append(detail_record)
        if detail_events_with_items >= event_detail_sample_size:
            break

    earliest_events_url = api_url(
        base_url,
        slug,
        "events",
        **{"$top": str(sample_size), "$orderby": "EventId asc"},
    )
    earliest_result, earliest_value = fetch_json(earliest_events_url, timeout_seconds, cache)
    earliest_events: list[JSONObject] = []
    if earliest_value is not None:
        try:
            earliest_events = as_objects(earliest_value, "earliest events")
        except ValueError:
            earliest_events = []

    earliest_matters_url = api_url(
        base_url,
        slug,
        "matters",
        **{"$top": str(sample_size), "$orderby": "MatterId asc"},
    )
    earliest_matters_result, earliest_matters_value = fetch_json(
        earliest_matters_url, timeout_seconds, cache
    )
    earliest_matters: list[JSONObject] = []
    if earliest_matters_value is not None:
        try:
            earliest_matters = as_objects(earliest_matters_value, "earliest matters")
        except ValueError:
            earliest_matters = []

    attachments = extract_attachments(detail_items)
    result["status"] = (
        "viable" if matters_result.status == 200 and detail_events_with_items else "partial"
    )
    result["event_count_sampled"] = len(events)
    result["event_field_population"] = count_fields(events, EVENT_FIELDS)
    result["event_item_count_sampled"] = len(detail_items)
    result["detail_events_with_items"] = detail_events_with_items
    result["event_item_field_population"] = count_fields(detail_items, EVENT_ITEM_FIELDS)
    result["attachment_count_sampled"] = len(attachments)
    result["attachment_field_population"] = count_fields(attachments, ATTACHMENT_FIELDS)
    result["event_id_range_desc_sample"] = range_for(events, "EventId")
    result["matter_id_range_desc_sample"] = range_for(matters, "MatterId")
    result["earliest_event_sample"] = {
        "event_id_range": range_for(earliest_events, "EventId"),
        "event_dates": values_for(earliest_events, "EventDate"),
        "request_status": earliest_result.status,
    }
    result["earliest_matter_sample"] = {
        "matter_id_range": range_for(earliest_matters, "MatterId"),
        "matter_intro_dates": values_for(earliest_matters, "MatterIntroDate"),
        "request_status": earliest_matters_result.status,
    }
    result["event_detail_requests"] = json_list(detail_requests)
    result["public_site_hosts_observed"] = json_list(public_hosts(events))
    result["terms_review"] = {
        "status": "manual_review_required",
        "evidence": [
            "The API response exposed public record URLs, but no terms document was "
            "identified automatically.",
            "The selected city must be checked against its public-site terms before "
            "production use.",
        ],
    }
    result["rate_limit_probe"] = probe_rate_limit(
        base_url,
        slug,
        rate_count,
        float(delay_value),
        timeout_seconds,
        cache,
    )
    return result


def sdk_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected an SDK mapping for {context}")
    output: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"Expected text SDK key for {context}")
        output[key] = item
    return output


def sdk_strings(value: object, context: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"Expected a list for {context}")
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"Expected text values for {context}")
        strings.append(item)
    return strings


def aws_error_status(error: Exception) -> str:
    """Separate missing permission from an unavailable AWS interface."""

    if type(error).__name__ == "AccessDeniedException" or "AccessDeniedException" in str(error):
        return "permission_blocked"
    return "unavailable"


def probe_aws(aws_config: JSONObject) -> JSONObject:
    regions_value = aws_config.get("discovery_regions")
    if not isinstance(regions_value, list) or not all(
        isinstance(item, str) for item in regions_value
    ):
        raise ValueError("AWS discovery_regions must be a list of strings")
    regions = cast(list[str], regions_value)
    service_value = aws_config.get("bedrock_service")
    control_value = aws_config.get("agentcore_control_service")
    runtime_value = aws_config.get("agentcore_runtime_service")
    package_value = aws_config.get("agentcore_python_package")
    if not all(
        isinstance(item, str)
        for item in (service_value, control_value, runtime_value, package_value)
    ):
        raise ValueError("AWS service names are incomplete")
    bedrock_service = cast(str, service_value)
    control_service = cast(str, control_value)
    runtime_service = cast(str, runtime_value)
    package_name = cast(str, package_value)
    output: JSONObject = {
        "python_version": platform.python_version(),
        "boto3_available": importlib.util.find_spec("boto3") is not None,
        "agentcore_python_package_available": importlib.util.find_spec(package_name) is not None,
        "regions_requested": json_list(regions),
        "foundation_models": {},
        "agentcore": {},
    }
    if not bool(output["boto3_available"]):
        output["blocker"] = "boto3 is not installed; AWS discovery could not run"
        return output

    try:
        import boto3
    except ImportError as error:
        output["blocker"] = f"boto3 import failed: {redacted_error(error)}"
        return output

    session = cast(AwsSession, boto3.Session())
    model_results: JSONObject = {}
    for region in regions:
        try:
            client = session.client(bedrock_service, region_name=region)
            raw_response: object = client.list_foundation_models()
            response = sdk_object(raw_response, f"{bedrock_service} list response")
            raw_models = response.get("modelSummaries", [])
            if not isinstance(raw_models, list):
                raise ValueError("modelSummaries was not a list")
            model_ids: list[str] = []
            for item in raw_models:
                model = sdk_object(item, "model summary")
                model_id = model.get("modelId")
                if isinstance(model_id, str):
                    model_ids.append(model_id)
            model_results[region] = {
                "status": "available",
                "model_ids": json_list(sorted(model_ids)),
            }
        except Exception as error:
            model_results[region] = {
                "status": aws_error_status(error),
                "error_type": type(error).__name__,
                "error": redacted_error(error),
            }
    output["foundation_models"] = model_results

    package_version: str | None = None
    try:
        package_version = importlib.metadata.version("bedrock-agentcore")
    except importlib.metadata.PackageNotFoundError:
        package_version = None
    agentcore_result: JSONObject = {
        "control_service": control_service,
        "runtime_service": runtime_service,
        "python_package_version": package_version,
        "sdk_control_service_model_present": control_service in session.get_available_services(),
        "sdk_runtime_service_model_present": runtime_service in session.get_available_services(),
        "regions": {},
    }
    control_regions = session.get_available_regions(control_service)
    control_model_present = control_service in session.get_available_services()
    for region in regions:
        region_result: JSONObject = {
            "sdk_service_model_present": control_model_present,
            "sdk_region_metadata_present": region in control_regions,
            "status": "unverified",
        }
        if not control_model_present:
            region_result["reason"] = (
                "installed boto3 does not contain the AgentCore control service model"
            )
            agentcore_regions = cast(dict[str, JSONValue], agentcore_result["regions"])
            agentcore_regions[region] = region_result
            continue
        try:
            control_client = session.client(control_service, region_name=region)
            raw_response = control_client.list_agent_runtimes(maxResults=1)
            sdk_object(raw_response, f"{control_service} list response")
            region_result["status"] = "available"
        except Exception as error:
            region_result["status"] = aws_error_status(error)
            region_result["error_type"] = type(error).__name__
            region_result["error"] = redacted_error(error)
        agentcore_regions = cast(dict[str, JSONValue], agentcore_result["regions"])
        agentcore_regions[region] = region_result
    output["agentcore"] = agentcore_result
    return output


def cost_arithmetic(cost: JSONObject) -> JSONObject:
    budget = number_value(cost.get("budget_usd"), "budget_usd")
    days = number_value(cost.get("measurement_days"), "measurement_days")
    lightsail = number_value(cost.get("lightsail_monthly_usd"), "lightsail_monthly_usd")
    storage_gb = number_value(cost.get("storage_gb_assumption"), "storage_gb_assumption")
    storage_rate = number_value(
        cost.get("storage_monthly_usd_per_gb"), "storage_monthly_usd_per_gb"
    )
    fixed_cost = lightsail * days / 30.0
    storage_cost = storage_gb * storage_rate * days / 30.0
    return {
        "status": "partial_model_cost_blocked",
        "budget_usd": budget,
        "measurement_days": int(days),
        "lightsail_cost_usd": round(fixed_cost, 4),
        "storage_cost_usd": round(storage_cost, 4),
        "fixed_cost_subtotal_usd": round(fixed_cost + storage_cost, 4),
        "model_cost_formula": (
            "triage input tokens × triage input price + triage output tokens × triage output price "
            "+ candidate multimodal tokens × multimodal prices + investigation tokens × "
            "investigation prices"
        ),
        "model_cost_status": (
            "not computed until a real model list and current prices are available"
        ),
        "source_urls": [
            "https://aws.amazon.com/lightsail/pricing/",
            "https://aws.amazon.com/bedrock/pricing/",
        ],
    }


def run(config_path: Path, output_path: Path) -> JSONObject:
    config_value = json.loads(config_path.read_text(encoding="utf-8"))
    config = as_object(as_json_value(config_value), "preflight config")
    legistar = as_object(config.get("legistar", {}), "legistar config")
    aws_config = as_object(config.get("aws", {}), "aws config")
    cost_config = as_object(config.get("cost", {}), "cost config")
    evidence_root = output_path.parent / "evidence" / "preflight"
    cache = EvidenceCache(evidence_root)
    captured_at = utc_now()

    references = legistar.get("official_reference_urls", [])
    reference_results: list[JSONObject] = []
    if isinstance(references, list):
        for reference in references:
            if not isinstance(reference, str):
                raise ValueError("official_reference_urls must contain strings")
            fetched = fetch(
                reference,
                number_value(legistar.get("timeout_seconds", 20), "timeout_seconds"),
                cache,
            )
            reference_results.append(
                {
                    "url": reference,
                    "status": fetched.status,
                    "error_type": fetched.error_type,
                    "error": fetched.error,
                }
            )

    candidate_value = legistar.get("candidates")
    if not isinstance(candidate_value, list):
        raise ValueError("Legistar candidates must be a list")
    candidates = [as_object(item, "Legistar candidate") for item in candidate_value]
    city_results: list[JSONObject] = []
    for candidate in candidates:
        city_results.append(probe_city(candidate, legistar, cache))

    aws_result = probe_aws(aws_config)
    result: JSONObject = {
        "schema_version": 1,
        "captured_at": captured_at,
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "legistar": {
            "base_url": legistar.get("base_url"),
            "official_references": json_list(reference_results),
            "clients": json_list(city_results),
        },
        "aws": aws_result,
        "cost_arithmetic": cost_arithmetic(cost_config),
        "cache_index": str((evidence_root / "index.json").relative_to(output_path.parent)),
    }
    viable = [
        city
        for city in city_results
        if city.get("status") == "viable"
    ]
    blockers: list[str] = []
    if len(viable) < 2:
        blockers.append("Fewer than two Legistar clients met the viable probe criteria")
    foundation_statuses = [
        item.get("status")
        for item in cast(dict[str, JSONValue], aws_result.get("foundation_models", {})).values()
        if isinstance(item, dict)
    ]
    if "available" not in foundation_statuses:
        if "permission_blocked" in foundation_statuses:
            blockers.append("No Bedrock model list succeeded because the AWS role lacks permission")
        else:
            blockers.append("No Bedrock model list succeeded with the available AWS interfaces")
    agentcore = aws_result.get("agentcore")
    agentcore_statuses = (
        [
            item.get("status")
            for item in cast(dict[str, JSONValue], agentcore.get("regions", {})).values()
            if isinstance(item, dict)
        ]
        if isinstance(agentcore, dict)
        else []
    )
    if "available" not in agentcore_statuses:
        if "permission_blocked" in agentcore_statuses:
            blockers.append("AgentCore endpoints were reached but the AWS role lacks permission")
        else:
            blockers.append(
                "AgentCore availability was not verified with the available AWS interfaces"
            )
    blockers.append("City terms-of-use review remains manual for each candidate")
    result["viable_clients_count"] = len(viable)
    result["blockers"] = json_list(blockers)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    cache.write_index()
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Page 47 source discovery")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args.config, args.output)
    print(
        json.dumps(
            {"captured_at": result["captured_at"], "blockers": result["blockers"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
