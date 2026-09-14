"use client";

/**
 * Verified laboratory results for one patient, as a doctor reads them.
 *
 * Only verified results appear. Abnormal values are marked the way the printed
 * report marks them; a value that was not compared against a range carries no
 * mark at all, because no mark must never be read as "normal".
 */
import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Loader2, Printer } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientLabResult } from "@/lib/labTypes";
import { FLAG_MARK, isAbnormal, isCritical } from "@/lib/labTypes";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function LabResultsPanel({
  patientId,
  admissionId,
  title = "Lab results",
}: {
  patientId: string;
  admissionId?: string;
  title?: string;
}) {
  const [results, setResults] = useState<PatientLabResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [printing, setPrinting] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    staffApi
      .patientLabResults(patientId, admissionId)
      .then((rows) => live && setResults(rows))
      .catch((err) => live && setError(err instanceof Error ? err.message : "Lab results could not be loaded."));
    return () => {
      live = false;
    };
  }, [patientId, admissionId]);

  const requests = useMemo(() => {
    const grouped = new Map<string, PatientLabResult[]>();
    for (const row of results ?? []) {
      const list = grouped.get(row.request_id) ?? [];
      list.push(row);
      grouped.set(row.request_id, list);
    }
    return Array.from(grouped.entries());
  }, [results]);

  async function print(requestId: string) {
    setPrinting(requestId);
    try {
      const url = URL.createObjectURL(await staffApi.labReportPdf(requestId));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The report could not be printed.");
    } finally {
      setPrinting(null);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <FlaskConical className="h-4 w-4 text-pine" />
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p className="text-sm text-clay">{error}</p>}
        {results === null && !error && <p className="text-sm text-ink-muted">Loading…</p>}
        {results !== null && results.length === 0 && <p className="text-sm text-ink-muted">No verified lab results yet.</p>}
        {requests.map(([requestId, tests]) => (
          <div key={requestId} className="space-y-2 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm">
                <span className="font-mono font-semibold text-pine">{tests[0].lab_number}</span>
                <span className="text-ink-muted">
                  {" "}
                  · {formatDateTime(tests[0].registered_at)}
                  {tests[0].referred_by ? ` · ${tests[0].referred_by}` : ""}
                </span>
              </p>
              <Button size="sm" variant="ghost" disabled={printing === requestId} onClick={() => void print(requestId)}>
                {printing === requestId ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Printer className="h-3.5 w-3.5" />} Report
              </Button>
            </div>
            {tests.map((test) => (
              <div key={test.id}>
                <p className="text-sm font-medium text-ink">
                  {test.name}
                  <span className="ml-2 text-[11px] font-normal text-ink-faint">
                    verified {formatDateTime(test.verified_at)} · {test.verified_by_name}
                    {test.version > 1 ? ` · amended (v${test.version})` : ""}
                  </span>
                </p>
                {test.is_culture ? (
                  <div className="mt-1 text-sm">
                    {test.culture?.growth === "no_growth" && <p className="text-ink">No growth ({test.culture.specimen})</p>}
                    {(test.culture?.isolates ?? []).map((isolate, index) => (
                      <p key={index} className="text-ink">
                        <span className="italic">{isolate.organism}</span>
                        {isolate.colony_count ? ` · ${isolate.colony_count}` : ""}
                        {" — resistant: "}
                        <span className="font-semibold text-clay">
                          {isolate.antibiotics.filter((row) => row.result === "R").map((row) => row.name).join(", ") || "none"}
                        </span>
                        {"; sensitive: "}
                        {isolate.antibiotics.filter((row) => row.result === "S").map((row) => row.name).join(", ") || "none"}
                      </p>
                    ))}
                  </div>
                ) : (
                  <div className="mt-1 grid gap-x-6 gap-y-0.5 text-sm sm:grid-cols-2">
                    {test.results
                      .filter((row) => row.print && row.result_type !== "heading")
                      .map((row) => (
                        <p key={row.parameter_id} className="flex justify-between gap-2 border-b border-border/40 py-0.5">
                          <span className="text-ink-muted">{row.name}</span>
                          <span className={cn(isAbnormal(row.flag) ? "font-semibold text-clay" : "text-ink")}>
                            {row.value}
                            {row.unit ? ` ${row.unit}` : ""}
                            {row.flag && FLAG_MARK[row.flag] ? (
                              <span className={cn("ml-1 rounded px-1 text-[10px]", isCritical(row.flag) ? "bg-clay text-white" : "bg-clay/15")}>
                                {FLAG_MARK[row.flag]}
                              </span>
                            ) : null}
                          </span>
                        </p>
                      ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
