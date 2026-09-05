#!/usr/bin/env python3
"""Verify the configured Bedrock models without storing credentials or model text."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from page47.models.config import ModelSettings, load_model_settings

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]

AWS_ACCOUNT_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<!\d)\d{12}(?!\d)")
AWS_ARN_PATTERN: Final[re.Pattern[str]] = re.compile(r"arn:aws:[^\s,]+")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def redact(message: str) -> str:
    return AWS_ACCOUNT_PATTERN.sub(
        "<aws-account-redacted>", AWS_ARN_PATTERN.sub("<aws-arn-redacted>", message)
    )


def json_value(value: object) -> JSONValue:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        output: JSONObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("AWS response key was not text")
            output[key] = json_value(item)
        return output
    raise ValueError(f"Unsupported AWS response value: {type(value).__name__}")


def object_value(value: object, context: str) -> JSONObject:
    decoded = json_value(value)
    if not isinstance(decoded, dict):
        raise ValueError(f"Expected an object for {context}")
    return decoded


def text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Expected non-empty text for {context}")
    return value


def text_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Expected a list of text for {context}")
    return list(value)


def selected_ids(settings: ModelSettings) -> tuple[str, ...]:
    ids = [settings.triage.model_id, settings.document.model_id]
    ids.extend(route.model_id for route in settings.agents)
    return tuple(dict.fromkeys(ids))


def verify(settings: ModelSettings) -> JSONObject:
    import boto3

    control = boto3.client("bedrock", region_name=settings.region)
    runtime = boto3.client("bedrock-runtime", region_name=settings.region)
    models: JSONObject = {}
    for model_id in selected_ids(settings):
        metadata: JSONObject = {"model_id": model_id}
        try:
            raw_details: object = control.get_foundation_model(modelIdentifier=model_id)
            details = object_value(raw_details, f"{model_id} metadata response")
            raw_model = details.get("modelDetails")
            model = object_value(raw_model, f"{model_id} modelDetails")
            metadata.update(
                {
                    "provider": text(model.get("providerName"), f"{model_id}.providerName"),
                    "input_modalities": text_list(
                        model.get("inputModalities"), f"{model_id}.inputModalities"
                    ),
                    "output_modalities": text_list(
                        model.get("outputModalities"), f"{model_id}.outputModalities"
                    ),
                    "response_streaming_supported": model.get("responseStreamingSupported"),
                }
            )
            metadata["metadata_status"] = "available"
        except Exception as error:
            metadata["metadata_status"] = "failed"
            metadata["metadata_error_type"] = type(error).__name__
            metadata["metadata_error"] = redact(str(error))

        try:
            raw_response: object = runtime.converse(
                modelId=model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": "Reply with the single word available."}],
                    }
                ],
                inferenceConfig={"maxTokens": 16, "temperature": settings.temperature},
            )
            response = object_value(raw_response, f"{model_id} invocation response")
            metadata["invocation_status"] = "available"
            metadata["stop_reason"] = text(response.get("stopReason"), f"{model_id}.stopReason")
            usage = response.get("usage")
            if usage is not None:
                metadata["usage"] = json_value(usage)
        except Exception as error:
            metadata["invocation_status"] = "failed"
            metadata["invocation_error_type"] = type(error).__name__
            metadata["invocation_error"] = redact(str(error))
        models[model_id] = metadata
    return {
        "schema_version": 1,
        "captured_at": utc_now(),
        "region": settings.region,
        "selected_model_ids": list(selected_ids(settings)),
        "models": models,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify configured Bedrock models")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = load_model_settings(args.config)
    result = verify(settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
