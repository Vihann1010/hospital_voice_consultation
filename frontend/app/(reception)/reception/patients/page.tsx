"use client";

import { useCallback, useEffect, useState } from "react";
import { Search, UserSearch } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientListItem } from "@/lib/types";
import { formatDate, initials } from "@/lib/format";
import { EmptyState } from "@/components/dashboard/empty-state";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function ReceptionPatientsPage() {
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
      setError(err instanceof Error ? err.message : "Could not load registered patients.");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(query), query ? 250 : 0);
    return () => clearTimeout(timer);
  }, [query, load]);

  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold text-pine">Registered patients</h1>
        <p className="mt-1 text-sm text-ink-muted">Search the hospital registration list.</p>
      </div>

      <div className="relative mb-4 max-w-md">
        <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name or phone number..."
          className="h-11 pl-10 text-[15px]"
          aria-label="Search registered patients"
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
          {[0, 1, 2, 3].map((item) => (
            <Skeleton key={item} className="h-[68px] w-full rounded-xl" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={UserSearch}
            title={query ? "No patients match that search" : "No patients registered yet"}
            description={query ? "Try a partial name or phone number." : "Patients appear here after registration."}
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {items.map((patient) => (
            <Card key={patient.id} className="flex items-center gap-4 p-4">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-mint font-display text-sm font-semibold text-pine">
                {initials(patient.name)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-display text-[15px] font-semibold text-pine">{patient.name}</p>
                <p className="tabular truncate text-xs text-ink-muted">
                  {patient.age}y · {patient.gender} · {patient.phone_number}
                </p>
                <p className="mt-1 truncate text-xs text-ink-muted">
                  <span className="font-medium text-ink">Reason:</span>{" "}
                  {patient.visit_reason ?? "Not recorded"}
                </p>
              </div>
              <div className="hidden text-right sm:block">
                <Badge variant="secondary">
                  {patient.visit_count} {patient.visit_count === 1 ? "visit" : "visits"}
                </Badge>
                <p className="mt-1 text-xs text-ink-muted">
                  <span className="font-medium text-ink">Payment:</span>{" "}
                  {patient.payment_status === "paid"
                    ? "Paid"
                    : patient.payment_status === "partially_paid"
                      ? "Partially paid"
                      : patient.payment_status === "refunded"
                        ? "Refunded"
                        : patient.payment_status === "cancelled"
                          ? "Cancelled"
                          : patient.payment_status === "issued"
                            ? "Due"
                            : "Not billed"}
                </p>
                <p className="mt-1 text-[11px] text-ink-faint">Registered {formatDate(patient.created_at)}</p>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
