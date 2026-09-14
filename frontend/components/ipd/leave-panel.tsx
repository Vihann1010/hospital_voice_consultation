"use client";

/**
 * Leave from the ward.
 *
 * The patient stays admitted. Keeping the bed holds it for them and it is
 * charged as usual; releasing it frees it for someone else, it is not charged,
 * and a bed is chosen when they come back. Doses that fall due while they are
 * away show as "on leave" and cannot be signed; on return they are recorded as
 * not given.
 */
import { useEffect, useState } from "react";
import { DoorOpen, Loader2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { AdmissionChart } from "@/lib/ipdTypes";
import { formatDate, formatDateTime, hospitalToday } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

export function LeavePanel({ chart, onChanged }: { chart: AdmissionChart; onChanged: () => void }) {
  const leaves = chart.leaves ?? [];
  const away = leaves.find((leave) => !leave.returned_at) ?? null;
  const admitted = chart.admission.status === "admitted";

  const [starting, setStarting] = useState(false);
  const [reason, setReason] = useState("");
  const [expected, setExpected] = useState("");
  const [keepBed, setKeepBed] = useState(true);
  const [note, setNote] = useState("");
  const [bedId, setBedId] = useState("");
  const [beds, setBeds] = useState<{ id: string; label: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    if (!away || away.bed_retained) return;
    void staffApi.wardBoard().then(({ wards }) =>
      setBeds(wards.flatMap((ward) => ward.beds.filter((bed) => bed.status === "vacant")
        .map((bed) => ({ id: bed.id, label: `${ward.name} · ${bed.label}` }))))
    ).catch(() => undefined);
  }, [away]);

  if (!away && !admitted && leaves.length === 0) return null;

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.startLeave(chart.admission.id, {
        reason: reason.trim(), expected_return_on: expected || null, bed_retained: keepBed,
      });
      setStarting(false);
      setReason("");
      setExpected("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The leave could not be recorded.");
    } finally {
      setBusy(false);
    }
  }

  async function back() {
    setBusy(true);
    setError(null);
    try {
      const result = await staffApi.returnFromLeave(chart.admission.id, { bed_id: bedId || null, note: note.trim() || null });
      setNotice(result.missed_doses_recorded
        ? `Back. ${result.missed_doses_recorded} dose(s) due while away were recorded as not given.`
        : "Back.");
      setNote("");
      setBedId("");
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The return could not be recorded.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className={away ? "border-marigold/50" : undefined}>
      <CardHeader className="flex flex-row items-center gap-2 pb-2">
        <CardTitle className="mr-auto flex items-center gap-2"><DoorOpen className="h-4 w-4" /> Leave</CardTitle>
        {!away && admitted && !starting && (
          <Button size="sm" variant="outline" onClick={() => setStarting(true)}>Send on leave</Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {away && (
          <div className="space-y-2 rounded-md bg-marigold/10 p-3">
            <p className="font-medium text-marigold-deep">
              On leave since {formatDateTime(away.started_at)}
              {away.expected_return_on ? ` · expected back ${formatDate(away.expected_return_on)}` : ""}
            </p>
            <p className="text-ink">
              {away.reason} · {away.bed_retained ? "bed kept (charged)" : `bed ${away.released_bed ?? ""} released (not charged)`}
              {" "}· by {away.started_by_name}
            </p>
            <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto]">
              {!away.bed_retained && (
                <select className={SELECT} value={bedId} onChange={(event) => setBedId(event.target.value)}>
                  <option value="">Bed on return…</option>
                  {beds.map((bed) => <option key={bed.id} value={bed.id}>{bed.label}</option>)}
                </select>
              )}
              <Input placeholder="Note on return (optional)" value={note} onChange={(event) => setNote(event.target.value)} />
              <Button disabled={busy || (!away.bed_retained && !bedId)} onClick={() => void back()}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Mark returned
              </Button>
            </div>
          </div>
        )}

        {starting && (
          <div className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-2">
            <Input className="sm:col-span-2" placeholder="Reason, e.g. family function at home" value={reason}
                   onChange={(event) => setReason(event.target.value)} />
            <label className="space-y-1 text-xs text-ink-muted">
              Expected back on
              <Input type="date" min={hospitalToday()} value={expected} onChange={(event) => setExpected(event.target.value)} />
            </label>
            <div className="space-y-1 text-xs text-ink-muted">
              The bed
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="radio" checked={keepBed} onChange={() => setKeepBed(true)} /> Keep it for them — charged
              </label>
              <label className="flex items-center gap-2 text-sm text-ink">
                <input type="radio" checked={!keepBed} onChange={() => setKeepBed(false)} /> Release it — not charged
              </label>
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <Button size="sm" disabled={busy || reason.trim().length < 3} onClick={() => void start()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Send on leave
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setStarting(false)}>Cancel</Button>
            </div>
          </div>
        )}

        {error && <p className="text-clay">{error}</p>}
        {notice && <p className="text-pine">{notice}</p>}

        {leaves.filter((leave) => leave.returned_at).length > 0 && (
          <ul className="space-y-1 text-xs text-ink-muted">
            {leaves.filter((leave) => leave.returned_at).map((leave) => (
              <li key={leave.id}>
                {formatDateTime(leave.started_at)} → {formatDateTime(leave.returned_at)} · {leave.reason}
                {leave.bed_retained ? " · bed kept" : " · bed released"}
                {leave.return_note ? ` · ${leave.return_note}` : ""}
              </li>
            ))}
          </ul>
        )}
        {!away && !starting && leaves.length === 0 && (
          <p className="text-xs text-ink-faint">The patient has not been on leave during this admission.</p>
        )}
      </CardContent>
    </Card>
  );
}
