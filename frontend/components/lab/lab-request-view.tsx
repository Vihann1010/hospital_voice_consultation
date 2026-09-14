"use client";

/**
 * One lab request: the sample, each test's results, verification, printing.
 *
 * Entry and verification sit on the same screen but are different people's
 * acts. The technician types and saves; the pathologist reads what was saved
 * and verifies it. Verify is disabled while there are unsaved edits, so what
 * a doctor signs is always what is stored — never what happens to be typed in
 * a box on somebody else's screen.
 *
 * Values read from an analyser printout are highlighted until saved, and the
 * screen says plainly that each one must be checked against the paper.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  FileUp,
  Loader2,
  Plus,
  Printer,
  RotateCcw,
  Trash2,
  XCircle,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import { formatINR } from "@/lib/emrTypes";
import { formatDateTime } from "@/lib/format";
import type {
  CultureAntibiotic,
  CultureIsolate,
  CultureResult,
  LabItem,
  LabMaster,
  LabRequest,
  PrintoutReading,
} from "@/lib/labTypes";
import {
  BILLING_LABEL,
  FLAG_MARK,
  ITEM_STATUS_LABEL,
  REQUEST_STATUS_LABEL,
  canBillAtCounter,
  canEnterLab,
  canRegisterLab,
  canVerifyLab,
  isAbnormal,
  isCritical,
} from "@/lib/labTypes";
import { ReasonDialog } from "@/components/ui/reason-dialog";
import type { ReasonRequest } from "@/components/ui/reason-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SELECT =
  "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

function FlagChip({ flag }: { flag: string | null }) {
  if (!flag || !isAbnormal(flag as LabItem["results"][number]["flag"])) return null;
  const critical = isCritical(flag as LabItem["results"][number]["flag"]);
  return (
    <span className={cn("rounded px-1.5 py-0.5 text-[11px] font-bold", critical ? "bg-clay text-white" : "bg-clay/15 text-clay")}>
      {FLAG_MARK[flag] ?? flag}
    </span>
  );
}

// ------------------------------------------------------------ result entry
function ResultEntry({
  item,
  onSaved,
  onDirty,
}: {
  item: LabItem;
  onSaved: (next: LabRequest) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const parameters = useMemo(() => item.parameters ?? [], [item.parameters]);
  const saved = useMemo(() => new Map(item.results.map((row) => [row.parameter_id, row])), [item.results]);
  const initialValues = useMemo(
    () => Object.fromEntries(parameters.map((p) => [p.id, saved.get(p.id)?.value ?? ""])) as Record<string, string>,
    [parameters, saved]
  );
  const initialPrints = useMemo(
    () => Object.fromEntries(parameters.map((p) => [p.id, saved.get(p.id)?.print ?? p.print_default])) as Record<string, boolean>,
    [parameters, saved]
  );
  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [prints, setPrints] = useState<Record<string, boolean>>(initialPrints);
  const [remarks, setRemarks] = useState(item.remarks ?? "");
  const [fromPrintout, setFromPrintout] = useState<Set<string>>(new Set());
  const [reading, setReading] = useState<PrintoutReading | null>(null);
  const [busy, setBusy] = useState<"save" | "read" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setValues(initialValues);
    setPrints(initialPrints);
    setRemarks(item.remarks ?? "");
    setFromPrintout(new Set());
  }, [initialValues, initialPrints, item.remarks]);

  const dirty =
    parameters.some((p) => (values[p.id] ?? "") !== (initialValues[p.id] ?? "") || prints[p.id] !== initialPrints[p.id]) ||
    remarks !== (item.remarks ?? "");
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  function update(id: string, value: string) {
    setValues((current) => ({ ...current, [id]: value }));
    setFromPrintout((current) => {
      if (!current.has(id)) return current;
      const next = new Set(current);
      next.delete(id);
      return next;
    });
  }

  async function save() {
    setBusy("save");
    setError(null);
    try {
      onSaved(await staffApi.saveLabResults(item.id, { values, prints, remarks: remarks.trim() || null }));
      setReading(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The results could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function readPrintout(file: File) {
    setBusy("read");
    setError(null);
    try {
      const result = await staffApi.readLabPrintout(item.id, file);
      setReading(result);
      if (!result.unclear) {
        setValues((current) => {
          const next = { ...current };
          for (const suggestion of result.suggestions) next[suggestion.parameter_id] = suggestion.value;
          return next;
        });
        setFromPrintout(new Set(result.suggestions.map((suggestion) => suggestion.parameter_id)));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "The printout could not be read.");
    } finally {
      setBusy(null);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-ink-faint">
              <th className="py-1.5 pr-2 font-medium">Investigation</th>
              <th className="py-1.5 pr-2 font-medium">Result</th>
              <th className="py-1.5 pr-2 font-medium">Unit</th>
              <th className="py-1.5 pr-2 font-medium">Reference range</th>
              <th className="py-1.5 text-center font-medium">Print</th>
            </tr>
          </thead>
          <tbody>
            {parameters.map((p) => {
              if (p.result_type === "heading") {
                return (
                  <tr key={p.id}>
                    <td colSpan={5} className="pb-1 pt-3 text-xs font-semibold text-pine">
                      {p.name}
                    </td>
                  </tr>
                );
              }
              const row = saved.get(p.id);
              const current = values[p.id] ?? "";
              const unchanged = row !== undefined && (row.value ?? "") === current;
              const highlighted = fromPrintout.has(p.id);
              return (
                <tr key={p.id} className="border-t border-border/60 align-top">
                  <td className="py-1.5 pr-2">
                    <p className="text-ink">{p.name}</p>
                    {p.method && <p className="text-[11px] text-ink-faint">{p.method}</p>}
                  </td>
                  <td className="py-1.5 pr-2">
                    <div className="flex items-center gap-2">
                      {p.result_type === "choice" ? (
                        <select
                          className={cn(SELECT, "w-40", highlighted && "border-marigold bg-marigold/10")}
                          value={current}
                          onChange={(event) => update(p.id, event.target.value)}
                          aria-label={p.name}
                        >
                          <option value="">—</option>
                          {p.choices.map((choice) => (
                            <option key={choice} value={choice}>
                              {choice}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <Input
                          value={current}
                          onChange={(event) => update(p.id, event.target.value)}
                          inputMode={p.result_type === "numeric" ? "decimal" : undefined}
                          aria-label={p.name}
                          className={cn("h-9", p.result_type === "numeric" ? "w-28" : "w-64", highlighted && "border-marigold bg-marigold/10")}
                        />
                      )}
                      {unchanged && <FlagChip flag={row?.flag ?? null} />}
                    </div>
                    {unchanged && row?.note && <p className="mt-0.5 text-[11px] text-ink-faint">{row.note}</p>}
                  </td>
                  <td className="py-1.5 pr-2 text-ink-muted">{p.unit ?? ""}</td>
                  <td className="py-1.5 pr-2 text-ink-muted">{p.range_preview ?? <span className="text-ink-faint">No range</span>}</td>
                  <td className="py-1.5 text-center">
                    <input
                      type="checkbox"
                      checked={prints[p.id] ?? true}
                      onChange={(event) => setPrints((currentPrints) => ({ ...currentPrints, [p.id]: event.target.checked }))}
                      aria-label={`Print ${p.name}`}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Input placeholder="Remarks printed under this test (optional)" value={remarks} onChange={(event) => setRemarks(event.target.value)} />

      {reading && (
        <div className={cn("space-y-1 rounded-lg border p-3 text-sm", reading.unclear ? "border-clay/40 bg-clay/5" : "border-marigold/40 bg-marigold/5")}>
          {reading.unclear ? (
            <p className="font-medium text-clay">{reading.message}</p>
          ) : (
            <p className="font-medium text-marigold-deep">
              {reading.suggestions.length} value{reading.suggestions.length === 1 ? "" : "s"} filled from the printout and highlighted.
              Check each one against the printout before saving.
            </p>
          )}
          {reading.conflicts.map((line) => (
            <p key={line} className="text-xs text-clay">{line}</p>
          ))}
          {reading.unit_mismatches.map((line) => (
            <p key={line} className="text-xs text-clay">Not filled: {line}</p>
          ))}
          {reading.unmatched_count > 0 && (
            <details className="text-xs text-ink-muted">
              <summary className="cursor-pointer">
                {reading.unmatched_count} line{reading.unmatched_count === 1 ? "" : "s"} on the printout did not match this test
              </summary>
              <ul className="mt-1 space-y-0.5">
                {reading.unmatched_lines.map((line, index) => (
                  <li key={index} className="font-mono text-[11px]">{line}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" disabled={busy !== null || !dirty} onClick={() => void save()}>
          {busy === "save" && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save results
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf,image/png,image/jpeg"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void readPrintout(file);
          }}
        />
        <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => fileRef.current?.click()}>
          {busy === "read" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileUp className="h-3.5 w-3.5" />} Read analyser printout
        </Button>
        {dirty && <span className="text-xs text-marigold-deep">Unsaved changes</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- culture
const blankCulture = (specimen: string | null): CultureResult => ({
  specimen,
  growth: null,
  incubation: null,
  isolates: [],
  comment: null,
});

function CultureEntry({
  item,
  organisms,
  antibiotics,
  onSaved,
  onDirty,
}: {
  item: LabItem;
  organisms: LabMaster[];
  antibiotics: LabMaster[];
  onSaved: (next: LabRequest) => void;
  onDirty: (dirty: boolean) => void;
}) {
  const initial = useMemo<CultureResult>(() => item.culture ?? blankCulture(item.specimen), [item.culture, item.specimen]);
  const [culture, setCulture] = useState<CultureResult>(initial);
  const [remarks, setRemarks] = useState(item.remarks ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCulture(initial);
    setRemarks(item.remarks ?? "");
  }, [initial, item.remarks]);

  const dirty = JSON.stringify(culture) !== JSON.stringify(initial) || remarks !== (item.remarks ?? "");
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  function setIsolate(index: number, patch: Partial<CultureIsolate>) {
    setCulture((current) => ({
      ...current,
      isolates: current.isolates.map((isolate, position) => (position === index ? { ...isolate, ...patch } : isolate)),
    }));
  }

  function setRow(isolateIndex: number, rowIndex: number, patch: Partial<CultureAntibiotic>) {
    setCulture((current) => ({
      ...current,
      isolates: current.isolates.map((isolate, position) =>
        position === isolateIndex
          ? { ...isolate, antibiotics: isolate.antibiotics.map((row, index) => (index === rowIndex ? { ...row, ...patch } : row)) }
          : isolate
      ),
    }));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      onSaved(await staffApi.saveLabResults(item.id, { culture, remarks: remarks.trim() || null }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The culture could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const organismList = `organisms-${item.id}`;
  const antibioticList = `antibiotics-${item.id}`;

  return (
    <div className="space-y-3 text-sm">
      <datalist id={organismList}>
        {organisms.map((entry) => (
          <option key={entry.id} value={entry.name} />
        ))}
      </datalist>
      <datalist id={antibioticList}>
        {antibiotics.map((entry) => (
          <option key={entry.id} value={entry.name} />
        ))}
      </datalist>

      <div className="grid gap-2 sm:grid-cols-3">
        <label className="space-y-1">
          <span className="text-xs text-ink-muted">Specimen</span>
          <Input value={culture.specimen ?? ""} onChange={(event) => setCulture({ ...culture, specimen: event.target.value })} />
        </label>
        <label className="space-y-1">
          <span className="text-xs text-ink-muted">Incubation</span>
          <Input
            placeholder="e.g. 48 hours aerobic"
            value={culture.incubation ?? ""}
            onChange={(event) => setCulture({ ...culture, incubation: event.target.value })}
          />
        </label>
        <div className="space-y-1">
          <span className="text-xs text-ink-muted">Result</span>
          <div className="flex gap-2">
            {(["growth", "no_growth"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() =>
                  setCulture({
                    ...culture,
                    growth: value,
                    isolates:
                      value === "no_growth"
                        ? []
                        : culture.isolates.length
                          ? culture.isolates
                          : [{ organism: "", colony_count: null, antibiotics: [] }],
                  })
                }
                className={cn(
                  "rounded-lg border px-3 py-1.5 text-sm",
                  culture.growth === value ? "border-pine bg-pine text-mint" : "border-border bg-white text-ink-muted"
                )}
              >
                {value === "growth" ? "Growth" : "No growth"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {culture.growth === "growth" &&
        culture.isolates.map((isolate, isolateIndex) => (
          <div key={isolateIndex} className="space-y-2 rounded-lg border border-border p-3">
            <div className="grid gap-2 sm:grid-cols-[1fr_12rem_auto]">
              <Input
                list={organismList}
                placeholder="Organism isolated"
                value={isolate.organism}
                onChange={(event) => setIsolate(isolateIndex, { organism: event.target.value })}
              />
              <Input
                placeholder="Colony count"
                value={isolate.colony_count ?? ""}
                onChange={(event) => setIsolate(isolateIndex, { colony_count: event.target.value })}
              />
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setCulture({ ...culture, isolates: culture.isolates.filter((_, index) => index !== isolateIndex) })}
              >
                <Trash2 className="h-3.5 w-3.5" /> Remove
              </Button>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-ink-faint">
                  <th className="py-1 font-medium">Antibiotic</th>
                  <th className="py-1 font-medium">S / I / R</th>
                  <th className="py-1 font-medium">MIC / zone</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {isolate.antibiotics.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    <td className="py-1 pr-2">
                      <Input list={antibioticList} value={row.name} onChange={(event) => setRow(isolateIndex, rowIndex, { name: event.target.value })} />
                    </td>
                    <td className="py-1 pr-2">
                      <select
                        className={cn(SELECT, row.result === "R" && "border-clay text-clay")}
                        value={row.result}
                        onChange={(event) => setRow(isolateIndex, rowIndex, { result: event.target.value as CultureAntibiotic["result"] })}
                        aria-label={`Interpretation for ${row.name || "antibiotic"}`}
                      >
                        <option value="">—</option>
                        <option value="S">Sensitive</option>
                        <option value="I">Intermediate</option>
                        <option value="R">Resistant</option>
                      </select>
                    </td>
                    <td className="py-1 pr-2">
                      <Input value={row.value ?? ""} onChange={(event) => setRow(isolateIndex, rowIndex, { value: event.target.value })} />
                    </td>
                    <td className="py-1">
                      <button
                        type="button"
                        className="rounded p-1 text-ink-faint hover:text-clay"
                        onClick={() =>
                          setIsolate(isolateIndex, { antibiotics: isolate.antibiotics.filter((_, index) => index !== rowIndex) })
                        }
                        aria-label="Remove antibiotic"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setIsolate(isolateIndex, { antibiotics: [...isolate.antibiotics, { name: "", result: "", value: null }] })}
              >
                <Plus className="h-3.5 w-3.5" /> Antibiotic
              </Button>
              {antibiotics.length > 0 && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    const present = new Set(isolate.antibiotics.map((row) => row.name.toLowerCase()));
                    setIsolate(isolateIndex, {
                      antibiotics: [
                        ...isolate.antibiotics,
                        ...antibiotics
                          .filter((entry) => !present.has(entry.name.toLowerCase()))
                          .map((entry) => ({ name: entry.name, result: "" as const, value: null })),
                      ],
                    });
                  }}
                >
                  Add every listed antibiotic
                </Button>
              )}
            </div>
            <p className="text-[11px] text-ink-faint">Rows left without S, I or R must be removed before the culture can be verified.</p>
          </div>
        ))}

      {culture.growth === "growth" && culture.isolates.length < 3 && (
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setCulture({ ...culture, isolates: [...culture.isolates, { organism: "", colony_count: null, antibiotics: [] }] })}
        >
          <Plus className="h-3.5 w-3.5" /> Another organism
        </Button>
      )}

      <Input placeholder="Comment (optional)" value={culture.comment ?? ""} onChange={(event) => setCulture({ ...culture, comment: event.target.value })} />
      <Input placeholder="Remarks (optional)" value={remarks} onChange={(event) => setRemarks(event.target.value)} />
      {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}
      <div className="flex items-center gap-2">
        <Button size="sm" disabled={busy || !dirty} onClick={() => void save()}>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save culture
        </Button>
        {dirty && <span className="text-xs text-marigold-deep">Unsaved changes</span>}
      </div>
    </div>
  );
}

// -------------------------------------------------------------- read-only
function ResultsTable({ item }: { item: LabItem }) {
  if (item.is_culture) {
    const culture = item.culture;
    if (!culture) return <p className="text-sm text-ink-muted">No culture recorded.</p>;
    return (
      <div className="space-y-2 text-sm">
        <p className="text-ink-muted">
          {culture.specimen ?? "Specimen not recorded"}
          {culture.incubation ? ` · ${culture.incubation}` : ""}
        </p>
        {culture.growth === "no_growth" && <p className="font-medium text-ink">No growth</p>}
        {culture.isolates.map((isolate, index) => (
          <div key={index}>
            <p className="font-medium italic text-ink">
              {isolate.organism}
              {isolate.colony_count ? <span className="not-italic text-ink-muted"> · {isolate.colony_count}</span> : null}
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {isolate.antibiotics.map((row) => (
                <span
                  key={row.name}
                  className={cn(
                    "rounded border px-1.5 py-0.5 text-[11px]",
                    row.result === "R" ? "border-clay/40 bg-clay/10 font-semibold text-clay" : "border-border text-ink-muted"
                  )}
                >
                  {row.name}: {row.result}
                  {row.value ? ` (${row.value})` : ""}
                </span>
              ))}
            </div>
          </div>
        ))}
        {culture.comment && <p className="text-ink-muted">{culture.comment}</p>}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <tbody>
          {item.results.map((row) =>
            row.result_type === "heading" ? (
              <tr key={row.parameter_id}>
                <td colSpan={4} className="pb-1 pt-2 text-xs font-semibold text-pine">
                  {row.name}
                </td>
              </tr>
            ) : (
              <tr key={row.parameter_id} className={cn("border-t border-border/60", !row.print && "text-ink-faint")}>
                <td className="py-1.5 pr-2">
                  {row.name}
                  {!row.print && <span className="ml-1 text-[10px]">(not printed)</span>}
                </td>
                <td className={cn("py-1.5 pr-2", isAbnormal(row.flag) && "font-semibold text-clay")}>
                  <span className="mr-2">{row.value ?? "—"}</span>
                  <FlagChip flag={row.flag} />
                </td>
                <td className="py-1.5 pr-2 text-ink-muted">{row.unit ?? ""}</td>
                <td className="py-1.5 text-ink-muted">{row.reference_text ?? ""}</td>
              </tr>
            )
          )}
        </tbody>
      </table>
      {item.remarks && <p className="mt-2 text-xs text-ink-muted">Remarks: {item.remarks}</p>}
    </div>
  );
}

// ----------------------------------------------------------------- a test
function ItemCard({
  item,
  request,
  organisms,
  antibiotics,
  onChange,
  onAsk,
}: {
  item: LabItem;
  request: LabRequest;
  organisms: LabMaster[];
  antibiotics: LabMaster[];
  onChange: (next: LabRequest) => void;
  onAsk: (ask: ReasonRequest) => void;
}) {
  const { user } = useAuth();
  const [dirty, setDirty] = useState(false);
  const [criticalNote, setCriticalNote] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const open = request.status !== "cancelled";
  const editable = open && canEnterLab(user?.role) && (item.status === "collected" || item.status === "entered");
  const critical = item.results.filter((row) => isCritical(row.flag));
  const mayVerify = open && canVerifyLab(user?.role) && item.status === "entered";

  async function verify() {
    setVerifying(true);
    setError(null);
    try {
      onChange(await staffApi.verifyLabResult(item.id, criticalNote.trim() || null));
      setCriticalNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The result could not be verified.");
    } finally {
      setVerifying(false);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-display text-base font-semibold text-ink">
              {item.name} <span className="text-xs font-normal text-ink-faint">{item.code}</span>
            </p>
            <p className="text-xs text-ink-muted">
              {item.group_name}
              {item.specimen ? ` · ${item.specimen}` : ""}
              {item.unit_rate_paise > 0 ? ` · ${formatINR(item.unit_rate_paise)}` : ""}
              {item.version > 1 ? ` · version ${item.version}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-medium",
                item.status === "verified" ? "bg-pine text-mint" : item.status === "cancelled" ? "bg-ink/10 text-ink-muted" : "bg-marigold/15 text-marigold-deep"
              )}
            >
              {ITEM_STATUS_LABEL[item.status]}
            </span>
            {open && item.status !== "verified" && item.status !== "cancelled" && canRegisterLab(user?.role) && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  onAsk({
                    title: `Cancel ${item.name}?`,
                    detail: "An unpaid bill is corrected. A paid one is left as it is, and the refund due is shown.",
                    confirmLabel: "Cancel test",
                    destructive: true,
                    run: async (reason) => onChange(await staffApi.cancelLab(request.id, { reason, item_ids: [item.id] })),
                  })
                }
              >
                <XCircle className="h-3.5 w-3.5" /> Cancel
              </Button>
            )}
            {item.status === "verified" && canVerifyLab(user?.role) && open && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  onAsk({
                    title: `Reopen ${item.name} for correction?`,
                    detail: "The verified version is kept. The report prints as amended once it is verified again.",
                    confirmLabel: "Reopen",
                    run: async (reason) => onChange(await staffApi.reopenLabResult(item.id, reason)),
                  })
                }
              >
                <RotateCcw className="h-3.5 w-3.5" /> Reopen
              </Button>
            )}
          </div>
        </div>

        {item.status === "registered" && open && (
          <p className="text-sm text-ink-muted">Waiting for the sample. Mark it collected above to enter results.</p>
        )}
        {item.status === "cancelled" && (
          <p className="text-sm text-ink-muted">
            Cancelled{item.cancel_reason ? `: ${item.cancel_reason}` : ""}
          </p>
        )}

        {editable &&
          (item.is_culture ? (
            <CultureEntry item={item} organisms={organisms} antibiotics={antibiotics} onSaved={onChange} onDirty={setDirty} />
          ) : (
            <ResultEntry item={item} onSaved={onChange} onDirty={setDirty} />
          ))}

        {(item.status === "verified" || (!editable && item.status === "entered")) && <ResultsTable item={item} />}

        {item.status === "verified" && (
          <p className="flex items-center gap-1.5 text-xs text-pine">
            <CheckCircle2 className="h-3.5 w-3.5" /> Verified by {item.verified_by_name}
            {item.verifier_qualification ? `, ${item.verifier_qualification}` : ""} · {formatDateTime(item.verified_at)}
            {item.critical_note ? ` · Critical value informed: ${item.critical_note}` : ""}
          </p>
        )}
        {item.amendments.length > 0 && (
          <p className="text-[11px] text-ink-faint">
            Corrections:{" "}
            {item.amendments.map((entry) => `v${entry.version} reopened by ${entry.reopened_by_name} — ${entry.reason}`).join("; ")}
          </p>
        )}

        {mayVerify && (
          <div className="space-y-2 rounded-lg border border-pine/20 bg-mint/40 p-3">
            {item.ranges_reviewed === false && (
              <p className="flex items-start gap-1.5 text-sm text-clay">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                The reference ranges for this test have not been reviewed. Review them in the{" "}
                <Link href="/lab/tests" className="underline">
                  test list
                </Link>{" "}
                first.
              </p>
            )}
            {critical.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm font-medium text-clay">
                  Critical: {critical.map((row) => `${row.name} ${row.value}${row.unit ? ` ${row.unit}` : ""}`).join(", ")}
                </p>
                <Input
                  placeholder="Who was told, and when — e.g. Dr Rao by phone, 10:40"
                  value={criticalNote}
                  onChange={(event) => setCriticalNote(event.target.value)}
                />
              </div>
            )}
            {error && <p className="text-sm text-clay">{error}</p>}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                disabled={verifying || dirty || item.ranges_reviewed === false || (critical.length > 0 && criticalNote.trim().length < 5)}
                onClick={() => void verify()}
              >
                {verifying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />} Verify
              </Button>
              {dirty && <span className="text-xs text-marigold-deep">Save the changes before verifying.</span>}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------- request
export function LabRequestView({ requestId }: { requestId: string }) {
  const { user } = useAuth();
  const [request, setRequest] = useState<LabRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string[]>([]);
  const [ask, setAsk] = useState<ReasonRequest | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [organisms, setOrganisms] = useState<LabMaster[]>([]);
  const [antibiotics, setAntibiotics] = useState<LabMaster[]>([]);

  const load = useCallback(async () => {
    try {
      setRequest(await staffApi.labRequest(requestId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request could not be loaded.");
    }
  }, [requestId]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasCulture = request?.items.some((item) => item.is_culture) ?? false;
  useEffect(() => {
    if (!hasCulture) return;
    void staffApi.labMasters({ kind: "organism" }).then(setOrganisms).catch(() => undefined);
    void staffApi.labMasters({ kind: "antibiotic" }).then(setAntibiotics).catch(() => undefined);
  }, [hasCulture]);

  const apply = useCallback((next: LabRequest) => {
    setRequest(next);
    if (next.notes && next.notes.length) setNotice(next.notes);
  }, []);

  async function act(key: string, run: () => Promise<LabRequest>) {
    setBusy(key);
    setError(null);
    try {
      apply(await run());
    } catch (err) {
      setError(err instanceof Error ? err.message : "That could not be done.");
    } finally {
      setBusy(null);
    }
  }

  async function print() {
    setBusy("print");
    setError(null);
    try {
      const url = URL.createObjectURL(await staffApi.labReportPdf(requestId));
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The report could not be printed.");
    } finally {
      setBusy(null);
    }
  }

  if (!request) {
    return error ? (
      <Card className="border-clay/30 bg-clay/5 p-6">
        <p className="text-sm text-clay">{error}</p>
      </Card>
    ) : (
      <p className="text-sm text-ink-muted">Loading…</p>
    );
  }

  const open = request.status !== "cancelled";
  const cancellable = request.items.some((item) => item.status !== "verified" && item.status !== "cancelled");

  return (
    <div className="space-y-4">
      <Link href="/lab" className="inline-flex items-center gap-1 text-sm text-ink-muted hover:text-pine">
        <ArrowLeft className="h-3.5 w-3.5" /> Worklist
      </Link>

      <Card>
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-mono text-lg font-semibold text-pine">{request.lab_number}</p>
              <p className="text-base font-medium text-ink">{request.patient.name}</p>
              <p className="text-sm text-ink-muted">
                {request.patient.uhid ?? "No UHID"} · {request.patient.age} y · {request.patient.gender}
                {request.admission ? ` · ${request.admission.ip_number}` : ""}
              </p>
            </div>
            <div className="text-right text-sm">
              <p className="font-medium text-ink">{REQUEST_STATUS_LABEL[request.status]}</p>
              {request.priority !== "routine" && <p className="font-semibold uppercase text-clay">{request.priority}</p>}
              <p className="text-xs text-ink-muted">
                Registered {formatDateTime(request.created_at)} by {request.registered_by_name}
              </p>
              {request.referred_by && <p className="text-xs text-ink-muted">Referred by {request.referred_by}</p>}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm">
            <p className="text-ink-muted">
              Sample:{" "}
              {request.sample_collected_at ? (
                <span className="text-ink">
                  collected {formatDateTime(request.sample_collected_at)} by {request.sample_collected_by_name}
                </span>
              ) : (
                <span className="text-marigold-deep">not collected yet</span>
              )}
            </p>
            <p className="text-ink-muted">
              Billing: <span className="text-ink">{BILLING_LABEL[request.billing]}</span>
              {request.invoice && (
                <span className="text-ink">
                  {" "}
                  · {request.invoice.invoice_number} · {formatINR(request.invoice.total_paise)}
                  {request.invoice.status === "cancelled"
                    ? " · cancelled"
                    : request.invoice.balance_paise > 0
                      ? ` · ${formatINR(request.invoice.balance_paise)} to collect at the counter`
                      : " · paid"}
                </span>
              )}
            </p>
            {request.clinical_notes && <p className="text-ink-muted">Notes: <span className="text-ink">{request.clinical_notes}</span></p>}
          </div>

          <div className="flex flex-wrap gap-2">
            {open && !request.sample_collected_at && canEnterLab(user?.role) && (
              <Button size="sm" disabled={busy !== null} onClick={() => void act("collect", () => staffApi.collectLabSample(request.id))}>
                {busy === "collect" && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Mark sample collected
              </Button>
            )}
            {request.printable && (
              <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void print()}>
                {busy === "print" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Printer className="h-3.5 w-3.5" />} Print report
              </Button>
            )}
            {open && request.billing === "unbilled" && canRegisterLab(user?.role) && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null || !canBillAtCounter(user?.role)}
                  onClick={() => void act("bill", () => staffApi.billLabRequest(request.id, { billing: "invoice" }))}
                >
                  Bill at the counter
                </Button>
                {request.admission && (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy !== null}
                    onClick={() =>
                      void act("bill", () => staffApi.billLabRequest(request.id, { billing: "ipd", admission_id: request.admission?.id }))
                    }
                  >
                    Bill to {request.admission.ip_number}
                  </Button>
                )}
              </>
            )}
            {open && cancellable && canRegisterLab(user?.role) && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setAsk({
                    title: `Cancel every open test on ${request.lab_number}?`,
                    detail: "Verified results stay. An unpaid bill is corrected or cancelled; for a paid one the refund due is shown.",
                    confirmLabel: "Cancel tests",
                    destructive: true,
                    run: async (reason) => {
                      const remaining = request.items
                        .filter((item) => item.status !== "verified" && item.status !== "cancelled")
                        .map((item) => item.id);
                      apply(await staffApi.cancelLab(request.id, { reason, item_ids: remaining }));
                    },
                  })
                }
              >
                <XCircle className="h-3.5 w-3.5" /> Cancel open tests
              </Button>
            )}
          </div>

          {notice.length > 0 && (
            <div className="rounded-md bg-marigold/10 px-3 py-2 text-sm text-marigold-deep">
              {notice.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          )}
          {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}
        </CardContent>
      </Card>

      {request.items.map((item) => (
        <ItemCard
          key={item.id}
          item={item}
          request={request}
          organisms={organisms}
          antibiotics={antibiotics}
          onChange={apply}
          onAsk={setAsk}
        />
      ))}

      <ReasonDialog request={ask} onClose={() => setAsk(null)} onDone={() => setAsk(null)} />
    </div>
  );
}
