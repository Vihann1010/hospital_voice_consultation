"use client";

/**
 * The inpatient drug chart.
 *
 * One row per medicine, and across it the day's doses as times: what was
 * given, what was not and why, what is due now, what has been missed. It is
 * the screen a nurse runs a drug round from and a doctor reads before
 * changing anything, so the state of every dose has to be visible without
 * opening anything.
 *
 * Prescribing runs the same safety checks as an OPD prescription, against the
 * admission's allergies and every medicine already running, and a serious
 * alert must be read and acknowledged before the order is accepted.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Pill,
  Plus,
  X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { FormularyMedicine, SafetyAlert } from "@/lib/types/prescriptions";
import type { ChartDose, ChartOrder, DoseState, DrugChart } from "@/lib/types/ipd";
import { formatDateTime, formatHospitalTime, hospitalToday } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const DOSE_STYLE: Record<DoseState, string> = {
  given: "bg-pine text-mint",
  omitted: "bg-clay/15 text-clay",
  overdue: "border border-clay bg-white text-clay font-semibold",
  due: "bg-marigold/30 text-marigold-deep font-semibold",
  upcoming: "border border-border bg-white text-ink-faint",
  on_leave: "border border-dashed border-marigold/60 bg-marigold/5 text-marigold-deep",
};

const DOSE_LABEL: Record<DoseState, string> = {
  given: "Given",
  omitted: "Not given",
  overdue: "Overdue",
  due: "Due now",
  upcoming: "Later",
  on_leave: "On leave",
};

const OMISSION_REASONS = [
  "Patient refused",
  "Nil by mouth",
  "Patient away from the ward",
  "Medicine not available",
  "Held on doctor's advice",
  "Vomited or unable to take",
];

const ROUTE_LABEL: Record<string, string> = {
  oral: "Oral", iv: "IV", im: "IM", sc: "SC", topical: "Topical", inhaled: "Inhaled",
  rectal: "Rectal", sublingual: "Sublingual", nasogastric: "Ryles tube",
};

function shiftDay(day: string, by: number): string {
  const moment = new Date(`${day}T12:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + by);
  return moment.toISOString().slice(0, 10);
}

function dayLabel(day: string): string {
  return new Date(`${day}T12:00:00Z`).toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    weekday: "short", day: "numeric", month: "short",
  });
}

function routeFromForm(form: string): string | null {
  const lowered = form.toLowerCase();
  if (/ointment|cream|gel|lotion/.test(lowered)) return "topical";
  if (/inhaler/.test(lowered)) return "inhaled";
  if (/injection/.test(lowered)) return "iv";
  if (/tablet|capsule|syrup|sachet|suspension/.test(lowered)) return "oral";
  return null;
}

/* -------------------------------------------------------- prescribe form -- */

interface OrderForm {
  drug_name: string;
  generic_name: string;
  strength: string;
  dose: string;
  route: string;
  frequency_code: string;
  times: string;
  instructions: string;
}

const BLANK_FORM: OrderForm = {
  drug_name: "", generic_name: "", strength: "", dose: "", route: "oral",
  frequency_code: "BD", times: "08:00, 20:00", instructions: "",
};

function alertKey(alert: SafetyAlert) {
  return `${alert.kind}:${[...alert.medicines].sort().join("|")}`;
}

function PrescribeCard({
  admissionId,
  chart,
  onDone,
  onCancel,
}: {
  admissionId: string;
  chart: DrugChart;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<OrderForm>(BLANK_FORM);
  const [suggestions, setSuggestions] = useState<FormularyMedicine[]>([]);
  const [strengths, setStrengths] = useState<string[]>([]);
  const [alerts, setAlerts] = useState<SafetyAlert[] | null>(null);
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ticket = useRef(0);

  const frequencies = Object.keys(chart.frequencies);
  const asNeeded = form.frequency_code === "SOS" || form.frequency_code === "STAT";

  // Formulary search as the name is typed; numbered so a slow reply for
  // "pa" cannot replace the reply for "panto".
  useEffect(() => {
    const term = form.drug_name.trim();
    if (term.length < 2) {
      setSuggestions([]);
      return;
    }
    const mine = ++ticket.current;
    const timer = setTimeout(async () => {
      try {
        const found = await staffApi.formulary({ q: term, limit: 8 });
        if (mine === ticket.current) setSuggestions(found.items);
      } catch {
        if (mine === ticket.current) setSuggestions([]);
      }
    }, 180);
    return () => clearTimeout(timer);
  }, [form.drug_name]);

  const set = (patch: Partial<OrderForm>) => {
    setForm((current) => ({ ...current, ...patch }));
    setAlerts(null);
    setAcknowledged(new Set());
  };

  const choose = (item: FormularyMedicine) => {
    const frequency = (item.default_frequency ?? "").toUpperCase();
    const known = frequencies.includes(frequency) ? frequency : form.frequency_code;
    set({
      drug_name: item.name,
      generic_name: item.ingredients.join(" + "),
      strength: item.strengths[0] ?? "",
      route: routeFromForm(item.form) ?? form.route,
      frequency_code: known,
      times: (chart.frequencies[known] ?? []).join(", "),
    });
    setStrengths(item.strengths);
    setSuggestions([]);
  };

  const serious = (alerts ?? []).filter((alert) => alert.severity === "serious");
  const allAcknowledged = serious.every((alert) => acknowledged.has(alertKey(alert)));

  async function place(checked: SafetyAlert[]) {
    await staffApi.orderMedication(admissionId, {
      drug_name: form.drug_name.trim(),
      generic_name: form.generic_name || null,
      strength: form.strength || null,
      dose: form.dose.trim(),
      route: form.route,
      frequency_code: form.frequency_code,
      schedule_times: asNeeded
        ? []
        : form.times.split(/[,\s]+/).map((value) => value.trim()).filter(Boolean),
      is_sos: form.frequency_code === "SOS",
      is_stat: form.frequency_code === "STAT",
      instructions: form.instructions.trim() || null,
      acknowledged_alerts: checked
        .filter((alert) => alert.severity === "serious")
        .map((alert) => ({ kind: alert.kind, medicines: alert.medicines })),
    });
    onDone();
  }

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (alerts === null) {
        // First press checks. Alerts are shown and the order waits; with none,
        // it goes straight through.
        const result = await staffApi.checkMedication(admissionId, form.drug_name.trim());
        if (result.alerts.length) {
          setAlerts(result.alerts);
          return;
        }
        await place([]);
        return;
      }
      await place(alerts);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The medicine was not prescribed.");
    } finally {
      setBusy(false);
    }
  }

  const ready = form.drug_name.trim() && form.dose.trim() && (asNeeded || form.times.trim());
  const label = "h-8 w-full rounded-md border border-input bg-white px-2.5 text-sm text-ink focus-visible:border-pine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/20";

  return (
    <Card className="border-pine/30">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle>Prescribe</CardTitle>
        <button type="button" onClick={onCancel} className="rounded p-1 text-ink-faint hover:text-clay" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 md:grid-cols-[minmax(0,2fr)_1fr_1fr]">
          <label className="relative block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">Medicine</span>
            <Input
              autoFocus
              value={form.drug_name}
              onChange={(event) => set({ drug_name: event.target.value })}
              placeholder="Start typing — Pantoprazole, Ceftriaxone…"
              className="h-8"
            />
            {suggestions.length > 0 && (
              <ul className="absolute left-0 right-0 top-full z-30 mt-1 max-h-60 overflow-auto rounded-md border border-border bg-white py-1 shadow-card">
                {suggestions.map((item) => (
                  <li key={item.code}>
                    <button
                      type="button"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        choose(item);
                      }}
                      className="flex w-full items-baseline justify-between gap-3 px-2.5 py-1.5 text-left text-sm hover:bg-mint"
                    >
                      <span className="text-ink">{item.name}</span>
                      <span className="truncate text-[11px] text-ink-faint">
                        {item.form} · {item.ingredients.join(" + ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </label>
          <label className="block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">Strength</span>
            <Input
              value={form.strength}
              list="strength-options"
              onChange={(event) => set({ strength: event.target.value })}
              placeholder="40 mg"
              className="h-8"
            />
            <datalist id="strength-options">
              {strengths.map((value) => <option key={value} value={value} />)}
            </datalist>
          </label>
          <label className="block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">Dose</span>
            <Input
              value={form.dose}
              onChange={(event) => set({ dose: event.target.value })}
              placeholder="1 tablet"
              className="h-8"
            />
          </label>
        </div>

        <div className="grid gap-2 md:grid-cols-[1fr_1fr_2fr]">
          <label className="block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">Route</span>
            <select value={form.route} onChange={(event) => set({ route: event.target.value })} className={label}>
              {chart.routes.map((route) => (
                <option key={route} value={route}>{ROUTE_LABEL[route] ?? route}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">How often</span>
            <select
              value={form.frequency_code}
              onChange={(event) => {
                const code = event.target.value;
                set({ frequency_code: code, times: (chart.frequencies[code] ?? []).join(", ") });
              }}
              className={label}
            >
              {frequencies.map((code) => (
                <option key={code} value={code}>
                  {code === "SOS" ? "SOS — when needed" : code === "STAT" ? "STAT — once, now" : code}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="mb-0.5 block text-[11px] text-ink-muted">
              {asNeeded ? "No round times" : "Due at (hospital time)"}
            </span>
            <Input
              value={asNeeded ? "" : form.times}
              disabled={asNeeded}
              onChange={(event) => set({ times: event.target.value })}
              placeholder="08:00, 20:00"
              className="h-8"
            />
          </label>
        </div>

        <label className="block">
          <span className="mb-0.5 block text-[11px] text-ink-muted">Instructions</span>
          <Input
            value={form.instructions}
            onChange={(event) => set({ instructions: event.target.value })}
            placeholder="Before food, dilute in 100 ml NS over 30 min…"
            className="h-8"
          />
        </label>

        {alerts && alerts.length > 0 && (
          <div className="space-y-1.5 rounded-lg border border-marigold/50 bg-marigold/[0.06] p-3">
            {alerts.map((alert) => (
              <div key={alertKey(alert)} className="flex items-start gap-2 text-sm">
                <AlertTriangle
                  className={cn(
                    "mt-0.5 h-4 w-4 shrink-0",
                    alert.severity === "serious" ? "text-clay" : "text-marigold-deep"
                  )}
                />
                <div className="min-w-0 flex-1">
                  <p className={alert.severity === "serious" ? "font-medium text-clay" : "text-ink"}>
                    {alert.description}
                  </p>
                  {alert.suggested_action && (
                    <p className="text-xs text-ink-muted">{alert.suggested_action}</p>
                  )}
                  {alert.severity === "serious" && (
                    <label className="mt-1 flex items-center gap-1.5 text-xs text-ink">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 accent-pine"
                        checked={acknowledged.has(alertKey(alert))}
                        onChange={(event) =>
                          setAcknowledged((current) => {
                            const next = new Set(current);
                            if (event.target.checked) next.add(alertKey(alert));
                            else next.delete(alertKey(alert));
                            return next;
                          })
                        }
                      />
                      I have read this and still want to prescribe it
                    </label>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {error && <p className="text-xs text-clay">{error}</p>}

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            disabled={!ready || busy || (alerts !== null && !allAcknowledged)}
            onClick={() => void submit()}
          >
            {busy ? <Loader2 className="animate-spin" /> : <Check />}
            {alerts === null ? "Check and prescribe" : "Prescribe"}
          </Button>
          <span className="text-[11px] text-ink-faint">
            Checked against allergies and the medicines already running.
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------ the chart -- */

export function DrugChartView({
  admissionId,
  active,
  onChanged,
}: {
  admissionId: string;
  /** False once discharged: the chart is still read, nothing new is written. */
  active: boolean;
  onChanged?: () => void;
}) {
  const today = hospitalToday();
  const [day, setDay] = useState(today);
  const [chart, setChart] = useState<DrugChart | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [prescribing, setPrescribing] = useState(false);
  const [signing, setSigning] = useState<{ order: ChartOrder; dose: ChartDose } | null>(null);
  const [notGiven, setNotGiven] = useState(false);
  const [reason, setReason] = useState(OMISSION_REASONS[0]);
  const [otherReason, setOtherReason] = useState("");
  const [note, setNote] = useState("");
  const [giving, setGiving] = useState<ChartOrder | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [stopRequest, setStopRequest] = useState<ReasonRequest | null>(null);

  const load = useCallback(async () => {
    try {
      setChart(await staffApi.drugChart(admissionId, day));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The drug chart could not be loaded.");
    }
  }, [admissionId, day]);

  useEffect(() => {
    void load();
    // The chart's "due" and "overdue" change with the clock, not only with
    // what people sign, so it refreshes on its own through a drug round.
    const timer = setInterval(() => void load(), 60_000);
    return () => clearInterval(timer);
  }, [load]);

  const changed = () => {
    void load();
    onChanged?.();
  };

  const openSign = (order: ChartOrder, dose: ChartDose) => {
    setSigning({ order, dose });
    setNotGiven(false);
    setReason(OMISSION_REASONS[0]);
    setOtherReason("");
    setNote("");
    setDialogError(null);
  };

  async function sign() {
    if (!signing) return;
    setBusy(true);
    setDialogError(null);
    try {
      await staffApi.signDose(signing.dose.id, {
        was_given: !notGiven,
        omission_reason: notGiven ? (reason === "Other" ? otherReason.trim() : reason) : undefined,
        notes: note.trim() || undefined,
      });
      setSigning(null);
      changed();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "The dose was not signed.");
    } finally {
      setBusy(false);
    }
  }

  async function giveNow() {
    if (!giving) return;
    setBusy(true);
    setDialogError(null);
    try {
      await staffApi.giveAsNeeded(giving.id, note.trim() || undefined);
      setGiving(null);
      changed();
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : "The dose was not recorded.");
    } finally {
      setBusy(false);
    }
  }

  const running = useMemo(
    () => (chart?.orders ?? []).filter((order) => order.status === "active"),
    [chart]
  );
  const finished = useMemo(
    () => (chart?.orders ?? []).filter((order) => order.status !== "active"),
    [chart]
  );

  if (error && !chart) {
    return (
      <Card className="border-clay/30 bg-clay/5">
        <CardContent className="flex items-center justify-between gap-3 p-4">
          <p className="text-sm text-clay">{error}</p>
          <Button size="sm" variant="outline" onClick={() => void load()}>Try again</Button>
        </CardContent>
      </Card>
    );
  }

  if (!chart) {
    return <Skeleton className="h-64 w-full rounded-xl" />;
  }

  const renderOrder = (order: ChartOrder) => {
    const stopped = order.status !== "active";
    return (
      <div
        key={order.id}
        className={cn(
          "grid gap-3 border-b border-border px-3 py-3 last:border-0 md:grid-cols-[minmax(0,1.3fr)_minmax(0,2fr)_auto]",
          stopped && "bg-mint/30"
        )}
      >
        <div className="min-w-0">
          <p className={cn("flex flex-wrap items-center gap-1.5 text-sm font-medium", stopped ? "text-ink-muted" : "text-ink")}>
            <Pill className="h-3.5 w-3.5 shrink-0 text-pine/60" />
            {order.drug_name} {order.strength ?? ""}
            {order.is_sos && <Badge variant="outline" size="sm">SOS</Badge>}
            {order.is_stat && <Badge variant="outline" size="sm">STAT</Badge>}
          </p>
          <p className="mt-0.5 text-xs text-ink-muted">
            {order.dose} · {ROUTE_LABEL[order.route] ?? order.route}
            {!order.is_sos && !order.is_stat ? ` · ${order.frequency_code}` : ""}
            {order.schedule_times.length ? ` (${order.schedule_times.join(", ")})` : ""}
          </p>
          {order.instructions && <p className="text-[11px] text-ink-faint">{order.instructions}</p>}
          <p className="text-[11px] text-ink-faint">
            {order.ordered_by_name} · from {formatDateTime(order.started_at)}
          </p>
          {stopped && (
            <p className="text-[11px] text-clay">
              {order.status === "completed" ? "Completed" : "Stopped"}{" "}
              {order.stopped_at ? formatDateTime(order.stopped_at) : ""}
              {order.stop_reason ? ` — ${order.stop_reason}` : ""}
            </p>
          )}
        </div>

        <div className="flex flex-wrap content-start items-start gap-1.5">
          {order.doses.length === 0 && (
            <span className="text-xs text-ink-faint">
              {order.is_sos
                ? order.last_given_at
                  ? `Last given ${formatDateTime(order.last_given_at)}`
                  : "Not given yet"
                : "No doses this day"}
            </span>
          )}
          {order.doses.map((dose) => {
            const time = formatHospitalTime(dose.due_at);
            const title =
              dose.state === "given"
                ? `Given ${formatHospitalTime(dose.given_at)} by ${dose.given_by_name}`
                : dose.state === "omitted"
                  ? `Not given — ${dose.omission_reason} (${dose.given_by_name})`
                  : DOSE_LABEL[dose.state];
            return (
              <button
                key={dose.id}
                type="button"
                title={title}
                disabled={!dose.can_sign}
                onClick={() => openSign(order, dose)}
                className={cn(
                  "tabular flex items-center gap-1 rounded-md px-2 py-1 text-xs transition disabled:cursor-default",
                  DOSE_STYLE[dose.state],
                  dose.can_sign && "hover:ring-2 hover:ring-pine/30"
                )}
              >
                {dose.state === "given" && <Check className="h-3 w-3" />}
                {dose.state === "omitted" && <X className="h-3 w-3" />}
                {time}
              </button>
            );
          })}
        </div>

        <div className="flex items-start gap-1.5">
          {!stopped && active && order.is_sos && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setGiving(order);
                setNote("");
                setDialogError(null);
              }}
            >
              Give now
            </Button>
          )}
          {!stopped && active && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setStopRequest({
                  title: `Stop ${order.drug_name}?`,
                  detail:
                    "Doses not yet due are removed from the chart. Doses already signed stay in the record.",
                  confirmLabel: "Stop medicine",
                  destructive: true,
                  run: async (why) => {
                    await staffApi.stopMedication(order.id, why);
                    changed();
                  },
                })
              }
            >
              Stop
            </Button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------- toolbar -- */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center rounded-lg border border-border bg-white">
          <button type="button" onClick={() => setDay((d) => shiftDay(d, -1))} className="rounded-l-lg p-2 text-ink-muted hover:bg-mint" aria-label="Previous day">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[8.5rem] px-2 text-center text-sm font-medium text-ink">
            {day === today ? `Today · ${dayLabel(day)}` : dayLabel(day)}
          </span>
          <button type="button" onClick={() => setDay((d) => shiftDay(d, 1))} className="rounded-r-lg p-2 text-ink-muted hover:bg-mint" aria-label="Next day">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {day !== today && (
          <Button size="sm" variant="ghost" onClick={() => setDay(today)}>Back to today</Button>
        )}
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {chart.summary.overdue > 0 && (
            <span className="rounded-md border border-clay px-2 py-0.5 font-semibold text-clay">
              {chart.summary.overdue} overdue
            </span>
          )}
          {chart.summary.due > 0 && (
            <span className="rounded-md bg-marigold/30 px-2 py-0.5 font-semibold text-marigold-deep">
              {chart.summary.due} due now
            </span>
          )}
          <span className="text-ink-faint">
            {chart.summary.given} given · {chart.summary.omitted} not given
          </span>
        </div>
        {active && !prescribing && (
          <Button size="sm" className="ml-auto" onClick={() => setPrescribing(true)}>
            <Plus /> Prescribe
          </Button>
        )}
      </div>

      {chart.allergies.length > 0 && (
        <p className="flex items-center gap-1.5 rounded-md bg-clay/10 px-3 py-2 text-sm font-medium text-clay">
          <AlertTriangle className="h-4 w-4" /> Allergic to {chart.allergies.join(", ")}
        </p>
      )}

      {prescribing && (
        <PrescribeCard
          admissionId={admissionId}
          chart={chart}
          onCancel={() => setPrescribing(false)}
          onDone={() => {
            setPrescribing(false);
            changed();
          }}
        />
      )}

      <Card>
        <CardContent className="p-0">
          {running.length === 0 && finished.length === 0 ? (
            <p className="p-8 text-center text-sm text-ink-muted">
              Nothing prescribed on this admission{day !== today ? " by this day" : ""}.
            </p>
          ) : (
            <>
              {running.map(renderOrder)}
              {finished.length > 0 && (
                <p className="border-y border-border bg-mint/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                  Stopped or completed
                </p>
              )}
              {finished.map(renderOrder)}
            </>
          )}
        </CardContent>
      </Card>

      <p className="text-[11px] text-ink-faint">
        Times are hospital time. A dose can be signed from an hour before it is due and turns red an
        hour after. Refreshes every minute.
      </p>

      {/* ------------------------------------------------------- dialogs -- */}
      <Dialog open={signing !== null} onOpenChange={(open) => !open && setSigning(null)}>
        <DialogContent>
          {signing && (
            <>
              <DialogHeader>
                <DialogTitle>
                  {signing.order.drug_name} {signing.order.strength ?? ""}
                </DialogTitle>
                <DialogDescription>
                  {signing.order.dose} · {ROUTE_LABEL[signing.order.route] ?? signing.order.route} · due{" "}
                  {formatHospitalTime(signing.dose.due_at)}
                </DialogDescription>
              </DialogHeader>
              {chart.allergies.length > 0 && (
                <p className="rounded-md bg-clay/10 px-3 py-1.5 text-xs font-medium text-clay">
                  Allergic to {chart.allergies.join(", ")}
                </p>
              )}
              <div className="flex gap-1 rounded-lg bg-mint p-1">
                {[
                  [false, "Given"],
                  [true, "Not given"],
                ].map(([value, text]) => (
                  <button
                    key={String(text)}
                    type="button"
                    onClick={() => setNotGiven(Boolean(value))}
                    className={cn(
                      "flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition",
                      notGiven === value ? "bg-white text-pine shadow-sm" : "text-ink-muted"
                    )}
                  >
                    {String(text)}
                  </button>
                ))}
              </div>
              {notGiven && (
                <div className="space-y-2">
                  <select
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    className="h-9 w-full rounded-md border border-input bg-white px-2 text-sm"
                  >
                    {[...OMISSION_REASONS, "Other"].map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                  {reason === "Other" && (
                    <Input
                      value={otherReason}
                      onChange={(event) => setOtherReason(event.target.value)}
                      placeholder="Why was it not given?"
                    />
                  )}
                </div>
              )}
              <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Note (optional)" />
              {dialogError && <p className="text-xs text-clay">{dialogError}</p>}
              <DialogFooter>
                <Button variant="ghost" onClick={() => setSigning(null)}>Cancel</Button>
                <Button
                  disabled={busy || (notGiven && reason === "Other" && !otherReason.trim())}
                  onClick={() => void sign()}
                >
                  {busy && <Loader2 className="animate-spin" />}
                  {notGiven ? "Record not given" : "Sign as given"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={giving !== null} onOpenChange={(open) => !open && setGiving(null)}>
        <DialogContent>
          {giving && (
            <>
              <DialogHeader>
                <DialogTitle>Give {giving.drug_name} now?</DialogTitle>
                <DialogDescription>
                  {giving.dose} · {ROUTE_LABEL[giving.route] ?? giving.route}.{" "}
                  {giving.last_given_at
                    ? `Last given ${formatDateTime(giving.last_given_at)}.`
                    : "Not given before on this admission."}
                </DialogDescription>
              </DialogHeader>
              <Input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Why it was needed (optional)" />
              {dialogError && <p className="text-xs text-clay">{dialogError}</p>}
              <DialogFooter>
                <Button variant="ghost" onClick={() => setGiving(null)}>Cancel</Button>
                <Button disabled={busy} onClick={() => void giveNow()}>
                  {busy && <Loader2 className="animate-spin" />} Record dose given
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <ReasonDialog request={stopRequest} onClose={() => setStopRequest(null)} />
    </div>
  );
}
