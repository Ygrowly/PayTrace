"""Integration tests for Incident API, DiagnosisRun API, and service layer.

Covers plan § 17 (diagnosis pipeline) and § 18.3-18.6 (API endpoints).
Tests run against the real PostgreSQL database with per-test rollback.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Incident
from app.diagnosis.report import DiagnosisReport, RootCause
from app.incidents import service
from tests.conftest import _incident_payload

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_incident(db: Session, **overrides) -> Incident:
    """Insert a fresh incident and return the ORM object."""
    now = datetime.now(UTC)
    data = dict(
        title="fixture incident",
        scenario_id="mixed_failure",
        dataset_ref="s3://test/ds",
        baseline_start=now - timedelta(days=14),
        baseline_end=now - timedelta(days=7),
        incident_start=now - timedelta(days=1),
        incident_end=now,
        trigger_metric="payment_success_rate",
        baseline_value=0.95,
        observed_value=0.72,
        ontology_version="paytrace.ontology.v1",
    )
    data.update(overrides)
    return service.create_incident(db, **data)


# ===================================================================
# Service-layer tests (plan § 17 state machine, idempotency, events)
# ===================================================================


class TestIncidentService:
    def test_create_incident_populates_defaults(self, db_session: Session) -> None:
        inc = _make_incident(db_session, title="Spike #1")
        assert inc.id is not None
        assert inc.title == "Spike #1"
        assert inc.status == "DETECTED"
        assert inc.created_at is not None
        assert inc.updated_at is not None

    def test_list_incidents_pagination(self, db_session: Session) -> None:
        for i in range(5):
            _make_incident(db_session, title=f"Incident {i}")

        items, total = service.list_incidents(db_session, page=1, page_size=3)
        assert len(items) == 3
        assert total == 5

        items2, _ = service.list_incidents(db_session, page=2, page_size=3)
        assert len(items2) == 2

    def test_list_incidents_filter_by_status(self, db_session: Session) -> None:
        _make_incident(db_session, title="detected")
        inc2 = _make_incident(db_session, title="resolved")
        inc2.status = "RESOLVED"
        db_session.flush()

        items, total = service.list_incidents(db_session, status="RESOLVED")
        assert total == 1
        assert items[0].title == "resolved"

    def test_list_incidents_filter_by_scenario(self, db_session: Session) -> None:
        _make_incident(db_session, title="mixed", scenario_id="mixed_failure")
        _make_incident(db_session, title="timeout", scenario_id="channel_timeout")

        items, total = service.list_incidents(db_session, scenario_id="channel_timeout")

        assert total == 1
        assert items[0].title == "timeout"

    def test_get_incident_found_and_missing(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        assert service.get_incident(db_session, inc.id) is not None
        assert service.get_incident(db_session, uuid.uuid4()) is None


class TestDiagnosisRunService:
    def test_create_or_get_run_idempotent(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        key = "ik-001"

        run1, created1 = service.create_or_get_run(db_session, inc.id, key)
        db_session.flush()
        assert created1 is True
        assert run1.status == "PENDING"

        # Same key → existing run
        run2, created2 = service.create_or_get_run(db_session, inc.id, key)
        assert created2 is False
        assert run2.id == run1.id

    def test_create_or_get_run_different_keys(self, db_session: Session) -> None:
        inc = _make_incident(db_session)

        run_a, _ = service.create_or_get_run(db_session, inc.id, "key-a")
        run_b, _ = service.create_or_get_run(db_session, inc.id, "key-b")
        db_session.flush()
        assert run_a.id != run_b.id

    def test_valid_state_transitions(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-valid")
        db_session.flush()

        # PENDING → QUEUED (valid)
        service.update_run_status(db_session, run, "QUEUED", celery_task_id="task-1")
        assert run.status == "QUEUED"
        assert run.celery_task_id == "task-1"

    def test_invalid_state_transition_raises(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-bad")
        db_session.flush()

        # PENDING → RUNNING is invalid (must go through QUEUED per state machine)
        with pytest.raises(ValueError, match="Invalid state transition"):
            service.update_run_status(db_session, run, "RUNNING")

    def test_running_sets_started_at(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-time")
        db_session.flush()

        service.update_run_status(db_session, run, "QUEUED")
        service.update_run_status(db_session, run, "RUNNING")
        assert run.started_at is not None
        assert run.started_at.tzinfo is not None

    def test_terminal_sets_finished_at(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-term")
        db_session.flush()

        service.update_run_status(db_session, run, "QUEUED")
        service.update_run_status(db_session, run, "RUNNING")
        service.update_run_status(db_session, run, "FAILED")
        assert run.finished_at is not None

    def test_write_event_appends_sequence(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-ev")
        db_session.flush()

        e1 = service.write_event(
            db_session,
            diagnosis_run_id=run.id,
            event_type="run_started",
            stage="RUNNING",
            message="Started",
        )
        e2 = service.write_event(
            db_session,
            diagnosis_run_id=run.id,
            event_type="run_done",
            stage="SUCCEEDED",
            message="Done",
        )
        db_session.flush()
        assert e1.sequence == 1
        assert e2.sequence == 2

    def test_persist_and_get_report(self, db_session: Session) -> None:
        inc = _make_incident(db_session)
        run, _ = service.create_or_get_run(db_session, inc.id, "ik-report")
        db_session.flush()

        report = DiagnosisReport(
            incident_id=str(inc.id),
            diagnosis_run_id=str(run.id),
            status="SUCCEEDED",
            summary="Payment gateway timeout caused 45% loss",
            total_estimated_lost_intents=450,
            explained_lost_intents=400,
            unexplained_lost_intents=50,
            missing_data=["payment_method_dimension_missing"],
            recommended_actions=["Retry with exponential backoff on gateway timeout"],
            root_causes=[
                RootCause(
                    label="GatewayTimeout",
                    category="infrastructure",
                    confidence="HIGH",
                    estimated_lost_intents=400,
                    explanation="Gateway timeout on payment_channel=visa_direct",
                    evidence_codes=["EV-001", "EV-002"],
                    rank=1,
                )
            ],
            ontology_version="paytrace.ontology.v1",
            validator_version="0.0.1",
        )

        service.persist_report(db_session, run_id=run.id, report=report, validator_version="0.0.1")

        # Retrieve
        rec, findings = service.get_report(db_session, run.id)
        assert rec is not None
        assert rec.status == "SUCCEEDED"
        assert rec.summary == report.summary
        assert rec.total_estimated_lost_intents == 450
        assert len(findings) == 1
        assert findings[0].label == "GatewayTimeout"
        assert findings[0].confidence == "HIGH"

    def test_get_report_not_found(self, db_session: Session) -> None:
        rec, findings = service.get_report(db_session, uuid.uuid4())
        assert rec is None
        assert findings == []


# ===================================================================
# API endpoint tests (plan § 18.3-18.6)
# ===================================================================


class TestIncidentAPI:
    async def test_create_incident_returns_201(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/incidents", json=_incident_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Test payment failure spike"
        assert body["status"] == "DETECTED"
        assert "id" in body
        uuid.UUID(body["id"])  # valid UUID

    async def test_create_incident_validation_error(self, client: AsyncClient) -> None:
        resp = await client.post("/api/v1/incidents", json={"title": ""})
        assert resp.status_code == 422

    async def test_list_incidents_returns_paginated(self, client: AsyncClient) -> None:
        # Create 3 incidents
        for i in range(3):
            await client.post("/api/v1/incidents", json=_incident_payload(title=f"Inc {i}"))

        resp = await client.get("/api/v1/incidents?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 2
        assert body["pagination"]["total"] == 3

    async def test_get_incident_by_id(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/incidents/{inc_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == inc_id

    async def test_get_incident_not_found(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/incidents/{fake_id}")
        assert resp.status_code == 404

    async def test_create_simulated_incident_materialises_dataset_and_funnel(
        self, client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scenario_root = tmp_path / "scenarios"
        monkeypatch.setattr(get_settings(), "scenario_root", str(scenario_root))

        create = await client.post(
            "/api/v1/incidents/simulated",
            json={"scenario_kind": "mixed_failure", "seed": 42, "num_intents": 20},
        )

        assert create.status_code == 201
        body = create.json()
        assert body["scenario_id"] == "mixed_failure"
        assert Path(body["dataset_ref"]).exists()
        assert (scenario_root / "ground_truth" / "mixed_failure.ground_truth.json").exists()

        funnel = await client.get(f"/api/v1/incidents/{body['id']}/funnel")
        assert funnel.status_code == 200
        funnel_body = funnel.json()
        assert funnel_body["baseline"]["order_confirmed_count"] > 0
        assert funnel_body["incident"]["order_confirmed_count"] > 0
        assert funnel_body["anomalous_stages"]


class TestDiagnosisAPI:
    async def test_trigger_diagnosis_returns_202(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        # Mock Celery to avoid actual task dispatch
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "celery-task-mock-id"
            resp = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-test-001"},
            )

        assert resp.status_code == 202
        body = resp.json()
        assert "diagnosis_run_id" in body
        assert body["status"] == "QUEUED"

    async def test_trigger_diagnosis_missing_idempotency_key(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/incidents/{inc_id}/diagnosis-runs",
            headers={"Idempotency-Key": ""},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["code"] == "INVALID_IDEMPOTENCY_KEY"

    async def test_trigger_diagnosis_incident_not_found(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/incidents/{fake_id}/diagnosis-runs",
            headers={"Idempotency-Key": "ik-404"},
        )
        assert resp.status_code == 404
        body = resp.json()
        assert body["detail"]["code"] == "INCIDENT_NOT_FOUND"

    async def test_trigger_diagnosis_duplicate_key_returns_existing(
        self, client: AsyncClient
    ) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        # First request — creates new run
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-1"
            resp1 = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-dup-001"},
            )
        assert resp1.status_code == 202
        run_id_1 = resp1.json()["diagnosis_run_id"]

        # Second request — same key → returns existing
        resp2 = await client.post(
            f"/api/v1/incidents/{inc_id}/diagnosis-runs",
            headers={"Idempotency-Key": "ik-dup-001"},
        )
        assert resp2.status_code == 202
        assert resp2.json()["diagnosis_run_id"] == run_id_1
        assert "Existing diagnosis run" in resp2.json()["message"]

    async def test_get_diagnosis_run_status(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-status"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-status-001"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == run_id
        assert body["incident_id"] == inc_id
        assert body["status"] == "QUEUED"
        assert body["celery_task_id"] == "task-status"

    async def test_get_diagnosis_run_not_found(self, client: AsyncClient) -> None:
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/diagnosis-runs/{fake_id}")
        assert resp.status_code == 404

    async def test_events_replay_from_last_event_and_trace_is_available(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-events"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-events-001"},
            )

        run_id = trigger.json()["diagnosis_run_id"]
        run = service.get_run(db_session, uuid.UUID(run_id))
        assert run is not None
        service.update_run_status(db_session, run, "RUNNING")
        service.write_event(
            db_session,
            diagnosis_run_id=run.id,
            event_type="run_started",
            stage="RUNNING",
            message="Started",
        )
        service.update_run_status(db_session, run, "FAILED")
        service.write_event(
            db_session,
            diagnosis_run_id=run.id,
            event_type="run_failed",
            stage="FAILED",
            message="Failed",
        )
        db_session.commit()

        events = await client.get(
            f"/api/v1/diagnosis-runs/{run_id}/events",
            headers={"Last-Event-ID": "1"},
        )
        assert events.status_code == 200
        assert events.headers["content-type"].startswith("text/event-stream")
        assert "event: run_started" in events.text
        assert "event: run_failed" in events.text
        assert "event: run_queued" not in events.text

        trace = await client.get(f"/api/v1/diagnosis-runs/{run_id}/trace")
        assert trace.status_code == 200
        assert [event["event_type"] for event in trace.json()["events"]] == [
            "run_queued",
            "run_started",
            "run_failed",
        ]


class TestReportAPI:
    async def test_get_report_no_report_yet(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-rpt"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-report-001"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        # No report persisted yet → 404
        resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}/report")
        assert resp.status_code == 404

    async def test_get_report_after_persistence(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-persist"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-persist-001"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        # Persist a report via the service layer directly
        run_uuid = uuid.UUID(run_id)
        run = service.get_run(db_session, run_uuid)
        assert run is not None

        report = DiagnosisReport(
            incident_id=inc_id,
            diagnosis_run_id=run_id,
            status="SUCCEEDED",
            summary="Analysis complete",
            total_estimated_lost_intents=100,
            explained_lost_intents=80,
            unexplained_lost_intents=20,
            missing_data=[],
            recommended_actions=["Fix gateway"],
            root_causes=[
                RootCause(
                    label="TestRootCause",
                    category="infra",
                    confidence="MEDIUM",
                    estimated_lost_intents=80,
                    explanation="Test explanation",
                    evidence_codes=["EV-001"],
                    rank=1,
                )
            ],
            ontology_version="paytrace.ontology.v1",
            validator_version="0.0.1",
        )
        service.persist_report(
            db_session, run_id=run_uuid, report=report, validator_version="0.0.1"
        )
        db_session.flush()

        resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}/report")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "SUCCEEDED"
        assert body["summary"] == "Analysis complete"
        assert body["total_estimated_lost_intents"] == 100
        assert len(body["root_causes"]) == 1
        assert body["root_causes"][0]["label"] == "TestRootCause"


class TestRetryAPI:
    async def test_retry_creates_new_run(self, client: AsyncClient, db_session: Session) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        # Create original run
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-orig"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-rt-orig"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        # Mark original run as FAILED (retry requires a terminal/failed status)
        run_uuid = uuid.UUID(run_id)
        original = service.get_run(db_session, run_uuid)
        assert original is not None
        service.update_run_status(db_session, original, "RUNNING")
        service.update_run_status(db_session, original, "FAILED")
        db_session.flush()

        # Retry with new key
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-retry"
            retry_resp = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs/{run_id}/retry",
                headers={"Idempotency-Key": "ik-rt-retry"},
            )

        assert retry_resp.status_code == 202
        body = retry_resp.json()
        assert body["status"] == "QUEUED"
        assert body["original_run_id"] == run_id
        assert body["new_diagnosis_run_id"] != run_id

    async def test_retry_not_retryable_status(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        """Retry of a QUEUED run should be rejected as not retryable."""

        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-nrt"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-retry-nrt"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        # Retry should be rejected (run is QUEUED, not retryable)
        resp = await client.post(
            f"/api/v1/incidents/{inc_id}/diagnosis-runs/{run_id}/retry",
            headers={"Idempotency-Key": "ik-retry-nrt-2"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "RUN_NOT_RETRYABLE"

    async def test_retry_invalid_idempotency_key(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/incidents/{inc_id}/diagnosis-runs/{uuid.uuid4()}/retry",
            headers={"Idempotency-Key": ""},
        )
        assert resp.status_code == 400

    async def test_retry_run_not_found(self, client: AsyncClient) -> None:
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/incidents/{inc_id}/diagnosis-runs/{uuid.uuid4()}/retry",
            headers={"Idempotency-Key": "ik-rt-missing"},
        )
        assert resp.status_code == 404

    async def test_retry_incident_mismatch(self, client: AsyncClient) -> None:
        # Create two incidents
        r1 = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_a = r1.json()["id"]
        r2 = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_b = r2.json()["id"]

        # Create a run under incident A
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-mm"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_a}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-mm-orig"},
            )
        run_id = trigger.json()["diagnosis_run_id"]

        # Try to retry that run under incident B
        resp = await client.post(
            f"/api/v1/incidents/{inc_b}/diagnosis-runs/{run_id}/retry",
            headers={"Idempotency-Key": "ik-mm-retry"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "INCIDENT_MISMATCH"


class TestStateMachineScenarios:
    """End-to-end state machine scenarios that combine service + API layers."""

    async def test_full_happy_path_flow(self, client: AsyncClient, db_session: Session) -> None:
        """Simulate the lifecycle: create → trigger → RUNNING → SUCCEEDED → report."""

        # 1. Create incident via API
        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        # 2. Trigger diagnosis (mocked Celery)
        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-e2e"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-e2e"},
            )
        run_id = trigger.json()["diagnosis_run_id"]
        run_uuid = uuid.UUID(run_id)

        # 3. Advance state through the chain (service layer)
        run = service.get_run(db_session, run_uuid)
        assert run is not None

        run_ids = [
            "RUNNING",
            "COLLECTING_EVIDENCE",
            "GENERATING_REPORT",
            "VALIDATING",
        ]
        for status in run_ids:
            service.update_run_status(db_session, run, status)
            db_session.flush()

        # Validate transition was applied
        db_session.refresh(run)
        assert run.status == "VALIDATING"

        # 4. Persist a report and mark SUCCEEDED
        report = DiagnosisReport(
            incident_id=inc_id,
            diagnosis_run_id=run_id,
            status="SUCCEEDED",
            summary="All good",
            total_estimated_lost_intents=50,
            explained_lost_intents=50,
            unexplained_lost_intents=0,
            missing_data=[],
            recommended_actions=[],
            root_causes=[],
            ontology_version="paytrace.ontology.v1",
            validator_version="0.0.1",
        )
        service.update_run_status(db_session, run, "SUCCEEDED")
        service.persist_report(
            db_session, run_id=run_uuid, report=report, validator_version="0.0.1"
        )
        db_session.flush()

        # 5. Verify final state via API
        status_resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}")
        assert status_resp.json()["status"] == "SUCCEEDED"

        report_resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}/report")
        assert report_resp.status_code == 200
        assert report_resp.json()["status"] == "SUCCEEDED"

    async def test_needs_data_flow(self, client: AsyncClient, db_session: Session) -> None:
        """Validate NEEDS_DATA terminal status after validation."""

        create_resp = await client.post("/api/v1/incidents", json=_incident_payload())
        inc_id = create_resp.json()["id"]

        with patch("app.api.v1.incidents.run_diagnosis.delay") as mock_delay:
            mock_delay.return_value.id = "task-nd"
            trigger = await client.post(
                f"/api/v1/incidents/{inc_id}/diagnosis-runs",
                headers={"Idempotency-Key": "ik-needs"},
            )
        run_id = trigger.json()["diagnosis_run_id"]
        run_uuid = uuid.UUID(run_id)
        run = service.get_run(db_session, run_uuid)
        assert run is not None

        statuses = ("QUEUED", "RUNNING", "COLLECTING_EVIDENCE", "GENERATING_REPORT", "VALIDATING")
        for status in statuses:
            service.update_run_status(db_session, run, status)
            db_session.flush()

        service.update_run_status(db_session, run, "NEEDS_DATA")
        db_session.flush()

        resp = await client.get(f"/api/v1/diagnosis-runs/{run_id}")
        assert resp.json()["status"] == "NEEDS_DATA"
