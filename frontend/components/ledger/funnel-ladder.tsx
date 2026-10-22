"use client";

import { useTrace, useTraceClass } from "@/components/ledger/trace";
import type { FunnelResult } from "@/lib/api/client";
import { humanize } from "@/lib/format";

const LOSS_TONE = "bg-partial";

/**
 * The funnel as a ladder of transitions, not a pair of bars.
 *
 * Each row is one transition into a stage: the baseline step rate is a tick, the
 * incident step rate is the bar, and the gap between them is the loss. The gap
 * is the point — a grouped bar chart makes a 8-point drop invisible at 60% bar
 * length, while a gap reads as a gap.
 *
 * These are step rates (conditional on reaching the previous stage) because that
 * is the quantity localization and loss attribution use. Overall rates are
 * diluted by upstream attrition and would show a smaller, misleading effect.
 */
export function FunnelLadder({ data }: { data: FunnelResult }) {
  const anomalous = new Set(data.anomalous_stages);

  // Five aligned columns cannot compress below this without the figures
  // colliding, so the ladder scrolls inside its own box rather than widening
  // the page.
  return (
    <div className="overflow-x-auto">
      <div className="min-w-[560px]">
        <div className="grid grid-cols-[minmax(140px,1.3fr)_92px_minmax(110px,1.6fr)_78px_62px] items-center gap-x-3 border-b border-rule pb-2">
          <div className="eyebrow">Transition into</div>
          <div className="eyebrow">Step rate</div>
          <div className="eyebrow">Incident vs baseline</div>
          <div className="eyebrow text-right">Delta</div>
          <div className="eyebrow text-right">Lost</div>
        </div>

        <div className="divide-y divide-rule">
          {data.deltas.map((delta) => (
            <FunnelRow
              anomalous={anomalous.has(delta.stage)}
              delta={delta}
              key={delta.stage}
            />
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-baseline justify-between gap-3 border-t border-rule-2 pt-3">
          <p className="text-[11px] leading-5 text-ink-3">
            Loss is charged to the transition the intents failed, so an intent
            that dropped out early is never counted again further down.
          </p>
          <p className="tnum font-mono text-[11px] text-ink-2">
            attributed{" "}
            <span className="font-semibold text-ink">
              {data.deltas.reduce((sum, item) => sum + item.estimated_lost_intents, 0)}
            </span>{" "}
            across {anomalous.size} degraded transition
            {anomalous.size === 1 ? "" : "s"}
          </p>
        </div>
      </div>
    </div>
  );
}

function FunnelRow({
  delta,
  anomalous,
}: {
  delta: FunnelResult["deltas"][number];
  anomalous: boolean;
}) {
  const { isLit } = useTrace();
  const trace = useTraceClass({ kind: "stage", id: delta.stage });

  const base = delta.baseline_step_rate;
  const incident = delta.incident_step_rate;
  const drop = base != null && incident != null ? base - incident : 0;
  const isEntry = base == null || incident == null;
  const lit = isLit({ kind: "stage", id: delta.stage });

  return (
    <button
      {...trace}
      className={`grid w-full cursor-pointer grid-cols-[minmax(140px,1.3fr)_92px_minmax(110px,1.6fr)_78px_62px] items-center gap-x-3 py-[9px] text-left transition-opacity duration-150 ${trace.className} ${
        lit ? "" : "opacity-25 saturate-0"
      }`}
      type="button"
    >
      <span className="flex items-center gap-2 truncate">
        <span
          aria-hidden
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            anomalous ? LOSS_TONE : "bg-rule-2"
          }`}
        />
        <span
          className={`truncate text-[12px] ${
            anomalous ? "font-medium text-ink" : "text-ink-2"
          }`}
        >
          {humanize(delta.stage)}
        </span>
      </span>

      <span className="tnum font-mono text-[11px] text-ink-2">
        {isEntry ? (
          <span className="text-ink-3">entry</span>
        ) : (
          <>
            {base.toFixed(3)}
            <span className="text-ink-3"> → </span>
            {incident.toFixed(3)}
          </>
        )}
      </span>

      <span className="relative block h-2.5 w-full rounded-[1px] bg-paper-2">
        {!isEntry && (
          <>
            <span
              className="absolute inset-y-0 left-0 rounded-[1px] bg-ink-2/70"
              style={{ width: `${Math.min(incident, 1) * 100}%` }}
            />
            {drop > 0.0005 && (
              <span
                aria-hidden
                className={`absolute inset-y-0 ${LOSS_TONE} opacity-70`}
                style={{
                  left: `${Math.min(incident, 1) * 100}%`,
                  width: `${drop * 100}%`,
                }}
              />
            )}
            <span
              aria-hidden
              className="absolute -top-0.5 -bottom-0.5 w-[2px] bg-ink"
              style={{ left: `calc(${Math.min(base, 1) * 100}% - 1px)` }}
            />
          </>
        )}
      </span>

      <span
        className={`tnum text-right font-mono text-[11px] ${
          anomalous ? "font-semibold text-partial" : "text-ink-3"
        }`}
      >
        {isEntry ? "—" : `${drop >= 0 ? "−" : "+"}${Math.abs(drop).toFixed(3)}`}
      </span>

      <span
        className={`tnum text-right font-mono text-[11px] ${
          delta.estimated_lost_intents > 0
            ? "font-semibold text-ink"
            : "text-ink-3"
        }`}
      >
        {delta.estimated_lost_intents || "·"}
      </span>
    </button>
  );
}
