from __future__ import annotations

import json
from pathlib import Path

from test_analysis import case

from page47.runtime.client import load_agentcore_settings
from page47.runtime.transport import request_bytes, request_from_case
from scripts.deploy_agentcore import _client_token, load_deployment_settings


def test_agentcore_is_explicitly_disabled_until_a_runtime_arn_is_configured() -> None:
    settings = load_agentcore_settings(Path("config/agentcore.yaml"))
    assert settings.enabled is False
    assert settings.region == "eu-west-2"
    assert settings.runtime_arn_parameter == "/page47/agentcore/runtime-arn"


def test_agentcore_runtime_name_matches_service_constraints() -> None:
    settings = load_deployment_settings(Path("config/agentcore.yaml"))
    assert settings.runtime_name == "page47_review"


def test_runtime_request_is_deterministic_and_carries_case_identity() -> None:
    matter = case("regular", "consent")
    first = request_bytes(matter)
    second = request_bytes(matter)
    assert first == second
    assert json.loads(first) == request_from_case(matter)
    payload = json.loads(first)
    assert payload["city"] == "Test city"
    assert payload["matter_id"] == 7
    assert payload["documents"] == []


def test_agentcore_client_token_meets_api_minimum_length() -> None:
    token = _client_token()
    assert len(token) >= 33
    assert token.startswith("page47-")
    assert token[-1].isalnum()
