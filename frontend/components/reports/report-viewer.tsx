"use client";

/**
 * One screen for every report.
 *
 * The reports are declared on the server — their columns, their types, which
 * figures total. This renders whatever it is handed, so the lab and accounts
 * reports arriving in Parts 4 and 5 need no work here at all.
 *
 * Three things the old reports got right and are kept:
 *
 * **A totals footer that does not move.** It sums every row, including rows
 * whose column somebody has hidden, because the footer is the figure copied
 * into the day book.
 *
 * **Export matches the screen.** The CSV carries the visible columns in the
 * order shown. An export that quietly differed from what was on screen would
 * defeat the one thing it is used for — checking a figure.
 *
 * **Money right-aligned and tabular.** A column of rupees that does not line
 * up cannot be scanned, and scanning is what these are for.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  Columns3,
  Download,
  Loader2,
  RefreshCw,
  UserCheck,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type {
  ReportColumn,
  ReportDefinition,
  ReportResult,
} from "@/lib/types/emr";
import { formatINR } from "@/lib/types/emr";
import { formatDate, formatDateTime, hospitalToday, titleCase } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function renderCell(value: unknown, column: ReportColumn, isTotal = false) {
  if (value === null || value === undefined || value === "") return "—";
  switch (column.type) {
    case "money":
      // A dash rather than ₹0.00, the way a ledger is written: a column of
      // zeroes hides the two rows that actually moved money. The footer
      // still prints its zero, because a total of nothing is a statement.
      if (Number(value) === 0 && !isTotal) return "—";
      return formatINR(Number(value));
    case "date":
      return formatDate(String(value));
    case "datetime":
      return formatDateTime(String(value));
    case "status":
      return titleCase(String(value));
    default:
      return String(value);
  }
}

const NUMERIC = new Set(["money", "number"]);

async function download(url: string, filename: string) {
  // Fetched with the bearer token: the CSV route is authenticated, so a bare
  // link would download a 401 page named like a spreadsheet.
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) return;
  const blobUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 30_000);
}

export function ReportViewer({ canConfigure = false }: { canConfigure?: boolean }) {
  const [reports, setReports] = useState<ReportDefinition[]>([]);
  const [key, setKey] = useState("");
  const [from, setFrom] = useState(() => hospitalToday(-6));
  const [to, setTo] = useState(() => hospitalToday());
  const [mine, setMine] = useState(false);
  const [result, setResult] = useState<ReportResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showColumns, setShowColumns] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const found = await staffApi.reportCatalogue();
        setReports(found);
        setKey((current) => current || found[0]?.key || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load the reports.");
      }
    })();
  }, []);

  const spec = reports.find((item) => item.key === key);

  const load = useCallback(async () => {
    if (!key) return;
    setLoading(true);
    setError(null);
    try {
      setResult(await staffApi.runReport(key, { from, to, mine }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run that report.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [key, from, to, mine]);

  useEffect(() => {
    void load();
  }, [load]);

  // The server narrows these reports to the reader's own till when they do
  // not hold finance rights. It says so in the response, which is how this
  // screen knows not to offer a choice that has already been made.
  const forcedToOwnTill = Boolean(result?.scoped_to) && !mine;

  const shown = useMemo(
    () => (result?.columns ?? []).filter((column) => column.visible),
    [result]
  );

  const toggleColumn = useCallback(
    async (column: ReportColumn) => {
      if (!result) return;
      const next = result.columns.map((item) => ({
        column_key: item.key,
        visible: item.key === column.key ? !item.visible : item.visible,
        position: item.position,
      }));
      try {
        await staffApi.setReportColumns(result.key, next);
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not save that.");
      }
    },
    [result, load]
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-[220px] flex-1">
          <label className="text-[11px] uppercase tracking-wide text-ink-faint" htmlFor="rp-key">
            Report
          </label>
          <select
            id="rp-key"
            value={key}
            onChange={(event) => setKey(event.target.value)}
            className="mt-1 h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink"
          >
            {reports.map((item) => (
              <option key={item.key} value={item.key}>
                {item.title}
              </option>
            ))}
          </select>
        </div>

        {/* A single-day report shows one date box, not two that must match. */}
        {!spec?.single_day && (
          <div>
            <label className="text-[11px] uppercase tracking-wide text-ink-faint" htmlFor="rp-from">
              From
            </label>
            <Input
              id="rp-from"
              type="date"
              value={from}
              max={to}
              onChange={(event) => setFrom(event.target.value)}
              className="mt-1 h-9 text-sm"
            />
          </div>
        )}
        <div>
          <label className="text-[11px] uppercase tracking-wide text-ink-faint" htmlFor="rp-to">
            {spec?.single_day ? "Day" : "To"}
          </label>
          <Input
            id="rp-to"
            type="date"
            value={to}
            onChange={(event) => setTo(event.target.value)}
            className="mt-1 h-9 text-sm"
          />
        </div>

        {/* Hidden when the server is forcing the scope anyway: a checkbox
            that changes nothing is worse than no checkbox. */}
        {spec?.self_service && !forcedToOwnTill && (
          <label className="flex h-9 items-center gap-1.5 rounded-md border border-border bg-white px-2.5 text-xs text-ink-muted">
            <input
              type="checkbox"
              checked={mine}
              onChange={(event) => setMine(event.target.checked)}
            />
            <UserCheck className="h-3.5 w-3.5" />
            My till only
          </label>
        )}

        <Button variant="outline" size="sm" className="h-9" onClick={() => void load()}>
          <RefreshCw className="mr-1 h-3.5 w-3.5" />
          Refresh
        </Button>
        {canConfigure && result && (
          <Button
            variant="outline"
            size="sm"
            className="h-9"
            onClick={() => setShowColumns((open) => !open)}
          >
            <Columns3 className="mr-1 h-3.5 w-3.5" />
            Columns
          </Button>
        )}
        <Button
          size="sm"
          className="h-9"
          disabled={!result || result.row_count === 0}
          onClick={() =>
            void download(
              staffApi.reportCsvUrl(key, { from, to, mine }),
              `${key}-${from}-to-${to}.csv`
            )
          }
        >
          <Download className="mr-1 h-3.5 w-3.5" />
          CSV
        </Button>
      </div>

      {canConfigure && showColumns && result && (
        <div className="flex flex-wrap gap-1.5 rounded-xl border border-pine/10 bg-white p-3">
          <p className="w-full text-[11px] text-ink-faint">
            Choose what this report shows. Totals are unaffected — they are summed
            over every row whatever is hidden.
          </p>
          {result.columns.map((column) => (
            <button
              key={column.key}
              type="button"
              onClick={() => void toggleColumn(column)}
              className={cn(
                "rounded border px-2 py-1 text-[11px] transition",
                column.visible
                  ? "border-pine bg-mint text-pine"
                  : "border-border text-ink-faint hover:border-pine/40"
              )}
            >
              {column.label}
            </button>
          ))}
        </div>
      )}

      {spec && (
        <p className="text-xs text-ink-muted">
          {spec.description}
          {result?.scoped_to && (
            <span className="ml-1 text-marigold-deep">
              {" · "}showing {result.scoped_to}&apos;s till only
            </span>
          )}
        </p>
      )}

      {error && (
        <p className="rounded-md bg-clay/5 px-3 py-2 text-xs text-clay">{error}</p>
      )}

      <div className="overflow-x-auto rounded-xl border border-pine/10 bg-white">
        {loading && (
          <p className="flex items-center gap-1.5 px-4 py-8 text-xs text-ink-faint">
            <Loader2 className="h-3 w-3 animate-spin" /> Running…
          </p>
        )}

        {!loading && result && result.row_count === 0 && (
          <div className="flex flex-col items-center gap-1 px-4 py-12 text-center">
            <BarChart3 className="h-5 w-5 text-ink-faint" />
            <p className="text-sm text-ink-muted">Nothing in this period.</p>
          </div>
        )}

        {!loading && result && result.row_count > 0 && (
          <table className="w-full min-w-[720px] text-xs">
            <thead>
              <tr className="border-b border-pine/10 bg-mint-card">
                {shown.map((column) => (
                  <th
                    key={column.key}
                    className={cn(
                      "whitespace-nowrap px-3 py-2 text-[10px] uppercase tracking-wide text-ink-faint",
                      NUMERIC.has(column.type) ? "text-right" : "text-left"
                    )}
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, index) => (
                <tr
                  key={index}
                  className="border-b border-border last:border-b-0 hover:bg-mint/40"
                >
                  {shown.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "px-3 py-1.5",
                        NUMERIC.has(column.type)
                          ? "tabular whitespace-nowrap text-right text-ink"
                          : "text-ink-muted",
                        column.key.includes("out") && "text-clay"
                      )}
                    >
                      {renderCell(row[column.key], column)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-pine/20 bg-mint-card font-medium">
                {shown.map((column, index) => (
                  <td
                    key={column.key}
                    className={cn(
                      "px-3 py-2",
                      NUMERIC.has(column.type)
                        ? "tabular whitespace-nowrap text-right text-pine"
                        : "text-ink-faint"
                    )}
                  >
                    {column.key in result.totals
                      ? renderCell(result.totals[column.key], column, true)
                      : index === 0
                        ? `${result.row_count} row${result.row_count === 1 ? "" : "s"}`
                        : ""}
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        )}
      </div>
    </div>
  );
}
