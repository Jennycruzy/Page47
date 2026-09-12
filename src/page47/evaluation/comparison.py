"""Run transparent comparison arms over a frozen Page 47 matter set."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Literal

from page47.analysis.case import AppearanceRecord, AttachmentRecord, MatterCase, load_matter_case
from page47.analysis.drift import (
    DriftComparison,
    DriftLedger,
    DriftState,
    EvidenceLink,
    PresentationConfig,
    compare_all_appearances,
    load_presentation_config,
)
from page47.analysis.signature import material_signature_changed, title_coverage_pair
from page47.records.store import RecordStore
from page47.snapshotter.config import JSONObject, JSONValue
from page47.snapshotter.store import SnapshotStore

ArmName = Literal["keyword", "search", "latest_document", "page47"]


@dataclass(frozen=True, slots=True)
class ArmResult:
    arm: ArmName
    state: DriftState | None
    surfaced: bool
    signals: tuple[str, ...]
    evidence: tuple[EvidenceLink, ...]
    reason: str
    diagnostics: JSONObject | None = None

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
                    "origin": item.origin,
                }
            )
        payload: JSONObject = {
            "arm": self.arm,
            "state": self.state,
            "surfaced": self.surfaced,
            "signals": signals,
            "evidence": evidence,
            "reason": self.reason,
        }
        if self.diagnostics is not None:
            payload["diagnostics"] = self.diagnostics
        return payload


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


def _state_from_ledger(ledger: DriftLedger) -> DriftState:
    counts = ledger.counts
    if counts["mixed"] > 0 or (counts["clearer"] > 0 and counts["less_clear"] > 0):
        return "mixed"
    if counts["less_clear"] > 0:
        return "less_clear"
    if counts["clearer"] > 0:
        return "clearer"
    if counts["unchanged"] > 0:
        return "unchanged"
    return "cannot_determine"


def _evidence_from_ledger(ledger: DriftLedger) -> tuple[EvidenceLink, ...]:
    links: list[EvidenceLink] = []
    seen: set[tuple[str, str, int | None]] = set()
    for comparison in ledger.comparisons:
        if comparison.state == "cannot_determine":
            continue
        for observation in comparison.observations:
            for evidence in observation.evidence:
                _append_unique(links, evidence, seen)
    return tuple(links)


def _page47_state(
    case: MatterCase, config: PresentationConfig
) -> tuple[DriftState, tuple[EvidenceLink, ...]]:
    ledger = compare_all_appearances(case, config)
    return _state_from_ledger(ledger), _evidence_from_ledger(ledger)


def _event_time(value: str | None) -> datetime | None:
    """Parse meeting dates for sequence checks, not publication-time claims."""

    if value is None or not value.strip():
        return None
    try:
        if len(value) == 10:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _stored_count(value: JSONValue) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError("Internal diagnostic counter was not an integer")


def _direction_for_key(comparison: DriftComparison, prefix: str) -> str | None:
    for observation in comparison.observations:
        if observation.key.startswith(prefix):
            return observation.direction
    return None


def _readable_attachment(attachment: AttachmentRecord) -> bool:
    return attachment.reading_status in {"candidate", "absent"}


def _anchored_attachment(attachment: AttachmentRecord) -> bool:
    return bool(attachment.anchors)


def _appearance_has_readable_attachments(appearance: AppearanceRecord) -> bool:
    return any(_readable_attachment(item) for item in appearance.attachments)


def _appearance_has_anchors(appearance: AppearanceRecord) -> bool:
    return any(_anchored_attachment(item) for item in appearance.attachments)


def _dimension_template() -> JSONObject:
    return {
        "comparable_pairs": 0,
        "directional_pairs": 0,
        "neutral_pairs": 0,
        "unavailable_pairs": 0,
    }


def _page47_diagnostics(
    case: MatterCase,
    config: PresentationConfig,
    ledger: DriftLedger,
    state: DriftState,
) -> JSONObject:
    """Explain what the comparator could and could not establish.

    These diagnostics deliberately describe evidence coverage rather than turning
    missing evidence into a score. The four-arm comparison does not run the
    model-level Skeptic, so that boundary is recorded explicitly below.
    """

    appearances = case.appearances
    actual_pairs = list(zip(appearances, appearances[1:], strict=False))
    pair_count = len(actual_pairs)
    title = _dimension_template()
    title["structured_signature_pairs"] = 0
    title["lexical_fallback_pairs"] = 0
    title["missing_pairs"] = 0
    placement = _dimension_template()
    placement["unavailable_pairs"] = 0
    substance: JSONObject = {
        "readable_appearance_count": sum(
            1 for appearance in appearances if _appearance_has_readable_attachments(appearance)
        ),
        "anchored_appearance_count": sum(
            1 for appearance in appearances if _appearance_has_anchors(appearance)
        ),
        "readable_pairs": 0,
        "anchored_pairs": 0,
        "material_change_pairs": 0,
    }

    unique_attachments = case.unique_attachments()
    readable_unique = sum(1 for item in unique_attachments if _readable_attachment(item))
    anchored_unique = sum(1 for item in unique_attachments if _anchored_attachment(item))
    readable_occurrences = sum(
        1
        for appearance in appearances
        for item in appearance.attachments
        if _readable_attachment(item)
    )
    anchored_occurrences = sum(
        1
        for appearance in appearances
        for item in appearance.attachments
        if _anchored_attachment(item)
    )
    unreadable_unique = len(unique_attachments) - readable_unique

    pair_details: list[JSONValue] = []
    chronology_untrusted_pairs = 0
    invalid_dates = sum(
        1 for appearance in appearances if _event_time(appearance.event_date) is None
    )
    for index, (previous, current) in enumerate(actual_pairs):
        comparison = ledger.comparisons[index]
        previous_time = _event_time(previous.event_date)
        current_time = _event_time(current.event_date)
        chronology_trusted = (
            previous_time is not None
            and current_time is not None
            and current_time >= previous_time
        )
        if not chronology_trusted:
            chronology_untrusted_pairs += 1

        previous_title = previous.title_as_presented
        current_title = current.title_as_presented
        title_detail: JSONObject
        if not previous_title or not current_title:
            title["missing_pairs"] = _stored_count(title["missing_pairs"]) + 1
            title_detail = {
                "status": "missing",
                "method": "not_available",
                "direction": "unavailable",
                "earlier_ratio": None,
                "later_ratio": None,
            }
        else:
            title["comparable_pairs"] = _stored_count(title["comparable_pairs"]) + 1
            if previous_title.strip().casefold() == current_title.strip().casefold():
                method = "exact_match"
                earlier_ratio: float | None = None
                later_ratio: float | None = None
            else:
                previous_coverage, current_coverage = title_coverage_pair(previous, current)
                if previous_coverage.total_facets > 0 and current_coverage.total_facets > 0:
                    method = "structured_substance_signature"
                    title["structured_signature_pairs"] = _stored_count(
                        title["structured_signature_pairs"]
                    ) + 1
                    earlier_ratio = round(previous_coverage.ratio, 3)
                    later_ratio = round(current_coverage.ratio, 3)
                else:
                    method = "lexical_fallback"
                    title["lexical_fallback_pairs"] = (
                        _stored_count(title["lexical_fallback_pairs"]) + 1
                    )
                    earlier_ratio = None
                    later_ratio = None
            title_direction = _direction_for_key(comparison, "title_") or "neutral"
            if title_direction in {"clearer", "less_clear"}:
                title["directional_pairs"] = _stored_count(title["directional_pairs"]) + 1
            else:
                title["neutral_pairs"] = _stored_count(title["neutral_pairs"]) + 1
            title_detail = {
                "status": "compared",
                "method": method,
                "direction": title_direction,
                "earlier_ratio": earlier_ratio,
                "later_ratio": later_ratio,
            }

        supported_placements = {"consent", "regular"}
        if (
            previous.pdf_placement in supported_placements
            and current.pdf_placement in supported_placements
        ):
            placement["comparable_pairs"] = _stored_count(placement["comparable_pairs"]) + 1
            placement_direction = _direction_for_key(comparison, "agenda_")
            if placement_direction is None:
                placement_direction = _direction_for_key(comparison, "moved_")
            placement_direction = placement_direction or "neutral"
            if placement_direction in {"clearer", "less_clear"}:
                placement["directional_pairs"] = _stored_count(placement["directional_pairs"]) + 1
            else:
                placement["neutral_pairs"] = _stored_count(placement["neutral_pairs"]) + 1
            placement_detail: JSONObject = {
                "status": "compared",
                "direction": placement_direction,
                "earlier": previous.pdf_placement,
                "later": current.pdf_placement,
            }
        else:
            placement["unavailable_pairs"] = _stored_count(placement["unavailable_pairs"]) + 1
            placement_detail = {
                "status": "unavailable",
                "direction": "unavailable",
                "earlier": previous.pdf_placement,
                "later": current.pdf_placement,
            }

        previous_readable = _appearance_has_readable_attachments(previous)
        current_readable = _appearance_has_readable_attachments(current)
        previous_anchored = _appearance_has_anchors(previous)
        current_anchored = _appearance_has_anchors(current)
        if previous_readable and current_readable:
            substance["readable_pairs"] = _stored_count(substance["readable_pairs"]) + 1
        if previous_anchored and current_anchored:
            substance["anchored_pairs"] = _stored_count(substance["anchored_pairs"]) + 1
            if material_signature_changed(previous, current):
                substance["material_change_pairs"] = _stored_count(
                    substance["material_change_pairs"]
                ) + 1
        if previous_anchored and current_anchored:
            material_changed: bool | None = material_signature_changed(previous, current)
            substance_status = "anchored"
        elif previous_readable and current_readable:
            material_changed = None
            substance_status = "readable_without_anchors"
        else:
            material_changed = None
            substance_status = "not_readable"

        pair_details.append(
            {
                "previous_event_item_id": previous.event_item_id,
                "current_event_item_id": current.event_item_id,
                "title": title_detail,
                "placement": placement_detail,
                "substance": {
                    "status": substance_status,
                    "material_signature_changed": material_changed,
                },
                "timing": {
                    "status": "unavailable",
                    "reason": "A city last-modified field does not prove public visibility time.",
                },
                "chronology": {
                    "status": "trusted" if chronology_trusted else "untrusted",
                },
            }
        )

    coverage_gaps: list[str] = []
    if pair_count == 0:
        coverage_gaps.append("no_comparable_appearances")
    if pair_count > 0 and title["comparable_pairs"] == 0:
        coverage_gaps.append("missing_comparable_title")
    if pair_count > 0 and placement["comparable_pairs"] == 0:
        coverage_gaps.append("placement_unavailable")
    if unique_attachments == () or readable_unique == 0:
        coverage_gaps.append("substance_not_readable")
    elif anchored_unique == 0:
        coverage_gaps.append("insufficient_substance_anchors")
    if pair_count > 0:
        coverage_gaps.append("timing_unavailable")
    if chronology_untrusted_pairs > 0:
        coverage_gaps.append("chronology_untrusted")

    if state == "cannot_determine":
        reason_codes = [*coverage_gaps, "no_directional_signal"]
    elif state == "mixed":
        reason_codes = ["opposing_directional_signals"]
    elif state == "unchanged":
        reason_codes = ["no_directional_signal"]
    else:
        reason_codes = []

    chronology_status = "not_applicable"
    if pair_count > 0:
        chronology_status = (
            "untrusted" if chronology_untrusted_pairs else "trusted_for_meeting_sequence"
        )

    return {
        "appearances": len(appearances),
        "pairs": pair_count,
        "dimensions": {
            "title": title,
            "placement": placement,
            "substance": substance,
            "timing": {
                "comparable_pairs": 0,
                "unavailable_pairs": pair_count,
                "status": "unavailable",
                "reason": "City last-modified fields do not prove public visibility time.",
            },
        },
        "readable_attachments": {
            "unique_attachments": len(unique_attachments),
            "occurrences": sum(len(appearance.attachments) for appearance in appearances),
            "readable": readable_unique,
            "with_anchors": anchored_unique,
            "readable_occurrences": readable_occurrences,
            "anchored_occurrences": anchored_occurrences,
            "unreadable_or_missing_reading": unreadable_unique,
        },
        "chronology": {
            "status": chronology_status,
            "ordered_pairs": pair_count - chronology_untrusted_pairs,
            "untrusted_pairs": chronology_untrusted_pairs,
            "missing_or_invalid_dates": invalid_dates,
            "note": (
                "Event dates order the recorded meeting appearances; they do not establish "
                "publication timing."
            ),
        },
        "skeptic": {
            "status": "not_run",
            "rejected_count": None,
            "note": (
                "The four-arm comparison runs the deterministic comparator only; model-level "
                "Skeptic review is evaluated separately."
            ),
        },
        "pair_details": pair_details,
        "coverage_gaps": list(dict.fromkeys(coverage_gaps)),
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "abstention_reason_codes": (
            list(dict.fromkeys(reason_codes)) if state == "cannot_determine" else []
        ),
        "state": state,
        "config": {
            "minimum_appearances": config.minimum_appearances,
            "minimum_title_overlap": config.minimum_title_overlap,
        },
    }


def _page47_arm(case: MatterCase, config: PresentationConfig) -> ArmResult:
    ledger = compare_all_appearances(case, config)
    state = _state_from_ledger(ledger)
    evidence = _evidence_from_ledger(ledger)
    diagnostics = _page47_diagnostics(case, config, ledger, state)
    surfaced = state in {"clearer", "less_clear", "mixed"}
    if state == "cannot_determine":
        reason = (
            "The comparator abstained; the diagnostics list the separate evidence gaps and "
            "coverage limits."
        )
    elif state == "unchanged":
        reason = "Comparable dimensions were recorded, but no directional change was found."
    else:
        reason = (
            "Page 47 compares adjacent recorded appearances and preserves the evidence used "
            "for the resulting direction."
        )
    return ArmResult("page47", state, surfaced, (), evidence, reason, diagnostics)


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


def _increment(counter: dict[str, int], key: object) -> None:
    if isinstance(key, str):
        counter[key] = counter.get(key, 0) + 1


def _diagnostic_metrics(rows: list[JSONObject]) -> JSONObject:
    page47_rows = _arm_rows(rows, "page47")
    reason_counts: dict[str, int] = {}
    abstention_reason_counts: dict[str, int] = {}
    coverage_gap_counts: dict[str, int] = {}
    skeptic_status_counts: dict[str, int] = {}
    dimension_coverage: JSONObject = {
        dimension: {
            "cases_with_comparable_pair": 0,
            "comparable_pairs": 0,
            "cases_with_directional_pair": 0,
            "directional_pairs": 0,
        }
        for dimension in ("title", "placement", "substance", "timing")
    }
    diagnosed_cases = 0
    for result in page47_rows:
        raw_diagnostics = result.get("diagnostics")
        if not isinstance(raw_diagnostics, dict):
            continue
        diagnosed_cases += 1
        raw_codes = raw_diagnostics.get("reason_codes")
        if isinstance(raw_codes, list):
            for code in raw_codes:
                _increment(reason_counts, code)
        raw_abstention_codes = raw_diagnostics.get("abstention_reason_codes")
        if isinstance(raw_abstention_codes, list):
            for code in raw_abstention_codes:
                _increment(abstention_reason_counts, code)
        raw_gaps = raw_diagnostics.get("coverage_gaps")
        if isinstance(raw_gaps, list):
            for gap in raw_gaps:
                _increment(coverage_gap_counts, gap)
        raw_skeptic = raw_diagnostics.get("skeptic")
        if isinstance(raw_skeptic, dict):
            _increment(skeptic_status_counts, raw_skeptic.get("status"))
        raw_dimensions = raw_diagnostics.get("dimensions")
        if not isinstance(raw_dimensions, dict):
            continue
        for dimension in dimension_coverage:
            raw_dimension = raw_dimensions.get(dimension)
            if not isinstance(raw_dimension, dict):
                continue
            comparable_pairs = raw_dimension.get("comparable_pairs")
            directional_pairs = raw_dimension.get("directional_pairs")
            if not isinstance(comparable_pairs, int) or isinstance(comparable_pairs, bool):
                comparable_pairs = 0
            if not isinstance(directional_pairs, int) or isinstance(directional_pairs, bool):
                directional_pairs = 0
            coverage = dimension_coverage[dimension]
            if not isinstance(coverage, dict):
                continue
            coverage["comparable_pairs"] = (
                _stored_count(coverage["comparable_pairs"]) + comparable_pairs
            )
            coverage["directional_pairs"] = (
                _stored_count(coverage["directional_pairs"]) + directional_pairs
            )
            if comparable_pairs > 0:
                coverage["cases_with_comparable_pair"] = (
                    _stored_count(coverage["cases_with_comparable_pair"]) + 1
                )
            if directional_pairs > 0:
                coverage["cases_with_directional_pair"] = (
                    _stored_count(coverage["cases_with_directional_pair"]) + 1
                )
    return {
        "cases_with_diagnostics": diagnosed_cases,
        "dimension_coverage": dimension_coverage,
        "reason_code_counts": dict(sorted(reason_counts.items())),
        "abstention_reason_counts": dict(sorted(abstention_reason_counts.items())),
        "coverage_gap_counts": dict(sorted(coverage_gap_counts.items())),
        "skeptic_status_counts": dict(sorted(skeptic_status_counts.items())),
        "note": (
            "Coverage counts describe what the stored records made comparable. They do not "
            "turn missing evidence into a directional score."
        ),
    }


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
        "page47_diagnostics": _diagnostic_metrics(rows),
        "historical_abstention_audit": {
            "cases_expected_to_abstain": len(cannot_rows),
            "page47_overclaims": overclaims,
            "note": (
                "Directional accuracy is not calculated when the gold label is "
                "cannot_determine."
            ),
        },
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_sha256_file(path: Path) -> str | None:
    return _sha256_file(path) if path.is_file() else None


def _evaluation_inputs(
    *,
    input_path: Path,
    database: Path,
    evidence_root: Path,
    presentation_path: Path,
    raw_items: list[JSONValue],
    city: str,
    code_revision: str,
    evidence: SnapshotStore,
) -> JSONObject:
    matter_ids = []
    for raw_item in raw_items:
        if isinstance(raw_item, dict):
            matter_id = raw_item.get("matter_id")
            if isinstance(matter_id, int) and not isinstance(matter_id, bool):
                matter_ids.append(str(matter_id))
    return {
        "code_revision": code_revision,
        "evaluation_timestamp_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "evaluation_manifest_sha256": _sha256_file(input_path),
        "presentation_config_sha256": _sha256_file(presentation_path),
        "record_database_sha256": _sha256_file(database),
        "evidence_manifest_sha256": _optional_sha256_file(evidence.manifest_path),
        "evidence_chain_sha256": _optional_sha256_file(evidence.integrity_path),
        "evidence_integrity_root": evidence.verify_integrity(),
        "matter_ids_sha256": sha256(
            "\n".join(f"{city}:{matter_id}" for matter_id in matter_ids).encode("utf-8")
        ).hexdigest(),
        "source_paths": {
            "evaluation_manifest": str(input_path),
            "presentation_config": str(presentation_path),
            "record_database": str(database),
            "evidence_root": str(evidence_root),
        },
        "note": (
            "The runner reloads cases from the SQLite database. These hashes pin the exact "
            "inputs used for this artifact, including the evidence integrity chain."
        ),
    }


def run_comparison(
    *,
    input_path: Path,
    database: Path,
    evidence_root: Path,
    presentation_path: Path,
    output_path: Path,
    code_revision: str,
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
    if not code_revision.strip():
        raise ValueError("code_revision must be non-empty text")
    config = load_presentation_config(presentation_path)
    evidence = SnapshotStore(evidence_root)
    evaluation_inputs = _evaluation_inputs(
        input_path=input_path,
        database=database,
        evidence_root=evidence_root,
        presentation_path=presentation_path,
        raw_items=raw_items,
        city=city,
        code_revision=code_revision,
        evidence=evidence,
    )
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
        "schema_version": 2,
        "evaluation_inputs": evaluation_inputs,
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
