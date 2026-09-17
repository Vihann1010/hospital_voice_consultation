"use client";

/** Prescriptions for one consultation: create, view, print, send, track. */
import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  AlertTriangle, CheckCircle2, Clock, Download, FileText, Loader2, Plus,
  Printer, RefreshCw, Send, XCircle,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type { Delivery, DeliveryStatus, Prescription } from "@/lib/types/prescriptions";
import { DELIVERY_LABEL } from "@/lib/types/prescriptions";
import { formatDateTime, timeAgo } from "@/lib/format";
import { PrescriptionComposer } from "@/components/prescriptions/prescription-composer";
import { EmptyState } from "@/components/dashboard/empty-state";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const DELIVERY_VARIANT: Record<DeliveryStatus, "success" | "warning" | "danger" | "outline"> = {
  pending: "warning", sending: "warning", sent: "success",
  delivered: "success", read: "success", failed: "danger", cancelled: "outline",
};

function DeliveryRow({ delivery, onRetry }: { delivery: Delivery; onRetry: () => void }) {
  const [busy, setBusy] = useState(false);
  const failed = delivery.status === "failed";
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-md bg-mint/60 px-3 py-2">
      <Badge variant={DELIVERY_VARIANT[delivery.status]} size="sm" className="gap-1">
        {failed ? <XCircle className="h-3 w-3" />
          : delivery.status === "pending" ? <Clock className="h-3 w-3" />
          : <CheckCircle2 className="h-3 w-3" />}
        {DELIVERY_LABEL[delivery.status]}
      </Badge>
      <span className="tabular text-xs text-ink-muted">+{delivery.recipient}</span>
      <span className="text-[11px] text-ink-faint">
        {delivery.provider} · attempt {delivery.attempts}
        {delivery.last_attempt_at ? ` · ${timeAgo(delivery.last_attempt_at)}` : ""}
      </span>
      {delivery.next_retry_at && delivery.status === "pending" && (
        <span className="text-[11px] text-marigold-deep">
          retrying {timeAgo(delivery.next_retry_at)}
        </span>
      )}
      {delivery.error_detail && (
        <span className="w-full text-[11px] text-clay">{delivery.error_detail}</span>
      )}
      {failed && (
        <Button
          size="sm" variant="outline" className="ml-auto h-7 px-2 text-[11px]"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await staffApi.retryDelivery(delivery.id);
              onRetry();
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? <Loader2 className="animate-spin" /> : <RefreshCw />} Retry
        </Button>
      )}
    </div>
  );
}

export function PrescriptionsTab({
  patientId,
  consultationId,
  department,
  prefill,
}: {
  patientId: string;
  consultationId: string;
  department?: string;
  prefill?: { diagnosis?: string | null; chiefComplaint?: string | null; investigations?: string[] };
}) {
  const toast = useToast();
  const [items, setItems] = useState<Prescription[] | null>(null);
  const [composerOpen, setComposerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sendingId, setSendingId] = useState<string | null>(null);
  const [printingId, setPrintingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await staffApi.prescriptions({ patient_id: patientId });
      setItems(result.items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load prescriptions.");
    }
  }, [patientId]);

  useEffect(() => {
    void load();
  }, [load]);

  /** Fetch the PDF once and hand back an object URL (the endpoint needs a token). */
  async function fetchPdfUrl(prescription: Prescription): Promise<string | null> {
    const response = await fetch(staffApi.prescriptionPdfUrl(prescription.id), {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    });
    if (!response.ok) {
      setError("The PDF is not available yet.");
      return null;
    }
    return URL.createObjectURL(await response.blob());
  }

  /**
   * Open the print dialog directly on the prescription.
   *
   * The PDF is loaded into a hidden iframe and printed from there, so the
   * doctor goes straight from "issue" to paper without a download step or a
   * stray file on the consulting-room machine.
   */
  async function print(prescription: Prescription) {
    setPrintingId(prescription.id);
    try {
      const url = await fetchPdfUrl(prescription);
      if (!url) return;

      const frame = document.createElement("iframe");
      frame.style.position = "fixed";
      frame.style.right = "0";
      frame.style.bottom = "0";
      frame.style.width = "0";
      frame.style.height = "0";
      frame.style.border = "0";
      frame.src = url;

      frame.onload = () => {
        try {
          frame.contentWindow?.focus();
          frame.contentWindow?.print();
        } catch {
          // Some browsers block printing a cross-document iframe; fall back
          // to opening the sheet in a tab so the doctor can still print it.
          window.open(url, "_blank");
        }
        // Leave the frame alive long enough for the dialog to take the
        // document, then release both it and the object URL.
        setTimeout(() => {
          frame.remove();
          URL.revokeObjectURL(url);
        }, 60000);
      };
      document.body.appendChild(frame);
    } finally {
      setPrintingId(null);
    }
  }

  async function download(prescription: Prescription) {
    const url = await fetchPdfUrl(prescription);
    if (!url) return;
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${prescription.prescription_number}.pdf`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function sendWhatsApp(prescription: Prescription) {
    setSendingId(prescription.id);
    setError(null);
    try {
      const delivery = await staffApi.sendPrescriptionWhatsApp(prescription.id);
      await load();
      if (delivery.status === "failed") {
        toast.error("Could not deliver the prescription",
                    delivery.error_detail ?? "It will be retried automatically.");
      } else {
        toast.success("Prescription sent",
                      `Delivered to +${delivery.recipient} via ${delivery.provider}.`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not send the prescription.";
      setError(message);
      toast.error("Send failed", message);
    } finally {
      setSendingId(null);
    }
  }

  return (
    <div className="space-y-5">
      {error && <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-display text-lg font-semibold text-pine">Prescriptions</h3>
          <p className="text-sm text-ink-muted">
            Dictate or type, then issue a signed A4 prescription.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw /> Refresh
          </Button>
          <Button size="sm" onClick={() => setComposerOpen(true)}>
            <Plus /> Create prescription
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
          <FileText className="h-4 w-4 text-pine" />
          <CardTitle>Issued prescriptions</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {items === null ? (
            <div className="space-y-2 px-5 pb-5">
              {[0, 1].map((i) => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No prescriptions yet"
              description="Create one with voice dictation or by typing the medicines."
            />
          ) : (
            <ul className="divide-y divide-border">
              {items.map((prescription, index) => (
                <motion.li
                  key={prescription.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.16, delay: Math.min(index * 0.03, 0.2) }}
                  className="px-5 py-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-display text-sm font-semibold text-pine">
                      {prescription.prescription_number}
                    </span>
                    <Badge
                      variant={
                        prescription.status === "issued" ? "success"
                        : prescription.status === "cancelled" ? "danger" : "outline"
                      }
                      size="sm"
                    >
                      {prescription.status}
                    </Badge>
                    <span className="text-xs text-ink-muted">
                      {prescription.doctor_name} ·{" "}
                      {formatDateTime(prescription.issued_at ?? prescription.created_at)}
                    </span>
                  </div>

                  {prescription.diagnosis && (
                    <p className="mt-1 text-sm text-ink">
                      <span className="text-ink-faint">Diagnosis: </span>
                      {prescription.diagnosis}
                    </p>
                  )}

                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {prescription.medicines.map((medicine) => (
                      <Badge key={medicine.id} variant="secondary" size="sm">
                        {[medicine.form, medicine.name, medicine.strength]
                          .filter(Boolean).join(" ")}
                        {medicine.frequency_text ? ` · ${medicine.frequency_text}` : ""}
                      </Badge>
                    ))}
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      onClick={() => print(prescription)}
                      disabled={printingId === prescription.id}
                    >
                      {printingId === prescription.id ? (
                        <Loader2 className="animate-spin" />
                      ) : (
                        <Printer />
                      )}
                      Print
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => download(prescription)}>
                      <Download /> Save PDF
                    </Button>
                    <Button
                      size="sm"
                      variant="accent"
                      disabled={sendingId === prescription.id || prescription.status !== "issued"}
                      onClick={() => sendWhatsApp(prescription)}
                    >
                      {sendingId === prescription.id ? <Loader2 className="animate-spin" /> : <Send />}
                      Send to WhatsApp
                    </Button>
                  </div>

                  {prescription.deliveries.length > 0 && (
                    <div className="mt-3 space-y-1.5">
                      {prescription.deliveries.map((delivery) => (
                        <DeliveryRow key={delivery.id} delivery={delivery} onRetry={load} />
                      ))}
                    </div>
                  )}
                </motion.li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <PrescriptionComposer
        open={composerOpen}
        onOpenChange={setComposerOpen}
        patientId={patientId}
        consultationId={consultationId}
          department={department}
        prefill={prefill}
        onCreated={() => void load()}
      />
    </div>
  );
}
