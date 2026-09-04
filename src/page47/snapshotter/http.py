"""Conditional HTTP access for public record and document URLs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from page47.snapshotter.config import JSONObject

USER_AGENT = "Page47-snapshotter/0.1 (public-record research)"
CAPTURE_HEADERS = frozenset(
    {"etag", "last-modified", "content-type", "retry-after", "content-length"}
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def selected_headers(headers: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers
        if key.lower() in CAPTURE_HEADERS
    }


def optional_text(record: JSONObject | None, key: str) -> str | None:
    if record is None:
        return None
    value = record.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


@dataclass(frozen=True, slots=True)
class FetchResult:
    target: str
    url: str
    captured_at: str
    status: int | None
    headers: dict[str, str]
    body: bytes
    error_type: str | None
    error: str | None
    not_modified: bool


class ConditionalHttpClient:
    """Fetch with validators from the last saved response."""

    def __init__(self, timeout_seconds: float, accept_header: str) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not accept_header.strip():
            raise ValueError("accept_header must not be empty")
        self.timeout_seconds = timeout_seconds
        self.accept_header = accept_header

    def fetch(self, target: str, url: str, previous: JSONObject | None) -> FetchResult:
        request_headers = {
            "User-Agent": USER_AGENT,
            "Accept": self.accept_header,
        }
        etag = optional_text(previous, "etag")
        if etag is not None:
            request_headers["If-None-Match"] = etag
        last_modified = optional_text(previous, "http_last_modified")
        if last_modified is not None:
            request_headers["If-Modified-Since"] = last_modified
        captured_at = utc_now()
        request = Request(url, headers=request_headers)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return FetchResult(
                    target=target,
                    url=url,
                    captured_at=captured_at,
                    status=response.status,
                    headers=selected_headers(response.headers.items()),
                    body=response.read(),
                    error_type=None,
                    error=None,
                    not_modified=False,
                )
        except HTTPError as error:
            body = error.read()
            if error.code == 304:
                return FetchResult(
                    target=target,
                    url=url,
                    captured_at=captured_at,
                    status=304,
                    headers=selected_headers(error.headers.items()),
                    body=body,
                    error_type=None,
                    error=None,
                    not_modified=True,
                )
            return FetchResult(
                target=target,
                url=url,
                captured_at=captured_at,
                status=error.code,
                headers=selected_headers(error.headers.items()),
                body=body,
                error_type=type(error).__name__,
                error=str(error),
                not_modified=False,
            )
        except (URLError, TimeoutError, OSError, ValueError) as error:
            return FetchResult(
                target=target,
                url=url,
                captured_at=captured_at,
                status=None,
                headers={},
                body=b"",
                error_type=type(error).__name__,
                error=str(error),
                not_modified=False,
            )
