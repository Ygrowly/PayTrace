"""Read-only unit coverage for FK-less service integrity guards."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.diagnosis.report import DiagnosisReport
from app.incidents import service


def _session_with_first(value) -> MagicMock:
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = value
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = (
        value
    )
    return db


def test_create_run_rejects_missing_incident_without_insert() -> None:
    db = _session_with_first(None)

    with pytest.raises(service.ReferentialIntegrityError, match="Incident"):
        service.create_or_get_run(db, uuid.uuid4(), "ik-orphan")

    db.execute.assert_not_called()


def test_write_event_rejects_missing_run_without_insert() -> None:
    db = _session_with_first(None)

    with pytest.raises(service.ReferentialIntegrityError, match="DiagnosisRun"):
        service.write_event(db, diagnosis_run_id=uuid.uuid4(), event_type="orphan")

    db.add.assert_not_called()


def test_persist_report_rejects_incident_mismatch_without_insert() -> None:
    run_id = uuid.uuid4()
    persisted_incident_id = uuid.uuid4()
    db = _session_with_first(SimpleNamespace(incident_id=persisted_incident_id))
    report = DiagnosisReport(
        incident_id=str(uuid.uuid4()),
        diagnosis_run_id=str(run_id),
        status="SUCCEEDED",
        summary="mismatch",
        ontology_version="paytrace.ontology.v1",
        validator_version="paytrace.validator.v1",
    )

    with pytest.raises(service.ReferentialIntegrityError, match="Report incident"):
        service.persist_report(
            db,
            run_id=run_id,
            report=report,
            validator_version=report.validator_version,
        )

    db.add.assert_not_called()
