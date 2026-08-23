const styles: Record<string, string> = {
  DETECTED: "border-amber-200 bg-amber-50 text-amber-800",
  INVESTIGATING: "border-blue-200 bg-blue-50 text-blue-800",
  ACTION_REQUIRED: "border-orange-200 bg-orange-50 text-orange-800",
  RESOLVED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  PENDING: "border-slate-200 bg-slate-50 text-slate-600",
  QUEUED: "border-blue-200 bg-blue-50 text-blue-800",
  RUNNING: "border-blue-200 bg-blue-50 text-blue-800",
  COLLECTING_EVIDENCE: "border-indigo-200 bg-indigo-50 text-indigo-800",
  GENERATING_REPORT: "border-indigo-200 bg-indigo-50 text-indigo-800",
  VALIDATING: "border-violet-200 bg-violet-50 text-violet-800",
  SUCCEEDED: "border-emerald-200 bg-emerald-50 text-emerald-800",
  NEEDS_DATA: "border-amber-200 bg-amber-50 text-amber-800",
  FAILED: "border-red-200 bg-red-50 text-red-800",
  DISPATCH_FAILED: "border-red-200 bg-red-50 text-red-800",
  CANCELLED: "border-slate-200 bg-slate-100 text-slate-600",
};

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const value = status || "UNKNOWN";
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] ${styles[value] ?? "border-slate-200 bg-slate-50 text-slate-600"}`}>{value.replaceAll("_", " ")}</span>;
}

