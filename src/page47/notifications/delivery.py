"""Send one stored review to a matching resident watch through Amazon SES."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import quote

import yaml

from page47.address.matcher import (
    AddressSettings,
    AreaMatch,
    census_lookup,
    load_address_settings,
    match_case_to_area,
)
from page47.analysis.case import MatterCase, load_matter_case
from page47.records.store import (
    NotificationObservation,
    RecordStore,
)
from page47.snapshotter.config import JSONObject, as_json_value


class ParameterClient(Protocol):
    def get_parameter(self, *, Name: str, WithDecryption: bool) -> object: ...


class EmailClient(Protocol):
    def send_email(self, **kwargs: object) -> object: ...


class AwsSession(Protocol):
    def client(self, service_name: str, *, region_name: str) -> object: ...


@dataclass(frozen=True, slots=True)
class NotificationSettings:
    region: str
    sender_parameter: str
    public_base_url_parameter: str


@dataclass(frozen=True, slots=True)
class EmailMessage:
    subject: str
    text: str
    html: str


BANNED_HUMAN_WORDS = frozenset(
    {
        "anomaly",
        "signal",
        "heuristic",
        "pipeline",
        "embedding",
        "vector",
        "semantic divergence",
        "confidence score",
        "entity",
        "ingestion",
        "orchestration",
        "agentic",
    }
)


def _json_object(value: object, context: str) -> JSONObject:
    decoded = as_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"{context} was not an object")
    return decoded


def load_notification_settings(path: Path) -> NotificationSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _json_object(decoded, "Notification configuration")
    email = root.get("email")
    if not isinstance(email, dict):
        raise ValueError("Notification configuration lacks email settings")

    def text(key: str) -> str:
        value = email.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"email.{key} must be non-empty text")
        return value

    return NotificationSettings(
        region=text("region"),
        sender_parameter=text("sender_parameter"),
        public_base_url_parameter=text("public_base_url_parameter"),
    )


def _plain_language(text: str, context: str) -> str:
    lowered = text.casefold()
    found = sorted(
        word
        for word in BANNED_HUMAN_WORDS
        if (
            re.search(rf"\b{re.escape(word)}\b", lowered) is not None
            if " " not in word
            else word in lowered
        )
    )
    if found:
        raise ValueError(f"{context} contained prohibited internal wording: {', '.join(found)}")
    return text


def _required_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be non-empty text")
    return value.strip()


def _evidence_lines(value: object, context: str) -> list[tuple[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context} must contain at least one primary record")
    output: list[tuple[str, str]] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, dict):
            raise ValueError(f"{context}[{index}] was not an object")
        url = _required_text(raw.get("url"), f"{context}[{index}].url")
        if not url.startswith(("https://", "http://", "/")):
            raise ValueError(f"{context}[{index}].url was not an allowed record link")
        label = _required_text(raw.get("label"), f"{context}[{index}].label")
        page = raw.get("page_number")
        page_text = f" (PDF page {page})" if isinstance(page, int) else ""
        captured_at = _required_text(
            raw.get("captured_at"), f"{context}[{index}].captured_at"
        )
        output.append((f"{label}{page_text} — captured {captured_at}", url))
    return output


def render_finding_email(
    finding: JSONObject,
    public_base_url: str,
) -> EmailMessage:
    finding_id = _required_text(finding.get("finding_id"), "finding.finding_id")
    city = _required_text(finding.get("city"), "finding.city")
    brief = finding.get("brief")
    decision = finding.get("decision")
    if not isinstance(brief, dict) or not isinstance(decision, dict):
        raise ValueError("Finding has no stored brief and decision")
    heading = _plain_language(
        _required_text(brief.get("heading"), "finding.brief.heading"),
        "Finding heading",
    )
    lines = brief.get("lines")
    if not isinstance(lines, list):
        raise ValueError("Finding brief lines were not a list")
    text_lines = [heading, "", f"City: {city}", ""]
    html_lines = [f"<h1>{html.escape(heading)}</h1>", f"<p>City: {html.escape(city)}</p>"]
    for index, raw_line in enumerate(lines):
        if not isinstance(raw_line, dict):
            raise ValueError(f"Finding brief line {index} was not an object")
        line_text = _plain_language(
            _required_text(raw_line.get("text"), f"finding.brief.lines[{index}].text"),
            f"Finding brief line {index}",
        )
        evidence = _evidence_lines(
            raw_line.get("evidence"), f"finding.brief.lines[{index}].evidence"
        )
        text_lines.append(line_text)
        for label, url in evidence:
            text_lines.append(f"  See {label}: {url}")
        text_lines.append("")
        html_lines.append(f"<p>{html.escape(line_text)}</p><ul>")
        for label, url in evidence:
            html_lines.append(
                f'<li><a href="{html.escape(url, quote=True)}">'
                f"See {html.escape(label)}</a></li>"
            )
        html_lines.append("</ul>")
    limitation = _plain_language(
        _required_text(
            brief.get("limitation"),
            "finding.brief.limitation",
        ),
        "Finding limitation",
    )
    restraint = "Page 47 does not determine why these changes were made."
    if restraint not in limitation:
        limitation = f"{limitation} {restraint}"
    text_lines.extend((limitation, "", "Read the complete review:", ""))
    html_lines.append(f"<p>{html.escape(limitation)}</p>")
    review_url = (
        f"{public_base_url.rstrip('/')}/finding/{quote(city, safe='')}/{quote(finding_id, safe='')}"
    )
    text_lines.append(review_url)
    html_lines.append(
        f'<p><a href="{html.escape(review_url, quote=True)}">Read the complete review</a></p>'
    )
    manage_url = finding.get("manage_url")
    if manage_url is not None:
        manage_url = _required_text(manage_url, "finding.manage_url")
        if not manage_url.startswith(("https://", "http://")):
            raise ValueError("finding.manage_url was not an HTTP(S) URL")
        text_lines.extend(("", "Manage or stop this watch:", manage_url))
        html_lines.append(
            f'<p><a href="{html.escape(manage_url, quote=True)}">Manage or stop this watch</a></p>'
        )
    subject = _plain_language(f"Page 47 review for {city}", "Email subject")
    return EmailMessage(subject, "\n".join(text_lines), "".join(html_lines))


def _parameter_value(client: ParameterClient, name: str) -> str:
    response = _json_object(
        client.get_parameter(Name=name, WithDecryption=True),
        f"SSM parameter response for {name}",
    )
    parameter = response.get("Parameter")
    if not isinstance(parameter, dict):
        raise ValueError(f"SSM parameter response for {name} had no Parameter object")
    return _required_text(parameter.get("Value"), f"SSM parameter {name}.Value")


def _provider_message_id(value: object) -> str:
    response = _json_object(value, "SES response")
    return _required_text(response.get("MessageId"), "SES response MessageId")


class EmailDelivery:
    def __init__(self, settings: NotificationSettings) -> None:
        try:
            import boto3
        except ImportError as error:
            raise RuntimeError("boto3 is required for email delivery") from error
        session = cast(AwsSession, boto3.Session())
        self.parameters = cast(
            ParameterClient,
            session.client("ssm", region_name=settings.region),
        )
        self.email = cast(EmailClient, session.client("sesv2", region_name=settings.region))
        self.settings = settings

    def send(self, finding: JSONObject) -> str:
        sender = _parameter_value(self.parameters, self.settings.sender_parameter)
        public_base_url = _parameter_value(
            self.parameters, self.settings.public_base_url_parameter
        )
        if not public_base_url.startswith(("https://", "http://")):
            raise ValueError("The public URL parameter must be an HTTP(S) URL")
        message_finding = dict(finding)
        watch_id = _required_text(finding.get("watch_id"), "finding.watch_id")
        message_finding["manage_url"] = (
            f"{public_base_url.rstrip('/')}/watch/{quote(watch_id, safe='')}"
        )
        message = render_finding_email(message_finding, public_base_url)
        response = self.email.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [_required_text(finding.get("recipient"), "recipient")]},
            Content={
                "Simple": {
                    "Subject": {"Data": message.subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": message.text, "Charset": "UTF-8"},
                        "Html": {"Data": message.html, "Charset": "UTF-8"},
                    },
                }
            },
        )
        return _provider_message_id(response)


def _watch_bodies(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} was not a list")
    output: list[str] = []
    for index, item in enumerate(value):
        output.append(_required_text(item, f"{context}[{index}]"))
    if not output:
        raise ValueError(f"{context} was empty")
    return tuple(output)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _notification_id(watch_id: str, finding_id: str) -> str:
    return sha256(f"{watch_id}\0{finding_id}".encode()).hexdigest()


def _finding_for_delivery(
    store: RecordStore,
    city: str,
    finding_id: str,
    recipient: str,
) -> JSONObject:
    matches = [
        item
        for item in store.finding_rows(city, 200)
        if item.get("finding_id") == finding_id
    ]
    if not matches:
        raise LookupError(f"Finding {finding_id} was not found")
    finding = dict(matches[0])
    if finding.get("publish") is not True:
        raise ValueError(f"Finding {finding_id} is not marked for delivery")
    finding["recipient"] = recipient
    return finding


def _body_selected(case: MatterCase, bodies: tuple[str, ...]) -> bool:
    return any(item.body_name in bodies for item in case.appearances)


def _area_for_watch(
    case: MatterCase,
    address: str | None,
    neighbourhood: str | None,
    address_settings: AddressSettings,
    evidence_root: Path,
) -> AreaMatch:
    geocoded = (
        census_lookup(address, address_settings, evidence_root)
        if address is not None
        else None
    )
    return match_case_to_area(case, geocoded, neighbourhood)


def deliver_finding(
    store: RecordStore,
    city: str,
    finding_id: str,
    evidence_root: Path,
    address_config: Path,
    notification_config: Path,
) -> JSONObject:
    """Deliver a stored finding once to each matching active watch."""

    settings = load_notification_settings(notification_config)
    address_settings = load_address_settings(address_config)
    watches = store.watch_rows(city)
    finding_rows = store.finding_rows(city, 200)
    matter_id = _required_int(finding_rows, finding_id)
    total = 0
    sent = 0
    skipped = 0
    delivery: EmailDelivery | None = None
    for watch in watches:
        watch_id = _required_text(watch.get("watch_id"), "watch.watch_id")
        bodies = _watch_bodies(watch.get("bodies"), "watch.bodies")
        recipient = _required_text(watch.get("email"), "watch.email")
        if store.notification_sent(watch_id, finding_id):
            continue
        total += 1
        case = load_matter_case(
            store,
            city,
            matter_id,
            evidence_root,
        )
        now = _now()
        notification_id = _notification_id(watch_id, finding_id)
        if not _body_selected(case, bodies):
            store.save_notification(
                NotificationObservation(
                    notification_id,
                    watch_id,
                    city,
                    finding_id,
                    "skipped",
                    "body_not_selected",
                    "The matter was not heard by one of the public bodies in this watch.",
                    None,
                    None,
                    now,
                    now,
                )
            )
            store.commit()
            skipped += 1
            continue
        area = _area_for_watch(
            case,
            _optional_text(watch.get("address")),
            _optional_text(watch.get("neighbourhood")),
            address_settings,
            evidence_root,
        )
        if area.status != "confirmed":
            store.save_notification(
                NotificationObservation(
                    notification_id,
                    watch_id,
                    city,
                    finding_id,
                    "skipped",
                    area.status,
                    area.reason,
                    None,
                    None,
                    now,
                    now,
                )
            )
            store.commit()
            skipped += 1
            continue
        finding = _finding_for_delivery(store, city, finding_id, recipient)
        finding["watch_id"] = watch_id
        try:
            if delivery is None:
                delivery = EmailDelivery(settings)
            provider_id = delivery.send(finding)
        except Exception as error:
            store.save_notification(
                NotificationObservation(
                    notification_id,
                    watch_id,
                    city,
                    finding_id,
                    "failed",
                    area.status,
                    area.reason,
                    None,
                    f"{type(error).__name__}: email delivery failed",
                    now,
                    _now(),
                )
            )
            store.commit()
            raise
        store.save_notification(
            NotificationObservation(
                notification_id,
                watch_id,
                city,
                finding_id,
                "sent",
                area.status,
                area.reason,
                provider_id,
                None,
                now,
                _now(),
            )
        )
        store.commit()
        sent += 1
    return {
        "city": city,
        "finding_id": finding_id,
        "watches_considered": total,
        "sent": sent,
        "skipped": skipped,
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return _required_text(value, "watch text")


def _required_int(rows: list[JSONObject], finding_id: str) -> int:
    for row in rows:
        if row.get("finding_id") == finding_id:
            value = row.get("matter_id")
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Finding {finding_id} had an invalid matter ID")
            return value
    raise LookupError(f"Finding {finding_id} was not found")
