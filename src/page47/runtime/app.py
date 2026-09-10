"""Bedrock AgentCore entrypoint for one Page 47 investigation."""

from __future__ import annotations

import os
from pathlib import Path
from threading import Lock

import yaml
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from page47.runtime.transport import context_from_request
from page47.snapshotter.config import JSONObject, as_json_value


def _configure_telemetry() -> None:
    """Connect Strands spans to the AgentCore-provided OTLP collector when enabled."""

    if os.environ.get("AGENT_OBSERVABILITY_ENABLED", "").casefold() != "true":
        return
    from strands.telemetry import StrandsTelemetry

    StrandsTelemetry().setup_otlp_exporter()


def _config_path(name: str) -> Path:
    configured_root = os.environ.get("PAGE47_CONFIG_DIR")
    if configured_root is not None and configured_root.strip():
        return Path(configured_root) / name
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find config/{name} above the package")


def _working_directory() -> Path:
    configured = os.environ.get("PAGE47_AGENTCORE_WORKING_DIRECTORY")
    if configured is None or not configured.strip():
        decoded = as_json_value(
            yaml.safe_load(_config_path("agentcore.yaml").read_text(encoding="utf-8"))
        )
        if not isinstance(decoded, dict):
            raise ValueError("AgentCore configuration was not an object")
        runtime = decoded.get("runtime")
        if not isinstance(runtime, dict):
            raise ValueError("AgentCore configuration lacks runtime settings")
        configured_value = runtime.get("working_directory")
        if not isinstance(configured_value, str) or not configured_value.strip():
            raise ValueError("runtime.working_directory must be non-empty text")
        configured = configured_value
    path = Path(configured)
    path.mkdir(parents=True, exist_ok=True)
    return path


_configure_telemetry()
app = BedrockAgentCoreApp()
INVOCATION_LOCK = Lock()


@app.entrypoint
def invoke(payload: object) -> JSONObject:
    # Strands Agent instances are stateful and do not support overlapping
    # requests. AgentCore can dispatch more than one request to a warm runtime,
    # so serialize graph execution within the process.
    from page47.agents.graph import graph_result_payload, invoke_investigation

    with INVOCATION_LOCK:
        context = context_from_request(
            payload,
            _config_path("models.yaml"),
            _working_directory(),
        )
        return graph_result_payload(invoke_investigation(context))


if __name__ == "__main__":
    app.run()
