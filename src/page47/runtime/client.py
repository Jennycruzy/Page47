"""Typed client for calling the deployed Page 47 AgentCore runtime."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

import yaml

from page47.analysis.case import MatterCase
from page47.runtime.transport import request_bytes
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value


class ParameterClient(Protocol):
    def get_parameter(self, *, Name: str, WithDecryption: bool) -> object: ...


class RuntimeClient(Protocol):
    def invoke_agent_runtime(self, **kwargs: object) -> object: ...


class AwsSession(Protocol):
    def client(self, service_name: str, *, region_name: str) -> object: ...


@dataclass(frozen=True, slots=True)
class AgentCoreSettings:
    enabled: bool
    region: str
    runtime_arn_parameter: str
    qualifier: str | None


def _object(value: object, context: str) -> JSONObject:
    decoded = _aws_json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"AgentCore {context} was not an object")
    return decoded


def _aws_json_value(value: object) -> JSONValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_aws_json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("AgentCore AWS response keys must be text")
            output[key] = _aws_json_value(item)
        return output
    raise ValueError(f"Unsupported AgentCore AWS response value: {type(value).__name__}")


def _text(value: JSONObject, key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"AgentCore {context}.{key} must be non-empty text")
    return item.strip()


def load_agentcore_settings(path: Path) -> AgentCoreSettings:
    decoded: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = _object(decoded, "configuration")
    runtime = _object(root.get("runtime"), "runtime")
    invocation = _object(runtime.get("invocation"), "runtime.invocation")
    enabled = invocation.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("AgentCore runtime.invocation.enabled must be a boolean")
    qualifier = invocation.get("qualifier")
    if qualifier is not None and (not isinstance(qualifier, str) or not qualifier.strip()):
        raise ValueError("AgentCore runtime.invocation.qualifier must be non-empty text")
    return AgentCoreSettings(
        enabled=enabled,
        region=_text(invocation, "region", "runtime.invocation"),
        runtime_arn_parameter=_text(
            invocation,
            "runtime_arn_parameter",
            "runtime.invocation",
        ),
        qualifier=qualifier.strip() if isinstance(qualifier, str) else None,
    )


def _parameter_value(client: ParameterClient, name: str) -> str:
    decoded = _object(
        client.get_parameter(Name=name, WithDecryption=True),
        f"parameter response for {name}",
    )
    parameter = _object(decoded.get("Parameter"), f"parameter response for {name}.Parameter")
    return _required_parameter_text(parameter.get("Value"), name)


def _required_parameter_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"AgentCore SSM parameter {name} had no value")
    return value.strip()


def _response_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("AgentCore response was not an object")
    if not all(isinstance(key, str) for key in value):
        raise ValueError("AgentCore response contained a non-text key")
    return cast(dict[str, object], value)


def _response_body(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, bytearray):
        return bytes(value)
    reader = getattr(value, "read", None)
    if not callable(reader):
        raise ValueError("AgentCore response had no readable body")
    body = cast(Callable[[], object], reader)()
    if isinstance(body, bytes):
        return body
    if isinstance(body, bytearray):
        return bytes(body)
    raise ValueError("AgentCore response body was not bytes")


class AgentCoreTransport:
    """Invoke one deployed runtime and validate its JSON result."""

    def __init__(self, settings: AgentCoreSettings) -> None:
        if not settings.enabled:
            raise ValueError("AgentCore transport cannot be created while it is disabled")
        try:
            import boto3
        except ImportError as error:
            raise RuntimeError("boto3 is required for AgentCore transport") from error
        session = cast(AwsSession, boto3.Session())
        self.parameters = cast(
            ParameterClient,
            session.client("ssm", region_name=settings.region),
        )
        self.runtime = cast(
            RuntimeClient,
            session.client("bedrock-agentcore", region_name=settings.region),
        )
        self.settings = settings

    def invoke_case(self, case: MatterCase) -> JSONObject:
        runtime_arn = _parameter_value(
            self.parameters,
            self.settings.runtime_arn_parameter,
        )
        payload = request_bytes(case)
        kwargs: dict[str, object] = {
            "contentType": "application/json",
            "accept": "application/json",
            "agentRuntimeArn": runtime_arn,
            "runtimeSessionId": uuid4().hex + uuid4().hex,
            "payload": payload,
        }
        if self.settings.qualifier is not None:
            kwargs["qualifier"] = self.settings.qualifier
        response = _response_object(self.runtime.invoke_agent_runtime(**kwargs))
        status = response.get("statusCode")
        if isinstance(status, bool) or not isinstance(status, int):
            raise ValueError("AgentCore response had no integer status code")
        if status != 200:
            raise RuntimeError(f"AgentCore runtime returned HTTP status {status}")
        decoded: object = json.loads(_response_body(response.get("response")))
        value: JSONValue = as_json_value(decoded)
        if not isinstance(value, dict):
            raise ValueError("AgentCore runtime returned a non-object JSON result")
        return value
