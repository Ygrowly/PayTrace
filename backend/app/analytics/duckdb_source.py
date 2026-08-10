"""DuckDB-backed PaymentAnalyticsSource (plan § 9.1).

Reads validated Parquet datasets. All value filters are parameterised; the
only interpolated identifiers are dimension column names, which are checked
against ``ALLOWED_DIMENSIONS`` before use. The DuckDB connection is created
per call and never exposed to callers.
"""

import json
from pathlib import Path
from typing import Any

import duckdb

from app.analytics.base import (
    ALLOWED_DIMENSIONS,
    BenefitGapBucket,
    BenefitPeriodStats,
    BenefitQuery,
    BenefitResult,
    BreakdownQuery,
    BreakdownResult,
    BreakdownRow,
    CancelReorderDeltas,
    CancelReorderMetrics,
    CancelReorderQuery,
    CancelReorderResult,
    ConfigChange,
    ConfigChangesQuery,
    ConfigChangesResult,
    DatasetValidationResult,
    ErrorCodeCount,
    FunnelPeriodStats,
    FunnelQuery,
    FunnelResult,
    FunnelStageDelta,
    FunnelStageStat,
    LatencyStats,
    PaymentEventPeriodStats,
    PaymentEventQuery,
    PaymentEventResult,
)
from app.domain.events import FUNNEL_STAGE_ORDER

_MAX_ROWS = 10_000
# |rate_delta| above which a funnel stage counts as anomalous. Set above the
# binomial sampling noise floor for the M1 dataset scale (>=400 intents per
# period) but well below the injected fault magnitudes (>=10pp).
_ANOMALY_THRESHOLD = 0.05

# Benefit gap bucket boundaries (minor units).
_GAP_BUCKETS: list[tuple[str, int | None, int | None]] = [
    ("0-300", 0, 300),
    ("300-1000", 300, 1000),
    (">=1000", 1000, None),
]


def _require_dimension(dimension: str) -> str:
    if dimension not in ALLOWED_DIMENSIONS:
        msg = f"dimension not in whitelist: {dimension!r}"
        raise ValueError(msg)
    return dimension


class DuckDBAnalyticsSource:
    """PaymentAnalyticsSource over a local Parquet dataset."""

    def __init__(self, max_rows: int = _MAX_ROWS) -> None:
        self._max_rows = max_rows

    # -- helpers ------------------------------------------------------------

    def _connect(self, dataset_ref: str) -> duckdb.DuckDBPyConnection:
        path = Path(dataset_ref)
        if not path.is_file():
            msg = f"dataset not found: {dataset_ref}"
            raise FileNotFoundError(msg)
        con = duckdb.connect(":memory:")
        # read_parquet(?) cannot be parameterised inside CREATE VIEW (DuckDB
        # binder limitation). The path originates from a validated DatasetRef,
        # and we escape single quotes defensively before interpolation.
        safe = str(path.resolve()).replace("'", "''")
        con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{safe}')")  # noqa: S608 - path escaped above
        return con

    @staticmethod
    def _filter_clause(filters: dict[str, str]) -> tuple[str, list[Any]]:
        """Build a parameterised AND clause for whitelisted dimension filters."""
        clause = ""
        params: list[Any] = []
        for dim, value in filters.items():
            col = _require_dimension(dim)
            clause += f" AND {col} = ?"
            params.append(value)
        return clause, params

    # -- 13.1 funnel ----------------------------------------------------------

    def get_funnel(self, query: FunnelQuery) -> FunnelResult:
        clause, params = self._filter_clause(query.filters)
        con = self._connect(query.dataset_ref)
        try:
            # reached_count per stage: an intent "reaches" a stage if it has a
            # FUNNEL_PROGRESSION event at that stage. Count distinct intents.
            # Only whitelist-validated identifiers are interpolated into SQL.
            sql = f"""
                SELECT period, funnel_stage, COUNT(DISTINCT purchase_intent_id) AS n
                FROM events
                WHERE event_type = 'FUNNEL_PROGRESSION' AND funnel_stage IS NOT NULL
                {clause}
                GROUP BY period, funnel_stage
                """  # noqa: S608
            rows = con.execute(sql, params).fetchall()
        finally:
            con.close()

        counts: dict[str, dict[str, int]] = {"baseline": {}, "incident": {}}
        for period, stage, n in rows:
            counts[period][stage] = n

        def build(period: str) -> FunnelPeriodStats:
            c = counts[period]
            first = c.get(FUNNEL_STAGE_ORDER[0].value, 0)
            stages: list[FunnelStageStat] = []
            prev: int | None = None
            for stage in FUNNEL_STAGE_ORDER:
                n = c.get(stage.value, 0)
                step = (n / prev) if prev else None
                overall = (n / first) if first else 0.0
                stages.append(
                    FunnelStageStat(
                        stage=stage.value,
                        reached_count=n,
                        step_rate=step,
                        overall_rate=overall,
                    )
                )
                prev = n
            return FunnelPeriodStats(
                period=period,  # type: ignore[arg-type]
                stages=stages,
                order_confirmed_count=first,
                completed_count=c.get(FUNNEL_STAGE_ORDER[-1].value, 0),
            )

        baseline = build("baseline")
        incident = build("incident")

        deltas: list[FunnelStageDelta] = []
        anomalous: list[str] = []
        for b, i in zip(baseline.stages, incident.stages, strict=True):
            delta = i.overall_rate - b.overall_rate
            lost = (
                max(
                    0,
                    round(
                        i.reached_count
                        * (b.overall_rate - i.overall_rate)
                        / max(b.overall_rate, 1e-9)
                    ),
                )
                if b.overall_rate > i.overall_rate
                else 0
            )
            deltas.append(
                FunnelStageDelta(
                    stage=b.stage,
                    baseline_overall_rate=b.overall_rate,
                    incident_overall_rate=i.overall_rate,
                    rate_delta=delta,
                    estimated_lost_intents=lost,
                )
            )
            # Anomaly detection uses the STEP rate (conditional on reaching the
            # previous stage). Overall-rate deltas are diluted by upstream
            # attrition and by dimension mix, so a localised fault (e.g. one
            # channel timing out) may not move the overall rate past threshold.
            if (
                b.step_rate is not None
                and i.step_rate is not None
                and abs(i.step_rate - b.step_rate) > _ANOMALY_THRESHOLD
            ):
                anomalous.append(b.stage)

        return FunnelResult(
            baseline=baseline,
            incident=incident,
            deltas=deltas,
            anomalous_stages=anomalous,
        )

    # -- 13.2 breakdown ---------------------------------------------------------

    def breakdown_loss(self, query: BreakdownQuery) -> BreakdownResult:
        dim = _require_dimension(query.dimension)
        con = self._connect(query.dataset_ref)
        # dim is whitelist-validated by _require_dimension before interpolation.
        sql = f"""
                WITH reached AS (
                    SELECT period, {dim} AS dim_value, funnel_stage,
                           COUNT(DISTINCT purchase_intent_id) AS n
                    FROM events
                    WHERE event_type = 'FUNNEL_PROGRESSION' AND funnel_stage IS NOT NULL
                    GROUP BY period, {dim}, funnel_stage
                )
                SELECT dim_value,
                       SUM(CASE WHEN period='baseline' AND funnel_stage=? THEN n ELSE 0 END),
                       SUM(CASE WHEN period='incident' AND funnel_stage=? THEN n ELSE 0 END),
                       SUM(CASE WHEN period='baseline' AND funnel_stage=? THEN n ELSE 0 END),
                       SUM(CASE WHEN period='incident' AND funnel_stage=? THEN n ELSE 0 END)
                FROM reached
                GROUP BY dim_value
                ORDER BY dim_value
                LIMIT ?
                """  # noqa: S608
        try:
            rows = con.execute(
                sql,
                [
                    FUNNEL_STAGE_ORDER[0].value,
                    FUNNEL_STAGE_ORDER[0].value,
                    FUNNEL_STAGE_ORDER[-1].value,
                    FUNNEL_STAGE_ORDER[-1].value,
                    min(query.top_k, 20),
                ],
            ).fetchall()
        finally:
            con.close()

        out: list[BreakdownRow] = []
        for dim_value, b_first, i_first, b_last, i_last in rows:
            b_rate = (b_last / b_first) if b_first else 0.0
            i_rate = (i_last / i_first) if i_first else 0.0
            lost = max(0, round(i_first * (b_rate - i_rate))) if b_rate > i_rate else 0
            out.append(
                BreakdownRow(
                    dimension_value=str(dim_value),
                    baseline_order_confirmed=b_first,
                    incident_order_confirmed=i_first,
                    baseline_completed=b_last,
                    incident_completed=i_last,
                    baseline_rate=b_rate,
                    incident_rate=i_rate,
                    rate_delta=i_rate - b_rate,
                    estimated_lost_intents=lost,
                )
            )
        out.sort(key=lambda r: r.estimated_lost_intents, reverse=True)
        return BreakdownResult(dimension=dim, rows=out)

    # -- 13.3 benefit gap ---------------------------------------------------------

    def analyze_benefit_gap(self, query: BenefitQuery) -> BenefitResult:
        con = self._connect(query.dataset_ref)
        try:
            # Per-intent aggregates: gap, cancelled, reordered, switched, recovered.
            rows = con.execute(
                """
                WITH per_intent AS (
                    SELECT period, purchase_intent_id,
                           MAX(selected_payable_minor - best_payable_minor) AS gap,
                           BOOL_OR(event_type = 'ORDER_CANCELLED') AS cancelled,
                           BOOL_OR(event_type = 'REORDERED') AS reordered,
                           BOOL_OR(event_type = 'PAYMENT_METHOD_SWITCHED') AS switched,
                           BOOL_OR(funnel_stage = 'PAYMENT_COMPLETED') AS completed
                    FROM events
                    GROUP BY period, purchase_intent_id
                )
                SELECT period, gap, cancelled, reordered, switched,
                       (reordered AND completed) AS recovered
                FROM per_intent
                """
            ).fetchall()
        finally:
            con.close()

        def build(period: str) -> BenefitPeriodStats:
            subset = [r for r in rows if r[0] == period]
            buckets: list[BenefitGapBucket] = []
            for label, lo, hi in _GAP_BUCKETS:
                in_bucket = [
                    r for r in subset if (lo is None or r[1] >= lo) and (hi is None or r[1] < hi)
                ]
                n = len(in_bucket)
                cancels = sum(1 for r in in_bucket if r[2])
                reorders = sum(1 for r in in_bucket if r[3])
                switches = sum(1 for r in in_bucket if r[4])
                recovered = sum(1 for r in in_bucket if r[5])
                buckets.append(
                    BenefitGapBucket(
                        bucket=label,
                        intent_count=n,
                        cancel_rate=(cancels / n) if n else 0.0,
                        reorder_rate=(reorders / n) if n else 0.0,
                        switch_method_rate=(switches / n) if n else 0.0,
                        reorder_recovery_rate=(recovered / reorders) if reorders else 0.0,
                    )
                )
            mean_gap = (sum(r[1] for r in subset) / len(subset)) if subset else 0.0
            return BenefitPeriodStats(period=period, buckets=buckets, mean_gap_minor=mean_gap)  # type: ignore[arg-type]

        baseline = build("baseline")
        incident = build("incident")
        return BenefitResult(
            baseline=baseline,
            incident=incident,
            mean_gap_shift_minor=incident.mean_gap_minor - baseline.mean_gap_minor,
        )

    # -- 13.4 inspect events ---------------------------------------------------------

    def inspect_payment_events(self, query: PaymentEventQuery) -> PaymentEventResult:
        con = self._connect(query.dataset_ref)
        try:
            status_rows = con.execute(
                """
                SELECT period, upper(status) AS status, COUNT(*)
                FROM events
                GROUP BY period, upper(status)
                """
            ).fetchall()
            error_rows = con.execute(
                """
                SELECT period, error_code, COUNT(*) AS n
                FROM events
                WHERE error_code IS NOT NULL
                GROUP BY period, error_code
                ORDER BY n DESC
                """,
            ).fetchall()
            latency_rows = con.execute(
                """
                SELECT period,
                       quantile_cont(latency_ms, 0.5),
                       quantile_cont(latency_ms, 0.95),
                       quantile_cont(latency_ms, 0.99)
                FROM events
                WHERE latency_ms IS NOT NULL
                GROUP BY period
                """
            ).fetchall()
            affected_rows = con.execute(
                """
                SELECT period, payment_method, payment_channel
                FROM events
                WHERE upper(status) IN ('FAILED', 'TIMEOUT') OR error_code IS NOT NULL
                GROUP BY period, payment_method, payment_channel
                """
            ).fetchall()
        finally:
            con.close()

        def build(period: str) -> PaymentEventPeriodStats:
            statuses = {s: n for p, s, n in status_rows if p == period}
            errors = [
                ErrorCodeCount(error_code=ec, count=n) for p, ec, n in error_rows if p == period
            ][: min(query.top_k, 20)]
            lat = next((r for r in latency_rows if r[0] == period), None)
            methods = sorted({m for p, m, _ in affected_rows if p == period and m})
            channels = sorted({c for p, _, c in affected_rows if p == period and c})
            return PaymentEventPeriodStats(
                period=period,  # type: ignore[arg-type]
                status_counts=statuses,
                top_error_codes=errors,
                latency=LatencyStats(
                    p50_ms=lat[1] if lat else None,
                    p95_ms=lat[2] if lat else None,
                    p99_ms=lat[3] if lat else None,
                ),
                affected_payment_methods=methods,
                affected_payment_channels=channels,
            )

        return PaymentEventResult(
            baseline=build("baseline"),
            incident=build("incident"),
        )

    # -- cancel / reorder trace ------------------------------------------------

    def trace_cancel_and_reorder(self, query: CancelReorderQuery) -> CancelReorderResult:
        con = self._connect(query.dataset_ref)
        try:
            rows = con.execute(
                """
                WITH per_intent AS (
                    SELECT period, purchase_intent_id,
                           BOOL_OR(event_type = 'ORDER_CANCELLED') AS cancelled,
                           BOOL_OR(event_type = 'REORDERED') AS reordered,
                           BOOL_OR(event_type = 'PAYMENT_METHOD_SWITCHED') AS switched,
                           BOOL_OR(funnel_stage = 'PAYMENT_COMPLETED') AS completed,
                           MAX(CASE WHEN event_type = 'PAYMENT_METHOD_SWITCHED'
                               THEN payment_method END) AS switch_to_method
                    FROM events
                    GROUP BY period, purchase_intent_id
                )
                SELECT period,
                       COUNT(*) AS total,
                       SUM(cancelled::INT) AS cancelled,
                       SUM(reordered::INT) AS reordered,
                       SUM(switched::INT) AS switched,
                       SUM((reordered AND completed)::INT) AS recovered
                FROM per_intent
                GROUP BY period
                """
            ).fetchall()

            switch_rows = con.execute(
                """
                WITH switches AS (
                    SELECT period, payment_method,
                           LAG(payment_method) OVER (
                               PARTITION BY purchase_intent_id, period
                               ORDER BY event_time
                           ) AS prev_method
                    FROM events
                    WHERE event_type = 'PAYMENT_METHOD_SWITCHED'
                )
                SELECT period, prev_method, payment_method
                FROM switches
                WHERE prev_method IS NOT NULL
                """
            ).fetchall()
        finally:
            con.close()

        def _build(period: str) -> CancelReorderMetrics:
            row = next((r for r in rows if r[0] == period), None)
            if not row:
                return CancelReorderMetrics(
                    period=period,
                    total_intents=0,
                    cancelled_count=0,
                    cancel_rate=0.0,
                    reordered_count=0,
                    reorder_rate=0.0,
                    switched_method_count=0,
                    switch_rate=0.0,
                    recovered_count=0,
                    recovery_rate=0.0,
                )
            _, total, cancelled, reordered, switched, recovered = row
            return CancelReorderMetrics(
                period=period,  # type: ignore[arg-type]
                total_intents=total,
                cancelled_count=int(cancelled),
                cancel_rate=(cancelled / total) if total else 0.0,
                reordered_count=int(reordered),
                reorder_rate=(reordered / cancelled) if cancelled else 0.0,
                switched_method_count=int(switched),
                switch_rate=(switched / cancelled) if cancelled else 0.0,
                recovered_count=int(recovered),
                recovery_rate=(recovered / reordered) if reordered else 0.0,
            )

        baseline = _build("baseline")
        incident = _build("incident")

        # Top switch patterns during incident only.
        inc_switches = [(r[1], r[2]) for r in switch_rows if r[0] == "incident"]
        from_counts: dict[str, int] = {}
        to_counts: dict[str, int] = {}
        for frm, to in inc_switches:
            if frm:
                from_counts[frm] = from_counts.get(frm, 0) + 1
            to_counts[to] = to_counts.get(to, 0) + 1
        top_from = sorted(from_counts, key=from_counts.get, reverse=True)[:3]
        top_to = sorted(to_counts, key=to_counts.get, reverse=True)[:3]

        def _extra_cancelled() -> int:
            if baseline.total_intents == 0:
                return 0
            extra_rate = max(0.0, incident.cancel_rate - baseline.cancel_rate)
            return round(extra_rate * incident.total_intents)

        return CancelReorderResult(
            baseline=baseline,
            incident=incident,
            deltas=CancelReorderDeltas(
                cancel_rate_delta=incident.cancel_rate - baseline.cancel_rate,
                reorder_rate_delta=incident.reorder_rate - baseline.reorder_rate,
                switch_rate_delta=incident.switch_rate - baseline.switch_rate,
                recovery_rate_delta=incident.recovery_rate - baseline.recovery_rate,
                estimated_extra_cancelled=_extra_cancelled(),
            ),
            top_switch_from=top_from,
            top_switch_to=top_to,
        )

    # -- config changes --------------------------------------------------------

    def get_config_changes(self, query: ConfigChangesQuery) -> ConfigChangesResult:
        path = Path(query.dataset_ref)
        config_path = path.with_suffix(".config_changes.json")
        changes: list[ConfigChange] = []
        if config_path.is_file():
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            for item in raw:
                changes.append(ConfigChange(**item))

        # Split by a simple heuristic: changes within 1 day of scenario start
        # are "baseline_window", later changes are "incident_window".
        baseline_window: list[ConfigChange] = []
        incident_window: list[ConfigChange] = []
        for c in changes:
            if "baseline" in c.changed_at.lower() or "baseline" in c.change_id.lower():
                baseline_window.append(c)
            else:
                incident_window.append(c)

        # Filter by change_types if requested.
        if query.change_types:
            allowed = set(query.change_types)
            baseline_window = [c for c in baseline_window if c.change_type in allowed]
            incident_window = [c for c in incident_window if c.change_type in allowed]

        return ConfigChangesResult(
            scenario_id=path.stem,
            baseline_window_changes=baseline_window,
            incident_window_changes=incident_window,
            relevant_changes=incident_window,  # incident-window changes are the relevant ones
        )

    # -- data quality ---------------------------------------------------------

    def validate_dataset(self, dataset_ref: str) -> DatasetValidationResult:
        con = self._connect(dataset_ref)
        try:
            row_count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            dup = con.execute("SELECT COUNT(*) - COUNT(DISTINCT event_id) FROM events").fetchone()[
                0
            ]
            null_rows = con.execute(
                """
                SELECT
                    SUM(CASE WHEN benefit_id IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*),
                    SUM(CASE WHEN payment_method IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*),
                    SUM(CASE WHEN payment_channel IS NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*)
                FROM events
                """
            ).fetchone()
            stage_rows = con.execute(
                """
                SELECT period, funnel_stage FROM events
                WHERE event_type = 'FUNNEL_PROGRESSION' AND funnel_stage IS NOT NULL
                GROUP BY period, funnel_stage
                """
            ).fetchall()
        finally:
            con.close()

        # A stage is "missing" if it is absent from ANY period (a stage dropped
        # only during the incident period is still a data gap).
        present_by_period: dict[str, set[str]] = {}
        for period, stage in stage_rows:
            present_by_period.setdefault(period, set()).add(stage)
        all_stages = {s.value for s in FUNNEL_STAGE_ORDER}
        missing: list[str] = []
        for period_present in present_by_period.values():
            for stage in sorted(all_stages - period_present):
                if stage not in missing:
                    missing.append(stage)
        null_rates = {
            "benefit_id": null_rows[0] or 0.0,
            "payment_method": null_rows[1] or 0.0,
            "payment_channel": null_rows[2] or 0.0,
        }
        warnings: list[str] = []
        if dup:
            warnings.append(f"duplicate event_id rows: {dup}")
        if missing:
            warnings.append(f"missing funnel stages: {', '.join(missing)}")
        if null_rates["benefit_id"] > 0.5:
            warnings.append(f"high benefit_id null rate: {null_rates['benefit_id']:.2%}")
        ok = not dup and not missing
        return DatasetValidationResult(
            dataset_ref=dataset_ref,
            ok=ok,
            row_count=row_count,
            duplicate_event_ids=dup,
            null_rates=null_rates,
            missing_stages=missing,
            warnings=warnings,
        )
