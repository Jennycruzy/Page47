"""Run one stored matter through the review graph and save its decision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel
from strands.agent import AgentResult
from strands.multiagent import GraphResult

from page47.agents.graph import invoke_investigation
from page47.agents.schemas import (
    AgentEvidence,
    AgentObservation,
    ArchivistReport,
    BriefWriterReport,
    ProcessReport,
    SkepticReport,
    SubstanceReport,
)
from page47.analysis.case import InvestigationContext, MatterCase, load_matter_case
from page47.analysis.drift import (
    DriftComparison,
    DriftLedger,
    EvidenceLink,
    compare_all_appearances,
    load_presentation_config,
)
from page47.analysis.norms import (
    HistoricalNorm,
    NormSettings,
    compute_historical_norms,
    load_norm_settings,
)
from page47.analysis.policy import (
    AgentReports,
    EvidenceDecision,
    EvidencePolicyConfig,
    ReviewedObservation,
    ReviewRejection,
    apply_evidence_policy,
    load_policy_config,
)
from page47.models.config import ModelSettings, load_model_settings
from page47.records.store import (
    FindingObservation,
    InvestigationRunObservation,
    RecordStore,
    stable_json,
)
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value


@dataclass(frozen=True, slots=True)
class InvestigationOutcome:
    run_id: str
    case: MatterCase
    drift: DriftLedger
    norm: HistoricalNorm | None
    decision: EvidenceDecision
    brief: BriefWriterReport
    graph_result: JSONObject


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _evidence(item: AgentEvidence) -> EvidenceLink:
    return EvidenceLink(
        label=item.label,
        url=item.url,
        captured_at=item.captured_at,
        page_number=item.page_number,
    )


def _evidence_json(link: EvidenceLink) -> JSONObject:
    return {
        "label": link.label,
        "url": link.url,
        "captured_at": link.captured_at,
        "page_number": link.page_number,
    }


def _observation(item: AgentObservation) -> ReviewedObservation:
    return ReviewedObservation(
        observation_id=item.observation_id,
        direction=item.direction,
        text=item.statement,
        evidence=tuple(_evidence(evidence) for evidence in item.evidence),
    )


def _substance_observations(report: SubstanceReport) -> tuple[ReviewedObservation, ...]:
    output: list[ReviewedObservation] = []
    for change in report.changes:
        if change.before is not None and change.after is not None:
            values = f"{change.before} to {change.after}"
        elif change.value is not None:
            values = change.value
        else:
            raise ValueError(f"Substance observation {change.observation_id} had no value")
        statement = change.statement
        if not statement.strip():
            statement = f"The document states {change.subject}: {values}."
        output.append(
            ReviewedObservation(
                observation_id=change.observation_id,
                direction="neutral",
                text=statement,
                evidence=(_evidence(change.evidence),),
            )
        )
    return tuple(output)


def _node_report[ReportModel: BaseModel](
    graph: GraphResult, node_id: str, model: type[ReportModel]
) -> ReportModel:
    node = graph.results.get(node_id)
    if node is None:
        raise ValueError(f"Graph did not return node {node_id}")
    result = node.result
    if not isinstance(result, AgentResult):
        raise ValueError(f"Graph node {node_id} returned {type(result).__name__}")
    structured = result.structured_output
    if not isinstance(structured, model):
        raise ValueError(f"Graph node {node_id} returned no validated structured report")
    return structured


def _graph_payload(graph: GraphResult) -> JSONObject:
    nodes: JSONObject = {}
    for node_id, node in sorted(graph.results.items()):
        result = node.result
        if isinstance(result, AgentResult):
            structured = result.structured_output
            if isinstance(structured, BaseModel):
                nodes[node_id] = as_json_value(structured.model_dump(mode="json"))
            else:
                nodes[node_id] = {"status": "no_structured_report"}
        elif isinstance(result, Exception):
            nodes[node_id] = {"status": "error", "type": type(result).__name__}
        else:
            nodes[node_id] = {"status": type(result).__name__}
    payload: JSONObject = {
        "status": str(graph.status),
        "total_nodes": graph.total_nodes,
        "completed_nodes": graph.completed_nodes,
        "failed_nodes": graph.failed_nodes,
        "execution_count": graph.execution_count,
        "execution_time": graph.execution_time,
        "nodes": nodes,
    }
    return payload


def _structural_observation(
    comparison: DriftComparison | None,
) -> tuple[ReviewedObservation, ...]:
    if comparison is None:
        return ()
    output: list[ReviewedObservation] = []
    for item in comparison.observations:
        output.append(
            ReviewedObservation(
                observation_id=f"record-{item.key}",
                direction=item.direction,
                text=item.text,
                evidence=item.evidence,
            )
        )
    return tuple(output)


def _norm_for_case(norms: tuple[HistoricalNorm, ...], case: MatterCase) -> HistoricalNorm | None:
    body_name = case.matter.body_name
    if body_name is None:
        return None
    for norm in norms:
        if norm.body_name == body_name:
            return norm
    return None


def _finding_id(city: str, matter_id: int) -> str:
    return f"{city.casefold().replace(' ', '-')}-{matter_id}"


def _decision_json(decision: EvidenceDecision) -> JSONObject:
    payload: JSONObject = {
        "state": decision.state,
        "publish": decision.publish,
        "accepted": [
            {
                "observation_id": item.observation_id,
                "direction": item.direction,
                "text": item.text,
                "evidence": [_evidence_json(link) for link in item.evidence],
            }
            for item in decision.accepted
        ],
        "rejected": [
            {"observation_id": item.observation_id, "reason": item.reason}
            for item in decision.rejected
        ],
        "reason": decision.reason,
        "human_text": decision.human_text,
    }
    return payload


def _save_outcome(
    store: RecordStore,
    outcome: InvestigationOutcome,
    started_at: str,
    finished_at: str,
) -> None:
    decision_json = _decision_json(outcome.decision)
    norms_json: JSONObject | None = None
    if outcome.norm is not None:
        norm_value = as_json_value(outcome.norm.as_json())
        if not isinstance(norm_value, dict):
            raise ValueError("Historical norm was not an object")
        norms_json = norm_value
    drift_value = as_json_value(outcome.drift.as_json())
    if not isinstance(drift_value, dict):
        raise ValueError("Drift ledger was not an object")
    fingerprint_payload: JSONObject = {
        "matter": outcome.case.structural_payload(),
        "drift": drift_value,
        "decision": decision_json,
        "norm": norms_json,
    }
    fingerprint = sha256(stable_json(fingerprint_payload).encode("utf-8")).hexdigest()
    store.save_investigation_run(
        InvestigationRunObservation(
            run_id=outcome.run_id,
            city=outcome.case.city,
            matter_id=outcome.case.matter_id,
            started_at=started_at,
            finished_at=finished_at,
            status="completed",
            graph_result=outcome.graph_result,
            policy=decision_json,
            error=None,
        )
    )
    store.save_finding(
        FindingObservation(
            finding_id=_finding_id(outcome.case.city, outcome.case.matter_id),
            city=outcome.case.city,
            matter_id=outcome.case.matter_id,
            state=outcome.decision.state,
            publish=outcome.decision.publish,
            supported_count=len(outcome.decision.accepted),
            rejected_count=len(outcome.decision.rejected),
            decision=decision_json,
            brief=_brief_json(outcome.brief),
            norms=norms_json,
            fingerprint=fingerprint,
            created_at=started_at,
            updated_at=finished_at,
        )
    )
    store.commit()


def _brief_json(brief: BriefWriterReport) -> JSONObject:
    value: JSONValue = as_json_value(brief.model_dump(mode="json"))
    if not isinstance(value, dict):
        raise ValueError("Brief writer report was not an object")
    return value


def investigate_matter(
    store: RecordStore,
    city: str,
    matter_id: int,
    evidence_root: Path,
    models_path: Path,
    presentation_path: Path,
    policy_path: Path,
    norms_path: Path,
) -> InvestigationOutcome:
    """Run, review, and persist one matter; errors remain visible in run history."""

    started_at = _now()
    run_id = uuid4().hex
    model_settings: ModelSettings = load_model_settings(models_path)
    presentation_config = load_presentation_config(presentation_path)
    policy_config: EvidencePolicyConfig = load_policy_config(policy_path)
    norm_settings: NormSettings = load_norm_settings(norms_path)
    case = load_matter_case(store, city, matter_id, evidence_root)
    drift = compare_all_appearances(case, presentation_config)
    norms = compute_historical_norms(store.connection, norm_settings)
    norm = _norm_for_case(norms, case)
    try:
        graph = invoke_investigation(
            InvestigationContext(case=case, evidence_root=evidence_root, models=model_settings)
        )
        archivist = _node_report(graph, "archivist", ArchivistReport)
        substance = _node_report(graph, "substance", SubstanceReport)
        process = _node_report(graph, "process", ProcessReport)
        skeptic = _node_report(graph, "skeptic", SkepticReport)
        brief = _node_report(graph, "brief_writer", BriefWriterReport)
        observations = (
            tuple(_observation(item) for item in archivist.observations)
            + _substance_observations(substance)
            + tuple(_observation(item) for item in process.observations)
        )
        structural = _structural_observation(
            drift.comparisons[-1] if drift.comparisons else None
        )
        by_id: dict[str, ReviewedObservation] = {}
        for observation in observations + structural:
            if observation.observation_id in by_id:
                raise ValueError(f"Duplicate observation ID {observation.observation_id}")
            by_id[observation.observation_id] = observation
        accepted = frozenset(skeptic.accepted_observation_ids)
        unknown_accepted = accepted - by_id.keys()
        if unknown_accepted:
            raise ValueError(f"Skeptic accepted unknown observations: {sorted(unknown_accepted)}")
        rejections = tuple(
            ReviewRejection(item.observation_id, item.reason)
            for item in skeptic.rejected_observations
        )
        unknown_rejected = {item.observation_id for item in rejections} - by_id.keys()
        if unknown_rejected:
            raise ValueError(f"Skeptic rejected unknown observations: {sorted(unknown_rejected)}")
        report = AgentReports(observations, accepted, rejections)
        decision = apply_evidence_policy(report, policy_config)
        accepted_ids = {item.observation_id for item in decision.accepted}
        for line in brief.lines:
            if line.observation_id not in accepted_ids:
                raise ValueError(
                    f"Brief writer cited observation not accepted by review: {line.observation_id}"
                )
        outcome = InvestigationOutcome(
            run_id=run_id,
            case=case,
            drift=drift,
            norm=norm,
            decision=decision,
            brief=brief,
            graph_result=_graph_payload(graph),
        )
        _save_outcome(store, outcome, started_at, _now())
        return outcome
    except Exception as error:
        finished_at = _now()
        store.save_investigation_run(
            InvestigationRunObservation(
                run_id=run_id,
                city=city,
                matter_id=matter_id,
                started_at=started_at,
                finished_at=finished_at,
                status="failed",
                graph_result={"status": "failed"},
                policy=None,
                error=f"{type(error).__name__}: {error}",
            )
        )
        store.commit()
        raise
