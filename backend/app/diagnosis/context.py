"""ContextBuilder (plan § 14.2).

Builds the structured DiagnosisContext passed to the ModelAdapter. Does not
send raw event rows or Ground Truth. Uses stable ordering for reproducibility.
"""

from app.diagnosis.model import DiagnosisContext
from app.ontology.registry import ONTOLOGY_VERSION
from app.tools.base import EvidenceLedger

# Maximum evidence items to include in context (plan § 14.2 budget)
_MAX_EVIDENCE_ITEMS = 20
_MAX_EVIDENCE_SUMMARY_CHARS = 4_000


class ContextBuilder:
    """Builds DiagnosisContext from incident info, tool results, and evidence.

    Constraints (plan § 14.2):
    - No raw event rows — only summaries and evidence codes.
    - No Ground Truth.
    - Max character/token budget applied per evidence summary.
    - Stable sort order (by evidence_code) for regression comparison.
    - Records which evidence was selected vs trimmed.
    """

    def __init__(self, max_evidence_items: int = _MAX_EVIDENCE_ITEMS) -> None:
        self._max_items = max_evidence_items

    def build(
        self,
        incident_id: str,
        diagnosis_run_id: str,
        scenario_id: str,
        funnel_summary: str,
        anomalous_stages: list[str],
        ledger: EvidenceLedger,
        missing_data: list[str],
    ) -> DiagnosisContext:
        all_evidence = ledger.all()

        # Stable sort by evidence_code (EV-NNN lexicographic).
        sorted_evidence = sorted(all_evidence, key=lambda e: e.evidence_code)

        # Select up to budget, sorted by evidence_code (stable lexicographic order).
        selected = sorted_evidence[: self._max_items]
        trimmed = sorted_evidence[self._max_items :]
        selected_codes = [e.evidence_code for e in selected]

        # Build summaries (one line per evidence, EV-XXX [TYPE] summary)
        summaries: list[str] = []
        total_chars = 0
        for ev in selected:
            line = f"{ev.evidence_code} [{ev.evidence_type.value}] {ev.summary}"
            if total_chars + len(line) > _MAX_EVIDENCE_SUMMARY_CHARS:
                break
            summaries.append(line)
            total_chars += len(line)

        if trimmed:
            summaries.append(f"({len(trimmed)} additional evidence items trimmed for budget)")

        return DiagnosisContext(
            incident_id=incident_id,
            diagnosis_run_id=diagnosis_run_id,
            scenario_id=scenario_id,
            ontology_version=ONTOLOGY_VERSION,
            funnel_summary=funnel_summary,
            anomalous_stages=anomalous_stages,
            evidence_summaries=summaries,
            evidence_list=selected,
            missing_data=missing_data,
            selected_evidence_codes=selected_codes,
        )
