"use client";

/**
 * Rendered analysis of one uploaded report.
 *
 * What is shown depends entirely on what kind of document it is, because the
 * three kinds are read by three different analysers and only one of them
 * produces measurements. A prescription has no reference ranges and a scan
 * report has no numbers worth comparing; showing either through the table of
 * measured values is how "PAN 40 MG" came to be flagged as an abnormal result
 * against a range of 1.0 to 0.0.
 *
 * The other rule this file exists to enforce: when the backend says a
 * document is unclear, that is all the doctor sees. No partial table, no
 * salvaged bullet points, no summary written around the doubt. One sentence
 * telling them to read the original, and the button to open it.
 */
import {
  AlertTriangle,
  Eye,
  FileWarning,
  HelpCircle,
  Info,
  Pill,
  Scan,
  Sparkles,
  Stethoscope,
} from "lucide-react";
import type {
  AbnormalFlag,
  InvestigationReport,
  MedicineRead,
  ReportResult,
} from "@/lib/investigationTypes";
import { FLAG_LABEL } from "@/lib/investigationTypes";
import { AiBadge } from "@/components/dashboard/badges";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const FLAG_STYLE: Record<AbnormalFlag, string> = {
  normal: "text-ink",
  low: "text-marigold-deep font-semibold",
  high: "text-marigold-deep font-semibold",
  critical_low: "text-clay font-bold",
  critical_high: "text-clay font-bold",
  abnormal: "text-clay font-semibold",
  unknown: "text-ink-faint",
};

const FLAG_BADGE: Record<AbnormalFlag, "success" | "warning" | "danger" | "outline"> = {
  normal: "success",
  low: "warning",
  high: "warning",
  critical_low: "danger",
  critical_high: "danger",
  abnormal: "danger",
  unknown: "outline",
};

/* -------------------------------------------------------------- unclear -- */

/**
 * The whole of what a doctor sees for a document we could not read.
 *
 * Deliberately not styled as an error: the upload worked, the file is intact
 * and openable. What failed is our reading of it, and the honest response to
 * that is to say so and get out of the way.
 */
function UnclearCard({
  reason,
  onOpenOriginal,
}: {
  reason?: string | null;
  onOpenOriginal?: () => void;
}) {
  return (
    <Card className="border-marigold/50 bg-marigold/[0.05]">
      <CardContent className="flex items-start gap-3 p-4">
        <HelpCircle className="mt-0.5 h-5 w-5 shrink-0 text-marigold-deep" />
        <div className="min-w-0">
          <p className="font-display text-[15px] font-semibold text-ink">
            Report unclear — please go through it manually.
          </p>
          {reason && (
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">{reason}</p>
          )}
          <p className="mt-2 text-xs text-ink-faint">
            Nothing on this document has been interpreted, and no values have been
            checked against any reference range.
          </p>
          {onOpenOriginal && (
            <button
              type="button"
              onClick={onOpenOriginal}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-pine px-3 py-1.5 text-xs font-semibold text-mint transition hover:bg-pine-deep"
            >
              <Eye className="h-3.5 w-3.5" /> Open the original
            </button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/* --------------------------------------------------------- prescription -- */

function MedicineRow({ medicine }: { medicine: MedicineRead }) {
  const schedule = [
    medicine.strength,
    medicine.dose_notation,
    medicine.frequency,
    medicine.duration,
    medicine.timing,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex items-start gap-2.5 border-b border-border py-2 last:border-0">
      <Pill className="mt-1 h-3.5 w-3.5 shrink-0 text-pine/60" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">
          {medicine.name}
          {/* Kept beside the name rather than replacing it: the doctor should
              be able to see that the page said "PAN" and we resolved it. */}
          {medicine.read_as && (
            <span className="ml-1.5 text-[11px] font-normal text-ink-faint">
              written as “{medicine.read_as}”
            </span>
          )}
        </p>
        {schedule && (
          <p className="mt-0.5 text-xs text-ink-muted">{schedule}</p>
        )}
        {medicine.ingredients.length > 0 && (
          <p className="text-[11px] text-ink-faint">
            {medicine.ingredients.join(" + ")}
          </p>
        )}
      </div>
    </div>
  );
}

function PrescriptionView({ report }: { report: InvestigationReport }) {
  const reading = report.analysis?.prescription;
  if (!reading) return null;

  return (
    <div className="space-y-3">
      {reading.problems.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
            <Stethoscope className="h-4 w-4 text-pine" />
            <CardTitle>Problems written on this prescription</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {reading.problems.map((problem) => (
                <li key={problem} className="flex gap-2 text-sm text-ink">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-pine/50" />
                  {/* Quoted exactly as written. Rewording somebody else's
                      diagnosis would be authoring a clinical opinion. */}
                  {problem}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-ink-faint">
              Copied word for word from the page.
            </p>
          </CardContent>
        </Card>
      )}

      {reading.medicines.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle>
              Medicines
              <span className="ml-2 text-xs font-normal text-ink-muted">
                {reading.medicines.length} recognised
              </span>
            </CardTitle>
            <span className="text-[11px] text-ink-faint">Matched to the formulary</span>
          </CardHeader>
          <CardContent className="pt-1">
            {reading.medicines.map((medicine, index) => (
              <MedicineRow key={`${medicine.name}-${index}`} medicine={medicine} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Anything not certain is shown as the printed line first. The
          suggested name is offered as a question, never as a heading. */}
      {reading.possible_medicines.length > 0 && (
        <Card className="border-marigold/40">
          <CardHeader className="pb-1">
            <CardTitle className="text-marigold-deep">
              Not certain — please check these against the original
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-1">
            {reading.possible_medicines.map((medicine, index) => (
              <div
                key={`${medicine.raw_line}-${index}`}
                className="border-b border-border py-2 last:border-0"
              >
                <p className="font-mono text-sm text-ink">{medicine.raw_line}</p>
                <p className="mt-0.5 text-xs text-ink-muted">
                  This may be <span className="font-medium">{medicine.name}</span>, but the
                  name on the page did not match exactly.
                </p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {reading.unidentified_lines.length > 0 && (
        <Card className="border-marigold/40">
          <CardHeader className="pb-1">
            <CardTitle className="text-marigold-deep">
              Could not be read ({reading.unidentified_lines.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-1">
            <p className="mb-2 text-xs text-ink-muted">
              These lines look like medicines but matched nothing known. Shown exactly
              as they came off the page.
            </p>
            {reading.unidentified_lines.map((line, index) => (
              <p
                key={`${line}-${index}`}
                className="border-b border-border py-1.5 font-mono text-sm text-ink last:border-0"
              >
                {line}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] leading-relaxed text-ink-faint">
        Read from the page by optical character recognition and matched against the
        hospital formulary. No interpretation has been added and no doses have been
        checked. The original is the authority.
      </p>
    </div>
  );
}

/* --------------------------------------------------------------- imaging -- */

function ImagingView({ report }: { report: InvestigationReport }) {
  const reading = report.analysis?.imaging;
  if (!reading) return null;

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-2">
          <Scan className="h-4 w-4 text-pine" />
          <CardTitle>
            Impression
            {reading.modality && (
              <span className="ml-2 text-xs font-normal text-ink-muted">
                {reading.modality}
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {/* Quoted, not summarised. Dropping a word like "acute" from a
              radiologist's conclusion changes what it says about the patient. */}
          <blockquote className="border-l-2 border-pine/30 pl-3">
            {reading.impression.map((line, index) => (
              <p key={index} className="text-sm leading-relaxed text-ink">
                {line}
              </p>
            ))}
          </blockquote>
          <p className="mt-2 text-[11px] text-ink-faint">
            The reporting radiologist&apos;s own words, copied from the report.
            Nothing has been interpreted or added.
          </p>
        </CardContent>
      </Card>

      {reading.findings.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Findings</CardTitle>
          </CardHeader>
          <CardContent>
            {reading.findings.map((line, index) => (
              <p key={index} className="text-sm leading-relaxed text-ink-muted">
                {line}
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ lab report -- */

function ResultRow({ result }: { result: ReportResult }) {
  const abnormal = result.flag !== "normal" && result.flag !== "unknown";
  const critical = result.flag === "critical_low" || result.flag === "critical_high";
  return (
    <tr
      className={cn(
        "border-b border-border last:border-0",
        critical && "bg-clay/[0.06]",
        abnormal && !critical && "bg-marigold/[0.06]"
      )}
    >
      <td className="py-2 pl-3 pr-2">
        <span className="text-sm text-ink">{result.display_name}</span>
        {result.printed_name !== result.display_name && (
          <span className="block text-[11px] text-ink-faint">
            as printed: {result.printed_name}
          </span>
        )}
      </td>
      <td className={cn("tabular whitespace-nowrap px-2 py-2 text-sm", FLAG_STYLE[result.flag])}>
        {result.value ?? result.value_text ?? "—"}
        {result.unit ? (
          <span className="ml-1 text-xs font-normal text-ink-muted">{result.unit}</span>
        ) : null}
      </td>
      <td className="tabular whitespace-nowrap px-2 py-2 text-xs text-ink-muted">
        {result.reference_text ?? "—"}
        {result.reference_source === "builtin" && (
          <span className="ml-1 text-[10px] uppercase text-ink-faint">(standard)</span>
        )}
      </td>
      <td className="px-2 py-2 pr-3 text-right">
        {result.flag !== "normal" && (
          <Badge variant={FLAG_BADGE[result.flag]} size="sm">
            {FLAG_LABEL[result.flag]}
          </Badge>
        )}
        {result.deviation_note && (
          <span className="mt-0.5 block text-[10px] text-ink-faint">
            {result.deviation_note}
          </span>
        )}
      </td>
    </tr>
  );
}

function LabReportView({ report }: { report: InvestigationReport }) {
  const analysis = report.analysis;
  const summary = analysis?.summary;
  const results = analysis?.results ?? [];
  const abnormalCount = analysis?.abnormal_count ?? 0;
  const criticalCount = analysis?.critical_count ?? 0;
  const uninterpreted = analysis?.uninterpreted_lines ?? [];

  const grouped = results.reduce<Record<string, ReportResult[]>>((accumulator, result) => {
    const key = result.section ?? "Results";
    (accumulator[key] ||= []).push(result);
    return accumulator;
  }, {});

  return (
    <div className="space-y-4">
      {criticalCount > 0 && (
        <div className="flex items-start gap-2.5 rounded-lg bg-clay px-4 py-3 text-white">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="text-sm font-semibold">
              {criticalCount} critical {criticalCount === 1 ? "value" : "values"} in this
              report
            </p>
            <p className="text-xs text-white/85">
              {(analysis?.critical ?? []).map((r) => r.display_name).join(", ")}
            </p>
          </div>
        </div>
      )}

      {summary && (
        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0 pb-3">
            <div className="min-w-0">
              <CardTitle>Report summary</CardTitle>
              {summary.report_type && (
                <p className="text-xs text-ink-muted">{summary.report_type}</p>
              )}
            </div>
            <AiBadge />
          </CardHeader>
          <CardContent className="space-y-3">
            {summary.headline && (
              <p className="border-l-2 border-marigold pl-3 font-display text-[15px] font-semibold leading-snug text-pine">
                {summary.headline}
              </p>
            )}
            {summary.doctor_summary && (
              <p className="text-sm leading-relaxed text-ink">{summary.doctor_summary}</p>
            )}

            {summary.key_findings && summary.key_findings.length > 0 && (
              <div className="space-y-1.5">
                <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                  Key findings
                </p>
                {summary.key_findings.map((finding, index) => (
                  <div key={index} className="flex items-start gap-2">
                    <span
                      className={cn(
                        "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                        finding.severity === "urgent" && "bg-clay",
                        finding.severity === "significant" && "bg-marigold-deep",
                        finding.severity === "notable" && "bg-pine/50",
                        finding.severity === "incidental" && "bg-ink-faint/50"
                      )}
                    />
                    <p className="text-sm text-ink">
                      {finding.finding}
                      {finding.significance && (
                        <span className="text-ink-muted"> — {finding.significance}</span>
                      )}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {summary.patterns_noticed && summary.patterns_noticed.length > 0 && (
              <div className="rounded-lg bg-mint p-3">
                <p className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-pine">
                  <Sparkles className="h-3 w-3" /> Patterns
                </p>
                <ul className="space-y-1">
                  {summary.patterns_noticed.map((pattern) => (
                    <li key={pattern} className="text-xs text-ink-muted">
                      {pattern}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {summary.comparison_with_previous && (
              <div className="rounded-lg border border-border p-3">
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                  Compared with the previous version
                </p>
                <p className="text-sm text-ink">{summary.comparison_with_previous}</p>
              </div>
            )}

            {summary.suggested_next_steps && summary.suggested_next_steps.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                  Suggested next steps{" "}
                  <span className="text-marigold-deep">(AI suggestion)</span>
                </p>
                <ul className="space-y-1">
                  {summary.suggested_next_steps.map((step) => (
                    <li key={step} className="flex gap-2 text-sm text-ink-muted">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-pine/40" />
                      {step}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {summary.limitations && (
              <p className="flex items-start gap-1.5 text-xs text-ink-faint">
                <Info className="mt-0.5 h-3 w-3 shrink-0" />
                {summary.limitations}
              </p>
            )}
            <p className="border-t border-border pt-2 text-[11px] leading-relaxed text-ink-muted">
              {summary.disclaimer}
            </p>
          </CardContent>
        </Card>
      )}

      {analysis?.summary_error && (
        <Card className="border-marigold/40 bg-marigold/[0.04] p-3">
          <p className="text-xs text-marigold-deep">
            The narrative summary could not be generated for this report. The measured
            values below were still compared against reference ranges.
          </p>
        </Card>
      )}

      {results.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle>
              Measured values
              {abnormalCount > 0 && (
                <span className="ml-2 text-xs font-normal text-clay">
                  {abnormalCount} outside range
                </span>
              )}
            </CardTitle>
            <span className="text-[11px] text-ink-faint">
              Compared arithmetically, not by AI
            </span>
          </CardHeader>
          <CardContent className="p-0">
            {Object.entries(grouped).map(([section, rows]) => (
              <div key={section}>
                <p className="bg-mint/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                  {section}
                </p>
                <table className="w-full">
                  <thead className="sr-only">
                    <tr>
                      <th>Test</th>
                      <th>Value</th>
                      <th>Reference</th>
                      <th>Flag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((result, index) => (
                      <ResultRow key={`${result.printed_name}-${index}`} result={result} />
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Lines carrying numbers that could not be read as measurements. A
          doctor who can see that four lines were skipped knows to open the
          original; one shown a tidy table of nine rows does not. */}
      {uninterpreted.length > 0 && (
        <Card className="border-marigold/40">
          <CardHeader className="pb-1">
            <CardTitle className="text-marigold-deep">
              {uninterpreted.length} line
              {uninterpreted.length === 1 ? "" : "s"} could not be read as a result
            </CardTitle>
          </CardHeader>
          <CardContent className="pt-1">
            <p className="mb-2 text-xs text-ink-muted">
              These carried numbers but no recognisable test or range, so nothing was
              compared. Shown as they came off the page.
            </p>
            {uninterpreted.map((line, index) => (
              <p
                key={`${line}-${index}`}
                className="border-b border-border py-1 font-mono text-xs text-ink-muted last:border-0"
              >
                {line}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      {analysis?.narrative_lines && analysis.narrative_lines.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Reporting doctor&apos;s remarks</CardTitle>
          </CardHeader>
          <CardContent>
            {analysis.narrative_lines.map((line, index) => (
              <p key={index} className="text-sm italic text-ink">
                {line}
              </p>
            ))}
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] text-ink-faint">
        Extracted by {analysis?.extraction?.method ?? "unknown method"}
        {analysis?.extraction?.page_count
          ? ` · ${analysis.extraction.page_count} page(s)`
          : ""}
        {typeof analysis?.recognised_rate === "number"
          ? ` · ${Math.round(analysis.recognised_rate * 100)}% of values matched a known analyte`
          : ""}
      </p>
    </div>
  );
}

/* ----------------------------------------------------------------- root -- */

export function ReportAnalysisView({
  report,
  onOpenOriginal,
}: {
  report: InvestigationReport;
  onOpenOriginal?: () => void;
}) {
  const analysis = report.analysis;
  const clarity = analysis?.clarity;

  // Extraction never produced anything at all — a corrupt file, an
  // unsupported type, or OCR unavailable on this server.
  if (report.status === "failed" && !analysis?.unclear_reason) {
    return (
      <Card className="border-marigold/40 bg-marigold/[0.04]">
        <CardContent className="flex items-start gap-3 p-4">
          <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-marigold-deep" />
          <div>
            <p className="text-sm font-semibold text-ink">No readable text in this file</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              {report.error_detail ??
                "The file is stored and can be downloaded, but nothing could be extracted from it."}
            </p>
            {analysis?.extraction?.warning && (
              <p className="mt-1 text-xs text-marigold-deep">
                {analysis.extraction.warning}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  // The backend declined to interpret this. That verdict is final here: no
  // partial results are shown alongside it.
  if (clarity === "unclear") {
    return (
      <UnclearCard reason={analysis?.unclear_reason} onOpenOriginal={onOpenOriginal} />
    );
  }

  if (clarity === "not_analysed") {
    return (
      <Card>
        <CardContent className="flex items-start gap-3 p-4">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" />
          <div>
            <p className="text-sm font-medium text-ink">Attached, not read</p>
            <p className="mt-0.5 text-xs text-ink-muted">
              {analysis?.unclear_reason ??
                "There is no automatic reading for this kind of document."}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  switch (analysis?.document_kind) {
    case "prescription":
      return <PrescriptionView report={report} />;
    case "imaging":
      return <ImagingView report={report} />;
    case "lab_report":
      return <LabReportView report={report} />;
    default:
      // Analyses stored before document kinds existed carry measured values
      // and no kind. They were produced by the laboratory parser, so that is
      // how they are rendered.
      return <LabReportView report={report} />;
  }
}
