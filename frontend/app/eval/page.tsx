"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Icon } from "@/components/icons";
import {
  Button,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
} from "@/components/page-elements";
import { RunStatus } from "@/components/status-badge";
import {
  ApiError,
  apiRequest,
  jsonBody,
  type EvaluationCreate,
  type EvaluationList,
  type EvaluationRun,
  type EvaluationTrigger,
} from "@/lib/api/client";
import { formatNumber, formatPercent, humanize } from "@/lib/format";

const SCENARIOS = [
  "normal",
  "benefit_friction",
  "channel_timeout",
  "mixed_failure",
  "data_gap",
  "adversarial_irrelevant_config",
  "adversarial_noise",
];

const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "DISPATCH_FAILED"]);

type ModelMode = NonNullable<EvaluationCreate["model_mode"]>;
type Run = EvaluationRun;

/* Class names mean nothing to a reader; say what actually ran. */
const GATHERED_BY: Record<string, string> = {
  OpenAIToolCallingPolicy: "model · tool-calling",
  ScriptedInvestigationPolicy: "scripted policy",
  RuleBasedModelAdapter: "rule adapter",
  OpenAICompatibleModelAdapter: "one-shot model",
};

function gatheredBy(result: {
  agent_mode?: string | null;
  policy_name?: string | null;
  adapter_name?: string | null;
}): string {
  const name =
    result.agent_mode === "B2" && result.policy_name
      ? result.policy_name
      : result.adapter_name;
  if (!name) return "—";
  return GATHERED_BY[name] ?? name;
}

const MODES: {
  mode: ModelMode;
  name: string;
  summary: string;
  detail: string;
}[] = [
  {
    mode: "B0",
    name: "Fixed pipeline",
    summary: "Six tools, always the same order.",
    detail:
      "Deterministic rule adapter, no API key and no paid call. The baseline the investigated run is measured against.",
  },
  {
    mode: "B1",
    name: "One-shot model",
    summary: "One model call writes the report.",
    detail:
      "The same fixed pipeline, but the report is written by the configured model. Falls back to rules — the run says which happened.",
  },
  {
    mode: "B2",
    name: "Investigated",
    summary: "The harness chooses what to run.",
    detail:
      "Routed capabilities, a hypothesis ledger and a budget. Uses the model when it is reachable, the deterministic policy otherwise, and records which.",
  },
];

/**
 * Metrics as ledger rows rather than a bar chart.
 *
 * The comparison that matters is against the other evidence-gathering mode, not
 * against 100% — a bar chart of five near-1.0 values communicates nothing.
 */
const METRIC_ROWS: {
  key: keyof NonNullable<Run["metrics"]>;
  label: string;
  format: (value: number) => string;
  higherIsBetter: boolean;
  note: string;
}[] = [
  {
    key: "run_success_rate",
    label: "Runs completed",
    format: (v) => formatPercent(v),
    higherIsBetter: true,
    note: "scenarios that reached a report",
  },
  {
    key: "stage_localization_exact_rate",
    label: "Stage localized exactly",
    format: (v) => formatPercent(v),
    higherIsBetter: true,
    note: "predicted degraded stages equal Ground Truth",
  },
  {
    key: "root_cause_f1_mean",
    label: "Root cause F1",
    format: (v) => v.toFixed(3),
    higherIsBetter: true,
    note: "seven scenarios with one dedicated rule each — not a generalisation measure",
  },
  {
    key: "unsupported_claim_rate_mean",
    label: "Unsupported claims",
    format: (v) => formatPercent(v),
    higherIsBetter: false,
    note: "claims the evidence contract could not carry",
  },
  {
    key: "loss_attribution_mape",
    label: "Loss attribution error",
    format: (v) => formatPercent(v),
    higherIsBetter: false,
    note: "mean relative error against the injected fault's true impact",
  },
  {
    key: "evidence_validity_rate_mean",
    label: "Evidence valid",
    format: (v) => formatPercent(v),
    higherIsBetter: true,
    note: "cited records that exist and came from a successful call",
  },
  {
    key: "tool_call_count_mean",
    label: "Tool calls per scenario",
    format: (v) => v.toFixed(2),
    higherIsBetter: false,
    note: "the cost of gathering the evidence",
  },
  {
    key: "badcase_count",
    label: "Badcase scenarios",
    format: (v) => formatNumber(v),
    higherIsBetter: false,
    note: "scenarios with any recorded failure",
  },
];

export default function EvalPage() {
  const queryClient = useQueryClient();
  const [runId, setRunId] = useState<string | null>(null);
  const [modelMode, setModelMode] = useState<ModelMode>("B2");
  const [scenarioKinds, setScenarioKinds] = useState<string[]>(SCENARIOS);
  const [seed, setSeed] = useState(42);
  const [numIntents, setNumIntents] = useState(500);
  const [promptVersion, setPromptVersion] = useState("diagnosis_v1");

  const recentRuns = useQuery<EvaluationList, ApiError>({
    queryKey: ["evaluation-runs"],
    queryFn: () =>
      apiRequest<EvaluationList>("/api/v1/evaluation-runs?page=1&page_size=12"),
  });

  const currentRun = useQuery<Run, ApiError>({
    enabled: Boolean(runId),
    queryKey: ["evaluation-run", runId],
    queryFn: () => apiRequest<Run>(`/api/v1/evaluation-runs/${runId}`),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && TERMINAL.has(status) ? false : 1500;
    },
  });

  const submit = useMutation<EvaluationTrigger, ApiError, EvaluationCreate>({
    mutationFn: (body) =>
      apiRequest<EvaluationTrigger>("/api/v1/evaluation-runs", {
        method: "POST",
        headers: { "Idempotency-Key": `eval-${Date.now()}-${seed}` },
        body: jsonBody(body),
      }),
    onSuccess: async (response) => {
      setRunId(response.evaluation_run_id);
      await queryClient.invalidateQueries({ queryKey: ["evaluation-runs"] });
    },
  });

  const run = currentRun.data;
  const metrics = run?.metrics ?? null;
  const canSubmit = scenarioKinds.length > 0 && numIntents >= 1 && numIntents <= 10000;

  // The comparison that carries information: the same seed, the other mode.
  const counterpart =
    run && TERMINAL.has(run.status)
      ? (recentRuns.data?.items ?? []).find(
          (item) =>
            item.id !== run.id &&
            item.model_mode !== run.model_mode &&
            item.seed === run.seed &&
            item.num_intents === run.num_intents &&
            item.metrics,
        )
      : undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        description="Every scenario carries an injected fault with its Ground Truth held separately. The evaluator compares the diagnosis against it after the diagnosis has finished — the diagnosis itself never sees it."
        eyebrow="Evaluation / Lab"
        title="Eval Lab"
      />

      <div className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="space-y-6">
          <Panel eyebrow="How the evidence gets gathered" title="New evaluation">
            <fieldset>
              <legend className="eyebrow">Mode</legend>
              <div className="mt-2.5 space-y-1.5">
                {MODES.map((item) => {
                  const selected = modelMode === item.mode;
                  return (
                    <label
                      className={`block cursor-pointer rounded-[2px] border p-3 transition-colors duration-150 ${
                        selected
                          ? "border-petrol-2 bg-petrol-soft"
                          : "border-rule-2 bg-surface hover:border-ink-3"
                      }`}
                      key={item.mode}
                    >
                      <input
                        checked={selected}
                        className="sr-only"
                        name="model-mode"
                        onChange={() => setModelMode(item.mode)}
                        type="radio"
                        value={item.mode}
                      />
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-[11px] font-semibold text-ink">
                          {item.mode}
                        </span>
                        <span className="text-[12px] font-medium text-ink">
                          {item.name}
                        </span>
                        {selected && (
                          <Icon
                            className="ml-auto text-petrol-2"
                            name="check"
                            size={14}
                          />
                        )}
                      </span>
                      <span className="mt-1 block text-[11px] text-ink-2">
                        {item.summary}
                      </span>
                      {selected && (
                        <span className="mt-2 block border-t border-petrol-2/20 pt-2 text-[11px] leading-5 text-ink-2">
                          {item.detail}
                        </span>
                      )}
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <label>
                <span className="eyebrow">Seed</span>
                <input
                  className="tnum mt-2 w-full rounded-[2px] border border-rule-2 bg-surface px-3 py-2 font-mono text-[12px] outline-none transition-colors focus:border-petrol-2"
                  onChange={(event) => setSeed(Number(event.target.value))}
                  type="number"
                  value={seed}
                />
              </label>
              <label>
                <span className="eyebrow">Intents</span>
                <input
                  className="tnum mt-2 w-full rounded-[2px] border border-rule-2 bg-surface px-3 py-2 font-mono text-[12px] outline-none transition-colors focus:border-petrol-2"
                  max={10000}
                  min={1}
                  onChange={(event) => setNumIntents(Number(event.target.value))}
                  type="number"
                  value={numIntents}
                />
              </label>
            </div>
            <p className="mt-2 text-[11px] leading-5 text-ink-3">
              Loss attribution error is scale-dependent — about 10% at 500
              intents, about 4% at 5000. Quote the intent count with any figure.
            </p>

            {modelMode === "B1" && (
              <label className="mt-4 block">
                <span className="eyebrow">Prompt version</span>
                <input
                  className="mt-2 w-full rounded-[2px] border border-rule-2 bg-surface px-3 py-2 font-mono text-[12px] outline-none transition-colors focus:border-petrol-2"
                  onChange={(event) => setPromptVersion(event.target.value)}
                  value={promptVersion}
                />
              </label>
            )}

            <div className="mt-5">
              <div className="flex items-baseline justify-between">
                <span className="eyebrow">Scenario set</span>
                <button
                  className="cursor-pointer font-mono text-[10px] text-petrol-2 underline underline-offset-2"
                  onClick={() =>
                    setScenarioKinds(
                      scenarioKinds.length === SCENARIOS.length ? [] : SCENARIOS,
                    )
                  }
                  type="button"
                >
                  {scenarioKinds.length === SCENARIOS.length
                    ? "clear all"
                    : "select all"}
                </button>
              </div>
              <div className="mt-2 space-y-px">
                {SCENARIOS.map((scenario) => {
                  const checked = scenarioKinds.includes(scenario);
                  return (
                    <label
                      className={`flex cursor-pointer items-center gap-2.5 py-1.5 text-[12px] transition-colors ${
                        checked ? "text-ink" : "text-ink-3 hover:text-ink-2"
                      }`}
                      key={scenario}
                    >
                      <input
                        checked={checked}
                        className="accent-petrol"
                        onChange={() =>
                          setScenarioKinds((current) =>
                            current.includes(scenario)
                              ? current.filter((item) => item !== scenario)
                              : [...current, scenario],
                          )
                        }
                        type="checkbox"
                      />
                      {humanize(scenario)}
                    </label>
                  );
                })}
              </div>
            </div>

            <div className="mt-6 border-t border-rule pt-4">
              <Button
                disabled={!canSubmit || submit.isPending}
                onClick={() =>
                  submit.mutate({
                    model_mode: modelMode,
                    prompt_version: modelMode === "B1" ? promptVersion || null : null,
                    scenario_kinds: scenarioKinds,
                    seed,
                    num_intents: numIntents,
                  })
                }
              >
                {submit.isPending && (
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                )}
                Run {modelMode} evaluation
              </Button>
            </div>
            {submit.isError && (
              <p className="mt-3 rounded-[2px] bg-alarm-soft p-3 text-[11px] text-alarm">
                {submit.error.detail}
              </p>
            )}
          </Panel>

          <Panel eyebrow="Recent" title="Evaluation history">
            {recentRuns.isLoading ? (
              <LoadingState label="Loading runs" />
            ) : (recentRuns.data?.items.length ?? 0) === 0 ? (
              <p className="text-[12px] text-ink-3">No evaluations have run yet.</p>
            ) : (
              <ul className="divide-y divide-rule">
                {recentRuns.data?.items.map((item) => (
                  <li key={item.id}>
                    <button
                      aria-label={`Open the ${item.model_mode} evaluation at seed ${item.seed}`}
                      className={`flex w-full cursor-pointer items-center gap-2.5 py-2 text-left transition-colors hover:bg-paper-2/60 ${
                        item.id === runId ? "text-ink" : "text-ink-2"
                      }`}
                      onClick={() => setRunId(item.id)}
                      type="button"
                    >
                      <span className="font-mono text-[11px] font-semibold text-ink">
                        {item.model_mode}
                      </span>
                      <span className="tnum font-mono text-[11px] text-ink-3">
                        seed {item.seed}
                      </span>
                      <span className="tnum font-mono text-[11px] text-ink-3">
                        {item.num_intents}
                      </span>
                      <span className="ml-auto">
                        <RunStatus status={item.status} />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <div className="space-y-6">
          {!run ? (
            <div className="flex min-h-[320px] flex-col items-center justify-center rounded-[2px] border border-dashed border-rule-2 bg-surface px-8 text-center">
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-rule text-ink-3">
                <Icon name="beaker" size={16} />
              </span>
              <h2 className="display mt-4 text-[14px] font-semibold text-ink">
                No evaluation selected
              </h2>
              <p className="mt-1.5 max-w-md text-[12px] leading-5 text-ink-3">
                Run one, or pick a previous run from the history. Comparing B0
                against B2 with the same seed is the interesting comparison —
                same conclusions, different cost.
              </p>
            </div>
          ) : (
            <>
              <Panel
                action={
                  <span className="tnum font-mono text-[11px] text-ink-3">
                    {run.scenario_count} scenarios · seed {run.seed} ·{" "}
                    {formatNumber(run.num_intents)} intents
                  </span>
                }
                eyebrow={
                  run.status === "SUCCEEDED"
                    ? "Completed"
                    : "Running — results appear as they land"
                }
                title={`${run.model_mode} · ${MODES.find((m) => m.mode === run.model_mode)?.name ?? ""}`}
              >
                {!TERMINAL.has(run.status) ? (
                  <LoadingState label={`Evaluation ${run.status.toLowerCase()}`} />
                ) : run.status === "FAILED" ? (
                  <ErrorState message={run.error_message ?? "The run failed."} />
                ) : (
                  <>
                    {run.model_name && (
                      <p className="mb-4 flex flex-wrap items-center gap-2 border-b border-rule pb-3 font-mono text-[11px] text-ink-3">
                        <span className="eyebrow">Model requested</span>
                        {run.model_name}
                        {metrics && (
                          <>
                            <span className="h-3 w-px bg-rule-2" />
                            <span className="eyebrow">Verified calls</span>
                            <span className="tnum text-ink-2">
                              {metrics.model_invocation_count}
                            </span>
                            <span className="eyebrow">Fallbacks</span>
                            <span className="tnum text-ink-2">
                              {metrics.fallback_count}
                            </span>
                          </>
                        )}
                      </p>
                    )}
                    {metrics && <MetricTable counterpart={counterpart} run={run} />}
                  </>
                )}
              </Panel>

              {run.scenario_results && (
                <Panel eyebrow="Prediction against Ground Truth" title="Per scenario">
                  <ScenarioTable run={run} />
                </Panel>
              )}

              {run.badcases && run.badcases.length > 0 && (
                <Panel eyebrow="Every failure the scorer recorded" title="Badcases">
                  <ul className="divide-y divide-rule">
                    {run.badcases.map((entry, index) => {
                      const badcase = entry as {
                        scenario_kind?: string;
                        categories?: string[];
                        summary?: string;
                      };
                      return (
                        <li className="py-2.5" key={`${badcase.scenario_kind}-${index}`}>
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-mono text-[11px] text-ink">
                              {badcase.scenario_kind ?? "unknown"}
                            </span>
                            {(badcase.categories ?? []).map((category) => (
                              <span
                                className="rounded-[2px] border border-partial/35 bg-partial-soft px-1.5 py-0.5 font-mono text-[10px] text-partial"
                                key={category}
                              >
                                {category}
                              </span>
                            ))}
                          </div>
                          {badcase.summary && (
                            <p className="mt-1 text-[11px] text-ink-3">
                              {badcase.summary}
                            </p>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </Panel>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricTable({ run, counterpart }: { run: Run; counterpart?: EvaluationList["items"][number] }) {
  const metrics = run.metrics!;
  const other = counterpart?.metrics ?? null;

  return (
    <div>
      <div className="grid grid-cols-[minmax(150px,1.4fr)_72px_72px_72px] items-center gap-x-4 border-b border-rule pb-2 sm:grid-cols-[minmax(180px,1.6fr)_80px_80px_80px]">
        <span className="eyebrow">Metric</span>
        <span className="eyebrow text-right">{run.model_mode}</span>
        <span className="eyebrow text-right">
          {counterpart ? counterpart.model_mode : "—"}
        </span>
        <span className="eyebrow text-right">Δ</span>
      </div>

      <div className="divide-y divide-rule">
        {METRIC_ROWS.map((row) => {
          const value = metrics[row.key] as number | null | undefined;
          const otherValue = other ? (other[row.key] as number | null | undefined) : null;
          const delta =
            value != null && otherValue != null ? value - otherValue : null;
          const better =
            delta != null && Math.abs(delta) > 1e-9
              ? row.higherIsBetter
                ? delta > 0
                : delta < 0
              : null;

          return (
            <div
              className="grid grid-cols-[minmax(150px,1.4fr)_72px_72px_72px] items-baseline gap-x-4 py-2.5 sm:grid-cols-[minmax(180px,1.6fr)_80px_80px_80px]"
              key={String(row.key)}
            >
              <span className="min-w-0">
                <span className="block text-[12px] text-ink">{row.label}</span>
                <span className="mt-0.5 block text-[10px] leading-4 text-ink-3">
                  {row.note}
                </span>
              </span>
              <span className="tnum text-right font-mono text-[12px] font-semibold text-ink">
                {value == null ? "—" : row.format(value)}
              </span>
              <span className="tnum text-right font-mono text-[12px] text-ink-3">
                {otherValue == null ? "—" : row.format(otherValue)}
              </span>
              <span
                className={`tnum text-right font-mono text-[11px] ${
                  better === true
                    ? "text-settled"
                    : better === false
                      ? "text-partial"
                      : "text-ink-3"
                }`}
              >
                {delta == null
                  ? "—"
                  : `${delta > 0 ? "+" : "−"}${row.format(Math.abs(delta))}`}
              </span>
            </div>
          );
        })}
      </div>

      {!counterpart && (
        <p className="mt-3 border-t border-rule pt-3 text-[11px] leading-5 text-ink-3">
          Run the same seed in another mode and its column will fill in here —
          that comparison is the one worth showing, not the absolute values.
        </p>
      )}
    </div>
  );
}

function ScenarioTable({ run }: { run: Run }) {
  const results = run.scenario_results ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[820px] text-left">
        <thead>
          <tr className="border-b border-rule">
            <th className="eyebrow py-2 font-semibold">Scenario</th>
            <th className="eyebrow py-2 font-semibold">Status</th>
            <th className="eyebrow py-2 font-semibold">Evidence gathered by</th>
            <th className="eyebrow py-2 text-right font-semibold">Calls</th>
            <th className="eyebrow py-2 text-right font-semibold">Stage</th>
            <th className="eyebrow py-2 text-right font-semibold">F1</th>
            <th className="eyebrow py-2 text-right font-semibold">Loss err.</th>
            <th className="eyebrow py-2 font-semibold">Badcases</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {results.map((result) => (
            <tr key={result.scenario_id}>
              <td className="py-2.5">
                <span className="text-[12px] text-ink">
                  {humanize(result.scenario_kind)}
                </span>
              </td>
              <td className="py-2.5">
                <RunStatus status={result.diagnosis_status} />
              </td>
              <td className="py-2.5">
                {/* B2's report is written by the rule adapter even when the
                    investigation used a model, so show which policy ran. */}
                <span className="text-[11px] text-ink-2">
                  {gatheredBy(result)}
                </span>
                {result.fallback_used && (
                  <span className="mt-0.5 block font-mono text-[10px] text-partial">
                    {result.fallback_reason ?? "FALLBACK"}
                  </span>
                )}
              </td>
              <td className="tnum py-2.5 text-right font-mono text-[11px] text-ink-2">
                {result.tool_call_count ?? "—"}
              </td>
              <td className="py-2.5 text-right">
                <StageMark value={result.stage_exact} />
              </td>
              <td className="tnum py-2.5 text-right font-mono text-[11px] text-ink-2">
                {result.root_cause_f1?.toFixed(2) ?? "—"}
              </td>
              <td className="tnum py-2.5 text-right font-mono text-[11px] text-ink-2">
                {result.loss_attribution_rel_error == null
                  ? "—"
                  : formatPercent(result.loss_attribution_rel_error)}
              </td>
              <td className="py-2.5">
                {(result.badcases ?? []).length === 0 ? (
                  <span className="text-[11px] text-ink-3">none</span>
                ) : (
                  <span className="font-mono text-[10px] text-partial">
                    {(result.badcases ?? []).join(", ")}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StageMark({ value }: { value: boolean | null | undefined }) {
  if (value == null) return <span className="text-[11px] text-ink-3">—</span>;
  return (
    <span
      className={`font-mono text-[11px] ${value ? "text-settled" : "text-partial"}`}
      title={value ? "Predicted stages match Ground Truth" : "Stage prediction differs from Ground Truth"}
    >
      {value ? "match" : "differ"}
    </span>
  );
}
