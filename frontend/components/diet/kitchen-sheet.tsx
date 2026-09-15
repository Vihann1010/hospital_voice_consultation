"use client";

/**
 * The kitchen's sheet for a day.
 *
 * Trays per diet per meal at the top — what the kitchen cooks — and bed by
 * bed below — where each tray goes. A patient with no diet order is shown in
 * red rather than left off, and a patient on leave at mealtime is marked so no
 * tray goes to an empty bed.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Printer, RefreshCw } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { KitchenMealCell, KitchenSheet as Sheet } from "@/lib/types/diet";
import { formatDate, formatTime, hospitalToday } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function Cell({ cell }: { cell?: KitchenMealCell }) {
  if (!cell || cell.state === "absent") return <span className="text-ink-faint">—</span>;
  if (cell.state === "on_leave") return <span className="font-medium text-marigold-deep">On leave</span>;
  if (cell.state === "no_order") return <span className="font-semibold text-clay">NO DIET ORDER</span>;
  return (
    <span className={cn("font-medium", cell.nil_by_mouth ? "text-clay" : "text-ink")}>{cell.diet}</span>
  );
}

export function KitchenSheet() {
  const [on, setOn] = useState(hospitalToday());
  const [sheet, setSheet] = useState<Sheet | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSheet(await staffApi.kitchenSheet(on));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The diet sheet could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [on]);

  useEffect(() => {
    void load();
  }, [load]);

  const missing = sheet
    ? sheet.rows.filter((row) => Object.values(row.meals).some((cell) => cell.state === "no_order")).length
    : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 print-hidden">
        <Input type="date" className="w-44" value={on} onChange={(e) => setOn(e.target.value)} />
        <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Refresh
        </Button>
        <Button variant="outline" size="sm" onClick={() => window.print()} disabled={!sheet}>
          <Printer className="h-4 w-4" /> Print
        </Button>
        {missing > 0 && (
          <p className="text-sm font-medium text-clay">
            {missing} patient{missing === 1 ? " has" : "s have"} no diet order for at least one meal.
          </p>
        )}
      </div>
      {error && <p className="text-sm text-clay">{error}</p>}

      {sheet && (
        <>
          <h2 className="hidden font-display text-lg font-semibold print:block">
            Kitchen diet sheet — {formatDate(sheet.on)}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sheet.meals.map((meal) => {
              const counts = Object.entries(sheet.counts[meal.label] ?? {}).sort((a, b) => b[1] - a[1]);
              const total = counts.reduce((sum, [, n]) => sum + n, 0);
              return (
                <Card key={meal.label}>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-baseline justify-between">
                      <span>{meal.label}</span>
                      <span className="text-xs font-normal text-ink-muted">{formatTime(meal.at)} · {total} trays</span>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    {counts.length === 0 && <p className="text-ink-muted">Nobody to serve.</p>}
                    {counts.map(([name, count]) => (
                      <div key={name} className="flex justify-between">
                        <span className={name === "No diet order" ? "font-semibold text-clay" : ""}>{name}</span>
                        <span className="tabular font-medium">{count}</span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              );
            })}
          </div>

          <Card>
            <CardContent className="overflow-x-auto p-0">
              <table className="w-full min-w-[760px] text-sm">
                <thead>
                  <tr className="border-b border-border bg-mint/50 text-left text-xs uppercase tracking-wide text-ink-faint">
                    <th className="px-3 py-2">Bed</th>
                    <th className="px-3 py-2">Patient</th>
                    {sheet.meals.map((meal) => (
                      <th key={meal.label} className="px-3 py-2">{meal.label}</th>
                    ))}
                    <th className="px-3 py-2">Instructions</th>
                    <th className="px-3 py-2">Allergies</th>
                  </tr>
                </thead>
                <tbody>
                  {sheet.rows.length === 0 && (
                    <tr>
                      <td colSpan={sheet.meals.length + 4} className="px-3 py-6 text-center text-ink-muted">
                        No inpatients on this day.
                      </td>
                    </tr>
                  )}
                  {sheet.rows.map((row) => (
                    <tr key={row.admission_id} className="border-b border-border last:border-0 align-top">
                      <td className="px-3 py-2">
                        <p className="font-medium">{row.bed || "—"}</p>
                        <p className="text-xs text-ink-muted">{row.ward}</p>
                      </td>
                      <td className="px-3 py-2">
                        <p className="font-medium">{row.patient_name}</p>
                        <p className="text-xs text-ink-muted">
                          {row.ip_number} · {row.age ?? "?"}/{(row.gender ?? "").slice(0, 1).toUpperCase()}
                        </p>
                      </td>
                      {sheet.meals.map((meal) => (
                        <td key={meal.label} className="px-3 py-2"><Cell cell={row.meals[meal.label]} /></td>
                      ))}
                      <td className="px-3 py-2 text-ink-muted">{row.instructions || "—"}</td>
                      <td className={cn("px-3 py-2", row.allergies.length ? "font-medium text-clay" : "text-ink-faint")}>
                        {row.allergies.length ? row.allergies.join(", ") : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
