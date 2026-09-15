"use client";

/**
 * A patient's diet on the case sheet.
 *
 * What the kitchen is sending now, what is scheduled next, and every change
 * during the stay. A new order closes the previous one at the moment the new
 * one starts, so "nil by mouth from midnight" can be written the evening
 * before without taking tonight's dinner away.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, UtensilsCrossed } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { AdmissionDiet, DietMode } from "@/lib/types/diet";
import { canOrderDiet } from "@/lib/types/diet";
import { formatDateTime } from "@/lib/format";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

export function DietPanel({ admissionId, active }: { admissionId: string; active: boolean }) {
  const { user } = useAuth();
  const mayOrder = active && canOrderDiet(user?.role);
  const [diet, setDiet] = useState<AdmissionDiet | null>(null);
  const [modes, setModes] = useState<DietMode[]>([]);
  const [ordering, setOrdering] = useState(false);
  const [modeId, setModeId] = useState("");
  const [instructions, setInstructions] = useState("");
  const [startNow, setStartNow] = useState(true);
  const [startsAt, setStartsAt] = useState("");
  const [stopping, setStopping] = useState(false);
  const [reason, setReason] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setDiet(await staffApi.admissionDiet(admissionId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The diet could not be loaded.");
    }
  }, [admissionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (ordering && modes.length === 0) void staffApi.dietModes().then(setModes).catch(() => undefined);
  }, [ordering, modes.length]);

  async function placeOrder() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.orderDiet(admissionId, {
        mode_id: modeId,
        instructions: instructions.trim() || null,
        starts_at: startNow || !startsAt ? null : new Date(startsAt).toISOString(),
      });
      setOrdering(false);
      setModeId("");
      setInstructions("");
      setStartNow(true);
      setStartsAt("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The diet could not be ordered.");
    } finally {
      setBusy(false);
    }
  }

  async function stop() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.stopDiet(admissionId, reason.trim());
      setStopping(false);
      setReason("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The diet order could not be stopped.");
    } finally {
      setBusy(false);
    }
  }

  const current = diet?.current ?? null;
  const upcoming = diet?.upcoming ?? null;
  const openOrder = upcoming ?? (current && !current.ends_at ? current : null);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="flex items-center gap-2">
          <UtensilsCrossed className="h-4 w-4 text-pine" /> Diet
        </CardTitle>
        {mayOrder && !ordering && !stopping && (
          <div className="flex gap-2">
            {openOrder && (
              <Button size="sm" variant="ghost" onClick={() => setStopping(true)}>Stop</Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setOrdering(true)}>
              {current || upcoming ? "Change diet" : "Order diet"}
            </Button>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {error && <p className="text-clay">{error}</p>}
        {diet === null && !error && <p className="text-ink-muted">Loading…</p>}

        {diet && (
          <div className="flex flex-wrap items-start gap-6">
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-faint">Now</p>
              {current ? (
                <>
                  <p className={current.is_nil_by_mouth ? "font-display text-lg font-semibold text-clay"
                    : "font-display text-lg font-semibold text-ink"}>
                    {current.mode_name}
                  </p>
                  {current.instructions && <p className="text-ink-muted">{current.instructions}</p>}
                  <p className="text-xs text-ink-faint">
                    Since {formatDateTime(current.starts_at)} · {current.ordered_by_name}
                    {current.ends_at ? ` · until ${formatDateTime(current.ends_at)}` : ""}
                  </p>
                </>
              ) : (
                <p className="font-medium text-clay">No diet ordered</p>
              )}
            </div>
            {upcoming && (
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-faint">Next</p>
                <p className="font-medium text-ink">{upcoming.mode_name}</p>
                {upcoming.instructions && <p className="text-ink-muted">{upcoming.instructions}</p>}
                <p className="text-xs text-ink-faint">From {formatDateTime(upcoming.starts_at)}</p>
              </div>
            )}
          </div>
        )}

        {ordering && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <select className={SELECT} value={modeId} onChange={(e) => setModeId(e.target.value)}>
              <option value="">Choose a diet…</option>
              {modes.map((mode) => (
                <option key={mode.id} value={mode.id}>{mode.name}</option>
              ))}
            </select>
            <Input
              placeholder="Instructions for the kitchen, e.g. low salt, no sugar"
              value={instructions}
              maxLength={500}
              onChange={(e) => setInstructions(e.target.value)}
            />
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2">
                <input type="radio" checked={startNow} onChange={() => setStartNow(true)} /> Start now
              </label>
              <label className="flex items-center gap-2">
                <input type="radio" checked={!startNow} onChange={() => setStartNow(false)} /> Start at
              </label>
              {!startNow && (
                <Input type="datetime-local" className="w-56" value={startsAt}
                       onChange={(e) => setStartsAt(e.target.value)} />
              )}
            </div>
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || !modeId || (!startNow && !startsAt)} onClick={() => void placeOrder()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Order
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setOrdering(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {stopping && openOrder && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p>
              Stop <span className="font-medium">{openOrder.mode_name}</span>
              {openOrder.upcoming ? " before it starts" : ""}? The kitchen will show no diet order.
            </p>
            <Input placeholder="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || reason.trim().length < 3} onClick={() => void stop()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Stop diet
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStopping(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {diet && diet.orders.length > 0 && (
          <div>
            <button className="text-xs font-medium text-pine hover:underline" onClick={() => setShowHistory((v) => !v)}>
              {showHistory ? "Hide" : "Show"} diet history ({diet.orders.length})
            </button>
            {showHistory && (
              <ul className="mt-2 divide-y divide-border rounded-lg border border-border">
                {diet.orders.map((order) => (
                  <li key={order.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2">
                    <span className="font-medium">{order.mode_name}</span>
                    {order.in_effect && <Badge>Now</Badge>}
                    {order.upcoming && <Badge variant="outline">Next</Badge>}
                    <span className="text-xs text-ink-muted">
                      {formatDateTime(order.starts_at)} → {order.ends_at ? formatDateTime(order.ends_at) : "open"}
                    </span>
                    <span className="text-xs text-ink-faint">by {order.ordered_by_name}</span>
                    {order.instructions && <span className="w-full text-xs text-ink-muted">{order.instructions}</span>}
                    {order.end_reason && (
                      <span className="w-full text-xs text-ink-faint">
                        Ended: {order.end_reason}{order.ended_by_name ? ` (${order.ended_by_name})` : ""}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
