"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { FunnelChart } from "@/components/charts/funnel-chart";
import { Icon } from "@/components/icons";
import { ErrorState, KpiCard, LoadingState, PageHeader, SectionCard } from "@/components/page-elements";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, apiRequest, type DiagnosisReport, type DiagnosisRun, type DiagnosisTrace, type Evidence, type FunnelResult, type Incident, type DiagnosisRunRetry, type DiagnosisRunTrigger } from "@/lib/api/client";
import { formatDate, formatNumber, formatPercent, humanize } from "@/lib/format";
import { useDiagnosisEvents } from "@/hooks/use-diagnosis-events";

const terminalStatuses = new Set(["SUCCEEDED", "NEEDS_DATA", "FAILED", "CANCELLED"]);
const retryableStatuses = new Set(["FAILED", "DISPATCH_FAILED", "CANCELLED", "NEEDS_DATA"]);

function evidenceLabel(type: string): string {
  return humanize(type).replace("Data Gap", "Data quality gap");
}

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = String(params.id);
  const queryClient = useQueryClient();
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<string | null>(null);

  const incident = useQuery<Incident, ApiError>({ queryKey: ["incident", incidentId], queryFn: () => apiRequest<Incident>(`/api/v1/incidents/${incidentId}`) });
  const runId = activeRunId ?? incident.data?.latest_diagnosis_run_id ?? null;
  const run = useQuery<DiagnosisRun, ApiError>({
    enabled: Boolean(runId),
    queryKey: ["diagnosis-run", runId],
    queryFn: () => apiRequest<DiagnosisRun>(`/api/v1/diagnosis-runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && terminalStatuses.has(status) ? false : 1500;
    },
  });
  const funnel = useQuery<FunnelResult, ApiError>({ enabled: Boolean(incident.data), queryKey: ["incident-funnel", incidentId], queryFn: () => apiRequest<FunnelResult>(`/api/v1/incidents/${incidentId}/funnel`) });
  const report = useQuery<DiagnosisReport, ApiError>({ enabled: Boolean(run.data && ["SUCCEEDED", "NEEDS_DATA"].includes(run.data.status)), queryKey: ["diagnosis-report", runId], queryFn: () => apiRequest<DiagnosisReport>(`/api/v1/diagnosis-runs/${runId}/report`), retry: false });
  const trace = useQuery<DiagnosisTrace, ApiError>({ enabled: Boolean(run.data && terminalStatuses.has(run.data.status)), queryKey: ["diagnosis-trace", runId], queryFn: () => apiRequest<DiagnosisTrace>(`/api/v1/diagnosis-runs/${runId}/trace`), retry: false });
  const evidence = useQuery<Evidence, ApiError>({ enabled: Boolean(selectedEvidence), queryKey: ["evidence", selectedEvidence], queryFn: () => apiRequest<Evidence>(`/api/v1/evidence/${encodeURIComponent(selectedEvidence ?? "")}`), retry: false });
  const events = useDiagnosisEvents(runId, Boolean(run.data && !terminalStatuses.has(run.data.status)));

  const diagnosis = useMutation<{ diagnosis_run_id: string; status: string; message: string }, ApiError, void>({
    mutationFn: () => {
      if (runId && run.data && retryableStatuses.has(run.data.status)) {
        return apiRequest<DiagnosisRunRetry>(`/api/v1/incidents/${incidentId}/diagnosis-runs/${runId}/retry`, { method: "POST", headers: { "Idempotency-Key": `retry-${incidentId}-${Date.now()}` } }).then((response) => ({ diagnosis_run_id: response.new_diagnosis_run_id, status: response.status, message: response.message }));
      }
      return apiRequest<DiagnosisRunTrigger>(`/api/v1/incidents/${incidentId}/diagnosis-runs`, { method: "POST", headers: { "Idempotency-Key": `diagnosis-${incidentId}-${Date.now()}` } });
    },
    onSuccess: async (response) => {
      setActiveRunId(response.diagnosis_run_id);
      await queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      await queryClient.invalidateQueries({ queryKey: ["diagnosis-run", response.diagnosis_run_id] });
    },
  });

  if (incident.isLoading) return <LoadingState label="Loading incident" />;
  if (incident.isError || !incident.data) return <ErrorState message={incident.error?.detail ?? "Incident not found"} onRetry={() => void incident.refetch()} />;
  const currentIncident = incident.data;
  const currentRun = run.data;
  const currentReport = report.data;
  const isTerminal = Boolean(currentRun && terminalStatuses.has(currentRun.status));
  const actionLabel = currentRun && retryableStatuses.has(currentRun.status) ? "Retry diagnosis" : currentRun && !isTerminal ? "Diagnosis running" : "Run diagnosis";

  return (
    <div className="space-y-7">
      <PageHeader action={<div className="flex flex-wrap gap-2"><Link className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition-colors duration-200 hover:border-blue-200 hover:text-blue-800" href="/incidents"><Icon name="arrow-right" size={15} /> Back to incidents</Link><button className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-blue-800 px-4 py-2.5 text-sm font-semibold text-white transition-colors duration-200 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={diagnosis.isPending || Boolean(currentRun && !isTerminal && !retryableStatuses.has(currentRun.status))} onClick={() => diagnosis.mutate()} type="button">{diagnosis.isPending && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-200 border-t-white" />}{actionLabel}</button></div>} description={currentIncident.description ?? "Deterministic incident dataset ready for evidence-backed diagnosis."} eyebrow={`Incident / ${currentIncident.scenario_id}`} title={currentIncident.title} />

      {diagnosis.isError && <ErrorState message={diagnosis.error.detail} />}
      <div className="flex flex-wrap items-center gap-3"><StatusBadge status={currentIncident.status} />{currentRun && <><span className="text-slate-300">/</span><span className="text-xs text-slate-500">Latest run</span><StatusBadge status={currentRun.status} /><span className="font-mono text-[10px] text-slate-400">{currentRun.id.slice(0, 12)}…</span></>}{events.connected && <span className="ml-auto inline-flex items-center gap-2 text-xs text-emerald-700"><span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> Live progress connected</span>}</div>

      <section className="grid gap-4 md:grid-cols-4"><KpiCard detail={`baseline ${formatPercent(currentIncident.baseline_value)}`} label="Observed completion" tone="blue" value={formatPercent(currentIncident.observed_value)} /><KpiCard detail={formatDate(currentIncident.incident_start)} label="Incident started" tone="amber" value={formatDate(currentIncident.incident_start).split(",")[0]} /><KpiCard detail="reported by backend" label="Unexplained loss" tone={currentReport?.unexplained_lost_intents ? "red" : "green"} value={formatNumber(currentReport?.unexplained_lost_intents)} /><KpiCard detail={currentIncident.trigger_metric} label="Trigger metric" tone="blue" value={humanize(currentIncident.trigger_metric)} /></section>

      {funnel.isLoading ? <LoadingState label="Loading funnel" /> : funnel.isError ? <ErrorState message={funnel.error.detail} onRetry={() => void funnel.refetch()} /> : funnel.data && <SectionCard eyebrow="Backend-calculated conversion rates" title="Baseline vs incident funnel"><div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-slate-500"><span className="rounded-md bg-red-50 px-2 py-1 text-red-700">{funnel.data.anomalous_stages.length} anomalous stage{funnel.data.anomalous_stages.length === 1 ? "" : "s"}</span>{funnel.data.anomalous_stages.map((stage) => <span className="font-mono text-[10px] text-slate-500" key={stage}>{humanize(stage)}</span>)}</div><FunnelChart data={funnel.data} /></SectionCard>}

      {currentRun && !isTerminal && <SectionCard eyebrow="SSE / persisted RunEvent" title="Diagnosis progress"><div className="space-y-3">{events.error && <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">{events.error}</p>}{events.events.length === 0 ? <p className="text-sm text-slate-500">Waiting for the worker to publish its first event…</p> : events.events.map((event) => <div className="flex gap-3 rounded-lg border border-slate-100 bg-slate-50/70 p-3" key={event.sequence}><div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 font-mono text-[10px] font-semibold text-blue-800">{event.sequence}</div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><span className="font-mono text-xs font-semibold text-slate-800">{humanize(event.event_type)}</span>{event.stage && <StatusBadge status={event.stage} />}</div><p className="mt-1 text-xs text-slate-500">{event.message ?? ""}</p></div><time className="ml-auto shrink-0 text-[10px] text-slate-400">{formatDate(event.created_at)}</time></div>)}</div></SectionCard>}

      {currentRun?.status === "FAILED" && <div className="rounded-xl border border-red-200 bg-red-50 p-5"><div className="flex items-center gap-2 font-semibold text-red-900"><Icon name="triangle" size={17} /> Diagnosis failed</div><p className="mt-2 text-sm text-red-800/80">{currentRun.error_message ?? "The worker did not produce a report."}</p></div>}
      {currentReport?.status === "NEEDS_DATA" && <div className="rounded-xl border border-amber-200 bg-amber-50 p-5"><div className="flex items-center gap-2 font-semibold text-amber-900"><Icon name="triangle" size={17} /> Needs more data</div><p className="mt-2 text-sm text-amber-800/80">The workflow withheld a causal claim until the following data is available.</p><ul className="mt-4 list-disc space-y-1 pl-5 text-sm text-amber-900">{currentReport.missing_data.map((item) => <li key={item}>{item}</li>)}</ul></div>}

      {currentReport && <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]"><SectionCard eyebrow="Validated report" title="Root causes"><p className="mb-5 text-sm leading-6 text-slate-600">{currentReport.summary}</p>{currentReport.root_causes.length === 0 ? <p className="rounded-lg bg-slate-50 p-4 text-sm text-slate-500">No causal claim was made for this run.</p> : <div className="space-y-3">{currentReport.root_causes.map((rootCause) => <div className="rounded-xl border border-slate-200 p-4" key={`${rootCause.rank}-${rootCause.label}`}><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-100 font-mono text-xs font-semibold text-blue-800">{rootCause.rank}</span><h3 className="font-semibold text-slate-900">{humanize(rootCause.label)}</h3></div><p className="mt-2 text-sm leading-5 text-slate-600">{rootCause.explanation}</p></div><span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[10px] font-semibold uppercase text-slate-600">{rootCause.confidence}</span></div><div className="mt-4 flex flex-wrap gap-2">{rootCause.evidence_codes.map((code) => <button className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2 py-1 font-mono text-[10px] font-semibold text-blue-800 transition-colors duration-200 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-200" key={code} onClick={() => setSelectedEvidence(code)} type="button">{code}<Icon name="arrow-right" size={11} /></button>)}</div></div>)}</div>}</SectionCard><SectionCard eyebrow="Attribution ledger" title="Loss and actions"><div className="grid grid-cols-3 gap-3"><div><div className="font-mono text-[10px] uppercase text-slate-400">Total</div><div className="mt-1 text-xl font-semibold">{formatNumber(currentReport.total_estimated_lost_intents)}</div></div><div><div className="font-mono text-[10px] uppercase text-slate-400">Explained</div><div className="mt-1 text-xl font-semibold text-emerald-700">{formatNumber(currentReport.explained_lost_intents)}</div></div><div><div className="font-mono text-[10px] uppercase text-slate-400">Unexplained</div><div className="mt-1 text-xl font-semibold text-red-700">{formatNumber(currentReport.unexplained_lost_intents)}</div></div></div><div className="mt-6 border-t border-slate-100 pt-5"><h3 className="text-sm font-semibold">Recommended actions</h3>{currentReport.recommended_actions.length === 0 ? <p className="mt-2 text-sm text-slate-500">No action was recommended.</p> : <ul className="mt-3 space-y-2">{currentReport.recommended_actions.map((action) => <li className="flex gap-2 text-sm leading-5 text-slate-600" key={action}><Icon name="check" size={15} /><span>{action}</span></li>)}</ul>}</div>{(currentReport.alternative_explanations?.length ?? 0) > 0 && <div className="mt-6 border-t border-slate-100 pt-5"><h3 className="text-sm font-semibold">Alternative explanations</h3><ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">{currentReport.alternative_explanations?.map((item) => <li key={item}>{item}</li>)}</ul></div>}</SectionCard></div>}

      {trace.data && <SectionCard eyebrow="Persisted tool trace" title="Execution trace"><div className="grid gap-3 md:grid-cols-2">{trace.data.tool_executions.map((tool) => <div className="rounded-lg border border-slate-200 p-4" key={tool.id}><div className="flex items-center justify-between"><span className="font-mono text-xs font-semibold text-slate-800">{tool.tool_name}</span><StatusBadge status={tool.status} /></div><div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500"><span>call <b className="font-mono text-slate-700">{tool.tool_call_id}</b></span><span>rows <b className="font-mono text-slate-700">{formatNumber(tool.row_count)}</b></span><span>duration <b className="font-mono text-slate-700">{tool.duration_ms ?? "—"}ms</b></span><span>artifact <b className="font-mono text-slate-700">{tool.artifact_id ? "linked" : "—"}</b></span></div></div>)}</div>{trace.data.events.length > 0 && <div className="mt-5 border-t border-slate-100 pt-5"><h3 className="text-sm font-semibold">Run event history</h3><div className="mt-3 flex flex-wrap gap-2">{trace.data.events.map((event) => <span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[10px] text-slate-600" key={event.id}>{event.sequence} · {event.event_type}</span>)}</div></div>}</SectionCard>}

      {selectedEvidence && <div aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog"><div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"><div className="flex items-start justify-between"><div><div className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-700">Evidence detail</div><h2 className="mt-2 text-xl font-semibold">{selectedEvidence}</h2></div><button aria-label="Close evidence" className="cursor-pointer rounded-md p-2 text-slate-400 transition-colors hover:bg-slate-100" onClick={() => setSelectedEvidence(null)} type="button"><Icon name="x" size={18} /></button></div>{evidence.isLoading ? <div className="py-10"><LoadingState label="Loading evidence" /></div> : evidence.isError ? <div className="mt-6"><ErrorState message={evidence.error.detail} /></div> : evidence.data && <div className="mt-6 space-y-4"><div className="flex flex-wrap gap-2"><span className="rounded-md bg-blue-50 px-2 py-1 font-mono text-[10px] text-blue-800">{evidenceLabel(evidence.data.evidence_type)}</span><span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-[10px] text-slate-600">{formatDate(evidence.data.created_at)}</span></div><p className="text-sm leading-6 text-slate-600">{evidence.data.summary}</p>{evidence.data.metrics && <pre className="max-h-56 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-blue-100">{JSON.stringify(evidence.data.metrics, null, 2)}</pre>}</div>}</div></div>}
    </div>
  );
}
