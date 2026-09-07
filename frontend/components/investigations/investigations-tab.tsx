"use client";

/**
 * Ordering investigations for one consultation.
 *
 * Report upload used to live here too, but a doctor's console is the wrong
 * place for it: reports arrive from the laboratory, not from the consulting
 * room. That flow is out of scope for now, so this screen does one thing well.
 *
 * What an order is *for*: the tests recorded here are pulled into the
 * prescription automatically, and the printed prescription is what the patient
 * carries to the laboratory. An order that lived only in this database would
 * never reach anybody.
 */
import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight, Download, FileText, FlaskConical, Info, Plus, RefreshCw, XCircle,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { InvestigationOrder, ReportListItem } from "@/lib/investigationTypes";
import { formatDateTime, titleCase } from "@/lib/format";
import { getToken } from "@/lib/auth";
import { InvestigationPicker } from "@/components/investigations/investigation-picker";
import { EmptyState } from "@/components/dashboard/empty-state";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function InvestigationsTab({
  patientId,
  consultationId,
}: {
  patientId: string;
  consultationId: string;
}) {
  const toast = useToast();
  const [orders, setOrders] = useState<InvestigationOrder[] | null>(null);
  const [patientReports, setPatientReports] = useState<ReportListItem[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [orderResult, reportResult] = await Promise.all([
        staffApi.orders({ consultation_id: consultationId }),
        // Reports the patient uploaded from the waiting area after intake.
        staffApi.reports({ consultation_id: consultationId }),
      ]);
      setOrders(orderResult.items);
      setPatientReports(reportResult.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load investigations.");
    }
  }, [consultationId]);

  /** Reports are behind bearer auth, so fetch then hand back a blob URL. */
  async function openReport(reportId: string, filename: string) {
    const response = await fetch(staffApi.reportFileUrl(reportId), {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!response.ok) {
      setError("That report could not be opened.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }

  useEffect(() => {
    void load();
  }, [load]);

  async function cancel(order: InvestigationOrder) {
    setCancellingId(order.id);
    try {
      await staffApi.cancelOrder(order.id);
      await load();
      toast.success("Request cancelled", "It will no longer appear on the prescription.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel the request.");
    } finally {
      setCancellingId(null);
    }
  }

  const active = (orders ?? []).filter((order) => order.status !== "cancelled");
  const testCount = active.reduce((total, order) => total + order.items.length, 0);

  return (
    <div className="space-y-5">
      {error && <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-semibold text-pine">Investigations</h3>
          <p className="text-sm text-ink-muted">
            Order tests for this visit. They print on the prescription.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw /> Refresh
          </Button>
          <Button size="sm" onClick={() => setPickerOpen(true)}>
            <Plus /> Order investigations
          </Button>
        </div>
      </div>

      {/* Make the handoff explicit, so it is obvious where an order ends up. */}
      {testCount > 0 && (
        <div className="flex items-start gap-2.5 rounded-lg border border-marigold/40 bg-marigold/[0.06] px-4 py-3">
          <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-marigold-deep" />
          <p className="text-sm text-ink">
            <span className="font-semibold">
              {testCount} {testCount === 1 ? "test" : "tests"} will appear on the prescription.
            </span>{" "}
            <span className="text-ink-muted">
              Create the prescription from the Prescription tab and these are filled in
              automatically, with any patient preparation noted.
            </span>
          </p>
        </div>
      )}

      {/* Anything the patient brought with them, uploaded from the waiting
          area — visible before the consultation rather than handed over
          halfway through it. */}
      {patientReports && patientReports.length > 0 && (
        <Card className="border-marigold/40 bg-marigold/[0.04]">
          <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
            <FileText className="h-4 w-4 text-marigold-deep" />
            <CardTitle>Reports the patient brought ({patientReports.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ul className="divide-y divide-border">
              {patientReports.map((report) => (
                <li key={report.id} className="flex flex-wrap items-center gap-2 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">{report.title}</p>
                    <p className="text-xs text-ink-faint">
                      {report.uploaded_by_name} · {formatDateTime(report.created_at)}
                      {report.status !== "analyzed" ? ` · ${titleCase(report.status)}` : ""}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => openReport(report.id, report.title)}
                  >
                    <Download /> Open
                  </Button>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
          <FlaskConical className="h-4 w-4 text-pine" />
          <CardTitle>Requests for this visit</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {orders === null ? (
            <div className="space-y-2 px-5 pb-5">
              {[0, 1].map((index) => (
                <Skeleton key={index} className="h-20 w-full rounded-lg" />
              ))}
            </div>
          ) : orders.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              title="No investigations ordered"
              description="Choose tests from the catalog and they will be printed on the patient's prescription."
            />
          ) : (
            <ul className="divide-y divide-border">
              {orders.map((order, index) => (
                <motion.li
                  key={order.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.16, delay: Math.min(index * 0.03, 0.2) }}
                  className="px-5 py-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={order.status === "cancelled" ? "outline" : "success"}>
                      {titleCase(order.status)}
                    </Badge>
                    {order.priority !== "routine" && (
                      <Badge variant={order.priority === "stat" ? "danger" : "warning"}>
                        {order.priority.toUpperCase()}
                      </Badge>
                    )}
                    <span className="text-xs text-ink-muted">
                      {order.ordered_by_name} ·{" "}
                      {formatDateTime(order.issued_at ?? order.created_at)}
                    </span>
                    {order.status !== "cancelled" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="ml-auto h-7 px-2 text-[11px] text-ink-faint hover:text-clay"
                        disabled={cancellingId === order.id}
                        onClick={() => cancel(order)}
                      >
                        <XCircle /> Cancel
                      </Button>
                    )}
                  </div>

                  {order.provisional_diagnosis && (
                    <p className="mt-1.5 text-sm text-ink">
                      <span className="text-ink-faint">Provisional: </span>
                      {order.provisional_diagnosis}
                    </p>
                  )}

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {order.items.map((item) => (
                      <Badge key={item.id} variant="secondary">
                        {item.name}
                      </Badge>
                    ))}
                  </div>

                  {order.items.some((item) => item.preparation) && (
                    <div className="mt-2 rounded-md bg-mint px-3 py-2">
                      <p className="mb-0.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-pine">
                        <Info className="h-3 w-3" /> Patient preparation
                      </p>
                      {order.items
                        .filter((item) => item.preparation)
                        .map((item) => (
                          <p key={item.id} className="text-xs text-ink-muted">
                            <span className="font-medium text-ink">{item.name}:</span>{" "}
                            {item.preparation}
                          </p>
                        ))}
                    </div>
                  )}

                  {order.clinical_notes && (
                    <p className="mt-2 text-xs italic text-ink-muted">{order.clinical_notes}</p>
                  )}
                </motion.li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <InvestigationPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        patientId={patientId}
        consultationId={consultationId}
        onOrdered={() => {
          void load();
          toast.success(
            "Investigations ordered",
            "They will print on the patient's prescription."
          );
        }}
      />
    </div>
  );
}
