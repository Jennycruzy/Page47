from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from strands.multiagent.graph import GraphState
from test_analysis import case

from page47.agents.graph import INVESTIGATION_GRAPH, _review_inputs_ready
from page47.runtime.client import _aws_json_value, load_agentcore_settings
from page47.runtime.transport import request_bytes, request_from_case
from scripts.deploy_agentcore import _client_token, _runtime_arguments, load_deployment_settings


def test_agentcore_is_enabled_after_runtime_deployment() -> None:
    settings = load_agentcore_settings(Path("config/agentcore.yaml"))
    assert settings.enabled is True
    assert settings.region == "eu-west-2"
    assert settings.runtime_arn_parameter == "/page47/agentcore/runtime-arn"


def test_agentcore_runtime_name_matches_service_constraints() -> None:
    settings = load_deployment_settings(Path("config/agentcore.yaml"))
    assert settings.runtime_name == "page47_review"


def test_agentcore_runtime_uses_unified_trace_destination() -> None:
    settings = load_deployment_settings(Path("config/agentcore.yaml"))
    arguments = _runtime_arguments("bucket", "key", "arn:aws:iam::1:role/page47", settings)
    assert arguments["environmentVariables"] == {
        "UNIFIED_TRACES_DESTINATION_ENABLED": "true"
    }


def test_agentcore_aws_response_normalizer_handles_timestamps() -> None:
    timestamp = datetime(2026, 9, 6, 17, 31, 55, tzinfo=UTC)
    normalized = _aws_json_value({"last_modified": timestamp})
    assert normalized == {"last_modified": "2026-09-06T17:31:55+00:00"}


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


def test_review_node_waits_for_all_reader_nodes() -> None:
    state = GraphState(completed_nodes={INVESTIGATION_GRAPH.nodes["archivist"]})
    assert _review_inputs_ready(state) is False
    state.completed_nodes.update(
        {
            INVESTIGATION_GRAPH.nodes["substance"],
            INVESTIGATION_GRAPH.nodes["process"],
        }
    )
    assert _review_inputs_ready(state) is True
    review_edges = [
        edge
        for edge in INVESTIGATION_GRAPH.edges
        if edge.to_node.node_id == "skeptic"
    ]
    assert len(review_edges) == 3
    assert all(edge.condition is _review_inputs_ready for edge in review_edges)
