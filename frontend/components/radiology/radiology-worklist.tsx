"use client";

/**
 * The radiology worklist: imaging studies ordered and waiting for a report.
 *
 * The report is written against the order, so its study, side and clinical
 * indication are the ones the ordering doctor gave, and signing it marks the
 * study reported on the order. Oldest first, because a study nobody reported
 * is the one to worry about.
 */
import { useCallback, useEffect, useState } from "react";
import { FileImage, Loader2, X } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { RadiologyWorkItem } from "@/lib/recordsTypes";
import { formatDateTime } from "@/lib/format";
import { VisitPad } from "@/components/pad/visit-pad";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = {
  xray: "X-ray", mri: "MRI", ct: "CT", ultrasound: "Ultrasound", dexa: "DEXA",
};

export function RadiologyWorklist() {
  const { user } = useAuth();
  const mayWrite = user?.role === "admin" || user?.role === "doctor";
  const [items, setItems] = useState<RadiologyWorkItem[] | null>(null);
  const [includeReported, setIncludeReported] = useState(false);
  const [open, setOpen] = useState<{ documentId: string; item: RadiologyWorkItem } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems((await staffApi.radiologyWorklist({ include_reported: includeReported || undefined })).items);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The worklist could not be loaded.");
    }
  }, [includeReported]);

  useEffect(() => {
    void load();
  }, [load]);

  async function report(item: RadiologyWorkItem) {
    setBusy(item.item_id);
    setError(null);
    try {
      const documentId = item.report?.id ?? (
        await staffApi.openPatientPad(item.patient.id, "radiology_report", { order_item_id: item.item_id })
      ).id;
      setOpen({ documentId, item });
    } catch (err) {
      setError(err instanceof Error ? err.message : "The report could not be opened.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
          <CardTitle className="mr-auto flex items-center gap-2"><FileImage className="h-4 w-4" /> Waiting for a report</CardTitle>
          <label className="flex items-center gap-1.5 text-xs text-ink-muted">
            <input type="checkbox" checked={includeReported} onChange={(e) => setIncludeReported(e.target.checked)} />
            Include reported
          </label>
        </CardHeader>
        <CardContent className="p-0">
          {error && <p className="px-4 pb-2 text-sm text-clay">{error}</p>}
          {!items ? (
            <div className="p-4"><Skeleton className="h-16 w-full rounded-lg" /></div>
          ) : items.length === 0 ? (
            <p className="px-4 pb-4 text-sm text-ink-muted">No imaging studies are waiting for a report.</p>
          ) : (
            <ul className="divide-y divide-border">
              {items.map((item) => (
                <li key={item.item_id}
                    className={cn("flex flex-wrap items-center gap-3 px-4 py-3",
                                  open?.item.item_id === item.item_id && "bg-mint/60")}>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-ink">
                      {item.name}
                      {item.site && <span className="ml-1 text-ink-muted">· {item.site}</span>}
                    </p>
                    <p className="text-xs text-ink-muted">
                      {item.patient.name} · {item.patient.age} y / {item.patient.gender} · UHID {item.patient.uhid ?? "—"}
                    </p>
                    <p className="text-xs text-ink-faint">
                      Ordered by {item.ordered_by_name} · {formatDateTime(item.ordered_at)}
                      {(item.provisional_diagnosis || item.clinical_notes) &&
                        ` · ${item.provisional_diagnosis || item.clinical_notes}`}
                    </p>
                  </div>
                  <Badge variant="secondary" size="sm">{CATEGORY_LABEL[item.category] ?? item.category}</Badge>
                  {item.priority !== "routine" && (
                    <Badge variant={item.priority === "stat" ? "danger" : "warning"} size="sm">
                      {item.priority.toUpperCase()}
                    </Badge>
                  )}
                  {item.report?.status === "signed" ? (
                    <Button size="sm" variant="outline" onClick={() => void report(item)}>
                      {item.report.serial_number ?? "Report"}
                    </Button>
                  ) : mayWrite ? (
                    <Button size="sm" disabled={busy !== null} onClick={() => void report(item)}>
                      {busy === item.item_id && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {item.report ? "Continue report" : "Write report"}
                    </Button>
                  ) : item.report ? (
                    <span className="text-xs text-marigold-deep">Draft by {item.report.author_name}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {open && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-pine">
              {open.item.name} — {open.item.patient.name}
            </p>
            <Button size="sm" variant="ghost" onClick={() => setOpen(null)}><X className="h-4 w-4" /> Close</Button>
          </div>
          <VisitPad key={open.documentId} documentId={open.documentId} onChanged={() => void load()} />
        </div>
      )}
    </div>
  );
}
