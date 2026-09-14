"use client";

/**
 * The bench's worklist.
 *
 * Two queues: requests already registered — waiting for a sample, a result or
 * the pathologist — and tests doctors have ordered that nobody has registered
 * yet. The second exists because an order on a consultation screen reaches the
 * laboratory only if someone looks for it.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, Plus, RefreshCw, Search } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { LabItemStatus, LabPriority, LabRequestSummary, PendingLabOrder } from "@/lib/labTypes";
import { BILLING_LABEL, REQUEST_STATUS_LABEL, canRegisterLab } from "@/lib/labTypes";
import { formatDateTime, hospitalToday } from "@/lib/format";
import { RegisterLabDialog, type RegisterPrefill } from "@/components/lab/register-lab-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const FILTERS = [
  { value: "pending", label: "Open" },
  { value: "today", label: "Today" },
  { value: "verified", label: "Verified" },
  { value: "cancelled", label: "Cancelled" },
  { value: "", label: "All" },
];

const TEST_TONE: Record<LabItemStatus, string> = {
  registered: "border-border bg-white text-ink-muted",
  collected: "border-marigold/40 bg-marigold/10 text-marigold-deep",
  entered: "border-pine/30 bg-pine/10 text-pine",
  verified: "border-pine bg-pine text-mint",
  cancelled: "border-border bg-white text-ink-faint line-through",
};

export function LabWorklist() {
  const router = useRouter();
  const { user } = useAuth();
  const mayRegister = canRegisterLab(user?.role);
  const [tab, setTab] = useState<"requests" | "orders">("requests");
  const [filter, setFilter] = useState("pending");
  const [search, setSearch] = useState("");
  const [requests, setRequests] = useState<LabRequestSummary[] | null>(null);
  const [orders, setOrders] = useState<PendingLabOrder[] | null>(null);
  const [registerOpen, setRegisterOpen] = useState(false);
  const [prefill, setPrefill] = useState<RegisterPrefill | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadRequests = useCallback(async () => {
    try {
      const today = hospitalToday();
      setRequests(
        await staffApi.labRequests({
          status: filter === "today" ? undefined : filter || undefined,
          date_from: filter === "today" ? today : undefined,
          q: search.trim() || undefined,
          limit: 200,
        })
      );
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The worklist could not be loaded.");
    }
  }, [filter, search]);

  const loadOrders = useCallback(async () => {
    if (!mayRegister) return;
    try {
      setOrders(await staffApi.pendingLabOrders());
    } catch {
      setOrders([]);
    }
  }, [mayRegister]);

  useEffect(() => {
    const timer = setTimeout(() => void loadRequests(), 250);
    return () => clearTimeout(timer);
  }, [loadRequests]);

  useEffect(() => {
    void loadOrders();
    const timer = setInterval(() => {
      void loadRequests();
      void loadOrders();
    }, 60000);
    return () => clearInterval(timer);
  }, [loadOrders, loadRequests]);

  function registerFromOrder(order: PendingLabOrder) {
    const priority = (["routine", "urgent", "stat"].includes(order.priority) ? order.priority : "routine") as LabPriority;
    setPrefill({
      patient: order.patient,
      admission: order.admission,
      tests: order.items
        .filter((item) => item.test)
        .map((item) => ({ test_id: item.test!.id, order_item_id: item.item_id })),
      order_id: order.order_id,
      consultation_id: order.consultation_id,
      referred_by: order.ordered_by_name,
      priority,
      clinical_notes: order.provisional_diagnosis ?? order.clinical_notes,
    });
    setRegisterOpen(true);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-semibold text-pine">Laboratory</h1>
          <p className="mt-1 text-sm text-ink-muted">Samples waiting, results to enter, and results to verify.</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => void Promise.all([loadRequests(), loadOrders()])}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
          {mayRegister && (
            <Button
              size="sm"
              onClick={() => {
                setPrefill(null);
                setRegisterOpen(true);
              }}
            >
              <Plus className="h-4 w-4" /> Register tests
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setTab("requests")}
          className={cn("rounded-lg px-3 py-1.5 text-sm font-medium", tab === "requests" ? "bg-pine text-mint" : "text-ink-muted hover:bg-white")}
        >
          Worklist
        </button>
        {mayRegister && (
          <button
            onClick={() => setTab("orders")}
            className={cn("rounded-lg px-3 py-1.5 text-sm font-medium", tab === "orders" ? "bg-pine text-mint" : "text-ink-muted hover:bg-white")}
          >
            Doctors&apos; orders{orders && orders.length > 0 ? ` (${orders.length})` : ""}
          </button>
        )}
      </div>

      {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}

      {tab === "requests" && (
        <Card>
          <CardContent className="space-y-3 p-4">
            <div className="flex flex-wrap items-center gap-2">
              {FILTERS.map((entry) => (
                <button
                  key={entry.label}
                  onClick={() => setFilter(entry.value)}
                  className={cn(
                    "rounded-full border px-3 py-1 text-xs font-medium",
                    filter === entry.value ? "border-pine bg-pine text-mint" : "border-border text-ink-muted hover:border-pine/40"
                  )}
                >
                  {entry.label}
                </button>
              ))}
              <div className="relative ml-auto w-full sm:w-72">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-faint" />
                <Input className="pl-8" placeholder="Lab no., patient, UHID or phone" value={search} onChange={(event) => setSearch(event.target.value)} />
              </div>
            </div>

            {requests === null && <p className="text-sm text-ink-muted">Loading…</p>}
            {requests !== null && requests.length === 0 && <p className="py-6 text-center text-sm text-ink-muted">Nothing here.</p>}
            <div className="divide-y divide-border">
              {(requests ?? []).map((entry) => (
                <Link
                  key={entry.id}
                  href={`/lab/requests/${entry.id}`}
                  className="flex flex-wrap items-center gap-3 py-2.5 transition hover:bg-mint/40"
                >
                  <div className="w-32 shrink-0">
                    <p className="font-mono text-sm font-semibold text-pine">{entry.lab_number}</p>
                    <p className="text-[11px] text-ink-faint">{formatDateTime(entry.created_at)}</p>
                  </div>
                  <div className="min-w-[10rem] flex-1">
                    <p className="text-sm font-medium text-ink">{entry.patient.name}</p>
                    <p className="text-xs text-ink-muted">
                      {entry.patient.uhid ?? "No UHID"} · {entry.patient.age} y · {entry.patient.gender}
                    </p>
                  </div>
                  <div className="flex flex-[2] flex-wrap gap-1">
                    {entry.tests.map((test) => (
                      <span key={test.id} className={cn("rounded-full border px-2 py-0.5 text-[11px]", TEST_TONE[test.status])}>
                        {test.name}
                      </span>
                    ))}
                  </div>
                  <div className="w-36 shrink-0 text-right">
                    <p className="text-xs font-medium text-ink">{REQUEST_STATUS_LABEL[entry.status]}</p>
                    <p className="text-[11px] text-ink-faint">
                      {entry.priority !== "routine" && (
                        <span className="mr-1 font-semibold uppercase text-clay">{entry.priority}</span>
                      )}
                      {BILLING_LABEL[entry.billing]}
                      {entry.status !== "verified" && entry.status !== "cancelled" ? ` · ${Math.round(entry.hours_waiting)} h` : ""}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {tab === "orders" && (
        <Card>
          <CardContent className="space-y-2 p-4">
            {orders === null && <p className="text-sm text-ink-muted">Loading…</p>}
            {orders !== null && orders.length === 0 && (
              <p className="py-6 text-center text-sm text-ink-muted">No doctor&apos;s orders are waiting for the laboratory.</p>
            )}
            {(orders ?? []).map((order) => {
              const unmatched = order.items.filter((item) => !item.test);
              return (
                <div key={order.order_id} className="rounded-lg border border-border p-3">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {order.patient.name}{" "}
                        <span className="text-xs font-normal text-ink-muted">
                          {order.patient.uhid ?? ""} · {order.patient.age} y{order.admission ? ` · ${order.admission.ip_number}` : ""}
                        </span>
                      </p>
                      <p className="text-xs text-ink-muted">
                        Ordered by {order.ordered_by_name} · {formatDateTime(order.ordered_at)}
                        {order.priority !== "routine" && <span className="ml-1 font-semibold uppercase text-clay">{order.priority}</span>}
                      </p>
                    </div>
                    <Button size="sm" disabled={order.items.every((item) => !item.test)} onClick={() => registerFromOrder(order)}>
                      Register
                    </Button>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {order.items.map((item) => (
                      <span
                        key={item.item_id}
                        className={cn(
                          "rounded-full border px-2 py-0.5 text-[11px]",
                          item.test ? "border-pine/20 bg-mint text-pine" : "border-clay/30 bg-clay/5 text-clay"
                        )}
                      >
                        {item.name}
                      </span>
                    ))}
                  </div>
                  {unmatched.length > 0 && (
                    <p className="mt-2 flex items-start gap-1.5 text-xs text-clay">
                      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                      No lab test is set up for {unmatched.map((item) => `${item.name} (${item.code})`).join(", ")}. Add one in the test
                      list with that catalogue code, or register a matching test by hand.
                    </p>
                  )}
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      <RegisterLabDialog
        open={registerOpen}
        prefill={prefill}
        onClose={() => setRegisterOpen(false)}
        onRegistered={(created) => {
          setRegisterOpen(false);
          router.push(`/lab/requests/${created.id}`);
        }}
      />
    </div>
  );
}
