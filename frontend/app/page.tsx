import Link from "next/link";
import type { components } from "@/lib/api/schema";
import { Icon } from "@/components/icons";

type ReadinessResponse = components["schemas"]["ReadinessResponse"];

export default async function Home() {
  const apiBase = process.env.PAYTRACE_API_BASE ?? "http://localhost:8000";
  let payload: ReadinessResponse | null = null;
  let error: string | null = null;

  try {
    const res = await fetch(`${apiBase}/api/v1/health/ready`, { cache: "no-store" });
    payload = (await res.json()) as ReadinessResponse;
    if (!res.ok) error = `HTTP ${res.status}`;
  } catch (err) {
    error = err instanceof Error ? err.message : "Unknown fetch error";
  }

  return (
    <div className="space-y-8">
      <section className="grid gap-6 overflow-hidden rounded-2xl bg-blue-900 px-6 py-8 text-white shadow-sm lg:grid-cols-[1.3fr_0.7fr] lg:px-10 lg:py-10">
        <div>
          <div className="mb-4 flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-200"><span className="h-2 w-2 rounded-full bg-amber-400" /> Payment conversion intelligence</div>
          <h1 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">Find the stage where payment conversion changes.</h1>
          <p className="mt-4 max-w-xl text-sm leading-6 text-blue-100">PayTrace turns deterministic funnel evidence into traceable incident diagnoses and repeatable evaluation runs.</p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link className="inline-flex cursor-pointer items-center gap-2 rounded-lg bg-amber-400 px-4 py-2.5 text-sm font-semibold text-blue-950 transition-colors duration-200 hover:bg-amber-300 focus:outline-none focus:ring-2 focus:ring-amber-300 focus:ring-offset-2 focus:ring-offset-blue-900" href="/incidents">Open incidents <Icon name="arrow-right" size={16} /></Link>
            <Link className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-blue-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors duration-200 hover:bg-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-300" href="/eval">Run an evaluation</Link>
          </div>
        </div>
        <div className="relative flex items-end justify-end">
          <div className="w-full max-w-xs rounded-xl border border-blue-700 bg-blue-800/70 p-5">
            <div className="flex items-center justify-between text-xs text-blue-200"><span>Workflow health</span><span className="font-mono">B0 / local</span></div>
            <div className="mt-5 flex items-end gap-1.5" aria-hidden="true">{[32, 48, 42, 68, 56, 78, 64, 88, 76, 92].map((height, index) => <span className={`w-full rounded-t-sm ${index > 6 ? "bg-amber-400" : "bg-blue-400"}`} key={`${height}-${index}`} style={{ height: `${height}px` }} />)}</div>
            <div className="mt-3 flex justify-between font-mono text-[10px] text-blue-200"><span>baseline</span><span>incident</span></div>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Link className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md" href="/incidents">
          <div className="flex items-start justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-800"><Icon name="activity" size={18} /></span><Icon name="arrow-right" size={17} /></div>
          <h2 className="mt-5 font-semibold">Incident workspace</h2><p className="mt-2 text-sm leading-5 text-slate-500">Filter detected incidents, create a deterministic scenario, and open a traceable diagnosis.</p>
        </Link>
        <Link className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md" href="/eval">
          <div className="flex items-start justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-50 text-amber-700"><Icon name="beaker" size={18} /></span><Icon name="arrow-right" size={17} /></div>
          <h2 className="mt-5 font-semibold">Eval Lab</h2><p className="mt-2 text-sm leading-5 text-slate-500">Run B0 against hidden Ground Truth and inspect real metrics, predictions, and badcases.</p>
        </Link>
        <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-50 text-emerald-700"><Icon name="shield" size={18} /></span><span className="font-mono text-[10px] uppercase tracking-[0.12em] text-slate-400">runtime</span></div>
          <h2 className="mt-5 font-semibold">Dependency readiness</h2>
          {payload ? <div className="mt-3 space-y-2">{Object.entries(payload.dependencies).map(([name, dependency]) => <div className="flex items-center justify-between text-xs" key={name}><span className="text-slate-500">{name}</span><span className={dependency.status === "ok" ? "text-emerald-700" : "text-red-700"}>{dependency.status}{dependency.latency_ms != null ? ` · ${dependency.latency_ms}ms` : ""}</span></div>)}</div> : <p className="mt-3 text-sm text-red-700">Backend unavailable: {error}</p>}
        </section>
      </section>
    </div>
  );
}
