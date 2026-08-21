"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { ChevronRight, Search, UserSearch } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientListItem } from "@/lib/types";
import { formatDate, initials } from "@/lib/format";
import { PageHeader } from "@/components/dashboard/page-header";
import { EmptyState } from "@/components/dashboard/empty-state";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function PatientSearchPage() {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PatientListItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (term: string) => {
    try {
      const result = await staffApi.patients({ q: term.trim() || undefined, limit: 50 });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not search patients.");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(query), query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [query, load]);

  return (
    <>
      <PageHeader
        title="Patient search"
        subtitle="Find any patient by name or phone number to open their full history."
      />

      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name or phone number…"
          className="h-11 pl-10 text-[15px]"
          aria-label="Search patients"
          autoFocus
        />
      </div>

      {error && <Card className="mb-4 border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>}

      {items !== null && items.length > 0 && (
        <p className="mb-3 tabular text-sm text-ink-muted">
          {total} {total === 1 ? "patient" : "patients"}
        </p>
      )}

      {items === null ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[68px] w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={UserSearch}
            title={query ? "No patients match that search" : "No patients registered yet"}
            description={
              query
                ? "Try a partial name or the last few digits of the phone number."
                : "Patients appear here after their first voice intake."
            }
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((patient, index) => (
            <motion.div
              key={patient.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.16, delay: Math.min(index * 0.02, 0.24) }}
            >
              <Link href={`/patients/${patient.id}`}>
                <Card className="group flex items-center gap-4 p-4 transition-all hover:border-pine/25 hover:shadow-lift">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-mint font-display text-sm font-semibold text-pine">
                    {initials(patient.name)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-display text-[15px] font-semibold text-pine">{patient.name}</p>
                    <p className="tabular truncate text-xs text-ink-muted">
                      {patient.age}y · {patient.gender} · {patient.phone_number}
                    </p>
                  </div>
                  <div className="hidden text-right sm:block">
                    <Badge variant="secondary">
                      {patient.visit_count} {patient.visit_count === 1 ? "visit" : "visits"}
                    </Badge>
                    <p className="mt-1 text-[11px] text-ink-faint">
                      Registered {formatDate(patient.created_at)}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-ink-faint transition group-hover:translate-x-0.5 group-hover:text-pine" />
                </Card>
              </Link>
            </motion.div>
          ))}
        </div>
      )}
    </>
  );
}
