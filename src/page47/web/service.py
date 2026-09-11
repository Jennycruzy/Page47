"""Record-backed operations shared by the API and the resident console."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from page47.address.matcher import (
    AreaMatch,
    CensusAddress,
    census_lookup,
    load_address_settings,
    match_case_to_area,
)
from page47.analysis.case import load_matter_case
from page47.analysis.drift import compare_all_appearances, load_presentation_config
from page47.analysis.investigation import (
    investigate_matter,
    record_failed_investigation,
    review_graph_payload,
)
from page47.analysis.norms import compute_historical_norms, load_norm_settings
from page47.records.store import RecordStore, SourceReference, WatchObservation
from page47.runtime.client import AgentCoreTransport, load_agentcore_settings
from page47.snapshotter.config import JSONObject, JSONValue, as_json_value, load_city_config
from page47.snapshotter.store import SnapshotStore
from page47.web.config import CityRuntime, WebSettings


@dataclass(frozen=True, slots=True)
class WatchInput:
    city: str
    bodies: tuple[str, ...]
    address: str | None
    neighbourhood: str | None
    email: str


class WebService:
    def __init__(self, settings: WebSettings) -> None:
        self.settings = settings
        self.address_settings = load_address_settings(
            settings.repository_root / "config" / "address.yaml"
        )
        self.norm_settings = load_norm_settings(settings.repository_root / "config" / "norms.yaml")
        self.agentcore_settings = load_agentcore_settings(
            settings.repository_root / "config" / "agentcore.yaml"
        )
        self.agentcore = (
            AgentCoreTransport(self.agentcore_settings)
            if self.agentcore_settings.enabled
            else None
        )

    def _runtime(self, city: str) -> CityRuntime:
        return self.settings.city(city)

    def _store(self, city: str) -> RecordStore:
        return RecordStore(self._runtime(city).database)

    def cities(self) -> JSONObject:
        items: list[JSONValue] = []
        for city in self.settings.cities:
            config = load_city_config(city.city_config)
            items.append(
                {
                    "name": city.name,
                    "client": config.client,
                    "bodies": [body.name for body in config.watched_bodies],
                    "consent_analysis": (
                        "verified"
                        if config.consent_calibration.get("mapping_usable") is True
                        else "could_not_determine"
                    ),
                }
            )
        return {"cities": items, "default_city": self.settings.default_city}

    def bodies(self, city: str) -> JSONObject:
        config = load_city_config(self._runtime(city).city_config)
        return {"city": city, "bodies": [body.name for body in config.watched_bodies]}

    def matters(self, city: str, limit: int) -> JSONObject:
        if limit < 1 or limit > 200:
            raise ValueError("Matter limit must be between 1 and 200")
        with self._store(city) as store:
            rows = store.connection.execute(
                """
                SELECT m.matter_id, m.file_number, m.current_title, m.body_name,
                       a.event_id, a.event_date, a.title_as_presented,
                       a.pdf_placement, a.pdf_evidence_pages_json
                FROM matters m
                JOIN appearances a ON a.matter_id = m.matter_id
                WHERE a.event_date IS NOT NULL
                ORDER BY a.event_date DESC, a.event_item_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            items: list[JSONValue] = []
            seen: set[int] = set()
            for row in rows:
                matter_id = row["matter_id"]
                if isinstance(matter_id, bool) or not isinstance(matter_id, int):
                    raise ValueError("Stored matter ID was invalid")
                if matter_id in seen:
                    continue
                seen.add(matter_id)
                items.append(
                    {
                        "matter_id": matter_id,
                        "file_number": row["file_number"],
                        "current_title": row["current_title"],
                        "body_name": row["body_name"],
                        "latest_event_id": row["event_id"],
                        "latest_event_date": row["event_date"],
                        "latest_title": row["title_as_presented"],
                        "placement": row["pdf_placement"],
                        "placement_note": (
                            "could not determine"
                            if row["pdf_placement"] is None
                            else row["pdf_placement"]
                        ),
                    }
                )
            return {"city": city, "matters": items}

    def matter(self, city: str, matter_id: int) -> JSONObject:
        runtime = self._runtime(city)
        with self._store(city) as store:
            case = load_matter_case(store, city, matter_id, runtime.evidence_root)
            findings = store.finding_rows(city=city, limit=200)
            finding = next(
                (item for item in findings if item.get("matter_id") == matter_id), None
            )
            return {
                "case": case.structural_payload(),
                "finding": finding,
            }

    def findings(self, city: str, limit: int) -> JSONObject:
        with self._store(city) as store:
            findings = as_json_value(store.finding_rows(city, limit))
            if not isinstance(findings, list):
                raise ValueError("Stored findings were not a list")
            return {"city": city, "findings": findings}

    def finding(self, city: str, finding_id: str) -> JSONObject:
        runtime = self._runtime(city)
        presentation = load_presentation_config(
            self.settings.repository_root / "config" / "presentation.yaml"
        )
        with self._store(city) as store:
            matches = [
                item for item in store.finding_rows(city, 200) if item["finding_id"] == finding_id
            ]
            if not matches:
                raise LookupError(f"Finding {finding_id} was not found")
            result = dict(matches[0])
            matter_id = result.get("matter_id")
            if isinstance(matter_id, bool) or not isinstance(matter_id, int):
                raise ValueError("Stored finding matter ID was invalid")
            case = load_matter_case(store, city, matter_id, runtime.evidence_root)
            result["case"] = case.structural_payload()
            result["drift"] = as_json_value(
                compare_all_appearances(case, presentation).as_json()
            )
            return result

    def ledger(self, city: str) -> JSONObject:
        runtime = self._runtime(city)
        with self._store(city) as store:
            counts = store.counts()
            findings = store.finding_rows(city, 10000)
            changes = 0
            changes_path = SnapshotStore(runtime.evidence_root).changes_path
            if changes_path.exists():
                changes = len(changes_path.read_text(encoding="utf-8").splitlines())
            less_clear = sum(1 for item in findings if item.get("state") == "less_clear")
            clearer = sum(1 for item in findings if item.get("state") == "clearer")
            mixed = sum(1 for item in findings if item.get("state") == "mixed")
            rejected = 0
            for item in findings:
                value = item.get("rejected_count")
                if isinstance(value, int) and not isinstance(value, bool):
                    rejected += value
            return {
                "city": city,
                "matters_observed": counts["matters"],
                "packet_changes_recorded": changes,
                "became_less_clear": less_clear,
                "became_clearer": clearer,
                "mixed_presentation": mixed,
                "reviewed_findings": len(findings),
                "interpretations_rejected": rejected,
                "claims_about_intent": 0,
                "document_readings": counts["document_extractions"],
            }

    def norms(self, city: str) -> JSONObject:
        with self._store(city) as store:
            values = compute_historical_norms(store.connection, self.norm_settings)
            bodies = as_json_value([value.as_json() for value in values])
            if not isinstance(bodies, list):
                raise ValueError("Historical norms were not a list")
            return {"city": city, "bodies": bodies}

    def create_watch(self, data: WatchInput) -> JSONObject:
        runtime = self._runtime(data.city)
        if not data.bodies:
            raise ValueError("Choose at least one public body")
        config = load_city_config(runtime.city_config)
        allowed = {body.name for body in config.watched_bodies}
        unknown = set(data.bodies) - allowed
        if unknown:
            raise ValueError(f"Unconfigured public bodies: {sorted(unknown)}")
        if data.address is None and data.neighbourhood is None:
            raise ValueError("Enter an address or neighbourhood")
        if "@" not in data.email or data.email.count("@") != 1:
            raise ValueError("Enter a valid email address")
        geocoded: CensusAddress | None = None
        if data.address is not None:
            geocoded = census_lookup(
                data.address,
                self.address_settings,
                runtime.evidence_root,
            )
        watch_id = uuid4().hex
        now = datetime.now(UTC).isoformat()
        with self._store(data.city) as store:
            store.save_watch(
                WatchObservation(
                    watch_id=watch_id,
                    city=data.city,
                    bodies=list(data.bodies),
                    address=data.address,
                    neighbourhood=data.neighbourhood,
                    email=data.email,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            store.commit()
        return {
            "watch_id": watch_id,
            "manage_path": f"/watch/{watch_id}",
            "city": data.city,
            "area": {
                "address": geocoded.as_json() if geocoded is not None else None,
                "neighbourhood": data.neighbourhood,
            },
            "message": (
                "Your watch is saved. Keep the private link to review or stop it. "
                "New public records will be checked on the next scheduled run."
            ),
        }

    def watch(self, watch_id: str) -> JSONObject:
        for city in self.settings.cities:
            with self._store(city.name) as store:
                watch = store.watch_row(watch_id)
                if watch is not None:
                    sent_row = store.connection.execute(
                        "SELECT COUNT(*) FROM notifications "
                        "WHERE watch_id = ? AND status = 'sent'",
                        (watch_id,),
                    ).fetchone()
                    if sent_row is None or not isinstance(sent_row[0], int):
                        raise ValueError("Stored watch delivery count was invalid")
                    run_row = store.connection.execute(
                        "SELECT finished_at FROM collection_runs "
                        "WHERE status = 'completed' ORDER BY finished_at DESC LIMIT 1"
                    ).fetchone()
                    last_check = run_row[0] if run_row is not None else None
                    if last_check is not None and not isinstance(last_check, str):
                        raise ValueError("Stored collector check time was invalid")
                    watch["manage_path"] = f"/watch/{watch_id}"
                    watch["reviews_delivered"] = sent_row[0]
                    watch["last_successful_check"] = last_check
                    return watch
        raise LookupError(f"Watch {watch_id} was not found")

    def deactivate_watch(self, watch_id: str) -> JSONObject:
        now = datetime.now(UTC).isoformat()
        for city in self.settings.cities:
            with self._store(city.name) as store:
                if store.watch_row(watch_id) is None:
                    continue
                store.deactivate_watch(watch_id, now)
                store.commit()
                return {
                    "watch_id": watch_id,
                    "active": False,
                    "message": (
                        "This watch has been stopped. It will not send further review emails."
                    ),
                }
        raise LookupError(f"Watch {watch_id} was not found")

    def match_matter(
        self,
        city: str,
        matter_id: int,
        address: str | None,
        neighbourhood: str | None,
    ) -> AreaMatch:
        runtime = self._runtime(city)
        with self._store(city) as store:
            case = load_matter_case(store, city, matter_id, runtime.evidence_root)
        geocoded = (
            census_lookup(address, self.address_settings, runtime.evidence_root)
            if address is not None
            else None
        )
        return match_case_to_area(case, geocoded, neighbourhood)

    def investigate(self, city: str, matter_id: int) -> JSONObject:
        runtime = self._runtime(city)
        root = self.settings.repository_root
        with self._store(city) as store:
            if self.agentcore is None:
                outcome = investigate_matter(
                    store=store,
                    city=city,
                    matter_id=matter_id,
                    evidence_root=runtime.evidence_root,
                    models_path=root / "config" / "models.yaml",
                    presentation_path=root / "config" / "presentation.yaml",
                    policy_path=root / "config" / "policy.yaml",
                    norms_path=root / "config" / "norms.yaml",
                )
            else:
                case = load_matter_case(store, city, matter_id, runtime.evidence_root)
                try:
                    graph_result = self.agentcore.invoke_case(case)
                except Exception as error:
                    record_failed_investigation(store, city, matter_id, error)
                    raise
                outcome = review_graph_payload(
                    store=store,
                    city=city,
                    matter_id=matter_id,
                    evidence_root=runtime.evidence_root,
                    models_path=root / "config" / "models.yaml",
                    presentation_path=root / "config" / "presentation.yaml",
                    policy_path=root / "config" / "policy.yaml",
                    norms_path=root / "config" / "norms.yaml",
                    graph_result=graph_result,
                )
            return {
                "run_id": outcome.run_id,
                "finding_id": f"{city.casefold().replace(' ', '-')}-{matter_id}",
                "state": outcome.decision.state,
                "publish": outcome.decision.publish,
                "message": (
                    "The stored public record was reviewed and the result is available below."
                ),
            }

    def attachment_file(self, city: str, attachment_id: int) -> tuple[bytes, SourceReference]:
        runtime = self._runtime(city)
        with self._store(city) as store:
            row = store.connection.execute(
                "SELECT matter_id FROM attachments WHERE attachment_id = ?", (attachment_id,)
            ).fetchone()
            if row is None or not isinstance(row[0], int):
                raise LookupError(f"Attachment {attachment_id} was not found")
            case = load_matter_case(store, city, row[0], runtime.evidence_root)
            for attachment in case.unique_attachments():
                if attachment.attachment_id == attachment_id:
                    capture = attachment.document_capture()
                    if capture is None:
                        raise LookupError(
                            f"Captured PDF bytes for attachment {attachment_id} were not found"
                        )
                    return capture
        raise LookupError(f"Attachment {attachment_id} was not found in its matter")

    def attachment_evidence(self, city: str, attachment_id: int) -> JSONObject:
        runtime = self._runtime(city)
        with self._store(city) as store:
            row = store.connection.execute(
                "SELECT matter_id FROM attachments WHERE attachment_id = ?", (attachment_id,)
            ).fetchone()
            if row is None or not isinstance(row[0], int):
                raise LookupError(f"Attachment {attachment_id} was not found")
            case = load_matter_case(store, city, row[0], runtime.evidence_root)
            for attachment in case.unique_attachments():
                if attachment.attachment_id == attachment_id:
                    capture = attachment.document_capture()
                    return {
                        "attachment": attachment.as_index_json(),
                        "capture": capture[1].as_json() if capture is not None else None,
                        "anchors": [anchor.as_json() for anchor in attachment.anchors],
                        "pdf_url": f"/evidence/{city}/attachment/{attachment_id}/file",
                    }
        raise LookupError(f"Attachment {attachment_id} was not found in its matter")
