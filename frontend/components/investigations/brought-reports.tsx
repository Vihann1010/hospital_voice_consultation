"use client";

/**
 * The reports the patient brought, read rather than merely attached.
 *
 * The order on this screen is the order of clinical urgency, and the top of
 * it is the only part a doctor is guaranteed to read: a patient is sitting
 * across the desk. So anything abnormal from any of the documents is
 * collected into one panel at the top, before the documents themselves — a
 * critical value on the third page photographed is still the first thing that
 * needs seeing, and nobody should have to open three cards to find it.
 *
 * Immediately below that sits the other thing a doctor must not miss: the
 * documents we could not read. Those are listed by name with the reason,
 * because a report silently absent from a summary looks exactly like a report
 * with nothing to say.
 *
 * Every report is fetched in full when the tab opens rather than on expand.
 * There are at most ten per visit, and the anomalies panel cannot be built
 * from the list rows alone — it needs the flagged values themselves.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  FileText,
  FlaskConical,
  HelpCircle,
  Loader2,
  Pill,
  Scan,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type {
  DocumentKind,
  InvestigationReport,
  ReportListItem,
  ReportResult,
} from "@/lib/investigationTypes";
import { FLAG_LABEL } from "@/lib/investigationTypes";
import { formatDateTime } from "@/lib/format";
import { ReportAnalysisView } from "@/components/investigations/report-analysis";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const KIND_ICON: Record<DocumentKind, typeof Pill> = {
  prescription: Pill,
  lab_report: FlaskConical,
  imaging: Scan,
  other: FileText,
};

async function openFile(reportId: string) {
  const response = await fetch(staffApi.reportFileUrl(reportId), {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) return;
  const url = URL.createObjectURL(await response.blob());
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** A flagged value, carrying the document it came from. */
interface Anomaly {
  reportId: string;
  reportTitle: string;
  result: ReportResult;
}

/**
 * The two or three lines that say what a document contains.
 *
 * Built from the deterministic reading, never from the narrative: these are
 * counts and quoted text, so a bullet cannot say something the document does
 * not.
 */
function bulletsFor(report: InvestigationReport): string[] {
  const analysis = report.analysis;
  if (!analysis) return [];
  const bullets: string[] = [];

  switch (analysis.document_kind) {
    case "prescription": {
      const reading = analysis.prescription;
      if (!reading) break;
      if (reading.problems.length > 0) {
        bullets.push(`For: ${reading.problems.join("; ")}`);
      }
      if (reading.medicines.length > 0) {
        bullets.push(
          `${reading.medicines.length} medicine${
            reading.medicines.length === 1 ? "" : "s"
          }: ${reading.medicines.map((item) => item.name).join(", ")}`
        );
      }
      const doubtful =
        reading.possible_medicines.length + reading.unidentified_lines.length;
      if (doubtful > 0) {
        bullets.push(
          `${doubtful} line${doubtful === 1 ? "" : "s"} not read with certainty`
        );
      }
      break;
    }
    case "imaging": {
      const reading = analysis.imaging;
      if (!reading) break;
      // The radiologist's own first line, quoted. Not a paraphrase of it.
      reading.impression.slice(0, 2).forEach((line) => bullets.push(line));
      break;
    }
    case "lab_report": {
      const total = analysis.results?.length ?? 0;
      const abnormal = analysis.abnormal_count ?? 0;
      bullets.push(
        abnormal > 0
          ? `${abnormal} of ${total} values outside range`
          : `${total} values, all within range`
      );
      if ((analysis.uninterpreted_lines?.length ?? 0) > 0) {
        bullets.push(
          `${analysis.uninterpreted_lines?.length} line(s) could not be read as a result`
        );
      }
      break;
    }
    default:
      break;
  }
  return bullets;
}

export function BroughtReports({ consultationId }: { consultationId: string }) {
  const [items, setItems] = useState<ReportListItem[] | null>(null);
  const [details, setDetails] = useState<Record<string, InvestigationReport>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const result = await staffApi.reports({ consultation_id: consultationId });
      setItems(result.items);
      setError(null);

      // One failed detail must not blank the whole tab, so each is settled
      // independently and whatever arrives is shown.
      const loaded = await Promise.allSettled(
        result.items.map((item) => staffApi.report(item.id))
      );
      const next: Record<string, InvestigationReport> = {};
      loaded.forEach((outcome) => {
        if (outcome.status === "fulfilled") next[outcome.value.id] = outcome.value;
      });
      setDetails(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the reports.");
    }
  }, [consultationId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Everything abnormal, from every document, in one list.
  const anomalies = useMemo<Anomaly[]>(() => {
    const found: Anomaly[] = [];
    Object.values(details).forEach((report) => {
      (report.analysis?.abnormal ?? []).forEach((result) =>
        found.push({ reportId: report.id, reportTitle: report.title, result })
      );
    });
    const rank = (value: Anomaly) =>
      value.result.flag === "critical_low" || value.result.flag === "critical_high"
        ? 0
        : 1;
    return found.sort((a, b) => rank(a) - rank(b));
  }, [details]);

  // Documents that could not be read. Listed by name: a report missing from
  // a summary is indistinguishable from one with nothing to report.
  const unreadable = useMemo(
    () =>
      Object.values(details).filter(
        (report) => report.analysis?.clarity === "unclear"
      ),
    [details]
  );

  const ordered = useMemo(() => {
    const rank = (item: ReportListItem) => {
      if ((item.critical_count ?? 0) > 0) return 0;
      if ((item.abnormal_count ?? 0) > 0) return 1;
      if (item.clarity === "unclear") return 2;
      return 3;
    };
    return [...(items ?? [])].sort(
      (a, b) => rank(a) - rank(b) || b.created_at.localeCompare(a.created_at)
    );
  }, [items]);

  if (items !== null && items.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <FileText className="mx-auto h-5 w-5 text-ink-faint" />
          <p className="mt-2 text-sm text-ink-muted">No earlier reports on this visit.</p>
          <p className="mt-1 text-xs text-ink-faint">
            The nurse can show a QR code at intake for the patient to photograph
            anything they brought.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {error && <p className="text-xs text-clay">{error}</p>}
      {items === null && (
        <p className="flex items-center gap-1.5 text-xs text-ink-faint">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading…
        </p>
      )}

      {/* ------------------------------------------------ anomalies first -- */}
      {anomalies.length > 0 && (
        <Card className="border-clay/40 bg-clay/[0.03]">
          <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
            <AlertTriangle className="h-4 w-4 text-clay" />
            <CardTitle className="text-clay">
              {anomalies.length} value{anomalies.length === 1 ? "" : "s"} outside range
            </CardTitle>
            <span className="ml-auto text-[11px] text-ink-faint">
              Compared arithmetically, not by AI
            </span>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {anomalies.map(({ reportId, reportTitle, result }, index) => {
              const critical =
                result.flag === "critical_low" || result.flag === "critical_high";
              return (
                <div
                  key={`${reportId}-${result.printed_name}-${index}`}
                  className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-clay/10 pb-1.5 last:border-0 last:pb-0"
                >
                  <span
                    className={cn(
                      "text-sm font-medium",
                      critical ? "text-clay" : "text-ink"
                    )}
                  >
                    {result.display_name}
                  </span>
                  <span
                    className={cn(
                      "tabular text-sm font-semibold",
                      critical ? "text-clay" : "text-marigold-deep"
                    )}
                  >
                    {result.value ?? result.value_text}
                    {result.unit ? (
                      <span className="ml-0.5 text-xs font-normal">{result.unit}</span>
                    ) : null}
                  </span>
                  <Badge variant={critical ? "danger" : "warning"} size="sm">
                    {FLAG_LABEL[result.flag]}
                  </Badge>
                  {result.reference_text && (
                    <span className="tabular text-[11px] text-ink-muted">
                      ref {result.reference_text}
                    </span>
                  )}
                  <span className="ml-auto truncate text-[11px] text-ink-faint">
                    {reportTitle}
                  </span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* --------------------------------------- then what we could not read -- */}
      {unreadable.length > 0 && (
        <Card className="border-marigold/50 bg-marigold/[0.04]">
          <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
            <HelpCircle className="h-4 w-4 text-marigold-deep" />
            <CardTitle className="text-marigold-deep">
              {unreadable.length} document{unreadable.length === 1 ? "" : "s"} could not
              be read — please go through {unreadable.length === 1 ? "it" : "them"}{" "}
              manually
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5">
            {unreadable.map((report) => (
              <div key={report.id} className="flex items-start gap-2">
                <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-marigold-deep" />
                <p className="text-sm text-ink">
                  <span className="font-medium">{report.title}</span>
                  <span className="text-ink-muted">
                    {" "}
                    — {report.analysis?.unclear_reason}
                  </span>
                </p>
                <Button
                  size="sm"
                  variant="outline"
                  className="ml-auto h-6 shrink-0 text-[11px]"
                  onClick={() => void openFile(report.id)}
                >
                  Open
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* -------------------------------------------- then the documents -- */}
      {ordered.map((item) => {
        const critical = (item.critical_count ?? 0) > 0;
        const abnormal = (item.abnormal_count ?? 0) > 0;
        const unclear = item.clarity === "unclear";
        const isOpen = open === item.id;
        const full = details[item.id];
        const bullets = full ? bulletsFor(full) : [];
        const Icon = item.document_kind ? KIND_ICON[item.document_kind] : FileText;

        return (
          <Card
            key={item.id}
            className={cn(
              critical && "border-clay/40",
              !critical && abnormal && "border-marigold-deep/30"
            )}
          >
            <CardHeader className="flex-row items-start gap-2 space-y-0 pb-3">
              <button
                type="button"
                onClick={() => setOpen((current) => (current === item.id ? null : item.id))}
                className="flex min-w-0 flex-1 items-start gap-2 text-left"
              >
                {critical ? (
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
                ) : unclear ? (
                  <HelpCircle className="mt-0.5 h-4 w-4 shrink-0 text-marigold-deep" />
                ) : (
                  <Icon className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" />
                )}
                <div className="min-w-0 flex-1">
                  <CardTitle className="truncate">{item.title}</CardTitle>
                  <p className="mt-0.5 truncate text-[11px] text-ink-faint">
                    {item.uploaded_by_name} · {formatDateTime(item.created_at)}
                    {critical
                      ? ` · ${item.critical_count} critical`
                      : abnormal
                        ? ` · ${item.abnormal_count} outside range`
                        : ""}
                  </p>

                  {/* The gist, without opening anything. */}
                  {unclear ? (
                    <p className="mt-1.5 text-xs font-medium text-marigold-deep">
                      Unclear — please go through it manually.
                    </p>
                  ) : (
                    bullets.length > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {bullets.map((bullet, index) => (
                          <li
                            key={index}
                            className="flex gap-1.5 text-xs leading-snug text-ink-muted"
                          >
                            <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-pine/40" />
                            {bullet}
                          </li>
                        ))}
                      </ul>
                    )
                  )}
                </div>
                <ChevronDown
                  className={cn(
                    "ml-auto mt-0.5 h-4 w-4 shrink-0 text-ink-faint transition",
                    isOpen && "rotate-180"
                  )}
                />
              </button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 shrink-0 text-xs"
                onClick={() => void openFile(item.id)}
              >
                Original
              </Button>
            </CardHeader>

            {isOpen && (
              <CardContent className="pt-0">
                {full ? (
                  <ReportAnalysisView
                    report={full}
                    onOpenOriginal={() => void openFile(item.id)}
                  />
                ) : (
                  <p className="flex items-center gap-1.5 text-xs text-ink-faint">
                    <Loader2 className="h-3 w-3 animate-spin" /> Reading…
                  </p>
                )}
              </CardContent>
            )}
          </Card>
        );
      })}
    </div>
  );
}
