"""Run transparent comparison arms over a frozen Page 47 matter set."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from page47.analysis.case import MatterCase, load_matter_case
from page47.analysis.drift import (
    DriftState,
    EvidenceLink,
    PresentationConfig,
    compare_all_appearances,
    load_presentation_config,
)
from page47.records.store import RecordStore
from page47.snapshotter.config import JSONObject, JSONValue

ArmName = Literal["keyword", "search", "latest_document", "page47"]


@dataclass(frozen=True, slots=True)
class ArmResult:
    arm: ArmName
    state: DriftState | None
    surfaced: bool
    signals: tuple[str, ...]
    evidence: tuple[EvidenceLink, ...]
    reason: str

    def as_json(self) -> JSONObject:
        signals: list[JSONValue] = []
        for signal in self.signals:
            signals.append(signal)
        evidence: list[JSONValue] = []
        for item in self.evidence:
            evidence.append(
                {
                    "label": item.label,
                    "url": item.url,
                    "captured_at": item.captured_at,
                    "page_number": item.page_number,
                }
            )
        return {
            "arm": self.arm,
            "state": self.state,
            "surfaced": self.surfaced,
            "signals": signals,
            "evidence": evidence,
            "reason": self.reason,
        }


def _tokens(value: str | None) -> set[str]:
    if value is None:
        return set()
    return {token.casefold() for token in re.findall(r"[A-Za-z0-9]{3,}", value)}


def _link(label: str, url: str, captured_at: str, page_number: int | None = None) -> EvidenceLink:
    return EvidenceLink(label, url, captured_at, page_number)


def _append_unique(
    output: list[EvidenceLink], item: EvidenceLink, seen: set[tuple[str, str, int | None]]
) -> None:
    key = (item.url, item.captured_at, item.page_number)
    if key not in seen:
        seen.add(key)
        output.append(item)


def _keyword_arm(case: MatterCase) -> ArmResult:
    """Model a keyword alert that flags explicit lexical changes only."""

    signals: list[str] = []
    evidence: list[EvidenceLink] = []
    seen: set[tuple[str, str, int | None]] = set()
    for previous, current in zip(case.appearances, case.appearances[1:], strict=False):
        if _tokens(previous.title_as_presented) != _tokens(current.title_as_presented):
            signals.append("title_word_set_changed")
            _append_unique(
                evidence,
                _link("earlier title", previous.source.url, previous.source.captured_at),
                seen,
            )
            _append_unique(
                evidence,
                _link("later title", current.source.url, current.source.captured_at),
                seen,
            )
        previous_names = {item.name for item in previous.attachments if item.name}
        current_names = {item.name for item in current.attachments if item.name}
        if previous_names != current_names:
            signals.append("attachment_name_set_changed")
            _append_unique(
                evidence,
                _link("earlier item record", previous.source.url, previous.source.captured_at),
                seen,
            )
            _append_unique(
                evidence,
                _link("later item record", current.source.url, current.source.captured_at),
                seen,
            )
    unique_signals = tuple(dict.fromkeys(signals))
    if unique_signals:
        reason = (
            "The keyword arm flags explicit lexical changes but does not determine their "
            "direction, meaning, or cause."
        )
    else:
        reason = "No explicit title or attachment-name change was found by the keyword arm."
    return ArmResult("keyword", None, bool(unique_signals), unique_signals, tuple(evidence), reason)


def _search_arm(case: MatterCase) -> ArmResult:
    """Model current-record search, which has no captured presentation history."""

    latest = case.appearances[-1] if case.appearances else None
    if latest is None:
        return ArmResult(
            "search",
            None,
            False,
            (),
            (),
            "The current-record search had no appearance to retrieve.",
        )
    evidence = (_link("current public record", latest.source.url, latest.source.captured_at),)
    return ArmResult(
        "search",
        None,
        False,
        ("current_record_available",),
        evidence,
        (
            "Current search retrieves the latest public record but does not retain the prior "
            "presentation needed to establish drift."
        ),
    )


def _latest_document_arm(case: MatterCase) -> ArmResult:
    """Model a reader that sees only the latest document set."""

    latest = case.appearances[-1] if case.appearances else None
    if latest is None or not latest.attachments:
        return ArmResult(
            "latest_document",
            None,
            False,
            (),
            (),
            "No latest document was available to the latest-document arm.",
        )
    evidence: list[EvidenceLink] = []
    seen: set[tuple[str, str, int | None]] = set()
    for attachment in latest.attachments:
        source = attachment.reading_source or attachment.source
        _append_unique(
            evidence,
            _link("latest document", source.url, source.captured_at),
            seen,
        )
    return ArmResult(
        "latest_document",
        None,
        False,
        ("latest_document_available",),
        tuple(evidence),
        (
            "The latest-document arm can describe the current document but cannot compare "
            "how the matter was presented earlier."
        ),
    )


def _page47_state(
    case: MatterCase, config: PresentationConfig
) -> tuple[DriftState, tuple[EvidenceLink, ...]]:
    ledger = compare_all_appearances(case, config)
    counts = ledger.counts
    if counts["mixed"] > 0 or (counts["clearer"] > 0 and counts["less_clear"] > 0):
        state: DriftState = "mixed"
    elif counts["less_clear"] > 0:
        state = "less_clear"
    elif counts["clearer"] > 0:
        state = "clearer"
    elif counts["unchanged"] > 0:
        state = "unchanged"
    else:
        state = "cannot_determine"

    links: list[EvidenceLink] = []
    seen: set[tuple[str, str, int | None]] = set()
    for comparison in ledger.comparisons:
        if comparison.state == "cannot_determine":
            continue
        for observation in comparison.observations:
            for evidence in observation.evidence:
                _append_unique(links, evidence, seen)
    return state, tuple(links)


def _page47_arm(case: MatterCase, config: PresentationConfig) -> ArmResult:
    state, evidence = _page47_state(case, config)
    surfaced = state in {"clearer", "less_clear", "mixed"}
    if state == "cannot_determine":
        reason = "The recorded appearances did not contain enough comparable presentation evidence."
    elif state == "unchanged":
        reason = "Comparable dimensions were recorded, but no directional change was found."
    else:
        reason = (
            "Page 47 compares adjacent recorded appearances and preserves the evidence used "
            "for the resulting direction."
        )
    return ArmResult("page47", state, surfaced, (), evidence, reason)


def _arm_results(case: MatterCase, config: PresentationConfig) -> tuple[ArmResult, ...]:
    return (
        _keyword_arm(case),
        _search_arm(case),
        _latest_document_arm(case),
        _page47_arm(case, config),
    )


def _gold_counts(items: list[JSONObject]) -> JSONObject:
    counts: JSONObject = {"yes": 0, "no": 0, "cannot_determine": 0}
    for item in items:
        label = item.get("gold_label")
        if isinstance(label, str) and label in counts:
            current = counts.get(label)
            if isinstance(current, int) and not isinstance(current, bool):
                counts[label] = current + 1
    return counts


def _arm_rows(rows: list[JSONObject], arm: ArmName) -> list[JSONObject]:
    output: list[JSONObject] = []
    for row in rows:
        raw_arms = row.get("arms")
        if not isinstance(raw_arms, list):
            continue
        for raw_result in raw_arms:
            if isinstance(raw_result, dict) and raw_result.get("arm") == arm:
                output.append(raw_result)
    return output


def _metrics(rows: list[JSONObject]) -> JSONObject:
    arm_metrics: JSONObject = {}
    for arm in ("keyword", "search", "latest_document", "page47"):
        arm_rows = _arm_rows(rows, arm)
        surfaced = sum(1 for result in arm_rows if result.get("surfaced") is True)
        states: JSONObject = {
            state: sum(1 for result in arm_rows if result.get("state") == state)
            for state in ("clearer", "less_clear", "mixed", "unchanged", "cannot_determine")
        }
        arm_metrics[arm] = {
            "cases": len(arm_rows),
            "surfaced": surfaced,
            "not_surfaced": len(arm_rows) - surfaced,
            "states": states,
        }

    cannot_rows = [row for row in rows if row.get("gold_label") == "cannot_determine"]
    overclaims = 0
    for row in cannot_rows:
        page47_results = _arm_rows([row], "page47")
        if page47_results and page47_results[0].get("state") != "cannot_determine":
            overclaims += 1
    return {
        "gold_label_counts": _gold_counts(rows),
        "arms": arm_metrics,
        "historical_abstention_audit": {
            "cases_expected_to_abstain": len(cannot_rows),
            "page47_overclaims": overclaims,
            "note": (
                "Directional accuracy is not calculated when the gold label is "
                "cannot_determine."
            ),
        },
    }


def run_comparison(
    *,
    input_path: Path,
    database: Path,
    evidence_root: Path,
    presentation_path: Path,
    output_path: Path,
) -> JSONObject:
    """Run all four arms over the frozen evaluation manifest."""

    decoded: object = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Evaluation export must be an object")
    raw_items = decoded.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("Evaluation export items must be a non-empty list")
    city = decoded.get("city")
    if not isinstance(city, str) or not city.strip():
        raise ValueError("Evaluation export city must be non-empty text")
    config = load_presentation_config(presentation_path)
    rows: list[JSONObject] = []
    with RecordStore(database) as records:
        for index, raw_item in enumerate(raw_items):
            if not isinstance(raw_item, dict):
                raise ValueError(f"Evaluation item {index} must be an object")
            matter_id = raw_item.get("matter_id")
            if isinstance(matter_id, bool) or not isinstance(matter_id, int) or matter_id < 1:
                raise ValueError(f"Evaluation item {index} had an invalid matter_id")
            case = load_matter_case(records, city, matter_id, evidence_root)
            case_id = raw_item.get("case_id")
            expected_case_id = f"{city}:{matter_id}"
            if case_id != expected_case_id:
                raise ValueError(
                    f"Evaluation item {index} case_id {case_id!r} did not match "
                    f"{expected_case_id!r}"
                )
            arms = _arm_results(case, config)
            rows.append(
                {
                    "case_id": expected_case_id,
                    "matter_id": matter_id,
                    "gold_label": raw_item.get("gold_label"),
                    "gold_label_reason": raw_item.get("gold_label_reason"),
                    "arms": [result.as_json() for result in arms],
                }
            )
    cases: list[JSONValue] = []
    for row in rows:
        cases.append(row)
    output: JSONObject = {
        "schema_version": 1,
        "source_manifest": str(input_path),
        "city": city,
        "case_count": len(rows),
        "methodology": {
            "keyword": (
                "Flags explicit title or attachment-name lexical changes and does not infer "
                "direction."
            ),
            "search": (
                "Uses only the latest public record and cannot establish a prior "
                "presentation."
            ),
            "latest_document": (
                "Uses only the latest document set and cannot establish a prior "
                "presentation."
            ),
            "page47": (
                "Compares adjacent recorded appearances with the configured evidence "
                "policy inputs."
            ),
            "gold_policy": (
                "The 30 cannot_determine cases are an abstention audit, not a directional "
                "accuracy benchmark."
            ),
        },
        "metrics": _metrics(rows),
        "cases": cases,
        "status": "review_required",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output
