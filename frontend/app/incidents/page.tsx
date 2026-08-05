"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { ErrorState, EmptyState, LoadingState, PageHeader } from "@/components/page-elements";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, type Incident, type IncidentList, jsonBody, apiRequest } from "@/lib/api/client";
import { formatDate, humanize } from "@/lib/format";

const scenarios = ["all", "normal", "benefit_friction", "channel_timeout", "mixed_failure", "data_gap"];

function incidentQuery(status: string, scenario: string) {
  const params = new URLSearchParams({ page: "1", page_size: "20" });
  if (status !== "all") params.set("status_filter", status);
  if (scenario !== "all") params.set("scenario_id", scenario);
  return `/api/v1/incidents?${params.toString()}`;
}

export default function IncidentsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("all");
  const [scenario, setScenario] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ scenario_kind: "mixed_failure", seed: 42, num_intents: 500, title: "" });

  const incidents = useQuery<IncidentList, ApiError>({
    queryKey: ["incidents", status, scenario],
    queryFn: () => apiRequest<IncidentList>(incidentQuery(status, scenario)),
  });

  const createIncident = useMutation<Incident, ApiError, typeof form>({
    mutationFn: (body) => apiRequest<Incident>("/api/v1/incidents/simulated", { method: "POST", body: jsonBody(body) }),
    onSuccess: async (incident) => {
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      router.push(`/incidents/${incident.id}`);
    },
  });

  const list = incidents.data?.items ?? [];
  return (
    <div className="space-y-7">
      <PageHeader
        action={<button className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-blue-800 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors duration-200 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-300" onClick={() => setShowCreate(true)} type="button"><Icon name="beaker" size={16} /> Create simulated incident</button>}
        description="Inspect conversion anomalies, launch a deterministic diagnosis, and follow every evidence-backed result."
        eyebrow="Operations / Incidents"
        title="Incident workspace"
      />

      <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
        <div className="flex flex-wrap items-center gap-3"><div className="flex items-center gap-2 text-xs font-semibold text-slate-600"><Icon name="filter" size={15} /> Filters</div><select aria-label="Filter by incident status" className="cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setStatus(event.target.value)} value={status}><option value="all">All statuses</option><option value="DETECTED">Detected</option><option value="INVESTIGATING">Investigating</option><option value="ACTION_REQUIRED">Action required</option><option value="RESOLVED">Resolved</option></select><select aria-label="Filter by scenario" className="cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setScenario(event.target.value)} value={scenario}>{scenarios.map((item) => <option key={item} value={item}>{item === "all" ? "All scenarios" : humanize(item)}</option>)}</select></div><div className="font-mono text-xs text-slate-400">{incidents.data ? `${incidents.data.pagination.total} records` : "Loading records"}</div>
      </div>

      {incidents.isLoading ? <LoadingState label="Loading incidents" /> : incidents.isError ? <ErrorState message={incidents.error.detail} onRetry={() => void incidents.refetch()} /> : list.length === 0 ? <EmptyState action={<button className="cursor-pointer rounded-lg bg-blue-800 px-4 py-2 text-sm font-semibold text-white transition-colors duration-200 hover:bg-blue-700" onClick={() => setShowCreate(true)} type="button">Create a simulated incident</button>} description="Try a deterministic mixed failure or data-gap scenario to exercise the full diagnosis flow." title="No incidents match these filters" /> : <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm"><div className="overflow-x-auto"><table className="w-full min-w-[780px] text-left text-sm"><thead className="border-b border-slate-200 bg-slate-50/80 text-[10px] uppercase tracking-[0.14em] text-slate-400"><tr><th className="px-5 py-3 font-semibold">Incident</th><th className="px-5 py-3 font-semibold">Scenario</th><th className="px-5 py-3 font-semibold">Trigger</th><th className="px-5 py-3 font-semibold">Observed</th><th className="px-5 py-3 font-semibold">Diagnosis</th><th className="px-5 py-3 font-semibold">Created</th><th className="px-5 py-3" /></tr></thead><tbody className="divide-y divide-slate-100">{list.map((incident) => <tr className="group transition-colors duration-200 hover:bg-blue-50/40" key={incident.id}><td className="px-5 py-4"><Link className="font-semibold text-slate-900 hover:text-blue-800" href={`/incidents/${incident.id}`}>{incident.title}</Link><div className="mt-1 font-mono text-[10px] text-slate-400">{incident.id.slice(0, 8)}…</div></td><td className="px-5 py-4"><span className="rounded-md bg-slate-100 px-2 py-1 font-mono text-xs text-slate-600">{incident.scenario_id}</span></td><td className="px-5 py-4 text-slate-600">{humanize(incident.trigger_metric)}</td><td className="px-5 py-4"><span className="font-mono font-semibold text-slate-800">{(incident.observed_value * 100).toFixed(1)}%</span><div className="mt-1 text-xs text-slate-400">baseline {(incident.baseline_value * 100).toFixed(1)}%</div></td><td className="px-5 py-4"><div className="flex flex-col items-start gap-1.5"><StatusBadge status={incident.status} />{incident.latest_diagnosis_status && <span className="text-[10px] text-slate-400">run: {humanize(incident.latest_diagnosis_status)}</span>}</div></td><td className="px-5 py-4 whitespace-nowrap text-xs text-slate-500">{formatDate(incident.created_at)}</td><td className="px-5 py-4 text-right"><Link aria-label={`Open ${incident.title}`} className="inline-flex cursor-pointer rounded-md p-2 text-slate-400 transition-colors duration-200 hover:bg-blue-100 hover:text-blue-800" href={`/incidents/${incident.id}`}><Icon name="arrow-right" size={16} /></Link></td></tr>)}</tbody></table></div></div>}

      {showCreate && <div aria-label="Create simulated incident" aria-modal="true" className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-4" role="dialog"><div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl"><div className="flex items-start justify-between"><div><div className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-blue-700">Harness</div><h2 className="mt-2 text-xl font-semibold">Create simulated incident</h2></div><button aria-label="Close dialog" className="cursor-pointer rounded-md p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700" onClick={() => setShowCreate(false)} type="button"><Icon name="x" size={18} /></button></div><div className="mt-6 grid gap-4 sm:grid-cols-2"><label className="text-sm font-medium text-slate-700 sm:col-span-2">Scenario<select className="mt-2 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setForm((current) => ({ ...current, scenario_kind: event.target.value }))} value={form.scenario_kind}>{scenarios.filter((item) => item !== "all").map((item) => <option key={item} value={item}>{humanize(item)}</option>)}</select></label><label className="text-sm font-medium text-slate-700">Seed<input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setForm((current) => ({ ...current, seed: Number(event.target.value) }))} type="number" value={form.seed} /></label><label className="text-sm font-medium text-slate-700">Intents<input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 font-mono text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" min={1} max={10000} onChange={(event) => setForm((current) => ({ ...current, num_intents: Number(event.target.value) }))} type="number" value={form.num_intents} /></label><label className="text-sm font-medium text-slate-700 sm:col-span-2">Title <span className="font-normal text-slate-400">(optional)</span><input className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm font-normal outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} placeholder="e.g. Checkout conversion dropped" value={form.title} /></label></div>{createIncident.isError && <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">{createIncident.error.detail}</p>}<div className="mt-7 flex justify-end gap-3"><button className="cursor-pointer rounded-lg px-4 py-2.5 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-100" onClick={() => setShowCreate(false)} type="button">Cancel</button><button className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-blue-800 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50" disabled={createIncident.isPending} onClick={() => createIncident.mutate(form)} type="button">{createIncident.isPending && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-blue-200 border-t-white" />}Create incident</button></div></div></div>}
    </div>
  );
}

