"use client";

/**
 * The ward terminal.
 *
 * Its own shell, like reception and intake: the IPD incharge runs one screen
 * all shift and has no business browsing consultations or hospital revenue.
 *
 * The census sits in the header rather than on a separate page, because "how
 * many beds are free" is asked constantly — by the OPD desk, by casualty, by
 * the family in the corridor — and it should never cost a click.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BedDouble, FlaskConical, LogOut, RefreshCw, Scissors, UtensilsCrossed } from "lucide-react";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Logo } from "@/components/brand/logo";
import { PlatformMark } from "@/components/brand/platform-mark";
import { staffApi } from "@/lib/staffApi";
import type { Census } from "@/lib/types/ipd";
import { cn } from "@/lib/utils";

const CENSUS_REFRESH_MS = 30000;

function Figure({
  label, value, tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "warn";
}) {
  return (
    <div className="text-center">
      <p
        className={cn(
          "tabular font-display text-lg font-semibold leading-none",
          tone === "warn" ? "text-clay" : tone === "good" ? "text-pine" : "text-ink"
        )}
      >
        {value}
      </p>
      <p className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-faint">
        {label}
      </p>
    </div>
  );
}

export function WardShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [census, setCensus] = useState<Census | null>(null);

  const load = useCallback(async () => {
    try {
      setCensus(await staffApi.ipdCensus());
    } catch {
      // The census is context, not the job. A failed refresh should not put
      // an error banner across a screen someone is using to admit a patient.
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), CENSUS_REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <div className="h-dvh overflow-hidden bg-mint">
      <header className="sticky top-0 z-30 border-b border-pine/10 bg-white print-hidden">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-4 px-4 py-3 sm:px-6">
          <div className="rounded bg-white">
            <Logo className="h-8 w-auto" />
            <PlatformMark variant="inline" width={92} />
          </div>
          <div className="hidden border-l border-pine/10 pl-4 sm:block">
            <p className="flex items-center gap-1.5 font-display text-sm font-semibold text-pine">
              <BedDouble className="h-3.5 w-3.5" /> Ward
            </p>
            <p className="text-[11px] text-ink-muted">Admissions &amp; inpatients</p>
          </div>

          <nav aria-label="Ward terminal" className="flex items-center gap-1">
            {[
              { href: "/ward", label: "Beds", icon: BedDouble,
                active: pathname === "/ward" || pathname.startsWith("/ward/admissions") },
              { href: "/ward/theatre", label: "Theatre", icon: Scissors,
                active: pathname.startsWith("/ward/theatre") },
              { href: "/ward/diet", label: "Diet", icon: UtensilsCrossed,
                active: pathname.startsWith("/ward/diet") },
              { href: "/lab", label: "Lab", icon: FlaskConical, active: false },
            ].map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition",
                  link.active ? "bg-pine text-mint" : "text-ink-muted hover:bg-mint hover:text-pine"
                )}
              >
                <link.icon className="h-3.5 w-3.5" /> {link.label}
              </Link>
            ))}
          </nav>

          {census && (
            <div className="flex items-center gap-5 rounded-xl bg-mint px-4 py-2">
              <Figure label="Occupied" value={`${census.occupied}/${census.total_beds}`} />
              <Figure label="Free" value={String(census.vacant)}
                      tone={census.vacant === 0 ? "warn" : "good"} />
              <Figure label="Cleaning" value={String(census.cleaning)} />
              <Figure label="In today" value={String(census.admissions_today)} />
              <Figure label="Out today" value={String(census.discharges_today)} />
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => void load()}
              className="rounded-lg p-2 text-ink-faint transition hover:bg-mint hover:text-pine"
              aria-label="Refresh"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
            <div className="hidden text-right sm:block">
              <p className="text-xs font-medium text-ink">{user?.full_name}</p>
              <p className="text-[11px] capitalize text-ink-faint">Ward incharge</p>
            </div>
            <button
              onClick={logout}
              className="rounded-lg p-2 text-ink-faint transition hover:bg-mint hover:text-clay"
              aria-label="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="h-[calc(100dvh-65px)] overflow-y-auto px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
