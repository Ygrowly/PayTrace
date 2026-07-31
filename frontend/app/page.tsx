import type { components } from "@/lib/api/schema";

type LivenessResponse = components["schemas"]["LivenessResponse"];

/**
 * M0b homepage: performs a server-side fetch against the FastAPI
 * `/api/v1/health/live` endpoint and renders the JSON payload.
 *
 * Falls back to an explicit error block when the backend is unreachable so
 * the page never pretends to be healthy. Real Incident / Eval UI arrives
 * in M3.
 */
export default async function Home() {
  const apiBase = process.env.PAYTRACE_API_BASE ?? "http://localhost:8000";

  let payload: LivenessResponse | null = null;
  let error: string | null = null;

  try {
    const res = await fetch(`${apiBase}/api/v1/health/live`, {
      // Always revalidate — this is a liveness probe, caching would defeat it.
      cache: "no-store",
    });
    if (!res.ok) {
      error = `HTTP ${res.status}`;
    } else {
      payload = (await res.json()) as LivenessResponse;
    }
  } catch (err) {
    error = err instanceof Error ? err.message : "Unknown fetch error";
  }

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold tracking-tight">PayTrace</h1>
      <p className="mt-2 text-sm text-neutral-700 dark:text-neutral-300">
        Payment conversion anomaly attribution and diagnosis agent.
      </p>
      <section className="mt-8 rounded-md border border-neutral-200 p-6 dark:border-neutral-800">
        <h2 className="text-lg font-medium">Backend liveness</h2>
        <p className="mt-1 text-xs text-neutral-500">
          GET <code>{apiBase}/api/v1/health/live</code>
        </p>
        {payload ? (
          <pre className="mt-4 overflow-auto rounded bg-neutral-50 p-4 text-xs dark:bg-neutral-900">
            {JSON.stringify(payload, null, 2)}
          </pre>
        ) : (
          <div className="mt-4 rounded bg-red-50 p-4 text-xs text-red-800 dark:bg-red-950 dark:text-red-200">
            backend unreachable: {error}
          </div>
        )}
        <p className="mt-6 text-xs text-neutral-500">
          Incident list (<code>/incidents</code>) and Eval Lab (<code>/eval</code>) routes are
          placeholders until M3.
        </p>
      </section>
    </main>
  );
}
