"use client";

/**
 * The reception terminal shell.
 *
 * Deliberately not the clinical dashboard. The front desk runs one screen all
 * day on a fixed machine, so this drops the clinical navigation entirely and
 * gives the counter the full width: there is nothing here to browse to, only
 * the patient in front of them.
 *
 * The queue sits alongside the counter rather than on another page, because
 * "what token are we on" is asked constantly and should never cost a click.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { CalendarDays, LogOut, Mic, RefreshCw, Users, Wallet } from "lucide-react";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Logo } from "@/components/brand/logo";
import { staffApi } from "@/lib/staffApi";
import type { Visit } from "@/lib/emrTypes";
import { formatFullDate } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const QUEUE_REFRESH_MS = 20000;

function TodaysQueue() {
  const [visits, setVisits] = useState<Visit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setVisits(await staffApi.todaysVisits());
      setError(null);
    } catch (err) {
      // Surfaced rather than swallowed: an empty queue and a failed request
      // look identical otherwise, and the difference matters at a counter.
      setError(err instanceof Error ? err.message : "Could not load today's list.");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), QUEUE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const waiting = (visits ?? []).filter((visit) => visit.status === "registered");

  return (
    <aside className="rounded-2xl border border-pine/10 bg-white">
      <div className="flex items-center gap-2 border-b border-pine/10 px-4 py-3">
        <Users className="h-4 w-4 text-pine" />
        <h2 className="font-display text-sm font-semibold text-pine">Today</h2>
        {visits && (
          <span className="rounded bg-mint px-1.5 py-0.5 text-[11px] font-medium text-pine">
            {visits.length}
          </span>
        )}
        <button
          onClick={() => void load()}
          className="ml-auto rounded p-1 text-ink-faint transition hover:text-pine"
          aria-label="Refresh the list"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="max-h-[calc(100vh-220px)] overflow-y-auto">
        {error && <p className="px-4 py-3 text-xs text-clay">{error}</p>}

        {visits === null && !error && (
          <p className="px-4 py-6 text-center text-xs text-ink-faint">Loading…</p>
        )}

        {visits?.length === 0 && (
          <p className="px-4 py-6 text-center text-xs text-ink-faint">
            No patients registered yet today.
          </p>
        )}

        <ul className="divide-y divide-border">
          {(visits ?? []).map((visit) => (
            <li key={visit.id} className="flex items-center gap-3 px-4 py-2.5">
              <span
                className={cn(
                  "tabular flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-semibold",
                  visit.status === "registered"
                    ? "bg-marigold/20 text-marigold-deep"
                    : "bg-mint text-pine"
                )}
              >
                {visit.token_number ?? "—"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-ink">{visit.visit_number}</p>
                <p className="truncate text-[11px] capitalize text-ink-faint">
                  {visit.department === "orthopedics" ? "Orthopedics" : "Gynecology"}
                  {" · "}
                  {visit.status.replace("_", " ")}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {visits && visits.length > 0 && (
        <div className="border-t border-pine/10 px-4 py-2.5 text-[11px] text-ink-muted">
          {waiting.length} waiting to be seen
        </div>
      )}
    </aside>
  );
}

export function ReceptionShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [today, setToday] = useState("");

  useEffect(() => {
    // Resolved after mount so the server and client cannot disagree about
    // the date and trip a hydration mismatch.
    const set = () => setToday(formatFullDate(new Date()));
    set();
    const timer = setInterval(set, 60000);
    return () => clearInterval(timer);
  }, []);

  // Doctors and admins can cover the desk, and need a way back to their own
  // screens. Front-desk staff have nowhere else to go, so they are not shown
  // a door that leads to a permission error.
  const isClinical = user?.role === "admin" || user?.role === "doctor";

  return (
    <div className="min-h-screen bg-mint">
      <header className="sticky top-0 z-30 border-b border-pine/10 bg-white">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <div className="rounded bg-white">
            <Logo className="h-8 w-auto" />
          </div>
          <div className="hidden border-l border-pine/10 pl-3 sm:block">
            <p className="font-display text-sm font-semibold text-pine">Reception</p>
            <p className="text-[11px] text-ink-muted">Registration &amp; billing</p>
          </div>

          <div className="ml-auto flex items-center gap-2">
            {today && (
              <span className="hidden items-center gap-1.5 text-xs text-ink-muted md:flex">
                <CalendarDays className="h-3.5 w-3.5" />
                {today}
              </span>
            )}

            <Link href="/intake">
              <Button variant="ghost" size="sm">
                <Mic /> Voice intake
              </Button>
            </Link>

            {isClinical && (
              <>
                <Link href="/finance">
                  <Button variant="ghost" size="sm">
                    <Wallet /> Finance
                  </Button>
                </Link>
                <Link href="/dashboard">
                  <Button variant="outline" size="sm">
                    Clinical dashboard
                  </Button>
                </Link>
              </>
            )}

            <div className="hidden text-right sm:block">
              <p className="text-xs font-medium text-ink">{user?.full_name}</p>
              <p className="text-[11px] capitalize text-ink-faint">{user?.role}</p>
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

      <main className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6">
        <div className="grid gap-5 xl:grid-cols-[1fr_280px]">
          <div>{children}</div>
          <div className="xl:sticky xl:top-20 xl:self-start">
            <TodaysQueue />
          </div>
        </div>
      </main>
    </div>
  );
}
