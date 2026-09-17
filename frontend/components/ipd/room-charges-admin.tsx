"use client";

/**
 * Room charges: when they are posted, and whether this morning's run happened.
 *
 * Each morning after the census hour, bed and nursing charges are posted for
 * every admitted patient. Running it again by hand is safe — days already
 * charged are skipped — so "post now" is the answer to "the server was down
 * this morning", not a risk.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Receipt } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { RoomChargeRuns } from "@/lib/types/ipd";
import { formatDate, formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const STATUS_VARIANT = {
  done: "success", partial: "warning", running: "secondary", skipped: "outline", failed: "danger",
} as const;

export function RoomChargesAdmin() {
  const { user } = useAuth();
  const mayRun = user?.role === "admin" || user?.role === "manager";
  const [data, setData] = useState<RoomChargeRuns | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await staffApi.roomChargeRuns());
    } catch (err) {
      setError(err instanceof Error ? err.message : "The runs could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runNow() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.runRoomCharges();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The run could not be started.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
        <CardTitle className="mr-auto flex items-center gap-2"><Receipt className="h-4 w-4" /> Room charges</CardTitle>
        {mayRun && (
          <Button size="sm" disabled={busy} onClick={() => void runNow()}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Post room charges now
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {data && (
          <p className="text-sm text-ink-muted">
            {data.enabled
              ? `Posted automatically every morning at ${data.run_at}, after the 8 am census. Days already charged are never charged twice.`
              : "Automatic posting is switched off on this server. Post charges by hand."}
          </p>
        )}
        {error && <p className="text-sm text-clay">{error}</p>}
        {!data ? (
          <Skeleton className="h-24 w-full rounded-lg" />
        ) : data.runs.length === 0 ? (
          <p className="text-sm text-ink-muted">No runs yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-muted">
                  <th className="py-1.5 pr-3 font-medium">Day</th>
                  <th className="py-1.5 pr-3 font-medium">Status</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Admissions</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Charges posted</th>
                  <th className="py-1.5 pr-3 font-medium">Run by</th>
                  <th className="py-1.5 font-medium">Finished</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.runs.map((run) => (
                  <tr key={run.id} className="align-top">
                    <td className="py-1.5 pr-3">{formatDate(run.run_on)}</td>
                    <td className="py-1.5 pr-3">
                      <Badge variant={STATUS_VARIANT[run.status]} size="sm">{run.status}</Badge>
                      {run.error && <p className="text-xs text-clay">{run.error}</p>}
                      {(run.summary.failed ?? []).map((item) => (
                        <p key={item.ip_number} className="text-xs text-clay">{item.ip_number}: {item.error}</p>
                      ))}
                    </td>
                    <td className="tabular py-1.5 pr-3 text-right">{run.summary.admissions ?? "—"}</td>
                    <td className="tabular py-1.5 pr-3 text-right">{run.summary.charges_posted ?? "—"}</td>
                    <td className="py-1.5 pr-3">{run.triggered_by === "schedule" ? "Automatic" : run.triggered_by}</td>
                    <td className="py-1.5">{run.finished_at ? formatDateTime(run.finished_at) : "Running"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
