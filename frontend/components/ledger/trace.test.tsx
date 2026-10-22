import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  TraceProvider,
  traceKey,
  useTraceClass,
  type TraceTarget,
} from "@/components/ledger/trace";
import type {
  DiagnosisReport,
  DiagnosisTrace,
  FunnelResult,
} from "@/lib/api/client";

/**
 * The trace rail's value is entirely in *what it links*. A probe renders one
 * button per target so a test can assert the reachable set directly, instead of
 * inferring it from a screenshot.
 */
function Probe({ target }: { target: TraceTarget }) {
  const state = useTraceClass(target);
  return (
    <button
      aria-pressed={state["aria-pressed"]}
      className={state.className}
      data-testid={traceKey(target)}
      onClick={state.onClick}
      type="button"
    >
      {traceKey(target)}
    </button>
  );
}

const TARGETS: TraceTarget[] = [
  { kind: "claim", id: "CHANNEL_TIMEOUT" },
  { kind: "claim", id: "BENEFIT_SELECTION_FRICTION" },
  { kind: "evidence", id: "EV-1-002" },
  { kind: "evidence", id: "EV-1-011" },
  { kind: "evidence", id: "EV-1-003" },
  { kind: "evidence", id: "EV-1-001" },
  { kind: "tool", id: "c5" },
  { kind: "tool", id: "c1" },
  { kind: "tool", id: "c0" },
  { kind: "hypothesis", id: "H-02" },
  { kind: "hypothesis", id: "H-01" },
  { kind: "stage", id: "CHANNEL_SUCCEEDED" },
  { kind: "stage", id: "PAYMENT_INITIATED" },
];

// Two independent chains, mirroring the real mixed_failure shape: a channel
// fault and a friction fault whose evidence, tools and hypotheses do not touch.
const report = {
  root_causes: [
    { label: "CHANNEL_TIMEOUT", evidence_codes: ["EV-1-002", "EV-1-011"] },
    { label: "BENEFIT_SELECTION_FRICTION", evidence_codes: ["EV-1-003", "EV-1-001"] },
  ],
} as unknown as DiagnosisReport;

const trace = {
  tool_executions: [
    { id: "uuid-5", tool_call_id: "c5", tool_name: "inspect_payment_events" },
    { id: "uuid-1", tool_call_id: "c1", tool_name: "analyze_benefit_gap" },
    { id: "uuid-0", tool_call_id: "c0", tool_name: "get_payment_funnel" },
  ],
  evidence: [
    { evidence_code: "EV-1-002", tool_execution_id: "uuid-5", metrics: { stage: "CHANNEL_SUCCEEDED" } },
    { evidence_code: "EV-1-011", tool_execution_id: "uuid-5", metrics: {} },
    { evidence_code: "EV-1-003", tool_execution_id: "uuid-1", metrics: {} },
    { evidence_code: "EV-1-001", tool_execution_id: "uuid-0", metrics: { stage: "PAYMENT_INITIATED" } },
  ],
  hypotheses: [
    {
      hypothesis_id: "H-02",
      root_cause_type: "CHANNEL_TIMEOUT",
      required_next_tool: "inspect_payment_events",
      supporting_evidence: ["EV-1-011"],
      conflicting_evidence: [],
    },
    {
      hypothesis_id: "H-01",
      root_cause_type: "BENEFIT_SELECTION_FRICTION",
      required_next_tool: "analyze_benefit_gap",
      supporting_evidence: ["EV-1-003"],
      conflicting_evidence: [],
    },
  ],
  events: [],
} as unknown as DiagnosisTrace;

const funnel = {
  deltas: [{ stage: "CHANNEL_SUCCEEDED" }, { stage: "PAYMENT_INITIATED" }],
} as unknown as FunnelResult;

function renderRail() {
  return render(
    <TraceProvider funnel={funnel} report={report} trace={trace}>
      {TARGETS.map((target) => (
        <Probe key={traceKey(target)} target={target} />
      ))}
    </TraceProvider>,
  );
}

function probe(target: TraceTarget): HTMLElement {
  return screen.getByTestId(traceKey(target));
}

function isDimmed(target: TraceTarget): boolean {
  return probe(target).className.includes("opacity-25");
}

describe("evidence trace rail", () => {
  it("dims nothing until something is selected", () => {
    renderRail();
    for (const target of TARGETS) {
      expect(isDimmed(target)).toBe(false);
    }
  });

  it("lights exactly the chain a claim belongs to, and dims the rest", () => {
    renderRail();
    fireEvent.click(probe({ kind: "claim", id: "CHANNEL_TIMEOUT" }));

    const linked: TraceTarget[] = [
      { kind: "claim", id: "CHANNEL_TIMEOUT" },
      { kind: "evidence", id: "EV-1-002" },
      { kind: "evidence", id: "EV-1-011" },
      { kind: "tool", id: "c5" },
      { kind: "hypothesis", id: "H-02" },
      { kind: "stage", id: "CHANNEL_SUCCEEDED" },
    ];
    const unrelated: TraceTarget[] = [
      { kind: "claim", id: "BENEFIT_SELECTION_FRICTION" },
      { kind: "evidence", id: "EV-1-003" },
      { kind: "evidence", id: "EV-1-001" },
      { kind: "tool", id: "c1" },
      { kind: "tool", id: "c0" },
      { kind: "hypothesis", id: "H-01" },
      { kind: "stage", id: "PAYMENT_INITIATED" },
    ];

    for (const target of linked) {
      expect(isDimmed(target), `${traceKey(target)} should be lit`).toBe(false);
    }
    for (const target of unrelated) {
      expect(isDimmed(target), `${traceKey(target)} should be dimmed`).toBe(true);
    }
  });

  it("walks the graph in both directions", () => {
    renderRail();
    // Picking one evidence record must light the claim that cites it, the tool
    // that produced it and the hypothesis it settled — not just itself.
    fireEvent.click(probe({ kind: "evidence", id: "EV-1-002" }));

    expect(isDimmed({ kind: "claim", id: "CHANNEL_TIMEOUT" })).toBe(false);
    expect(isDimmed({ kind: "tool", id: "c5" })).toBe(false);
    expect(isDimmed({ kind: "hypothesis", id: "H-02" })).toBe(false);
    expect(isDimmed({ kind: "stage", id: "CHANNEL_SUCCEEDED" })).toBe(false);
    expect(isDimmed({ kind: "claim", id: "BENEFIT_SELECTION_FRICTION" })).toBe(true);
  });

  it("marks the selection exclusively and clears it on a second click", () => {
    renderRail();
    const claim = { kind: "claim", id: "CHANNEL_TIMEOUT" } as const;

    fireEvent.click(probe(claim));
    expect(probe(claim)).toHaveAttribute("aria-pressed", "true");
    for (const other of TARGETS) {
      if (traceKey(other) !== traceKey(claim)) {
        expect(probe(other)).toHaveAttribute("aria-pressed", "false");
      }
    }

    fireEvent.click(probe(claim));
    expect(probe(claim)).toHaveAttribute("aria-pressed", "false");
    for (const target of TARGETS) {
      expect(isDimmed(target)).toBe(false);
    }
  });

  it("keeps every funnel stage selectable even when no claim cites it", () => {
    // A stage that degraded without being attributed must still be reachable,
    // otherwise the row would be inert with no explanation.
    render(
      <TraceProvider
        funnel={
          {
            deltas: [{ stage: "CHANNEL_SUCCEEDED" }, { stage: "CHECKOUT_ENTERED" }],
          } as unknown as FunnelResult
        }
        report={report}
        trace={trace}
      >
        <Probe target={{ kind: "stage", id: "CHECKOUT_ENTERED" }} />
        <Probe target={{ kind: "stage", id: "CHANNEL_SUCCEEDED" }} />
      </TraceProvider>,
    );

    fireEvent.click(probe({ kind: "stage", id: "CHECKOUT_ENTERED" }));
    expect(isDimmed({ kind: "stage", id: "CHECKOUT_ENTERED" })).toBe(false);
    expect(isDimmed({ kind: "stage", id: "CHANNEL_SUCCEEDED" })).toBe(true);
  });
});
