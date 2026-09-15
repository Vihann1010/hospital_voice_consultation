"use client";

/**
 * How often this patient has attended, and when.
 *
 * This replaced a turn-by-turn replay of the intake conversation, which
 * duplicated the Transcript tab and told a doctor nothing they could act on.
 * What matters clinically is the pattern of attendance: how many times, how
 * recently, and whether they keep returning with the same complaint.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { CalendarDays, TrendingUp } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientHistory } from "@/lib/types/core";
import { DEPARTMENT_LABEL, formatDate, formatDateTime, timeAgo } from "@/lib/format";
import { RiskBadge } from "@/components/dashboard/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/dashboard/empty-state";
import { cn } from "@/lib/utils";

/** Whole months between two dates, for the gap shown between visits. */
function gapLabel(laterIso: string, earlierIso: string): string | null {
  const later = new Date(laterIso).getTime();
  const earlier = new Date(earlierIso).getTime();
  if (Number.isNaN(later) || Number.isNaN(earlier)) return null;
  const days = Math.round((later - earlier) / 86_400_000);
  if (days < 1) return "same day";
  if (days === 1) return "next day";
  if (days < 31) return `${days} days later`;
  const months = Math.round(days / 30);
  return months <= 1 ? "about a month later" : `${months} months later`;
}

export function VisitHistory({
  patientId,
  currentConsultationId,
}: {
  patientId: string;
  currentConsultationId?: string;
}) {
  const [data, setData] = useState<PatientHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    staffApi
      .patientHistory(patientId)
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Could not load the visit history.")
      );
  }, [patientId]);

  if (error) {
    return <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>;
  }
  if (!data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-56 w-full rounded-xl" />
      </div>
    );
  }

  const visits = data.visits;
  const first = visits.length ? visits[visits.length - 1] : null;
  const previous = visits.filter((visit) => visit.consultation_id !== currentConsultationId);

  return (
    <div className="space-y-4">
      {/* At-a-glance attendance */}
      <Card className="bg-pine p-5 text-mint">
        <div className="grid grid-cols-3 gap-4">
          <div>
            <p className="tabular font-display text-3xl font-semibold leading-none">
              {visits.length}
            </p>
            <p className="mt-1.5 text-xs text-mint/70">
              {visits.length === 1 ? "Visit" : "Visits"} on record
            </p>
          </div>
          <div>
            <p className="tabular font-display text-3xl font-semibold leading-none">
              {previous.length}
            </p>
            <p className="mt-1.5 text-xs text-mint/70">Before today</p>
          </div>
          <div>
            <p className="font-display text-lg font-semibold leading-tight">
              {first ? formatDate(first.started_at) : "—"}
            </p>
            <p className="mt-1.5 text-xs text-mint/70">First seen</p>
          </div>
        </div>
        {previous.length >= 2 && (
          <p className="mt-4 flex items-center gap-2 border-t border-white/15 pt-3 text-xs text-mint/80">
            <TrendingUp className="h-3.5 w-3.5 shrink-0" />
            A returning patient — read the earlier visits before deciding today&apos;s plan.
          </p>
        )}
      </Card>

      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
          <CalendarDays className="h-4 w-4 text-pine" />
          <CardTitle>Attendance history</CardTitle>
        </CardHeader>
        <CardContent>
          {visits.length === 0 ? (
            <EmptyState icon={CalendarDays} title="No visits recorded" />
          ) : (
            <ol className="relative space-y-5 border-l border-border pl-6">
              {visits.map((visit, index) => {
                const isCurrent = visit.consultation_id === currentConsultationId;
                const older = visits[index + 1];
                const gap = older ? gapLabel(visit.started_at, older.started_at) : null;
                return (
                  <motion.li
                    key={visit.consultation_id}
                    initial={{ opacity: 0, x: -6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.18, delay: Math.min(index * 0.04, 0.3) }}
                    className="relative"
                  >
                    <span
                      className={cn(
                        "absolute -left-[27px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white",
                        isCurrent ? "bg-marigold" : "bg-pine"
                      )}
                    />
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="tabular text-sm font-semibold text-pine">
                        {formatDateTime(visit.started_at)}
                      </span>
                      {isCurrent ? (
                        <span className="rounded-full bg-marigold px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-pine-deep">
                          This visit
                        </span>
                      ) : (
                        <span className="text-xs text-ink-faint">{timeAgo(visit.started_at)}</span>
                      )}
                      <RiskBadge risk={visit.overall_risk} />
                    </div>

                    <p className="mt-1 text-sm text-ink">
                      {visit.one_liner ?? visit.chief_complaint ?? "No summary recorded"}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-faint">
                      {DEPARTMENT_LABEL[visit.department]}
                      {gap ? ` · ${gap}` : ""}
                    </p>

                    {!isCurrent && (
                      <Link
                        href={`/consultations/${visit.consultation_id}`}
                        className="mt-1 inline-block text-xs font-semibold text-pine hover:underline"
                      >
                        Open this visit →
                      </Link>
                    )}
                  </motion.li>
                );
              })}
            </ol>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
