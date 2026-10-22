"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { FunnelLadder } from "@/components/ledger/funnel-ladder";
import { InvestigationSpine, shortCode } from "@/components/ledger/spine";
import { LossStatement } from "@/components/ledger/statement";
import { TraceProvider, useTrace } from "@/components/ledger/trace";
import { Icon } from "@/components/icons";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/page-elements";
import { RunStatus, StatusBadge, SupportStatus } from "@/components/status-badge";
import {
  ApiError,
  apiRequest,
  type DiagnosisEvent,
  type DiagnosisReport,
  type DiagnosisRun,
  type DiagnosisRunRetry,
  type DiagnosisRunTrigger,
  type DiagnosisTrace,
  type Evidence,
  type FunnelResult,
  type Incident,
} from "@/lib/api/client";
import { formatDate, humanize } from "@/lib/format";
import { useDiagnosisEvents } from "@/hooks/use-diagnosis-events";

const TERMINAL = new Set(["SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"]);
const RETRYABLE = new Set(["FAILED", "DISPATCH_FAILED", "CANCELLED", "NEEDS_DATA"]);

const EVENT_LABEL: Record<string, string> = {
  run_queued: "Queued",
  run_started: "Diagnosis started",
  harness_routed: "Capabilities routed",
  tool_completed: "Tool completed",
  run_succeeded: "Diagnosis completed",
  run_needs_data: "Withheld — data incomplete",
  run_failed: "Diagnosis failed",
  run_retrying: "Retrying after a transient error",
};

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = String(params.id);

  const incident = useQuery<Incident, ApiError>({
    queryKey: ["incident", incidentId],
    queryFn: () => apiRequest<Incident>(`/api/v1/incidents/${incidentId}`),
  });
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const runId = activeRunId ?? incident.data?.latest_diagnosis_run_id ?? null;

  return (
    <IncidentWorkspace
      activeRunId={runId}
      incident={incident}
      incidentId={incidentId}
      onRunStarted={setActiveRunId}
    />
  );
}

function IncidentWorkspace({
  incident,
  incidentId,
  activeRunId,
  onRunStarted,
}: {
  incident: ReturnType<typeof useQuery<Incident, ApiError>>;
  incidentId: string;
  activeRunId: string | null;
  onRunStarted: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);

  const run = useQuery<DiagnosisRun, ApiError>({
    enabled: Boolean(activeRunId),
    queryKey: ["diagnosis-run", activeRunId],
    queryFn: () => apiRequest<DiagnosisRun>(`/api/v1/diagnosis-runs/${activeRunId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : 1500;
    },
  });

  const funnel = useQuery<FunnelResult, ApiError>({
    enabled: Boolean(incident.data),
    queryKey: ["incident-funnel", incidentId],
    queryFn: () => apiRequest<FunnelResult>(`/api/v1/incidents/${incidentId}/funnel`),
  });

  const isTerminal = Boolean(run.data && TERMINAL.has(run.data.status));
  const report = useQuery<DiagnosisReport, ApiError>({
    enabled: Boolean(run.data && ["SUCCEEDED", "NEEDS_DATA"].includes(run.data.status)),
    queryKey: ["diagnosis-report", activeRunId],
    queryFn: () =>
      apiRequest<DiagnosisReport>(`/api/v1/diagnosis-runs/${activeRunId}/report`),
    retry: false,
  });
  const trace = useQuery<DiagnosisTrace, ApiError>({
    enabled: isTerminal,
    queryKey: ["diagnosis-trace", activeRunId],
    queryFn: () => apiRequest<DiagnosisTrace>(`/api/v1/diagnosis-runs/${activeRunId}/trace`),
    retry: false,
  });
  const events = useDiagnosisEvents(
    activeRunId,
    Boolean(run.data && !isTerminal),
  );

  const diagnosis = useMutation<
    { diagnosis_run_id: string; status: string; message: string },
    ApiError,
    void
  >({
    mutationFn: () => {
      if (activeRunId && run.data && RETRYABLE.has(run.data.status)) {
        return apiRequest<DiagnosisRunRetry>(
          `/api/v1/incidents/${incidentId}/diagnosis-runs/${activeRunId}/retry`,
          { method: "POST", headers: { "Idempotency-Key": `retry-${incidentId}-${Date.now()}` } },
        ).then((response) => ({
          diagnosis_run_id: response.new_diagnosis_run_id,
          status: response.status,
          message: response.message,
        }));
      }
      return apiRequest<DiagnosisRunTrigger>(
        `/api/v1/incidents/${incidentId}/diagnosis-runs`,
        { method: "POST", headers: { "Idempotency-Key": `diagnosis-${incidentId}-${Date.now()}` } },
      );
    },
    onSuccess: async (response) => {
      onRunStarted(response.diagnosis_run_id);
      await queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
    },
  });

  if (incident.isLoading) return <LoadingState label="Loading incident" />;
  if (incident.isError || !incident.data) {
    return (
      <ErrorState
        message={incident.error?.detail ?? "This incident could not be found."}
        onRetry={() => void incident.refetch()}
      />
    );
  }

  const current = incident.data;
  const currentRun = run.data ?? null;
  const currentReport = report.data ?? null;
  const busy = diagnosis.isPending || Boolean(currentRun && !isTerminal);

  return (
    <TraceProvider
      funnel={funnel.data}
      report={currentReport ?? undefined}
      trace={trace.data}
    >
      <div className="space-y-6">
        <PageHeader
          action={
            <div className="flex flex-wrap gap-2">
              <Button href="/incidents" variant="secondary">
                <Icon name="arrow-right" size={14} />
                All incidents
              </Button>
              <Button disabled={busy} onClick={() => diagnosis.mutate()}>
                {diagnosis.isPending && (
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                )}
                {currentRun && RETRYABLE.has(currentRun.status)
                  ? "Re-run diagnosis"
                  : currentRun && !isTerminal
                    ? "Diagnosis running"
                    : "Run diagnosis"}
              </Button>
            </div>
          }
          description={
            current.description ??
            "A deterministic scenario ready for evidence-backed diagnosis."
          }
          eyebrow={`Incidents / ${current.scenario_id}`}
          meta={
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px]">
              <span className="flex items-center gap-2">
                <span className="eyebrow">Incident</span>
                <StatusBadge status={current.status} />
              </span>
              {currentRun && (
                <>
                  <span className="h-3 w-px bg-rule-2" />
                  <span className="flex items-center gap-2">
                    <span className="eyebrow">Latest run</span>
                    <RunStatus status={currentRun.status} />
                    <span className="font-mono text-ink-3">
                      {currentRun.id.slice(0, 8)}
                    </span>
                  </span>
                  {currentRun.agent_mode && (
                    <span
                      className="rounded-[2px] border border-rule-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2"
                      title={
                        currentRun.agent_mode === "B2"
                          ? "Governed investigation: routed capabilities, hypothesis ledger, early exit"
                          : "Fixed six-tool pipeline"
                      }
                    >
                      {currentRun.agent_mode}
                    </span>
                  )}
                  {currentRun.model_provider === "harness_scripted_fallback" && (
                    <span
                      className="rounded-[2px] border border-partial/35 bg-partial-soft px-1.5 py-0.5 font-mono text-[10px] text-partial"
                      title={`The configured model was not reached (${currentRun.model_name ?? "unknown"}). The deterministic policy ran instead — this is not a model investigation.`}
                    >
                      scripted fallback
                    </span>
                  )}
                </>
              )}
              {events.connected && (
                <span className="ml-auto flex items-center gap-1.5 text-settled">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-settled" />
                  live
                </span>
              )}
            </div>
          }
          title={current.title}
        />

        {diagnosis.isError && <ErrorState message={diagnosis.error.detail} />}

        {currentRun && !isTerminal && (
          <Panel
            eyebrow="Server-sent events, persisted per run"
            title="Diagnosis progress"
          >
            <RunProgress events={events.events} error={events.error} />
          </Panel>
        )}

        {currentRun?.status === "FAILED" && (
          <div className="rounded-[2px] border border-alarm/30 bg-alarm-soft p-5">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-alarm">
              <Icon name="triangle" size={16} />
              The diagnosis failed
            </div>
            <p className="mt-2 text-[12px] text-alarm/85">
              {currentRun.error_message ??
                "The worker did not produce a report. Nothing is being presented as a result."}
            </p>
          </div>
        )}

        {!currentRun && (
          <EmptyState
            action={
              <Button disabled={busy} onClick={() => diagnosis.mutate()}>
                Run diagnosis
              </Button>
            }
            description="No run has been started for this incident. Running it executes the investigation over the incident's own dataset — no other incident's data is reachable."
            title="Not diagnosed yet"
          />
        )}

        {currentReport && (
          <Panel
            eyebrow="Deterministic funnel accounting"
            title="Loss statement"
          >
            <LossStatement
              baselineValue={current.baseline_value}
              observedValue={current.observed_value}
              report={currentReport}
            />
          </Panel>
        )}

        {currentReport?.status === "NEEDS_DATA" && (
          <div className="rounded-[2px] border border-partial/35 bg-partial-soft p-5">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-partial">
              <Icon name="triangle" size={16} />
              No causal claim was made
            </div>
            <p className="mt-2 text-[12px] text-partial/85">
              The workflow withheld a conclusion until the following data is
              available. Reporting a root cause without it would be a guess.
            </p>
            <ul className="mt-3 space-y-1">
              {currentReport.missing_data.map((item) => (
                <li
                  className="font-mono text-[11px] text-partial"
                  key={item}
                >
                  — {item}
                </li>
              ))}
            </ul>
          </div>
        )}

        {funnel.data && (
          <Panel
            eyebrow="Step rate = conversion into the stage, given the previous one"
            title="Where conversion broke"
          >
            {funnel.isError ? (
              <ErrorState
                message={funnel.error.detail}
                onRetry={() => void funnel.refetch()}
              />
            ) : (
              <FunnelLadder data={funnel.data} />
            )}
          </Panel>
        )}

        {trace.data && (
          <Panel
            eyebrow={
              currentRun?.agent_mode === "B2"
                ? "Governed investigation / B2"
                : "Fixed pipeline / B0"
            }
            title="How this was established"
          >
            <InvestigationSpine
              agentMode={currentRun?.agent_mode ?? null}
              trace={trace.data}
            />
          </Panel>
        )}

        {currentReport && trace.data && (
          <TraceSurface
            onSelectEvidence={setSelectedEvidence}
            report={currentReport}
            trace={trace.data}
          />
        )}
      </div>

      {selectedEvidence && (
        <EvidenceDrawer
          code={selectedEvidence}
          onClose={() => setSelectedEvidence(null)}
        />
      )}
    </TraceProvider>
  );
}

function RunProgress({
  events,
  error,
}: {
  events: DiagnosisEvent[];
  error: string | null;
}) {
  if (error) {
    return (
      <p className="rounded-[2px] bg-partial-soft p-3 text-[12px] text-partial">
        {error}
      </p>
    );
  }
  if (events.length === 0) {
    return (
      <p className="text-[12px] text-ink-3">
        Waiting for the worker to publish its first event.
      </p>
    );
  }
  return (
    <ol className="space-y-2">
      {events.map((event) => (
        <li className="flex items-baseline gap-3 text-[12px]" key={event.sequence}>
          <span className="tnum w-4 shrink-0 text-right font-mono text-[10px] text-ink-3">
            {event.sequence}
          </span>
          <span className="font-medium text-ink">
            {EVENT_LABEL[event.event_type] ?? humanize(event.event_type)}
          </span>
          <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-3">
            {event.message ?? ""}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The claims themselves, with every citation selectable. */
function TraceSurface({
  report,
  trace,
  onSelectEvidence,
}: {
  report: DiagnosisReport;
  trace: DiagnosisTrace;
  onSelectEvidence: (code: string) => void;
}) {
  const { selection, clear } = useTrace();

  return (
    <Panel
      action={
        selection && (
          <button
            className="cursor-pointer font-mono text-[10px] text-petrol-2 underline underline-offset-2"
            onClick={clear}
            type="button"
          >
            clear trace
          </button>
        )
      }
      eyebrow="Each claim, its evidence, and how far it reaches"
      title="Claims"
    >
      <div className="space-y-4">
        {report.root_causes.map((claim) => (
          <ClaimCard
            claim={claim}
            key={claim.label}
            onSelectEvidence={onSelectEvidence}
            wasHypothesis={Boolean(
              trace.hypotheses?.some(
                (hypothesis) => hypothesis.root_cause_type === claim.label,
              ),
            )}
          />
        ))}
        {report.root_causes.length === 0 && (
          <p className="text-[12px] text-ink-3">
            No causal claim was made for this run.
          </p>
        )}

        {report.alternative_explanations?.length ? (
          <div className="border-t border-rule pt-4">
            <div className="eyebrow">Alternative explanations kept open</div>
            <ul className="mt-2 space-y-1">
              {report.alternative_explanations.map((item) => (
                <li className="text-[12px] leading-5 text-ink-2" key={item}>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Panel>
  );
}

function ClaimCard({
  claim,
  wasHypothesis,
  onSelectEvidence,
}: {
  claim: DiagnosisReport["root_causes"][number];
  /** True when the investigation raised this before any evidence existed. */
  wasHypothesis: boolean;
  onSelectEvidence: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const codes = claim.evidence_codes;
  const shown = expanded ? codes : codes.slice(0, 4);
  const hidden = codes.length - shown.length;

  return (
    <article className="rounded-[2px] border border-rule">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-rule px-4 py-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] text-ink-3">
              {String(claim.rank).padStart(2, "0")}
            </span>
            <h3 className="display text-[13px] font-semibold text-ink">
              {humanize(claim.label)}
            </h3>
            {claim.category && (
              <span className="font-mono text-[10px] text-ink-3">
                {claim.category}
              </span>
            )}
          </div>
          <p className="mt-1.5 max-w-2xl text-[12px] leading-5 text-ink-2">
            {claim.explanation}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <SupportStatus status={claim.support_status} />
          <span
            className="rounded-[2px] border border-rule-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2"
            title="Model's own confidence in this claim"
          >
            {claim.confidence}
          </span>
          <span className="tnum font-mono text-[13px] font-semibold text-ink">
            {claim.estimated_lost_intents ?? "—"}
          </span>
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-1.5 px-4 py-2.5">
        {shown.map((code) => (
          <button
            className="cursor-pointer rounded-[2px] border border-rule-2 bg-paper-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2 transition-colors hover:border-ink-3"
            key={code}
            onClick={() => onSelectEvidence(code)}
            title={code}
            type="button"
          >
            {shortCode(code)}
          </button>
        ))}
        {hidden > 0 && (
          <button
            className="cursor-pointer font-mono text-[10px] text-petrol-2 underline underline-offset-2"
            onClick={() => setExpanded(true)}
            type="button"
          >
            +{hidden} more
          </button>
        )}
        {expanded && codes.length > 4 && (
          <button
            className="cursor-pointer font-mono text-[10px] text-ink-3 underline underline-offset-2"
            onClick={() => setExpanded(false)}
            type="button"
          >
            collapse
          </button>
        )}
        <span className="tnum ml-auto font-mono text-[10px] text-ink-3">
          {codes.length} evidence records
        </span>
      </div>

      {wasHypothesis && (
        <p className="border-t border-rule px-4 py-2 text-[11px] text-ink-3">
          Raised as a hypothesis before any evidence was collected. Select the
          claim, or any citation above, to light the whole chain.
        </p>
      )}
    </article>
  );
}

function EvidenceDrawer({
  code,
  onClose,
}: {
  code: string;
  onClose: () => void;
}) {
  const evidence = useQuery<Evidence, ApiError>({
    enabled: true,
    queryKey: ["evidence", code],
    queryFn: () =>
      apiRequest<Evidence>(`/api/v1/evidence/${encodeURIComponent(code)}`),
    retry: false,
  });

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        aria-label="Close evidence"
        className="flex-1 cursor-pointer bg-ink/25 backdrop-blur-[1px]"
        onClick={onClose}
        type="button"
      />
      <aside
        aria-label="Evidence record"
        aria-modal="true"
        className="h-full w-full max-w-md overflow-y-auto border-l border-rule bg-surface"
        role="dialog"
      >
        <div className="sticky top-0 flex items-start justify-between gap-4 border-b border-rule bg-surface px-5 py-4">
          <div className="min-w-0">
            <div className="eyebrow">Evidence record</div>
            <h2 className="mt-1.5 font-mono text-[13px] font-semibold break-all text-ink">
              {code}
            </h2>
          </div>
          <button
            aria-label="Close"
            className="cursor-pointer rounded-[2px] p-1.5 text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
            onClick={onClose}
            type="button"
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="px-5 py-4">
          {evidence.isLoading ? (
            <LoadingState label="Loading evidence" />
          ) : evidence.isError ? (
            <ErrorState message={evidence.error.detail} />
          ) : evidence.data ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-1.5">
                <span className="rounded-[2px] border border-rule-2 bg-paper-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
                  {evidence.data.evidence_type}
                </span>
                <span className="rounded-[2px] border border-rule-2 bg-paper-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
                  {formatDate(evidence.data.created_at)}
                </span>
              </div>
              <p className="text-[12px] leading-5 text-ink-2">
                {evidence.data.summary}
              </p>
              {evidence.data.metrics && (
                <div>
                  <div className="eyebrow mb-2">Measured values</div>
                  <dl className="divide-y divide-rule border-y border-rule">
                    {Object.entries(evidence.data.metrics).map(([key, value]) => (
                      <div
                        className="flex items-baseline justify-between gap-4 py-2"
                        key={key}
                      >
                        <dt className="font-mono text-[11px] text-ink-3">
                          {key}
                        </dt>
                        <dd className="tnum font-mono text-[12px] text-ink">
                          {typeof value === "number"
                            ? value.toLocaleString("en", {
                                maximumFractionDigits: 6,
                              })
                            : String(value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
