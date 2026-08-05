"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/icons";

const links = [
  { href: "/", label: "Overview", icon: "grid" as const },
  { href: "/incidents", label: "Incidents", icon: "activity" as const },
  { href: "/eval", label: "Eval Lab", icon: "beaker" as const },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  return (
    <div className="min-h-screen bg-[#f8fafc] text-slate-950">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-800 text-white shadow-sm">
            <Icon name="activity" size={20} strokeWidth={2.2} />
          </div>
          <div>
            <div className="font-semibold tracking-tight text-slate-950">PayTrace</div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-400">diagnostic workbench</div>
          </div>
        </div>
        <nav aria-label="Primary navigation" className="flex-1 space-y-1 px-3 py-6">
          <div className="mb-3 px-3 font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Workspace</div>
          {links.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
            return (
              <Link
                className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors duration-200 ${
                  active ? "bg-blue-50 font-semibold text-blue-800" : "text-slate-600 hover:bg-slate-50 hover:text-slate-950"
                }`}
                href={link.href}
                key={link.href}
              >
                <Icon name={link.icon} size={17} />
                <span>{link.label}</span>
                {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-amber-500" />}
              </Link>
            );
          })}
        </nav>
        <div className="m-4 rounded-xl border border-blue-100 bg-blue-50/70 p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-900"><Icon name="shield" size={15} /> Deterministic mode</div>
          <p className="mt-2 text-xs leading-5 text-blue-800/75">B0 rule-based workflow is enabled for local evaluation.</p>
        </div>
      </aside>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200/80 bg-white/90 px-5 backdrop-blur lg:px-8">
          <div className="flex items-center gap-2 lg:hidden"><Icon name="activity" size={18} /><span className="font-semibold">PayTrace</span></div>
          <div className="hidden font-mono text-[11px] uppercase tracking-[0.16em] text-slate-400 lg:block">Payment conversion intelligence</div>
          <div className="flex items-center gap-2 text-xs text-slate-500"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Local workspace</div>
        </header>
        <main className="mx-auto w-full max-w-[1480px] px-5 py-7 lg:px-8 lg:py-9">{children}</main>
      </div>
    </div>
  );
}

