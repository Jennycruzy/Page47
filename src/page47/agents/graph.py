"""Build the five-node investigation graph once at module load."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel
from strands import Agent
from strands.agent import AgentResult
from strands.models import BedrockModel
from strands.multiagent import GraphBuilder, GraphResult
from strands.multiagent.graph import Graph, GraphState

from page47.agents.schemas import (
    ArchivistReport,
    BriefWriterReport,
    ProcessReport,
    SkepticReport,
    SubstanceAgentReport,
)
from page47.agents.tools import (
    list_attachment_documents,
    read_attachment_document,
    read_presentation_record,
    read_record,
)
from page47.analysis.case import InvestigationContext
from page47.models.config import ModelSettings, load_model_settings

type JSONScalar = None | bool | int | float | str
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]

def _config_path(name: str) -> Path:
    configured_root = os.environ.get("PAGE47_CONFIG_DIR")
    if configured_root is not None and configured_root.strip():
        return Path(configured_root) / name
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find config/{name} above the package")


def _json_value(value: object) -> JSONValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    raise ValueError(f"Unsupported agent configuration value: {type(value).__name__}")


def _object(value: JSONValue | None, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object for {context}")
    return value


def _text(value: JSONObject, key: str, context: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{context}.{key} must be non-empty text")
    return item


def _integer(value: JSONObject, key: str, context: str, minimum: int) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int) or item < minimum:
        raise ValueError(f"{context}.{key} must be an integer of at least {minimum}")
    return item


def _review_inputs_ready(state: GraphState) -> bool:
    """Allow the review node to run only after all three readers finish."""

    completed_ids = {node.node_id for node in state.completed_nodes}
    return {"archivist", "substance", "process"}.issubset(completed_ids)


def _agent_settings() -> tuple[ModelSettings, JSONObject, JSONObject]:
    model_settings = load_model_settings(_config_path("models.yaml"))
    decoded: object = yaml.safe_load(_config_path("agents.yaml").read_text(encoding="utf-8"))
    root = _object(_json_value(decoded), "agent configuration")
    graph = _object(root.get("graph"), "graph")
    prompts = _object(root.get("prompts"), "prompts")
    return model_settings, graph, prompts


def _make_agent(
    settings: ModelSettings,
    prompts: JSONObject,
    name: str,
    output_model: type,
    tools: list[object] | None = None,
) -> Agent:
    route = settings.agent_model(name)
    model = BedrockModel(
        model_id=route.model_id,
        region_name=settings.region,
        temperature=settings.temperature,
        max_tokens=settings.agent_max_output_tokens,
        streaming=settings.streaming,
    )
    prompt = _text(prompts, name, "prompts")
    return Agent(
        model=model,
        name=name,
        callback_handler=None,
        system_prompt=prompt,
        tools=tools,
        structured_output_model=output_model,
    )


def build_investigation_graph() -> Graph:
    settings, graph_config, prompts = _agent_settings()
    archivist = _make_agent(settings, prompts, "archivist", ArchivistReport, [read_record])
    substance = _make_agent(
        settings,
        prompts,
        "substance",
        SubstanceAgentReport,
        [list_attachment_documents, read_attachment_document],
    )
    process = _make_agent(
        settings,
        prompts,
        "process",
        ProcessReport,
        [read_presentation_record],
    )
    skeptic = _make_agent(settings, prompts, "skeptic", SkepticReport)
    brief_writer = _make_agent(settings, prompts, "brief_writer", BriefWriterReport)

    builder = GraphBuilder()
    builder.add_node(archivist, "archivist")
    builder.add_node(substance, "substance")
    builder.add_node(process, "process")
    builder.add_node(skeptic, "skeptic")
    builder.add_node(brief_writer, "brief_writer")
    builder.add_edge("archivist", "substance")
    builder.add_edge("archivist", "process")
    builder.add_edge("archivist", "skeptic", _review_inputs_ready)
    builder.add_edge("substance", "skeptic", _review_inputs_ready)
    builder.add_edge("process", "skeptic", _review_inputs_ready)
    builder.add_edge("skeptic", "brief_writer")
    builder.set_entry_point("archivist")
    builder.set_graph_id(_text(graph_config, "id", "graph"))
    builder.set_execution_timeout(
        float(_integer(graph_config, "execution_timeout_seconds", "graph", 1))
    )
    builder.set_node_timeout(
        float(_integer(graph_config, "node_timeout_seconds", "graph", 1))
    )
    builder.set_max_node_executions(_integer(graph_config, "max_node_executions", "graph", 1))
    return builder.build()


INVESTIGATION_GRAPH: Graph = build_investigation_graph()


def invoke_investigation(context: InvestigationContext) -> GraphResult:
    """Run an isolated graph with the matter carried in invocation state.

    Strands agents keep invocation state on their instances and reject
    overlapping calls. Build a fresh graph for each investigation so warm
    AgentCore processes cannot reuse an agent from another request.
    """

    graph = build_investigation_graph()
    return graph(
        "Investigate the supplied public matter and return the requested structured result.",
        invocation_state={"page47_context": context},
    )


def graph_result_payload(graph: GraphResult) -> JSONObject:
    """Serialize validated node reports for the runtime transport."""

    nodes: JSONObject = {}
    for node_id, node in sorted(graph.results.items()):
        result = node.result
        if isinstance(result, AgentResult):
            structured = result.structured_output
            if isinstance(structured, BaseModel):
                nodes[node_id] = _json_value(structured.model_dump(mode="json"))
            else:
                nodes[node_id] = {"status": "no_structured_report"}
        elif isinstance(result, Exception):
            nodes[node_id] = {"status": "error", "type": type(result).__name__}
        else:
            nodes[node_id] = {"status": type(result).__name__}
    return {
        "status": str(graph.status),
        "total_nodes": graph.total_nodes,
        "completed_nodes": graph.completed_nodes,
        "failed_nodes": graph.failed_nodes,
        "execution_count": graph.execution_count,
        "execution_time": graph.execution_time,
        "nodes": nodes,
    }
