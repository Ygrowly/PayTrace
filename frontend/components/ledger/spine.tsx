"use client";

import { SupportStatus } from "@/components/status-badge";
import { useTraceClass } from "@/components/ledger/trace";
import type { DiagnosisEvent, DiagnosisTrace } from "@/lib/api/client";
import { humanize } from "@/lib/format";

/** Human wording for the harness's stop reasons. */
const EXIT_REASON: Record<string, string> = {
  ALL_HYPOTHESES_RESOLVED: "every hypothesis settled",
  BUDGET_EXHAUSTED: "tool budget spent",
  POLICY_FINISHED: "investigation plan completed",
  NO_OPEN_HYPOTHESES: "nothing left open",
  BLOCKED_CALLS_EXHAUSTED: "stopped after repeated blocked calls",
};

function governanceOf(events: DiagnosisEvent[]) {
  const routed = events.find((event) => event.event_type === "harness_routed");
  const concluded = [...events]
    .reverse()
    .find((event) => event.event_type.startsWith("run_"));
  return {
    bundle: routed?.payload ?? null,
    conclusion: concluded?.payload ?? null,
  };
}

/**
 * The investigation spine: what was proposed, what tested it, what the system
 * refused to do, and why it stopped.
 *
 * This is deliberately a separate panel from the conclusion. A report says what
 * happened; this says how the system came to believe it, which is the part that
 * distinguishes an investigation from a summary.
 */
export function InvestigationSpine({
  trace,
  agentMode,
}: {
  trace: DiagnosisTrace;
  agentMode: string | null;
}) {
  const { bundle, conclusion } = governanceOf(trace.events);
  const hypotheses = trace.hypotheses ?? [];
  const toolNames = new Map(
    trace.tool_executions.map((tool) => [tool.tool_name, tool]),
  );

  if (agentMode !== "B2") {
    return (
      <p className="text-[12px] leading-5 text-ink-3">
        This run used the fixed pipeline, so no hypotheses were raised. Switch
        the agent mode to B2 to run a governed investigation.
      </p>
    );
  }

  const allowed = (bundle?.allowed_tools as string[] | undefined) ?? [];
  const signals = (bundle?.signals as string[] | undefined) ?? [];
  const blocked = (conclusion?.blocked_calls as unknown[] | undefined) ?? [];
  const degradations = (conclusion?.degradations as string[] | undefined) ?? [];
  const earlyExit = conclusion?.early_exit_reason as string | undefined;

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 border-b border-rule pb-4 sm:grid-cols-4">
        <div>
          <dt className="eyebrow">Signals detected</dt>
          <dd className="mt-1.5 flex flex-wrap gap-1">
            {signals.length ? (
              signals.map((signal) => (
                <span
                  className="rounded-[2px] bg-paper-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2"
                  key={signal}
                >
                  {signal}
                </span>
              ))
            ) : (
              <span className="text-[12px] text-ink-3">—</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Tools allowed</dt>
          <dd className="tnum mt-1.5 font-mono text-[15px] text-ink">
            {allowed.length || "—"}
            <span className="text-[11px] font-normal text-ink-3"> / 6</span>
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Calls made</dt>
          <dd className="tnum mt-1.5 font-mono text-[15px] text-ink">
            {trace.tool_executions.length}
          </dd>
        </div>
        <div>
          <dt className="eyebrow">Stopped because</dt>
          <dd className="mt-1.5 text-[12px] text-ink-2">
            {earlyExit ? (EXIT_REASON[earlyExit] ?? earlyExit) : "—"}
          </dd>
        </div>
      </dl>

      {(blocked.length > 0 || degradations.length > 0) && (
        <ul className="space-y-1.5 border-b border-rule pb-4">
          {blocked.map((entry, index) => {
            const call = entry as { tool?: string; code?: string; message?: string };
            return (
              <li
                className="flex items-start gap-2 text-[11px] leading-5 text-alarm"
                key={`blocked-${index}`}
              >
                <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-alarm" />
                <span>
                  <span className="font-mono font-semibold">
                    {call.code ?? "BLOCKED"}
                  </span>{" "}
                  — refused to run{" "}
                  <span className="font-mono">{call.tool}</span>:{" "}
                  {call.message}
                </span>
              </li>
            );
          })}
          {degradations.map((note, index) => (
            <li
              className="flex items-start gap-2 text-[11px] leading-5 text-partial"
              key={`degraded-${index}`}
            >
              <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-partial" />
              <span>Degraded, continued on the summary: {note}</span>
            </li>
          ))}
        </ul>
      )}

      <ol className="space-y-3">
        {hypotheses.map((hypothesis) => (
          <HypothesisRow
            hypothesis={hypothesis}
            key={hypothesis.hypothesis_id}
            tool={toolNames.get(hypothesis.required_next_tool ?? "")}
          />
        ))}
      </ol>

      {hypotheses.length === 0 && (
        <p className="text-[12px] text-ink-3">
          No hypotheses were raised for this incident.
        </p>
      )}
    </div>
  );
}

function HypothesisRow({
  hypothesis,
  tool,
}: {
  hypothesis: NonNullable<DiagnosisTrace["hypotheses"]>[number];
  tool?: DiagnosisTrace["tool_executions"][number];
}) {
  const trace = useTraceClass({
    kind: "hypothesis",
    id: hypothesis.hypothesis_id,
  });
  const support = hypothesis.supporting_evidence ?? [];
  const conflicts = hypothesis.conflicting_evidence ?? [];

  return (
    <li>
      <div
        className={`rounded-[2px] border border-rule bg-surface transition-opacity duration-150 ${
          trace.className
        }`}
      >
        <button
          aria-pressed={trace["aria-pressed"]}
          className="flex w-full cursor-pointer items-start gap-3 px-4 py-3 text-left"
          onClick={trace.onClick}
          type="button"
        >
          <span className="mt-px font-mono text-[11px] font-semibold text-ink-3">
            {hypothesis.hypothesis_id}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[13px] font-medium text-ink">
              {humanize(hypothesis.root_cause_type)}
            </span>
            <span className="mt-1 block text-[11px] leading-5 text-ink-3">
              {tool ? (
                <>
                  tested by{" "}
                  <span className="font-mono text-ink-2">{tool.tool_call_id}</span>{" "}
                  · {tool.tool_name ?? hypothesis.required_next_tool} ·{" "}
                  <span className="tnum">{tool.row_count ?? 0}</span> rows ·{" "}
                  <span className="tnum">{tool.duration_ms ?? 0}</span> ms
                </>
              ) : (
                <>
                  no tool tested this — proposed as{" "}
                  {humanize(hypothesis.status)}
                </>
              )}
            </span>
          </span>
          <SupportStatus status={hypothesis.status} />
        </button>

        {(support.length > 0 || conflicts.length > 0) && (
          <div className="flex flex-wrap gap-1.5 border-t border-rule px-4 py-2.5">
            {support.map((code) => (
              <EvidenceChip code={code} key={code} tone="settled" />
            ))}
            {conflicts.map((code) => (
              <EvidenceChip code={code} key={code} tone="alarm" />
            ))}
          </div>
        )}

        {hypothesis.rejection_reason && (
          <p className="border-t border-rule px-4 py-2.5 text-[11px] leading-5 text-ink-3">
            {hypothesis.rejection_reason}
          </p>
        )}
      </div>
    </li>
  );
}

export function EvidenceChip({
  code,
  tone = "settled",
}: {
  code: string;
  tone?: "settled" | "alarm" | "neutral";
}) {
  const trace = useTraceClass({ kind: "evidence", id: code });
  const tones = {
    settled: "border-settled/30 bg-settled-soft text-settled hover:bg-settled/15",
    alarm: "border-alarm/30 bg-alarm-soft text-alarm hover:bg-alarm/15",
    neutral: "border-rule-2 bg-paper-2 text-ink-2 hover:border-ink-3",
  };
  return (
    <button
      {...trace}
      className={`cursor-pointer rounded-[2px] border px-1.5 py-0.5 font-mono text-[10px] transition-colors duration-150 ${tones[tone]} ${trace.className}`}
      title={`${code} — select to trace the chain that produced it`}
      type="button"
    >
      {shortCode(code)}
    </button>
  );
}

/**
 * ``EV-1a2b3c4d-011`` → ``EV-011``.
 *
 * The middle segment is the run's own hash, identical for every code on the
 * page, so it is noise. The full code stays in the tooltip and in the detail
 * drawer, where it is actually needed.
 */
export function shortCode(code: string): string {
  const parts = code.split("-");
  return parts.length >= 3 ? `${parts[0]}-${parts[parts.length - 1]}` : code;
}
