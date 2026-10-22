import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { SupportStatus } from "@/components/status-badge";
import { Panel } from "@/components/page-elements";
import { apiUrl } from "@/lib/api/client";

type Readiness = components["schemas"]["ReadinessResponse"];
type IncidentList = components["schemas"]["IncidentListResponse"];
type Report = components["schemas"]["ReportResponse"];

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    // Same resolver the client uses, so the server and browser halves cannot
    // disagree about which host the API is on.
    const response = await fetch(apiUrl(path), { cache: "no-store" });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

/** The latest diagnosis, so the front page shows a real one rather than a mock. */
async function latestDiagnosis(): Promise<{
  incidentId: string;
  title: string;
  scenario: string;
  report: Report;
} | null> {
  const list = await fetchJson<IncidentList>("/api/v1/incidents?page=1&page_size=10");
  const incidents = list?.items ?? [];

  for (const incident of incidents) {
    if (!incident.latest_diagnosis_run_id) continue;
    const report = await fetchJson<Report>(
      `/api/v1/diagnosis-runs/${incident.latest_diagnosis_run_id}/report`,
    );
    if (report && report.status === "SUCCEEDED" && report.root_causes.length > 0) {
      return {
        incidentId: incident.id,
        title: incident.title,
        scenario: incident.scenario_id,
        report,
      };
    }
  }
  return null;
}

const REFUSALS = [
  {
    title: "Invent a cause",
    body: "Every claim cites evidence the system computed. A claim the evidence cannot carry is republished as unknown, and its loss moves to the unattributed line.",
  },
  {
    title: "Explain more than it lost",
    body: "Attribution is charged to the transition the intents failed, so an intent that dropped out early is never counted again further down the funnel.",
  },
  {
    title: "Re-open a settled explanation",
    body: "A hypothesis its own evidence rejected is not investigated again unless a different tool would ask a genuinely different question.",
  },
  {
    title: "Call a fallback a model run",
    body: "When the configured model is unreachable the deterministic policy runs, and the run records that — never as a successful model investigation.",
  },
];

const STEPS = [
  {
    label: "Detect",
    body: "The nine-stage funnel and its step rates are computed from the incident's own dataset, against the baseline window.",
  },
  {
    label: "Account",
    body: "Loss is charged per transition. Only intents that would have completed without the fault count as lost.",
  },
  {
    label: "Investigate",
    body: "Signals route a restricted tool set. The harness raises hypotheses and tests them under a budget and a hook chain.",
  },
  {
    label: "Constrain",
    body: "Every claim is checked against the evidence contract before it can be published, and its support status is set by the evidence, not by the model.",
  },
];

export default async function Overview() {
  const [readiness, diagnosis] = await Promise.all([
    fetchJson<Readiness>("/api/v1/health/ready"),
    latestDiagnosis(),
  ]);

  return (
    <div className="space-y-6">
      <section className="border-b border-rule-2 pb-8">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:gap-14">
          <div className="max-w-xl">
            <p className="eyebrow">Evidence-driven diagnosis</p>
            <h1 className="display mt-3 text-[34px] leading-[1.1] font-semibold text-ink">
              Payment conversion drops.
              <br />
              This says exactly how much,
              <br />
              and what it cannot explain.
            </h1>
            <p className="mt-5 text-[13px] leading-6 text-ink-2">
              PayTrace computes the loss with deterministic code, investigates
              the cause with a governed agent, and refuses to publish a claim
              its evidence cannot carry.
            </p>
            <div className="mt-7 flex flex-wrap gap-2">
              <Link
                className="inline-flex items-center gap-2 rounded-[2px] bg-petrol px-3.5 py-2 text-[12px] font-semibold text-white transition-colors hover:bg-petrol-2"
                href="/incidents"
              >
                Open incidents
              </Link>
              <Link
                className="inline-flex items-center gap-2 rounded-[2px] border border-rule-2 px-3.5 py-2 text-[12px] font-semibold text-ink transition-colors hover:border-ink-3"
                href="/eval"
              >
                Compare evaluation modes
              </Link>
            </div>
          </div>

          {diagnosis ? (
            <div className="rounded-[2px] border border-rule bg-surface">
              <div className="flex items-baseline justify-between gap-3 border-b border-rule px-5 py-3">
                <span className="eyebrow">Latest diagnosis</span>
                <span className="font-mono text-[10px] text-ink-3">
                  {diagnosis.scenario}
                </span>
              </div>
              <div className="px-5 py-4">
                <p className="tnum font-mono text-[38px] leading-none font-semibold text-ink">
                  {diagnosis.report.total_estimated_lost_intents}
                </p>
                <p className="mt-2 text-[12px] text-ink-3">
                  purchase intents lost, and who can account for them
                </p>

                <ul className="mt-4 border-t border-rule">
                  {diagnosis.report.root_causes.map((cause) => (
                    <li
                      className="flex items-center gap-3 border-b border-rule py-2.5"
                      key={cause.label}
                    >
                      <span className="min-w-0 flex-1 truncate text-[12px] text-ink">
                        {cause.label.replaceAll("_", " ")}
                      </span>
                      <span className="tnum shrink-0 font-mono text-[12px] font-semibold text-ink">
                        {cause.estimated_lost_intents ?? "—"}
                      </span>
                      <span className="shrink-0">
                        <SupportStatus status={cause.support_status} />
                      </span>
                    </li>
                  ))}
                  <li className="flex items-center gap-3 py-2.5">
                    <span className="flex-1 text-[12px] text-ink-2">
                      Not attributed
                    </span>
                    <span className="tnum font-mono text-[12px] text-ink-2">
                      {diagnosis.report.unexplained_lost_intents}
                    </span>
                    <span className="w-[74px]" />
                  </li>
                </ul>

                <Link
                  className="mt-4 inline-flex items-center gap-1.5 font-mono text-[10px] text-petrol-2 underline underline-offset-2"
                  href={`/incidents/${diagnosis.incidentId}`}
                >
                  open the full trace
                </Link>
              </div>
            </div>
          ) : (
            <div className="flex items-center rounded-[2px] border border-dashed border-rule-2 bg-surface px-5 py-6 text-[12px] leading-5 text-ink-3">
              No completed diagnosis yet. Create a simulated incident and run it
              — this panel shows the newest one, unedited.
            </div>
          )}
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Panel
          eyebrow="Each step is a separate guarantee, not a stage of one blob"
          title="How a diagnosis is reached"
        >
          <ol className="divide-y divide-rule">
            {STEPS.map((step, index) => (
              <li className="flex gap-4 py-3.5 first:pt-0 last:pb-0" key={step.label}>
                <span className="tnum mt-px font-mono text-[11px] font-semibold text-petrol-2">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <h3 className="text-[13px] font-semibold text-ink">
                    {step.label}
                  </h3>
                  <p className="mt-1 text-[12px] leading-5 text-ink-2">
                    {step.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>

        <div className="space-y-6">
          <Panel eyebrow="Stated as behaviour, verifiable in the trace" title="What it refuses to do">
            <ul className="divide-y divide-rule">
              {REFUSALS.map((item) => (
                <li className="py-3 first:pt-0 last:pb-0" key={item.title}>
                  <h3 className="text-[13px] font-semibold text-ink">
                    {item.title}
                  </h3>
                  <p className="mt-1 text-[12px] leading-5 text-ink-2">
                    {item.body}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel eyebrow="This workspace" title="Runtime">
            {readiness ? (
              <ul className="divide-y divide-rule">
                {Object.entries(readiness.dependencies).map(([name, dep]) => (
                  <li className="py-2.5" key={name}>
                    <div className="flex items-center gap-3">
                      <span
                        aria-hidden
                        className={`h-1.5 w-1.5 rounded-full ${
                          dep.status === "ok" ? "bg-settled" : "bg-alarm"
                        }`}
                      />
                      <span className="flex-1 font-mono text-[11px] text-ink-2">
                        {name}
                      </span>
                      {/* The word, not only the dot: colour alone does not
                          convey status to everyone reading this. */}
                      <span
                        className={`font-mono text-[11px] ${
                          dep.status === "ok" ? "text-settled" : "text-alarm"
                        }`}
                      >
                        {dep.status}
                      </span>
                      <span className="tnum w-16 text-right font-mono text-[11px] text-ink-3">
                        {dep.latency_ms != null ? `${dep.latency_ms} ms` : "—"}
                      </span>
                    </div>
                    {dep.detail && dep.status !== "ok" && (
                      <p className="mt-1 pl-[18px] text-[11px] leading-5 text-alarm">
                        {dep.detail}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[12px] leading-5 text-alarm">
                The backend did not answer. Start it with{" "}
                <code className="font-mono">make run-api</code> — this page will
                not show invented dependency state.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
