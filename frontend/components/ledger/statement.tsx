"use client";

import { SupportStatus } from "@/components/status-badge";
import { useTraceClass } from "@/components/ledger/trace";
import type { DiagnosisReport } from "@/lib/api/client";
import { formatPercent } from "@/lib/format";

/**
 * The loss statement — the first thing on the page and the product's thesis.
 *
 * A payment team's question is "how much did we lose, and who can account for
 * it". That is a statement that has to balance, so it is laid out as one:
 * attributed claims plus an honest remainder against the total. The remainder
 * is a first-class line, never hidden — a diagnosis that cannot explain
 * everything must say so on its face.
 */
export function LossStatement({
  report,
  baselineValue,
  observedValue,
}: {
  report: DiagnosisReport;
  baselineValue: number;
  observedValue: number;
}) {
  const total = report.total_estimated_lost_intents;
  const attributed = report.root_causes.filter(
    (cause) => cause.support_status !== "UNKNOWN",
  );
  const unexplained = report.unexplained_lost_intents;
  const completionDelta = observedValue - baselineValue;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div>
        <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-3">
          <span className="eyebrow">Purchase intents lost</span>
          <span className="text-[11px] text-ink-3">
            vs the same window&apos;s baseline
          </span>
        </div>

        <div className="tnum mt-4 flex items-baseline gap-2 font-mono text-[46px] leading-none font-semibold text-ink">
          {total}
        </div>

        <ul className="mt-5">
          {attributed.map((cause) => (
            <ClaimLine cause={cause} key={cause.label} />
          ))}

          <li className="flex items-center gap-3 border-t border-rule py-2.5">
            <span
              aria-hidden
              className="w-4 shrink-0 text-center font-mono text-[11px] text-ink-3"
            >
              └
            </span>
            <span className="flex-1 truncate text-[13px] text-ink-2">
              Not attributed
            </span>
            <span className="tnum w-16 text-right font-mono text-[13px] text-ink-2">
              {unexplained}
            </span>
            <span className="hidden w-28 sm:block" />
            <span className="hidden w-20 text-right text-[11px] text-ink-3 sm:block">
              {unexplained > 0 ? "needs more data" : "—"}
            </span>
          </li>
        </ul>

        <p className="mt-3 border-t border-rule-2 pt-3 text-[11px] leading-5 text-ink-3">
          A claim the evidence cannot carry is republished as unknown and moves
          its loss here, so the statement never explains more than it can
          support.
        </p>
      </div>

      <div className="flex flex-col gap-5 lg:border-l lg:border-rule lg:pl-8">
        <div>
          <div className="eyebrow">Payment completion rate</div>
          <div className="mt-3 flex items-baseline gap-3">
            <span className="tnum font-mono text-[22px] leading-none text-ink-3">
              {formatPercent(baselineValue)}
            </span>
            <span aria-hidden className="text-ink-3">
              →
            </span>
            <span className="tnum font-mono text-[30px] leading-none font-semibold text-ink">
              {formatPercent(observedValue)}
            </span>
          </div>
          <div className="tnum mt-2 font-mono text-[12px] font-semibold text-partial">
            {completionDelta >= 0 ? "+" : "−"}
            {Math.abs(completionDelta * 100).toFixed(1)} points
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-t border-rule pt-4 text-[12px]">
          <div>
            <dt className="eyebrow">Claims</dt>
            <dd className="tnum mt-1 font-mono text-[15px] text-ink">
              {report.root_causes.length}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">Explained</dt>
            <dd className="tnum mt-1 font-mono text-[15px] text-ink">
              {report.explained_lost_intents}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">Diagnosis status</dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-2">
              {report.status}
            </dd>
          </div>
          <div>
            <dt className="eyebrow">Validator</dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-2">
              {report.validator_version.replace("paytrace.validator.", "")}
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}

function ClaimLine({ cause }: { cause: DiagnosisReport["root_causes"][number] }) {
  const trace = useTraceClass({ kind: "claim", id: cause.label });

  return (
    <li>
      <button
        {...trace}
        className={`flex w-full cursor-pointer items-center gap-3 border-b border-rule py-2.5 text-left transition-opacity duration-150 hover:bg-paper-2/60 ${trace.className}`}
        type="button"
      >
        <span
          aria-hidden
          className="w-4 shrink-0 text-center font-mono text-[11px] text-ink-3"
        >
          ├
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium text-ink">
            {cause.label.replaceAll("_", " ")}
          </span>
        </span>
        <span className="tnum w-16 shrink-0 text-right font-mono text-[15px] font-semibold text-ink">
          {cause.estimated_lost_intents ?? "—"}
        </span>
        <span className="hidden w-28 shrink-0 sm:block">
          <SupportStatus status={cause.support_status} />
        </span>
        <span className="tnum hidden w-20 shrink-0 text-right font-mono text-[11px] text-ink-3 sm:block">
          {cause.evidence_codes.length} ev.
        </span>
      </button>
    </li>
  );
}
