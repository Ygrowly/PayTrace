"""ReportValidator — 13 validation rules for DiagnosisReport (plan § 16.1).

Returns structured ValidationIssue objects with code/field/message/retryable.
Non-retryable issues indicate permanent failures; retryable ones trigger the
one correction round in the orchestrator.
"""

from dataclasses import dataclass

from app.diagnosis.model import DiagnosisContext
from app.diagnosis.report import DiagnosisReport
from app.ontology.registry import EvidenceType, RootCauseLabel
from app.tools.base import Evidence

# Acceptable rounding tolerance for explained + unexplained vs total (rule 6)
_ROUNDING_TOLERANCE = 2


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    field: str
    message: str
    retryable: bool


class ReportValidator:
    """Validates a DiagnosisReport against the 13 rules in plan § 16.1."""

    def __init__(self, validator_version: str = "paytrace.validator.v1") -> None:
        self._version = validator_version

    def validate(self, report: DiagnosisReport, context: DiagnosisContext) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        # Collect evidence codes present in this run's context.
        run_evidence_codes = {e.evidence_code for e in context.evidence_list}
        run_evidence: dict[str, Evidence] = {e.evidence_code: e for e in context.evidence_list}

        # ----------------------------------------------------------------
        # Rule 1: Incident and Run IDs match context
        # ----------------------------------------------------------------
        if report.incident_id != context.incident_id:
            issues.append(
                ValidationIssue(
                    code="R1_INCIDENT_MISMATCH",
                    field="incident_id",
                    message=(
                        f"report incident_id {report.incident_id!r} "
                        f"!= context {context.incident_id!r}"
                    ),
                    retryable=True,
                )
            )
        if report.diagnosis_run_id != context.diagnosis_run_id:
            issues.append(
                ValidationIssue(
                    code="R1_RUN_MISMATCH",
                    field="diagnosis_run_id",
                    message=(
                        f"report run_id {report.diagnosis_run_id!r} "
                        f"!= context {context.diagnosis_run_id!r}"
                    ),
                    retryable=True,
                )
            )

        # ----------------------------------------------------------------
        # Rule 2: Evidence codes in report exist in current run's evidence
        # ----------------------------------------------------------------
        all_referenced_codes: set[str] = set()
        for rc in report.root_causes:
            all_referenced_codes.update(rc.evidence_codes)
        missing_codes = all_referenced_codes - run_evidence_codes
        if missing_codes:
            codes_str = ", ".join(sorted(missing_codes))
            issues.append(
                ValidationIssue(
                    code="R2_BAD_EVIDENCE_REF",
                    field="root_causes.evidence_codes",
                    message=f"evidence codes not in run: {codes_str}",
                    retryable=True,
                )
            )

        # ----------------------------------------------------------------
        # Rule 3: Each root cause has at least one valid evidence code
        # ----------------------------------------------------------------
        for i, rc in enumerate(report.root_causes):
            valid = [c for c in rc.evidence_codes if c in run_evidence_codes]
            if not valid:
                msg = f"root_causes[{i}] ({rc.label}) has no valid evidence codes"
                if report.status == "NEEDS_DATA":
                    # NEEDS_DATA may legitimately have no root causes
                    if report.root_causes:
                        issues.append(
                            ValidationIssue(
                                "R3_NO_EVIDENCE", f"root_causes[{i}]", msg, retryable=False
                            )
                        )
                elif report.status == "SUCCEEDED":
                    issues.append(
                        ValidationIssue("R3_NO_EVIDENCE", f"root_causes[{i}]", msg, retryable=True)
                    )

        # ----------------------------------------------------------------
        # Rule 4: Root cause labels are valid according to Ontology
        # ----------------------------------------------------------------
        valid_labels = {r.value for r in RootCauseLabel}
        for i, rc in enumerate(report.root_causes):
            if rc.label not in valid_labels:
                issues.append(
                    ValidationIssue(
                        code="R4_BAD_LABEL",
                        field=f"root_causes[{i}].label",
                        message=f"invalid root cause label: {rc.label!r}",
                        retryable=True,
                    )
                )

        # ----------------------------------------------------------------
        # Rule 5: Loss values are non-negative
        # ----------------------------------------------------------------
        if report.total_estimated_lost_intents < 0:
            issues.append(
                ValidationIssue(
                    "R5_NEGATIVE_TOTAL",
                    "total_estimated_lost_intents",
                    f"negative: {report.total_estimated_lost_intents}",
                    retryable=True,
                )
            )
        if report.explained_lost_intents < 0:
            issues.append(
                ValidationIssue(
                    "R5_NEGATIVE_EXPLAINED",
                    "explained_lost_intents",
                    f"negative: {report.explained_lost_intents}",
                    retryable=True,
                )
            )
        if report.unexplained_lost_intents < 0:
            issues.append(
                ValidationIssue(
                    "R5_NEGATIVE_UNEXPLAINED",
                    "unexplained_lost_intents",
                    f"negative: {report.unexplained_lost_intents}",
                    retryable=True,
                )
            )
        for i, rc in enumerate(report.root_causes):
            if rc.estimated_lost_intents is not None and rc.estimated_lost_intents < 0:
                issues.append(
                    ValidationIssue(
                        "R5_NEGATIVE_RC_LOSS",
                        f"root_causes[{i}].estimated_lost_intents",
                        f"negative: {rc.estimated_lost_intents}",
                        retryable=True,
                    )
                )

        # ----------------------------------------------------------------
        # Rule 6: explained + unexplained ≈ total (allow rounding)
        # ----------------------------------------------------------------
        diff = abs(
            report.total_estimated_lost_intents
            - (report.explained_lost_intents + report.unexplained_lost_intents)
        )
        if diff > _ROUNDING_TOLERANCE:
            issues.append(
                ValidationIssue(
                    "R6_LOSS_IMBALANCE",
                    "explained_lost_intents",
                    (
                        f"explained({report.explained_lost_intents}) + "
                        f"unexplained({report.unexplained_lost_intents}) != "
                        f"total({report.total_estimated_lost_intents}), diff={diff}"
                    ),
                    retryable=True,
                )
            )

        # ----------------------------------------------------------------
        # Rule 7: Single root cause loss ≤ total
        # ----------------------------------------------------------------
        for i, rc in enumerate(report.root_causes):
            if (
                rc.estimated_lost_intents is not None
                and rc.estimated_lost_intents > report.total_estimated_lost_intents
            ):
                issues.append(
                    ValidationIssue(
                        "R7_RC_EXCEEDS_TOTAL",
                        f"root_causes[{i}].estimated_lost_intents",
                        (
                            f"{rc.estimated_lost_intents} "
                            f"> total {report.total_estimated_lost_intents}"
                        ),
                        retryable=True,
                    )
                )

        # ----------------------------------------------------------------
        # Rule 8: Evidence type can support the root cause label
        # ----------------------------------------------------------------
        for i, rc in enumerate(report.root_causes):
            rc_ev_types: set[EvidenceType] = set()
            for code in rc.evidence_codes:
                ev = run_evidence.get(code)
                if ev:
                    rc_ev_types.add(ev.evidence_type)
            if rc_ev_types and not _evidence_supports_label(rc_ev_types, rc.label):
                issues.append(
                    ValidationIssue(
                        "R8_EVIDENCE_LABEL_MISMATCH",
                        f"root_causes[{i}]",
                        f"evidence types {sorted(t.value for t in rc_ev_types)} "
                        f"do not support label {rc.label!r}",
                        retryable=True,
                    )
                )

        # ----------------------------------------------------------------
        # Rule 9: NEEDS_DATA must list specific missing data
        # ----------------------------------------------------------------
        if report.status == "NEEDS_DATA" and not report.missing_data:
            issues.append(
                ValidationIssue(
                    "R9_NEEDS_DATA_EMPTY",
                    "missing_data",
                    "status is NEEDS_DATA but missing_data is empty",
                    retryable=True,
                )
            )

        # ----------------------------------------------------------------
        # Rule 10: Low-/no-evidence reports must not claim HIGH confidence
        # ----------------------------------------------------------------
        has_real_evidence = any(
            e.evidence_type != EvidenceType.DATA_GAP for e in context.evidence_list
        )
        for i, rc in enumerate(report.root_causes):
            if rc.confidence == "HIGH" and not has_real_evidence:
                issues.append(
                    ValidationIssue(
                        "R10_HIGH_CONF_NO_EV",
                        f"root_causes[{i}].confidence",
                        "HIGH confidence with no significant evidence",
                        retryable=True,
                    )
                )
        # Also flag NORMAL_PAYMENT_FAILURE with HIGH confidence.
        for i, rc in enumerate(report.root_causes):
            if rc.label == "NORMAL_PAYMENT_FAILURE" and rc.confidence == "HIGH":
                issues.append(
                    ValidationIssue(
                        "R10_HIGH_CONF_NORMAL",
                        f"root_causes[{i}]",
                        "NORMAL_PAYMENT_FAILURE should not be HIGH confidence",
                        retryable=True,
                    )
                )

        # ----------------------------------------------------------------
        # Rule 11: Benefit gap must not be sole causal proof
        #     (plan § 13.3: always warn; if it is the ONLY evidence for
        #      a BENEFIT_SELECTION_FRICTION root cause, flag a validation
        #      issue — not an error, but recorded as a warning.)
        # ----------------------------------------------------------------
        for i, rc in enumerate(report.root_causes):
            if rc.label == "BENEFIT_SELECTION_FRICTION":
                r11_ev_types: set[EvidenceType] = set()
                for code in rc.evidence_codes:
                    ev = run_evidence.get(code)
                    if ev:
                        r11_ev_types.add(ev.evidence_type)
                # If BENEFIT_GAP_FRICTION is the only evidence type, flag.
                if r11_ev_types == {EvidenceType.BENEFIT_GAP_FRICTION}:
                    issues.append(
                        ValidationIssue(
                            "R11_BENEFIT_ONLY",
                            f"root_causes[{i}]",
                            "BENEFIT_SELECTION_FRICTION supported only by BENEFIT_GAP_FRICTION "
                            "(observational, not causal proof)",
                            retryable=False,  # Not retryable; model should learn but not fail
                        )
                    )

        # ----------------------------------------------------------------
        # Rule 12: Validator version matches
        # ----------------------------------------------------------------
        if report.validator_version != self._version:
            issues.append(
                ValidationIssue(
                    "R12_SCHEMA_VERSION",
                    "validator_version",
                    f"expected {self._version!r}, got {report.validator_version!r}",
                    retryable=False,
                )
            )

        # ----------------------------------------------------------------
        # Rule 13: Reference consistency — all evidence_codes in report map
        #     to unique evidence records in the current run (duplicate check).
        # ----------------------------------------------------------------
        # Check for duplicates within a single root cause's evidence_codes.
        for i, rc in enumerate(report.root_causes):
            if len(rc.evidence_codes) != len(set(rc.evidence_codes)):
                issues.append(
                    ValidationIssue(
                        "R13_DUPLICATE_CODES",
                        f"root_causes[{i}].evidence_codes",
                        "duplicate evidence codes in root cause",
                        retryable=True,
                    )
                )

        return issues


def _evidence_supports_label(ev_types: set[EvidenceType], label: str) -> bool:
    """Check if the given evidence types can support a root cause label.

    Mapping logic:
    - FUNNEL_STAGE_DEGRADATION → supports any label (generic degradation signal)
    - DIMENSION_CONTRIBUTION → supports any label (directional signal)
    - ERROR_CODE_CONCENTRATION → supports any label
    - CHANNEL_TIMEOUT → supports CHANNEL_TIMEOUT
    - BENEFIT_GAP_FRICTION → supports BENEFIT_SELECTION_FRICTION
    - DATA_GAP → supports DATA_QUALITY_ISSUE
    - BENEFIT_GAP_FRICTION + any degradation → supports BENEFIT_SELECTION_FRICTION
    """
    generic = {
        EvidenceType.FUNNEL_STAGE_DEGRADATION,
        EvidenceType.DIMENSION_CONTRIBUTION,
        EvidenceType.ERROR_CODE_CONCENTRATION,
    }

    # If all evidence is generic, it supports any label.
    if ev_types.issubset(generic):
        return True

    # Check specific evidence-to-label mappings.
    specific_checks: list[tuple[EvidenceType, str]] = [
        (EvidenceType.CHANNEL_TIMEOUT, "CHANNEL_TIMEOUT"),
        (EvidenceType.BENEFIT_GAP_FRICTION, "BENEFIT_SELECTION_FRICTION"),
        (EvidenceType.DATA_GAP, "DATA_QUALITY_ISSUE"),
    ]

    for ev_type, expected_label in specific_checks:
        if ev_type in ev_types and label != expected_label:
            return False

    # AUTHENTICATION_FAILURE, CALLBACK_FAILURE, NORMAL_PAYMENT_FAILURE accept
    # any evidence (generic + specific — they're catch-all labels).
    if label in ("AUTHENTICATION_FAILURE", "CALLBACK_FAILURE", "NORMAL_PAYMENT_FAILURE", "UNKNOWN"):
        return True

    return True
