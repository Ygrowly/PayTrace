"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/icons";

const links = [
  { href: "/", label: "Overview", icon: "grid" as const },
  { href: "/incidents", label: "Incidents", icon: "activity" as const },
  { href: "/eval", label: "Eval Lab", icon: "beaker" as const },
];

/** The funnel, read as three rules of decreasing length. */
function Mark() {
  return (
    <span className="flex h-8 w-8 shrink-0 flex-col justify-center gap-[3px] rounded-sm bg-petrol px-[7px]">
      <span className="h-[2px] w-full rounded-full bg-white/95" />
      <span className="h-[2px] w-[72%] rounded-full bg-white/70" />
      <span className="h-[2px] w-[42%] rounded-full bg-white/45" />
    </span>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-paper text-ink">
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-rule bg-paper-2 lg:flex">
        <div className="flex h-[68px] items-center gap-3 border-b border-rule px-5">
          <Mark />
          <div className="min-w-0">
            <div className="display text-[15px] font-semibold leading-none text-ink">
              PayTrace
            </div>
            <div className="eyebrow mt-1">conversion forensics</div>
          </div>
        </div>

        <nav aria-label="Primary" className="flex-1 px-3 py-5">
          <div className="eyebrow mb-3 px-2">Workspace</div>
          <ul className="space-y-px">
            {links.map((link) => {
              const active =
                link.href === "/" ? pathname === "/" : pathname.startsWith(link.href);
              return (
                <li key={link.href}>
                  <Link
                    aria-current={active ? "page" : undefined}
                    className={`group flex items-center gap-2.5 border-l-2 py-2 pr-2 pl-2.5 text-[13px] transition-colors duration-150 ${
                      active
                        ? "border-petrol bg-surface font-semibold text-ink"
                        : "border-transparent text-ink-2 hover:border-rule-2 hover:bg-surface/70 hover:text-ink"
                    }`}
                    href={link.href}
                  >
                    <Icon name={link.icon} size={15} />
                    <span>{link.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="border-t border-rule px-5 py-4">
          <div className="eyebrow">How it decides</div>
          <p className="mt-2 text-[11px] leading-[1.6] text-ink-3">
            Every claim cites evidence the system computed. A claim the evidence
            cannot carry is published as{" "}
            <span className="font-semibold text-ink-2">unknown</span> — never
            asserted.
          </p>
        </div>
      </aside>

      <div className="lg:pl-60">
        <header className="sticky top-0 z-10 flex h-[68px] items-center justify-between gap-4 border-b border-rule bg-paper/85 px-5 backdrop-blur lg:px-8">
          <Link className="flex items-center gap-2.5 lg:hidden" href="/">
            <Mark />
            <span className="display font-semibold">PayTrace</span>
          </Link>
          <p className="hidden items-center gap-2.5 text-[12px] text-ink-2 lg:flex">
            <span className="eyebrow">Synthetic data</span>
            <span className="h-3 w-px bg-rule-2" />
            <span>
              Injected faults with isolated Ground Truth. No live payment
              traffic, no card data.
            </span>
          </p>
          <div className="flex items-center gap-2 text-[11px] text-ink-3">
            <span className="h-1.5 w-1.5 rounded-full bg-settled" />
            <span className="eyebrow">Local workspace</span>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1400px] px-5 py-7 lg:px-8 lg:py-9">
          {children}
        </main>
      </div>
    </div>
  );
}
