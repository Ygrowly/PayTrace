import { Icon } from "@/components/icons";

export function PageHeader({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="flex flex-col gap-5 border-b border-slate-200 pb-7 md:flex-row md:items-end md:justify-between"><div><div className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-blue-700">{eyebrow}</div><h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">{title}</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">{description}</p></div>{action && <div className="shrink-0">{action}</div>}</div>;
}

export function LoadingState({ label = "Loading workspace data" }: { label?: string }) {
  return <div aria-live="polite" className="flex min-h-40 items-center justify-center rounded-xl border border-slate-200 bg-white text-sm text-slate-500"><span className="mr-3 h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-700" />{label}</div>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div aria-live="assertive" className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><Icon name="triangle" size={18} /><div className="flex-1"><p className="font-semibold">Unable to load this view</p><p className="mt-1 text-red-700/80">{message}</p></div>{onRetry && <button className="cursor-pointer rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-semibold transition-colors duration-200 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-300" onClick={onRetry} type="button">Retry</button>}</div>;
}

export function EmptyState({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return <div className="flex min-h-56 flex-col items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white px-6 text-center"><div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-500"><Icon name="search" size={18} /></div><h2 className="mt-4 font-semibold text-slate-900">{title}</h2><p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>{action && <div className="mt-5">{action}</div>}</div>;
}

export function KpiCard({ label, value, detail, tone = "blue" }: { label: string; value: string; detail?: string; tone?: "blue" | "amber" | "red" | "green" }) {
  const tones = { blue: "bg-blue-50 text-blue-800", amber: "bg-amber-50 text-amber-800", red: "bg-red-50 text-red-800", green: "bg-emerald-50 text-emerald-800" };
  return <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"><div className="flex items-center justify-between"><span className="font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</span><span className={`h-2 w-2 rounded-full ${tones[tone].split(" ")[0]}`} /></div><div className="mt-3 text-2xl font-semibold tracking-tight text-slate-950">{value}</div>{detail && <div className="mt-1 text-xs text-slate-500">{detail}</div>}</div>;
}

export function SectionCard({ title, eyebrow, children, className = "" }: { title: string; eyebrow?: string; children: React.ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:p-6 ${className}`}><div className="mb-5 flex items-start justify-between gap-4"><div><h2 className="font-semibold text-slate-950">{title}</h2>{eyebrow && <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">{eyebrow}</p>}</div></div>{children}</section>;
}

