"use client";

/** Shared queue view used by Waiting, Current and Completed pages. */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronRight, Inbox, RefreshCw, Search } from "lucide-react";
import { staffApi, type ConsultationFilters } from "@/lib/staffApi";
import type { ConsultationListItem } from "@/lib/types";
import { timeAgo } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/dashboard/empty-state";
import { RiskBadge, StatusBadge } from "@/components/dashboard/badges";

interface Props {
  filters: ConsultationFilters;
  emptyTitle: string;
  emptyDescription: string;
  /** Poll interval in ms; used for live queues. */
  refreshMs?: number;
  showSearch?: boolean;
}

export function ConsultationList({
  filters,
  emptyTitle,
  emptyDescription,
  refreshMs,
  showSearch = true,
}: Props) {
  const [items, setItems] = useState<ConsultationListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const serialized = JSON.stringify(filters);

  const load = useCallback(
    async (silent = false) => {
      if (!silent) setRefreshing(true);
      try {
        const result = await staffApi.consultations({
          ...(JSON.parse(serialized) as ConsultationFilters),
          q: search.trim() || undefined,
          limit: 100,
        });
        setItems(result.items);
        setTotal(result.total);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load consultations.");
      } finally {
        setRefreshing(false);
      }
    },
    [serialized, search]
  );

  useEffect(() => {
    void load(true);
  }, [load]);

  useEffect(() => {
    if (!refreshMs) return;
    const timer = setInterval(() => void load(true), refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, load]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {showSearch ? (
          <div className="relative w-full max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search name or phone"
              className="pl-9"
              aria-label="Search consultations"
            />
          </div>
        ) : (
          <span />
        )}
        <div className="flex items-center gap-3">
          <span className="tabular text-sm text-ink-muted">
            {items ? `${total} ${total === 1 ? "record" : "records"}` : ""}
          </span>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={refreshing}>
            <RefreshCw className={refreshing ? "animate-spin" : ""} />
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>
      )}

      {items === null ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-[76px] w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState icon={Inbox} title={emptyTitle} description={emptyDescription} />
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((consultation, index) => {
            const dossier = consultation.medical_json;
            const complaint =
              dossier?.clinical_summary?.one_liner ??
              dossier?.medical_json?.chief_complaint ??
              (consultation.status === "in_progress" ? "Intake in progress…" : "No summary recorded");
            return (
              <motion.div
                key={consultation.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: Math.min(index * 0.025, 0.3) }}
              >
                <Link href={`/consultations/${consultation.id}`} className="block">
                  <Card className="group p-4 transition-all hover:border-pine/25 hover:shadow-lift">
                    <div className="flex items-center gap-4">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-display text-[15px] font-semibold text-pine">
                            {consultation.patient?.name ?? "Unknown patient"}
                          </span>
                          <span className="tabular text-xs text-ink-faint">
                            {consultation.patient
                              ? `${consultation.patient.age}y · ${consultation.patient.gender}`
                              : ""}
                          </span>
                          <StatusBadge
                            status={consultation.status}
                            reviewed={Boolean(consultation.reviewed_at)}
                          />
                          <RiskBadge risk={dossier?.risk_assessment?.overall_risk} />
                          {dossier?.risk_assessment?.emergency && (
                            <span className="rounded-full bg-clay px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                              Emergency
                            </span>
                          )}
                        </div>
                        <p className="mt-1 truncate text-sm text-ink-muted">{complaint}</p>
                      </div>

                      {/* Department and call duration were removed: a
                          consultant sees only their own department, and how
                          long the intake ran is detail for the record, not
                          for a triage list. */}
                      <span className="tabular hidden shrink-0 text-xs text-ink-faint sm:block">
                        {timeAgo(consultation.started_at)}
                      </span>
                      <ChevronRight className="h-4 w-4 shrink-0 text-ink-faint transition group-hover:translate-x-0.5 group-hover:text-pine" />
                    </div>
                  </Card>
                </Link>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
