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
    BriefLine,
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


type InvestigationReports = tuple[
    ArchivistReport,
    SubstanceReport,
    ProcessReport,
    SkepticReport,
    BriefWriterReport,
]

type EvidenceKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _EvidenceCatalog:
    all_sources: frozenset[EvidenceKey]
    document_sources: frozenset[EvidenceKey]
    attachment_sources: frozenset[EvidenceKey]
    page_sources: dict[EvidenceKey, frozenset[int]]


@dataclass(frozen=True, slots=True)
class _ReviewInputs:
    model_settings: ModelSettings
    case: MatterCase
    drift: DriftLedger
    norm: HistoricalNorm | None
    policy_config: EvidencePolicyConfig


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


def _namespaced_observation(role: str, item: AgentObservation) -> ReviewedObservation:
    observation = _observation(item)
    return ReviewedObservation(
        observation_id=f"{role}:{observation.observation_id}",
        direction=observation.direction,
        text=observation.text,
        evidence=observation.evidence,
    )


def _substance_observations(report: SubstanceReport) -> tuple[ReviewedObservation, ...]:
    output: list[ReviewedObservation] = []
    for change in report.changes:
        if change.before is not None and change.after is not None:
            values = f"{change.before} to {change.after}"
            statement = f"The document records {change.subject}: {values}."
        elif change.value is not None:
            statement = f"The document states: {change.excerpt}"
        else:
            raise ValueError(f"Substance observation {change.observation_id} had no value")
        output.append(
            ReviewedObservation(
                observation_id=f"substance:{change.observation_id}",
                direction="neutral",
                text=statement,
                evidence=(_evidence(change.evidence),),
            )
        )
    return tuple(output)


def _evidence_catalog(case: MatterCase) -> _EvidenceCatalog:
    all_sources: set[EvidenceKey] = set()
    document_sources: set[EvidenceKey] = set()
    attachment_sources: set[EvidenceKey] = set()
    page_sources: dict[EvidenceKey, set[int]] = {}

    def add_source(
        url: str,
        captured_at: str,
        *,
        document: bool = False,
        attachment: bool = False,
        pages: tuple[int, ...] = (),
    ) -> None:
        key = (url, captured_at)
        all_sources.add(key)
        if document:
            document_sources.add(key)
        if attachment:
            attachment_sources.add(key)
        if pages:
            page_sources.setdefault(key, set()).update(pages)

    add_source(case.matter.source.url, case.matter.source.captured_at)
    for appearance in case.appearances:
        add_source(appearance.source.url, appearance.source.captured_at)
        if appearance.pdf_source is not None:
            add_source(
                appearance.pdf_source.url,
                appearance.pdf_source.captured_at,
                document=True,
                pages=appearance.pdf_evidence_pages,
            )
        for attachment in appearance.attachments:
            add_source(attachment.source.url, attachment.source.captured_at)
            if attachment.reading_source is not None:
                pages: tuple[int, ...] = ()
                if attachment.page_count is not None:
                    pages = tuple(range(1, attachment.page_count + 1))
                add_source(
                    attachment.reading_source.url,
                    attachment.reading_source.captured_at,
                    document=True,
                    attachment=True,
                    pages=pages,
                )
            for anchor in attachment.anchors:
                add_source(
                    anchor.source.url,
                    anchor.source.captured_at,
                    document=True,
                    attachment=True,
                    pages=(anchor.page_number,),
                )
            capture = attachment.document_capture()
            if capture is not None:
                capture_source = capture[1]
                pages = ()
                if attachment.page_count is not None:
                    pages = tuple(range(1, attachment.page_count + 1))
                add_source(
                    capture_source.url,
                    capture_source.captured_at,
                    document=True,
                    attachment=True,
                    pages=pages,
                )
    return _EvidenceCatalog(
        all_sources=frozenset(all_sources),
        document_sources=frozenset(document_sources),
        attachment_sources=frozenset(attachment_sources),
        page_sources={key: frozenset(values) for key, values in page_sources.items()},
    )


def _validate_agent_evidence(
    evidence: AgentEvidence,
    catalog: _EvidenceCatalog,
    context: str,
    *,
    document_required: bool = False,
    page_required: bool = False,
) -> None:
    key = (evidence.url, evidence.captured_at)
    if key not in catalog.all_sources:
        raise ValueError(
            f"{context} cited a primary record that was not in the stored matter: {evidence.url}"
        )
    if document_required and key not in catalog.attachment_sources:
        raise ValueError(f"{context} cited a non-document record for an attachment fact")
    if page_required and evidence.page_number is None:
        raise ValueError(f"{context} must include a PDF page number")
    if evidence.page_number is not None:
        pages = catalog.page_sources.get(key)
        if pages is None or evidence.page_number not in pages:
            raise ValueError(
                f"{context} cited PDF page {evidence.page_number}, which is not available "
                "at its source"
            )


def _validate_agent_reports(
    reports: InvestigationReports,
    catalog: _EvidenceCatalog,
) -> None:
    archivist, substance, process, _skeptic, _brief = reports
    for role, observations in (
        ("Archivist", archivist.observations),
        ("Process", process.observations),
    ):
        for observation in observations:
            for index, evidence in enumerate(observation.evidence):
                _validate_agent_evidence(
                    evidence,
                    catalog,
                    f"{role} observation {observation.observation_id} evidence {index}",
                )
    if bool(substance.changes) == substance.no_substantive_change:
        raise ValueError(
            "Substance report disagreed with its no-substantive-change declaration"
        )
    for change in substance.changes:
        _validate_agent_evidence(
            change.evidence,
            catalog,
            f"Substance change {change.observation_id} evidence",
            document_required=True,
            page_required=True,
        )
        if change.evidence.page_number != change.page_number:
            raise ValueError(
                f"Substance change {change.observation_id} used different page numbers "
                "in its fields"
            )


def _brief_observation_id(
    raw_id: str,
    accepted_ids: frozenset[str],
    aliases: dict[str, tuple[str, ...]],
    observations: dict[str, ReviewedObservation],
) -> str:
    if raw_id in observations:
        resolved = raw_id
    else:
        candidates = aliases.get(raw_id)
        if candidates is None:
            raise ValueError(f"Brief writer cited unknown observation: {raw_id}")
        if len(candidates) != 1:
            raise ValueError(f"Brief writer cited ambiguous observation: {raw_id}")
        resolved = candidates[0]
    if resolved not in accepted_ids:
        raise ValueError(f"Brief writer cited an observation rejected by review: {raw_id}")
    return resolved


def _validate_brief(
    brief: BriefWriterReport,
    accepted_ids: frozenset[str],
    aliases: dict[str, tuple[str, ...]],
    observations: dict[str, ReviewedObservation],
) -> None:
    """Check cited observation IDs before rebuilding the brief from records.

    Brief-writer links are advisory. The model's link values are never copied
    into the resident-facing result; `_brief_with_resolved_ids` rebuilds every
    line from the accepted observations and their stored evidence.
    """

    for line in brief.lines:
        _brief_observation_id(
            line.observation_id,
            accepted_ids,
            aliases,
            observations,
        )


def _agent_observations(
    role: str,
    observations: tuple[AgentObservation, ...],
) -> tuple[tuple[ReviewedObservation, ...], dict[str, tuple[str, ...]]]:
    output = tuple(_namespaced_observation(role, item) for item in observations)
    aliases: dict[str, list[str]] = {}
    for item in output:
        raw_id = item.observation_id.removeprefix(f"{role}:")
        aliases.setdefault(raw_id, []).append(item.observation_id)
    return output, {key: tuple(value) for key, value in aliases.items()}


def _merge_aliases(
    groups: tuple[dict[str, tuple[str, ...]], ...],
) -> dict[str, tuple[str, ...]]:
    merged: dict[str, list[str]] = {}
    for group in groups:
        for raw_id, namespaced_ids in group.items():
            merged.setdefault(raw_id, []).extend(namespaced_ids)
    return {key: tuple(value) for key, value in merged.items()}


def _resolved_ids(
    raw_ids: list[str],
    aliases: dict[str, tuple[str, ...]],
    context: str,
) -> tuple[frozenset[str], tuple[ReviewRejection, ...]]:
    resolved: set[str] = set()
    ambiguous: list[ReviewRejection] = []
    for raw_id in raw_ids:
        candidates = aliases.get(raw_id)
        if candidates is None:
            raise ValueError(f"Skeptic {context} unknown observation: {raw_id}")
        if len(candidates) == 1:
            resolved.add(candidates[0])
            continue
        for candidate in candidates:
            ambiguous.append(
                ReviewRejection(
                    observation_id=candidate,
                    reason=(
                        f"The review record used {raw_id}, which was shared by multiple readers; "
                        "the point was not counted."
                    ),
                )
            )
    return frozenset(resolved), tuple(ambiguous)


def _agent_reports(
    archivist: ArchivistReport,
    substance: SubstanceReport,
    process: ProcessReport,
    skeptic: SkepticReport,
) -> tuple[AgentReports, dict[str, tuple[str, ...]]]:
    archivist_observations, archivist_aliases = _agent_observations(
        "archivist", tuple(archivist.observations)
    )
    substance_observations = _substance_observations(substance)
    substance_aliases: dict[str, tuple[str, ...]] = {}
    for item in substance.changes:
        substance_aliases.setdefault(item.observation_id, ())
        substance_aliases[item.observation_id] += (f"substance:{item.observation_id}",)
    process_observations, process_aliases = _agent_observations(
        "process", tuple(process.observations)
    )
    aliases = _merge_aliases((archivist_aliases, substance_aliases, process_aliases))
    observations = archivist_observations + substance_observations + process_observations
    by_id: dict[str, ReviewedObservation] = {}
    for observation in observations:
        if observation.observation_id in by_id:
            raise ValueError(f"Duplicate namespaced observation ID {observation.observation_id}")
        by_id[observation.observation_id] = observation
    accepted, ambiguous_accepts = _resolved_ids(
        skeptic.accepted_observation_ids, aliases, "accepted"
    )
    rejected: dict[str, ReviewRejection] = {
        ambiguous.observation_id: ReviewRejection(
            observation_id=ambiguous.observation_id,
            reason=ambiguous.reason,
        )
        for ambiguous in ambiguous_accepts
    }
    for rejected_observation in skeptic.rejected_observations:
        candidates = aliases.get(rejected_observation.observation_id)
        if candidates is None:
            raise ValueError(
                "Skeptic rejected unknown observation: "
                f"{rejected_observation.observation_id}"
            )
        for candidate in candidates:
            rejected[candidate] = ReviewRejection(
                observation_id=candidate,
                reason=rejected_observation.reason,
            )
    return (
        AgentReports(
            observations=observations,
            accepted_observation_ids=accepted,
            rejections=tuple(rejected.values()),
        ),
        aliases,
    )


def _brief_with_resolved_ids(
    brief: BriefWriterReport,
    accepted_ids: frozenset[str],
    observations: dict[str, ReviewedObservation],
) -> BriefWriterReport:
    lines = [
        BriefLine(
            observation_id=observation_id,
            text=observations[observation_id].text,
            evidence=[
                AgentEvidence(
                    label=link.label,
                    url=link.url,
                    captured_at=link.captured_at,
                    page_number=link.page_number,
                )
                for link in observations[observation_id].evidence
            ],
        )
        for observation_id in observations
        if observation_id in accepted_ids
    ]
    return BriefWriterReport(
        heading="Worth a look",
        lines=lines,
        questions=brief.questions,
        limitation="Page 47 does not determine why these changes were made.",
    )


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


def _payload_report[ReportModel: BaseModel](
    payload: JSONObject,
    node_id: str,
    model: type[ReportModel],
) -> ReportModel:
    raw_nodes = payload.get("nodes")
    if not isinstance(raw_nodes, dict):
        raise ValueError("Graph payload did not contain node reports")
    raw_report = raw_nodes.get(node_id)
    if not isinstance(raw_report, dict):
        raise ValueError(f"Graph payload did not contain a report for node {node_id}")
    try:
        return model.model_validate(raw_report, strict=True)
    except ValueError as error:
        raise ValueError(f"Graph payload report {node_id} failed validation") from error


def _reports_from_graph(graph: GraphResult) -> InvestigationReports:
    return (
        _node_report(graph, "archivist", ArchivistReport),
        _node_report(graph, "substance", SubstanceReport),
        _node_report(graph, "process", ProcessReport),
        _node_report(graph, "skeptic", SkepticReport),
        _node_report(graph, "brief_writer", BriefWriterReport),
    )


def _reports_from_payload(payload: JSONObject) -> InvestigationReports:
    return (
        _payload_report(payload, "archivist", ArchivistReport),
        _payload_report(payload, "substance", SubstanceReport),
        _payload_report(payload, "process", ProcessReport),
        _payload_report(payload, "skeptic", SkepticReport),
        _payload_report(payload, "brief_writer", BriefWriterReport),
    )


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


def _load_review_inputs(
    store: RecordStore,
    city: str,
    matter_id: int,
    evidence_root: Path,
    models_path: Path,
    presentation_path: Path,
    policy_path: Path,
    norms_path: Path,
) -> _ReviewInputs:
    model_settings = load_model_settings(models_path)
    presentation_config = load_presentation_config(presentation_path)
    policy_config = load_policy_config(policy_path)
    norm_settings = load_norm_settings(norms_path)
    case = load_matter_case(store, city, matter_id, evidence_root)
    drift = compare_all_appearances(case, presentation_config)
    norms = compute_historical_norms(store.connection, norm_settings)
    return _ReviewInputs(
        model_settings=model_settings,
        case=case,
        drift=drift,
        norm=_norm_for_case(norms, case),
        policy_config=policy_config,
    )


def _complete_review(
    inputs: _ReviewInputs,
    run_id: str,
    reports: InvestigationReports,
    graph_result: JSONObject,
) -> InvestigationOutcome:
    archivist, substance, process, skeptic, brief = reports
    catalog = _evidence_catalog(inputs.case)
    _validate_agent_reports(reports, catalog)
    agent_reports, aliases = _agent_reports(archivist, substance, process, skeptic)
    structural = _structural_observation(
        inputs.drift.comparisons[-1] if inputs.drift.comparisons else None
    )
    observations = agent_reports.observations + structural
    by_id: dict[str, ReviewedObservation] = {}
    for observation in observations:
        if observation.observation_id in by_id:
            raise ValueError(f"Duplicate observation ID {observation.observation_id}")
        by_id[observation.observation_id] = observation
    report = AgentReports(
        observations=observations,
        accepted_observation_ids=agent_reports.accepted_observation_ids,
        rejections=agent_reports.rejections,
    )
    decision = apply_evidence_policy(report, inputs.policy_config)
    accepted_ids = frozenset(item.observation_id for item in decision.accepted)
    _validate_brief(brief, accepted_ids, aliases, by_id)
    safe_brief = _brief_with_resolved_ids(brief, accepted_ids, by_id)
    return InvestigationOutcome(
        run_id=run_id,
        case=inputs.case,
        drift=inputs.drift,
        norm=inputs.norm,
        decision=decision,
        brief=safe_brief,
        graph_result=graph_result,
    )


def _save_failed_run(
    store: RecordStore,
    city: str,
    matter_id: int,
    run_id: str,
    started_at: str,
    graph_result: JSONObject,
    error: Exception,
) -> None:
    store.save_investigation_run(
        InvestigationRunObservation(
            run_id=run_id,
            city=city,
            matter_id=matter_id,
            started_at=started_at,
            finished_at=_now(),
            status="failed",
            graph_result=graph_result,
            policy=None,
            error=f"{type(error).__name__}: {error}",
        )
    )
    store.commit()


def record_failed_investigation(
    store: RecordStore,
    city: str,
    matter_id: int,
    error: Exception,
    graph_result: JSONObject | None = None,
) -> str:
    """Persist a failure that happened before a graph result reached review."""

    run_id = uuid4().hex
    payload: JSONObject = {"status": "transport_failed"}
    if graph_result is not None:
        payload = graph_result
    _save_failed_run(
        store,
        city,
        matter_id,
        run_id,
        _now(),
        payload,
        error,
    )
    return run_id


def review_graph_payload(
    store: RecordStore,
    city: str,
    matter_id: int,
    evidence_root: Path,
    models_path: Path,
    presentation_path: Path,
    policy_path: Path,
    norms_path: Path,
    graph_result: JSONObject,
) -> InvestigationOutcome:
    """Review and persist a graph result returned by local or managed runtime."""

    started_at = _now()
    run_id = uuid4().hex
    try:
        inputs = _load_review_inputs(
            store,
            city,
            matter_id,
            evidence_root,
            models_path,
            presentation_path,
            policy_path,
            norms_path,
        )
        reports = _reports_from_payload(graph_result)
        outcome = _complete_review(inputs, run_id, reports, graph_result)
        _save_outcome(store, outcome, started_at, _now())
        return outcome
    except Exception as error:
        _save_failed_run(store, city, matter_id, run_id, started_at, graph_result, error)
        raise


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
    graph_result: JSONObject = {"status": "failed"}
    try:
        inputs = _load_review_inputs(
            store,
            city,
            matter_id,
            evidence_root,
            models_path,
            presentation_path,
            policy_path,
            norms_path,
        )
        graph = invoke_investigation(
            InvestigationContext(
                case=inputs.case,
                evidence_root=evidence_root,
                models=inputs.model_settings,
            )
        )
        graph_result = _graph_payload(graph)
        outcome = _complete_review(
            inputs,
            run_id,
            _reports_from_graph(graph),
            graph_result,
        )
        _save_outcome(store, outcome, started_at, _now())
        return outcome
    except Exception as error:
        _save_failed_run(store, city, matter_id, run_id, started_at, graph_result, error)
        raise
