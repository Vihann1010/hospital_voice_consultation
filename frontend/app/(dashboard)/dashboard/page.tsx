"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, ArrowRight, CheckCircle2, Users } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ConsultationListItem, ConsultationStats } from "@/lib/types";
import { DEPARTMENT_LABEL, formatFullDate, timeAgo } from "@/lib/format";
import { useAuth } from "@/components/dashboard/auth-provider";
import { PageHeader } from "@/components/dashboard/page-header";
import { RiskBadge, StatusBadge } from "@/components/dashboard/badges";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/dashboard/empty-state";
import { cn } from "@/lib/utils";

function StatCard({
  label,
  value,
  icon: Icon,
  href,
  tone = "default",
  index,
}: {
  label: string;
  value: number | undefined;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  tone?: "default" | "accent" | "danger";
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: index * 0.05 }}
    >
      <Link href={href}>
        <Card className="group h-full p-5 transition-all hover:border-pine/25 hover:shadow-lift">
          <div className="flex items-start justify-between">
            <div
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                tone === "accent" && "bg-marigold/15 text-marigold-deep",
                tone === "danger" && "bg-clay/12 text-clay",
                tone === "default" && "bg-mint text-pine"
              )}
            >
              <Icon className="h-4 w-4" />
            </div>
            <ArrowRight className="h-4 w-4 text-ink-faint opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
          </div>
          <p className="tabular mt-4 font-display text-3xl font-semibold leading-none text-pine">
            {value === undefined ? <Skeleton className="h-8 w-12" /> : value}
          </p>
          <p className="mt-1.5 text-sm text-ink-muted">{label}</p>
        </Card>
      </Link>
    </motion.div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [stats, setStats] = useState<ConsultationStats | null>(null);
  const [recent, setRecent] = useState<ConsultationListItem[] | null>(null);

  // Resolved after mount so the server and client cannot disagree about the
  // date, and refreshed each minute so a console left open overnight rolls
  // over to the new day instead of showing yesterday.
  const [today, setToday] = useState<string>("");
  useEffect(() => {
    const tick = () => setToday(formatFullDate());
    tick();
    const timer = setInterval(tick, 60000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const load = () => {
      void staffApi.stats().then(setStats).catch(() => undefined);
      void staffApi
        .consultations({ limit: 6 })
        .then((result) => setRecent(result.items))
        .catch(() => undefined);
    };
    load();
    const timer = setInterval(load, 20000);
    return () => clearInterval(timer);
  }, []);

  const greetingName = user?.full_name?.split(" ").slice(0, 2).join(" ") ?? "";

  return (
    <>
      <PageHeader
        title={greetingName ? `Good day, ${greetingName}` : "Overview"}
        subtitle={
          user?.department
            ? `${DEPARTMENT_LABEL[user.department] ?? ""} · your patients today`
            : "Live view across both departments"
        }
        actions={
          today ? (
            <div className="text-right">
              <p className="text-[10px] uppercase tracking-[0.16em] text-ink-faint">Today</p>
              <p className="tabular font-display text-sm font-semibold text-pine">{today}</p>
            </div>
          ) : null
        }
      />

      {/* Three tiles that map exactly to the three queues. A "last 24 hours"
          count was removed: it answered no question a clinic actually asks. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        <StatCard index={0} label="Waiting to be seen" value={stats?.waiting} icon={Users} href="/waiting" tone="accent" />
        <StatCard index={1} label="Intake in progress" value={stats?.in_progress} icon={Activity} href="/active" />
        <StatCard index={2} label="Reviewed" value={stats?.completed} icon={CheckCircle2} href="/completed" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, delay: 0.15 }}
        className="mt-6"
      >
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Recent activity</CardTitle>
            <Link href="/completed" className="text-xs font-semibold text-pine hover:underline">
              View all
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {recent === null ? (
              <div className="space-y-2 p-5 pt-0">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-14 w-full rounded-lg" />
                ))}
              </div>
            ) : recent.length === 0 ? (
              <EmptyState
                icon={Activity}
                title="No consultations yet"
                description="Once patients begin using the voice intake, their visits will appear here."
              />
            ) : (
              <ul className="divide-y divide-border">
                {recent.map((item) => (
                  <li key={item.id}>
                    <Link
                      href={`/consultations/${item.id}`}
                      className="flex items-center gap-3 px-5 py-3.5 transition hover:bg-mint/60"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-pine">
                            {item.patient?.name ?? "Unknown patient"}
                          </span>
                          <StatusBadge status={item.status} reviewed={Boolean(item.reviewed_at)} />
                          <RiskBadge risk={item.medical_json?.risk_assessment?.overall_risk} />
                        </div>
                        <p className="mt-0.5 truncate text-xs text-ink-muted">
                          {item.medical_json?.medical_json?.chief_complaint ?? "Intake pending"}
                        </p>
                      </div>
                      <span className="tabular shrink-0 text-xs text-ink-faint">
                        {timeAgo(item.started_at)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </>
  );
}
