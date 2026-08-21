"use client";

/** Rendered analysis of one uploaded report: values, flags, AI narrative. */
import { AlertTriangle, FileWarning, Info, Sparkles } from "lucide-react";
import type { AbnormalFlag, InvestigationReport, ReportResult } from "@/lib/investigationTypes";
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
          <span className="block text-[11px] text-ink-faint">as printed: {result.printed_name}</span>
        )}
      </td>
      <td className={cn("tabular whitespace-nowrap px-2 py-2 text-sm", FLAG_STYLE[result.flag])}>
        {result.value ?? result.value_text ?? "—"}
        {result.unit ? <span className="ml-1 text-xs font-normal text-ink-muted">{result.unit}</span> : null}
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
          <span className="mt-0.5 block text-[10px] text-ink-faint">{result.deviation_note}</span>
        )}
      </td>
    </tr>
  );
}

export function ReportAnalysisView({ report }: { report: InvestigationReport }) {
  const analysis = report.analysis;
  const summary = analysis?.summary;
  const results = analysis?.results ?? [];
  const abnormalCount = analysis?.abnormal_count ?? 0;
  const criticalCount = analysis?.critical_count ?? 0;

  if (report.status === "failed" || (!results.length && !summary)) {
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
              <p className="mt-1 text-xs text-marigold-deep">{analysis.extraction.warning}</p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Group results by the section printed on the report.
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
              {criticalCount} critical {criticalCount === 1 ? "value" : "values"} in this report
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
                    <li key={pattern} className="text-xs text-ink-muted">{pattern}</li>
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
                  Suggested next steps <span className="text-marigold-deep">(AI suggestion)</span>
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
            The narrative summary could not be generated for this report. The measured values
            below were still compared against reference ranges.
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
                    <tr><th>Test</th><th>Value</th><th>Reference</th><th>Flag</th></tr>
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

      {analysis?.narrative_lines && analysis.narrative_lines.length > 0 && (
        <Card>
          <CardHeader className="pb-2"><CardTitle>Reporting doctor&apos;s remarks</CardTitle></CardHeader>
          <CardContent>
            {analysis.narrative_lines.map((line, index) => (
              <p key={index} className="text-sm italic text-ink">{line}</p>
            ))}
          </CardContent>
        </Card>
      )}

      <p className="text-[11px] text-ink-faint">
        Extracted by {analysis?.extraction?.method ?? "unknown method"}
        {analysis?.extraction?.page_count ? ` · ${analysis.extraction.page_count} page(s)` : ""}
        {typeof analysis?.recognised_rate === "number"
          ? ` · ${Math.round(analysis.recognised_rate * 100)}% of values matched a known analyte`
          : ""}
      </p>
    </div>
  );
}
