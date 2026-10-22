"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Icon } from "@/components/icons";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/page-elements";
import { RunStatus, SupportStatus } from "@/components/status-badge";
import {
  ApiError,
  type Incident,
  type IncidentList,
  apiRequest,
  jsonBody,
} from "@/lib/api/client";
import { formatDate, formatPercent, humanize } from "@/lib/format";

const SCENARIOS = [
  "all",
  "normal",
  "benefit_friction",
  "channel_timeout",
  "mixed_failure",
  "data_gap",
];

function incidentQuery(status: string, scenario: string) {
  const params = new URLSearchParams({ page: "1", page_size: "20" });
  if (status !== "all") params.set("status_filter", status);
  if (scenario !== "all") params.set("scenario_id", scenario);
  return `/api/v1/incidents?${params.toString()}`;
}

const selectClass =
  "cursor-pointer rounded-[2px] border border-rule-2 bg-surface px-2.5 py-1.5 font-mono text-[11px] text-ink-2 outline-none transition-colors hover:border-ink-3";

export default function IncidentsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("all");
  const [scenario, setScenario] = useState("all");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    scenario_kind: "mixed_failure",
    seed: 42,
    num_intents: 500,
    title: "",
  });

  const incidents = useQuery<IncidentList, ApiError>({
    queryKey: ["incidents", status, scenario],
    queryFn: () => apiRequest<IncidentList>(incidentQuery(status, scenario)),
  });

  const createIncident = useMutation<Incident, ApiError, typeof form>({
    mutationFn: (body) =>
      apiRequest<Incident>("/api/v1/incidents/simulated", {
        method: "POST",
        body: jsonBody(body),
      }),
    onSuccess: async (incident) => {
      await queryClient.invalidateQueries({ queryKey: ["incidents"] });
      router.push(`/incidents/${incident.id}`);
    },
  });

  const list = incidents.data?.items ?? [];
  const diagnosed = list.filter((item) => item.latest_diagnosis_run_id);

  return (
    <div className="space-y-6">
      <PageHeader
        action={
          <Button onClick={() => setShowCreate(true)}>
            <Icon name="beaker" size={14} />
            Create simulated incident
          </Button>
        }
        description="Each incident is a deterministic scenario with an injected fault and an isolated Ground Truth the diagnosis never sees. Open one to read the loss statement and the trace behind it."
        eyebrow="Operations / Incidents"
        meta={
          <div className="flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2">
              <span className="eyebrow">Status</span>
              <select
                aria-label="Filter by incident status"
                className={selectClass}
                onChange={(event) => setStatus(event.target.value)}
                value={status}
              >
                <option value="all">All</option>
                <option value="DETECTED">Detected</option>
                <option value="INVESTIGATING">Investigating</option>
                <option value="ACTION_REQUIRED">Action required</option>
                <option value="RESOLVED">Resolved</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              <span className="eyebrow">Scenario</span>
              <select
                aria-label="Filter by scenario"
                className={selectClass}
                onChange={(event) => setScenario(event.target.value)}
                value={scenario}
              >
                {SCENARIOS.map((item) => (
                  <option key={item} value={item}>
                    {item === "all" ? "All" : humanize(item)}
                  </option>
                ))}
              </select>
            </label>
            <span className="tnum ml-auto font-mono text-[11px] text-ink-3">
              {incidents.data
                ? `${list.length} of ${incidents.data.pagination.total} · ${diagnosed.length} diagnosed`
                : "loading"}
            </span>
          </div>
        }
        title="Incidents"
      />

      {incidents.isLoading ? (
        <LoadingState label="Loading incidents" />
      ) : incidents.isError ? (
        <ErrorState
          message={incidents.error.detail}
          onRetry={() => void incidents.refetch()}
        />
      ) : list.length === 0 ? (
        <EmptyState
          action={<Button onClick={() => setShowCreate(true)}>Create one</Button>}
          description="Nothing matches these filters. A mixed-failure scenario exercises both a channel fault and payment-decision friction in one incident."
          title="No incidents match"
        />
      ) : (
        <Panel bodyClassName="px-0 py-0" eyebrow="Newest first" title="Incident register">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left">
              <thead>
                <tr className="border-b border-rule">
                  <th className="eyebrow px-5 py-2.5 font-semibold">Incident</th>
                  <th className="eyebrow px-4 py-2.5 font-semibold">Scenario</th>
                  <th className="eyebrow px-4 py-2.5 font-semibold">Completion</th>
                  <th className="eyebrow px-4 py-2.5 font-semibold">
                    Diagnosis
                  </th>
                  <th className="eyebrow px-4 py-2.5 font-semibold">Started</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-rule">
                {list.map((incident) => (
                  <IncidentRow incident={incident} key={incident.id} />
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {showCreate && (
        <CreateDialog
          form={form}
          isError={createIncident.isError}
          isPending={createIncident.isPending}
          onCancel={() => setShowCreate(false)}
          onChange={setForm}
          onError={createIncident.error?.detail}
          onSubmit={() => createIncident.mutate(form)}
        />
      )}
    </div>
  );
}

function IncidentRow({ incident }: { incident: Incident }) {
  const delta = incident.observed_value - incident.baseline_value;
  const diagnosed = Boolean(incident.latest_diagnosis_run_id);

  return (
    <tr className="group transition-colors hover:bg-paper-2/60">
      <td className="px-5 py-3.5 align-top">
        <Link
          className="text-[13px] font-medium text-ink hover:text-petrol-2"
          href={`/incidents/${incident.id}`}
        >
          {incident.title}
        </Link>
        <div className="mt-0.5 font-mono text-[10px] text-ink-3">
          {incident.id.slice(0, 8)}
        </div>
      </td>

      <td className="px-4 py-3.5 align-top">
        <span className="rounded-[2px] bg-paper-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-2">
          {incident.scenario_id}
        </span>
      </td>

      <td className="px-4 py-3.5 align-top">
        <div className="tnum font-mono text-[12px] text-ink">
          {formatPercent(incident.observed_value)}
          <span
            className={`ml-1.5 text-[11px] ${
              delta < 0 ? "text-partial" : "text-ink-3"
            }`}
          >
            {delta < 0 ? "−" : "+"}
            {Math.abs(delta * 100).toFixed(1)}
          </span>
        </div>
        <div className="tnum mt-0.5 font-mono text-[10px] text-ink-3">
          from {formatPercent(incident.baseline_value)}
        </div>
      </td>

      <td className="px-4 py-3.5 align-top">
        {diagnosed ? (
          <div className="space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="tnum font-mono text-[13px] font-semibold text-ink">
                {incident.latest_lost_intents ?? "—"}
              </span>
              <span className="text-[10px] text-ink-3">lost</span>
              {(incident.latest_root_causes ?? []).length === 0 && (
                <RunStatus status={incident.latest_diagnosis_status} />
              )}
            </div>
            <ul className="space-y-1">
              {(incident.latest_root_causes ?? []).map((cause) => (
                <li className="flex items-center gap-2" key={cause.label}>
                  <span className="font-mono text-[10px] text-ink-2">
                    {cause.label.replaceAll("_", " ").toLowerCase()}
                  </span>
                  <SupportStatus status={cause.support_status} />
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <RunStatus status={incident.latest_diagnosis_status ?? "NOT RUN"} />
        )}
      </td>

      <td className="px-4 py-3.5 align-top whitespace-nowrap">
        <span className="font-mono text-[11px] text-ink-3">
          {formatDate(incident.created_at).split(",")[0]}
        </span>
      </td>

      <td className="px-4 py-3.5 align-top text-right">
        <Link
          aria-label={`Open ${incident.title}`}
          className="inline-flex rounded-[2px] p-1.5 text-ink-3 transition-colors group-hover:bg-petrol-soft group-hover:text-petrol-2"
          href={`/incidents/${incident.id}`}
        >
          <Icon name="arrow-right" size={15} />
        </Link>
      </td>
    </tr>
  );
}

function CreateDialog({
  form,
  onChange,
  onCancel,
  onSubmit,
  isPending,
  isError,
  onError,
}: {
  form: {
    scenario_kind: string;
    seed: number;
    num_intents: number;
    title: string;
  };
  onChange: (value: typeof form) => void;
  onCancel: () => void;
  onSubmit: () => void;
  isPending: boolean;
  isError: boolean;
  onError?: string;
}) {
  const field =
    "mt-2 w-full rounded-[2px] border border-rule-2 bg-surface px-3 py-2 text-[12px] outline-none transition-colors focus:border-petrol-2";
  const label = "eyebrow";

  return (
    <div
      aria-label="Create simulated incident"
      aria-modal="true"
      className="fixed inset-0 z-40 flex items-center justify-center bg-ink/25 p-4 backdrop-blur-[1px]"
      role="dialog"
    >
      <div className="w-full max-w-lg rounded-[2px] border border-rule bg-surface">
        <div className="flex items-start justify-between gap-4 border-b border-rule px-5 py-4">
          <div>
            <div className="eyebrow">Scenario harness</div>
            <h2 className="display mt-1.5 text-[15px] font-semibold text-ink">
              Create a simulated incident
            </h2>
          </div>
          <button
            aria-label="Close"
            className="cursor-pointer rounded-[2px] p-1.5 text-ink-3 transition-colors hover:bg-paper-2 hover:text-ink"
            onClick={onCancel}
            type="button"
          >
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="grid gap-4 px-5 py-4 sm:grid-cols-2">
          <label className="sm:col-span-2">
            <span className={label}>Injected fault</span>
            <select
              className={`${field} cursor-pointer`}
              onChange={(event) =>
                onChange({ ...form, scenario_kind: event.target.value })
              }
              value={form.scenario_kind}
            >
              {SCENARIOS.filter((item) => item !== "all").map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </select>
            <span className="mt-1.5 block text-[11px] text-ink-3">
              The Ground Truth for this fault is written separately and is never
              reachable from the diagnosis.
            </span>
          </label>

          <label>
            <span className={label}>Seed</span>
            <input
              className={`${field} tnum font-mono`}
              onChange={(event) =>
                onChange({ ...form, seed: Number(event.target.value) })
              }
              type="number"
              value={form.seed}
            />
          </label>

          <label>
            <span className={label}>Purchase intents</span>
            <input
              className={`${field} tnum font-mono`}
              max={10000}
              min={1}
              onChange={(event) =>
                onChange({ ...form, num_intents: Number(event.target.value) })
              }
              type="number"
              value={form.num_intents}
            />
          </label>

          <label className="sm:col-span-2">
            <span className={label}>Title</span>
            <input
              className={field}
              onChange={(event) =>
                onChange({ ...form, title: event.target.value })
              }
              placeholder={`Simulated ${form.scenario_kind.replaceAll("_", " ")} incident`}
              value={form.title}
            />
          </label>
        </div>

        {isError && (
          <p className="mx-5 mb-4 rounded-[2px] bg-alarm-soft p-3 text-[12px] text-alarm">
            {onError}
          </p>
        )}

        <div className="flex justify-end gap-2 border-t border-rule px-5 py-4">
          <Button onClick={onCancel} variant="secondary">
            Cancel
          </Button>
          <Button disabled={isPending} onClick={onSubmit}>
            {isPending && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            Create and diagnose
          </Button>
        </div>
      </div>
    </div>
  );
}
