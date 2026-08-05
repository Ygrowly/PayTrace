"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { EvaluationChart } from "@/components/charts/evaluation-chart";
import { Icon } from "@/components/icons";
import { ErrorState, EmptyState, KpiCard, LoadingState, PageHeader, SectionCard } from "@/components/page-elements";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, apiRequest, apiUrl, jsonBody, type EvaluationCreate, type EvaluationList, type EvaluationRun, type EvaluationTrigger } from "@/lib/api/client";
import { formatNumber, formatPercent, humanize } from "@/lib/format";

const scenarios = ["normal", "benefit_friction", "channel_timeout", "mixed_failure", "data_gap"];
const terminalStatuses = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

type Badcase = { scenario_kind?: string; categories?: string[]; summary?: string };
type ScenarioResult = NonNullable<EvaluationRun["scenario_results"]>[number];

function asBadcase(value: Record<string, never>): Badcase {
  return value as unknown as Badcase;
}

function toggle(items: string[], item: string): string[] {
  return items.includes(item) ? items.filter((current) => current !== item) : [...items, item];
}

function scenarioLabels(result: ScenarioResult, predicted: boolean): string[] {
  const causes = predicted ? result.predicted_root_causes ?? [] : result.expected_root_causes ?? [];
  const gaps = predicted ? result.predicted_missing_data ?? [] : result.expected_data_gaps ?? [];
  return [...new Set([...causes, ...gaps])];
}

export default function EvalPage() {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const [scenarioKinds, setScenarioKinds] = useState<string[]>(scenarios);
  const [seed, setSeed] = useState(42);
  const [numIntents, setNumIntents] = useState(500);
  const [promptVersion, setPromptVersion] = useState("rule-based.v1");

  const recentRuns = useQuery<EvaluationList, ApiError>({ queryKey: ["evaluation-runs"], queryFn: () => apiRequest<EvaluationList>("/api/v1/evaluation-runs?page=1&page_size=8") });
  const currentRun = useQuery<EvaluationRun, ApiError>({
    enabled: Boolean(runId),
    queryKey: ["evaluation-run", runId],
    queryFn: () => apiRequest<EvaluationRun>(`/api/v1/evaluation-runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && terminalStatuses.has(status) ? false : 1500;
    },
  });
  const submit = useMutation<EvaluationTrigger, ApiError, EvaluationCreate>({
    mutationFn: (body) => apiRequest<EvaluationTrigger>("/api/v1/evaluation-runs", { method: "POST", headers: { "Idempotency-Key": `eval-${Date.now()}-${seed}` }, body: jsonBody(body) }),
    onSuccess: async (response) => {
      setRunId(response.evaluation_run_id);
      await queryClient.invalidateQueries({ queryKey: ["evaluation-runs"] });
    },
  });

  const run = currentRun.data;
  const metrics = run?.metrics;
  const canSubmit = scenarioKinds.length > 0 && numIntents >= 1 && numIntents <= 10000;
  const submitRun = () => submit.mutate({ model_mode: "B0", prompt_version: promptVersion || null, scenario_kinds: scenarioKinds, seed, num_intents: numIntents });

  return (
    <div className="space-y-7">
      <PageHeader description="Compare the fixed rule-based workflow against isolated Ground Truth. Metrics and badcase classification are calculated by the backend." eyebrow="Evaluation / Lab" title="Eval Lab" />

      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <SectionCard eyebrow="B0 / no paid calls" title="New evaluation">
          <div className="space-y-5"><div><label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Model mode</label><div className="mt-2 flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-3 py-2.5"><span className="font-mono text-sm font-semibold text-blue-900">B0 · RuleBasedModelAdapter</span><Icon name="shield" size={15} /></div></div><label className="block text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Prompt version<input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-normal normal-case tracking-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setPromptVersion(event.target.value)} value={promptVersion} /></label><div className="grid grid-cols-2 gap-3"><label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Seed<input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm font-normal tracking-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setSeed(Number(event.target.value))} type="number" value={seed} /></label><label className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Intents<input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm font-normal tracking-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" min={1} max={10000} onChange={(event) => setNumIntents(Number(event.target.value))} type="number" value={numIntents} /></label></div><div><div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">Scenario set</div><div className="mt-3 space-y-2">{scenarios.map((scenario) => <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-slate-100 px-3 py-2.5 text-sm text-slate-700 transition-colors duration-200 hover:border-blue-200 hover:bg-blue-50/50" key={scenario}><input checked={scenarioKinds.includes(scenario)} className="h-4 w-4 accent-blue-700" onChange={() => setScenarioKinds((current) => toggle(current, scenario))} type="checkbox" /><span>{humanize(scenario)}</span></label>)}</div></div>{submit.isError && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{submit.error.detail}</p>}<button className="inline-flex w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-blue-800 px-4 py-3 text-sm font-semibold text-white transition-colors duration-200 hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={!canSubmit || submit.isPending} onClick={submitRun} type="button">{submit.isPending && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-200 border-t-white" />}Submit evaluation</button></div>
        </SectionCard>

        <div className="space-y-5">
          {!runId && !run ? <EmptyState description="Submit a B0 run to see aggregate metrics, scenario-level predictions, and actionable badcases here." title="No evaluation selected" /> : currentRun.isLoading ? <LoadingState label="Loading evaluation run" /> : currentRun.isError ? <ErrorState message={currentRun.error.detail} onRetry={() => void currentRun.refetch()} /> : run && <><div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"><StatusBadge status={run.status} /><span className="font-mono text-xs text-slate-500">{run.id.slice(0, 12)}…</span><span className="text-xs text-slate-400">{run.scenario_count} scenarios · seed {run.seed} · {run.num_intents} intents</span>{run.status === "SUCCEEDED" && <div className="ml-auto flex gap-2"><a className="cursor-pointer rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-200 hover:text-blue-800" download href={`${apiUrl(`/api/v1/evaluation-runs/${run.id}/report?format=json`)}`}>JSON report</a><a className="cursor-pointer rounded-md border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-200 hover:text-blue-800" download href={`${apiUrl(`/api/v1/evaluation-runs/${run.id}/report?format=markdown`)}`}>Markdown</a></div>}</div>{run.status === "FAILED" && <div className="rounded-xl border border-red-200 bg-red-50 p-5"><div className="font-semibold text-red-900">Evaluation failed</div><p className="mt-2 text-sm text-red-800/80">{run.error_message ?? "The worker did not produce a report."}</p></div>}{run.status !== "SUCCEEDED" && run.status !== "FAILED" && <div className="rounded-xl border border-blue-200 bg-blue-50 p-5"><div className="flex items-center gap-2 font-semibold text-blue-900"><span className="h-2 w-2 animate-pulse rounded-full bg-blue-600" /> Evaluation is running</div><p className="mt-2 text-sm text-blue-800/75">The page polls the persisted run state; the browser can be refreshed safely.</p></div>}{metrics && <><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"><KpiCard label="Run success" tone="green" value={formatPercent(metrics.run_success_rate)} detail={`${metrics.succeeded_count}/${metrics.scenario_count} scenarios`} /><KpiCard label="Root cause F1" tone="blue" value={metrics.root_cause_f1_mean.toFixed(3)} detail="mean set F1" /><KpiCard label="Evidence validity" tone="blue" value={formatPercent(metrics.evidence_validity_rate_mean)} detail="mean supported evidence" /><KpiCard label="Badcase scenarios" tone={metrics.badcase_count > 0 ? "amber" : "green"} value={formatNumber(metrics.badcase_count)} detail="needs inspection" /></div><SectionCard eyebrow="Backend metrics / ECharts" title="Aggregate quality"><EvaluationChart run={run} /></SectionCard></>}</>}</div>
      </div>

      {run?.scenario_results && <SectionCard eyebrow="Prediction vs Ground Truth" title="Scenario comparison"><div className="overflow-x-auto"><table className="w-full min-w-[980px] text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50/80 text-[10px] uppercase tracking-[0.14em] text-slate-400"><tr><th className="px-4 py-3 font-semibold">Scenario</th><th className="px-4 py-3 font-semibold">Status</th><th className="px-4 py-3 font-semibold">Predicted findings</th><th className="px-4 py-3 font-semibold">Expected findings</th><th className="px-4 py-3 font-semibold">F1</th><th className="px-4 py-3 font-semibold">Badcases</th></tr></thead><tbody className="divide-y divide-slate-100">{run.scenario_results.map((result) => { const predicted = scenarioLabels(result, true); const expected = scenarioLabels(result, false); return <tr className="align-top transition-colors duration-200 hover:bg-blue-50/40" key={result.scenario_id}><td className="px-4 py-4"><div className="font-semibold text-slate-900">{humanize(result.scenario_kind)}</div><div className="mt-1 font-mono text-[10px] text-slate-400">{result.scenario_id}</div></td><td className="px-4 py-4"><StatusBadge status={result.diagnosis_status} /></td><td className="px-4 py-4"><div className="flex max-w-xs flex-wrap gap-1.5">{predicted.length === 0 ? <span className="text-xs text-slate-400">None</span> : predicted.map((item) => <span className="rounded-md bg-blue-50 px-2 py-1 text-[10px] text-blue-800" key={item}>{humanize(item)}</span>)}</div></td><td className="px-4 py-4"><div className="flex max-w-xs flex-wrap gap-1.5">{expected.length === 0 ? <span className="text-xs text-slate-400">None</span> : expected.map((item) => <span className="rounded-md bg-slate-100 px-2 py-1 text-[10px] text-slate-700" key={item}>{humanize(item)}</span>)}</div></td><td className="px-4 py-4 font-mono text-xs text-slate-700">{result.root_cause_f1 == null ? "—" : result.root_cause_f1.toFixed(3)}</td><td className="px-4 py-4"><div className="flex max-w-xs flex-wrap gap-1.5">{(result.badcases ?? []).length === 0 ? <span className="text-xs text-emerald-700">Clean</span> : result.badcases?.map((badcase) => <span className="rounded-md bg-red-50 px-2 py-1 text-[10px] text-red-700" key={badcase}>{humanize(badcase)}</span>)}</div>{result.report_summary && <p className="mt-2 max-w-xs text-xs text-slate-500">{result.report_summary}</p>}</td></tr>; })}</tbody></table></div></SectionCard>}

      {run?.badcases && run.badcases.length > 0 && <SectionCard eyebrow="Failure triage" title="Badcase index"><div className="space-y-3">{run.badcases.map((raw, index) => { const badcase = asBadcase(raw); return <div className="rounded-lg border border-red-100 bg-red-50/50 p-4" key={`${badcase.scenario_kind ?? "badcase"}-${index}`}><div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-red-900">{humanize(badcase.scenario_kind)}</span>{badcase.categories?.map((category) => <span className="rounded-md bg-white px-2 py-1 font-mono text-[10px] text-red-700" key={category}>{category}</span>)}</div>{badcase.summary && <p className="mt-2 text-sm text-red-800/80">{badcase.summary}</p>}</div>; })}</div></SectionCard>}

      <SectionCard eyebrow="Recent runs" title="Evaluation history">{recentRuns.isLoading ? <p className="text-sm text-slate-500">Loading history…</p> : recentRuns.isError ? <ErrorState message={recentRuns.error.detail} onRetry={() => void recentRuns.refetch()} /> : recentRuns.data?.items.length ? <div className="divide-y divide-slate-100">{recentRuns.data.items.map((item) => <button className="flex w-full cursor-pointer items-center gap-3 py-3 text-left transition-colors duration-200 hover:bg-blue-50/50" key={item.id} onClick={() => setRunId(item.id)} type="button"><StatusBadge status={item.status} /><span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-600">{item.id}</span><span className="text-xs text-slate-400">{item.scenario_count} scenarios</span><span className="text-xs text-slate-400">{item.created_at.slice(0, 16).replace("T", " ")}</span><Icon name="arrow-right" size={15} /></button>)}</div> : <p className="text-sm text-slate-500">No previous evaluation runs.</p>}</SectionCard>
    </div>
  );
}
