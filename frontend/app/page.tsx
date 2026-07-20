export default function Home() {
  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="text-3xl font-semibold tracking-tight">PayTrace</h1>
      <p className="mt-2 text-sm text-neutral-700 dark:text-neutral-300">
        Payment conversion anomaly attribution and diagnosis agent.
      </p>
      <section className="mt-8 rounded-md border border-neutral-200 p-6 dark:border-neutral-800">
        <h2 className="text-lg font-medium">M0a skeleton</h2>
        <p className="mt-2 text-sm">
          Only the monorepo skeleton is in place. FastAPI health endpoint,
          Alembic migrations, OpenAPI type generation, and Incident / Eval UI
          arrive in subsequent milestones.
        </p>
        <ul className="mt-4 list-disc space-y-1 pl-6 text-sm">
          <li>
            <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-900">
              make infra-up
            </code>{" "}
            starts PostgreSQL, Redis, MinIO.
          </li>
          <li>
            <code className="rounded bg-neutral-100 px-1 dark:bg-neutral-900">
              cd backend &amp;&amp; uv sync
            </code>{" "}
            installs the backend skeleton package.
          </li>
          <li>
            Incident list (<code>/incidents</code>) and Eval Lab (
            <code>/eval</code>) routes are empty placeholders for now.
          </li>
        </ul>
      </section>
    </main>
  );
}
