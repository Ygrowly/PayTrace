"use client";

/**
 * The evidence trace rail.
 *
 * The product's claim is that every figure can be located back to the tool call
 * that produced it. This makes that literal: selecting any figure lights the
 * whole chain — the funnel stage it belongs to, the claim that cites it, the
 * hypothesis the call was testing, and the evidence record itself.
 *
 * The graph is derived from data the page already has; nothing is inferred from
 * naming conventions or hard-coded.
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import type {
  DiagnosisReport,
  DiagnosisTrace,
  Evidence,
  FunnelResult,
} from "@/lib/api/client";

export type TraceTarget =
  | { kind: "claim"; id: string }
  | { kind: "evidence"; id: string }
  | { kind: "tool"; id: string }
  | { kind: "hypothesis"; id: string }
  | { kind: "stage"; id: string };

export type TraceKey = string;

export function traceKey(target: TraceTarget): TraceKey {
  return `${target.kind}:${target.id}`;
}

type Index = Map<TraceKey, Set<TraceKey>>;

interface TraceContextValue {
  selection: TraceTarget | null;
  select: (target: TraceTarget) => void;
  clear: () => void;
  isLit: (target: TraceTarget) => boolean;
  /** Null when nothing is selected — callers dim everything equally then. */
  active: boolean;
}

const TraceContext = createContext<TraceContextValue | null>(null);

function link(index: Index, a: TraceKey, b: TraceKey) {
  if (!index.has(a)) index.set(a, new Set());
  if (!index.has(b)) index.set(b, new Set());
  index.get(a)!.add(b);
  index.get(b)!.add(a);
}

/** The funnel stage a claim's degradation evidence reports, if any. */
function stagesOf(codes: string[], evidence: Evidence[]): string[] {
  const stages = new Set<string>();
  for (const code of codes) {
    const record = evidence.find((item) => item.evidence_code === code);
    const stage = record?.metrics?.stage;
    if (typeof stage === "string") stages.add(stage);
  }
  return [...stages];
}

function buildIndex(
  report: DiagnosisReport | undefined,
  trace: DiagnosisTrace | undefined,
  funnel: FunnelResult | undefined,
): Index {
  const index: Index = new Map();
  if (!trace) return index;

  const evidenceByCode = new Map(
    (trace.evidence ?? []).map((item) => [item.evidence_code, item]),
  );
  const toolById = new Map(trace.tool_executions.map((item) => [item.id, item]));

  // claim <-> evidence <-> tool, and claim -> funnel stage
  for (const claim of report?.root_causes ?? []) {
    const claimKey = traceKey({ kind: "claim", id: claim.label });
    for (const code of claim.evidence_codes) {
      link(index, claimKey, traceKey({ kind: "evidence", id: code }));
      const record = evidenceByCode.get(code);
      const tool = record ? toolById.get(record.tool_execution_id) : undefined;
      if (tool) link(index, claimKey, traceKey({ kind: "tool", id: tool.tool_call_id }));
    }
    for (const stage of stagesOf(claim.evidence_codes, trace.evidence ?? [])) {
      link(index, claimKey, traceKey({ kind: "stage", id: stage }));
    }
  }

  // hypothesis <-> evidence it gathered, hypothesis -> the tool that tested it
  for (const hypothesis of trace.hypotheses ?? []) {
    const key = traceKey({ kind: "hypothesis", id: hypothesis.hypothesis_id });
    for (const code of [
      ...(hypothesis.supporting_evidence ?? []),
      ...(hypothesis.conflicting_evidence ?? []),
    ]) {
      link(index, key, traceKey({ kind: "evidence", id: code }));
    }
    if (hypothesis.required_next_tool) {
      const tool = trace.tool_executions.find(
        (item) => item.tool_name === hypothesis.required_next_tool,
      );
      if (tool) link(index, key, traceKey({ kind: "tool", id: tool.tool_call_id }));
    }
  }

  // Every funnel stage exists as a node even when no claim cites it, so stages
  // that degraded without attribution can still be selected and read.
  for (const delta of funnel?.deltas ?? []) {
    const key = traceKey({ kind: "stage", id: delta.stage });
    if (!index.has(key)) index.set(key, new Set());
  }

  return index;
}

export function TraceProvider({
  report,
  trace,
  funnel,
  children,
}: {
  report?: DiagnosisReport;
  trace?: DiagnosisTrace;
  funnel?: FunnelResult;
  children: React.ReactNode;
}) {
  const [selection, setSelection] = useState<TraceTarget | null>(null);
  const index = useMemo(
    () => buildIndex(report, trace, funnel),
    [report, trace, funnel],
  );

  // Walking the graph from the selection gives the whole chain at once, in both
  // directions: picking an evidence code lights the claim that cites it just as
  // picking the claim lights that code.
  const lit = useMemo(() => {
    if (!selection) return null;
    const start = traceKey(selection);
    const seen = new Set<TraceKey>([start]);
    const queue: TraceKey[] = [start];
    while (queue.length) {
      const current = queue.shift()!;
      for (const neighbour of index.get(current) ?? []) {
        if (!seen.has(neighbour)) {
          seen.add(neighbour);
          queue.push(neighbour);
        }
      }
    }
    return seen;
  }, [index, selection]);

  const select = useCallback((target: TraceTarget) => {
    setSelection((current) =>
      current && traceKey(current) === traceKey(target) ? null : target,
    );
  }, []);

  const value = useMemo<TraceContextValue>(
    () => ({
      selection,
      select,
      clear: () => setSelection(null),
      isLit: (target) => lit === null || lit.has(traceKey(target)),
      active: selection !== null,
    }),
    [lit, select, selection],
  );

  return <TraceContext.Provider value={value}>{children}</TraceContext.Provider>;
}

export function useTrace(): TraceContextValue {
  const context = useContext(TraceContext);
  if (!context) {
    throw new Error("useTrace must be used inside a TraceProvider");
  }
  return context;
}

/** Class names for a traceable element — dimmed while another chain is lit. */
export function useTraceClass(target: TraceTarget): {
  className: string;
  onClick: () => void;
  "aria-pressed": boolean;
} {
  const { isLit, select, selection } = useTrace();
  const lit = isLit(target);
  const selected = selection !== null && traceKey(selection) === traceKey(target);
  return {
    className: lit
      ? selected
        ? "ring-1 ring-petrol-2 bg-petrol-soft/60"
        : ""
      : "opacity-25 saturate-0",
    onClick: () => select(target),
    "aria-pressed": selected,
  };
}
