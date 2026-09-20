"use client";

/**
 * Prescription composer.
 *
 * Voice dictation is a fast way to fill the form — never a way to bypass it.
 * Parsed rows land in editable fields, deterministic safety checks re-run on
 * every change, and serious warnings must be acknowledged before issuing.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, Check, FileText, Loader2, Mic, MicOff, Plus, ShieldAlert, Sparkles, Trash2,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useDictation } from "@/lib/hooks/useDictation";
import type { MedicineRow, Prescription, PrescriptionAssist, SafetyAlert } from "@/lib/types/prescriptions";
import { FOLLOW_UP_OPTIONS, durationForFollowUp } from "@/lib/types/prescriptions";
import { MedicineRowEditor } from "@/components/prescriptions/medicine-row";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useModules } from "@/components/dashboard/modules-provider";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

let rowCounter = 0;
const newKey = () => `row-${++rowCounter}-${Date.now()}`;

function emptyRow(): MedicineRow {
  return { key: newKey(), name: "", source: "manual" };
}

const SEVERITY_STYLE: Record<SafetyAlert["severity"], string> = {
  serious: "border-clay/45 bg-clay/[0.05]",
  caution: "border-marigold/45 bg-marigold/[0.05]",
  info: "border-border bg-white",
};

function alertKey(alert: SafetyAlert) {
  return `${alert.kind}:${[...alert.medicines].sort().join("+")}`;
}

export function PrescriptionComposer({
  open,
  onOpenChange,
  patientId,
  consultationId,
  department,
  prefill,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  patientId: string;
  consultationId?: string | null;
  department?: string;
  prefill?: {
    diagnosis?: string | null;
    chiefComplaint?: string | null;
    investigations?: string[];
  };
  onCreated: (prescription: Prescription) => void;
}) {
  const dictation = useDictation();
  // True while this department's drafted formulary is still withheld; see
  // APPROVED_FORMULARY in the backend configuration.
  const { formularyPendingSignoff } = useModules();
  const formularyPending =
    department !== undefined && formularyPendingSignoff.includes(department);

  const [rows, setRows] = useState<MedicineRow[]>([emptyRow()]);
  const [diagnosis, setDiagnosis] = useState("");
  const [cause, setCause] = useState("");
  const [chiefComplaint, setChiefComplaint] = useState("");
  const [findings, setFindings] = useState("");
  const [instructions, setInstructions] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [followUpDays, setFollowUpDays] = useState<number | null>(null);

  /**
   * Choosing a follow-up interval also sets how long each medicine runs.
   *
   * Rows the doctor has already given an explicit duration are left alone —
   * a three-month calcium course should not be cut to eight days because the
   * review is next week.
   */
  function applyFollowUp(days: number | null) {
    setFollowUpDays(days);
    if (days === null) {
      setFollowUp("");
      return;
    }
    const option = FOLLOW_UP_OPTIONS.find((item) => item.days === days);
    setFollowUp(option ? `Review ${option.label.toLowerCase()}` : `Review after ${days} days`);
    const duration = durationForFollowUp(days);
    setRows((current) =>
      current.map((row) =>
        row.name.trim() && (!row.duration || row.durationFromFollowUp)
          ? { ...row, duration, durationFromFollowUp: true }
          : row
      )
    );
  }
  const [investigations, setInvestigations] = useState<string>("");

  const [alerts, setAlerts] = useState<SafetyAlert[]>([]);
  const [allergies, setAllergies] = useState<string[]>([]);
  const [acknowledged, setAcknowledged] = useState<Set<string>>(new Set());
  const [parsing, setParsing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [prefilling, setPrefilling] = useState(false);
  const [prefilled, setPrefilled] = useState(false);
  const [orderedCount, setOrderedCount] = useState(0);
  const [assisting, setAssisting] = useState(false);
  const [templateNames, setTemplateNames] = useState<string[]>([]);

  // Everything except the medicines is composed by the AI from the intake
  // dossier. It is loaded into ordinary editable fields, so the doctor amends
  // or overwrites anything before issuing.
  useEffect(() => {
    if (!open || !consultationId) return;
    setPrefilling(true);
    staffApi
      .prescriptionPrefill(consultationId)
      .then((data) => {
        const value = (key: string) => String((data as Record<string, unknown>)[key] ?? "");
        setDiagnosis(value("diagnosis") || (prefill?.diagnosis ?? ""));
        setCause(value("cause"));
        setChiefComplaint(value("chief_complaint") || (prefill?.chiefComplaint ?? ""));
        setFindings(value("clinical_findings"));
        setInstructions(value("general_instructions"));
        setFollowUp(value("follow_up_notes"));
        const tests = (data as { investigations?: string[] }).investigations ?? [];
        setInvestigations(
          (tests.length ? tests : prefill?.investigations ?? []).join("\n")
        );
        setOrderedCount(
          ((data as { investigations_ordered?: string[] }).investigations_ordered ?? []).length
        );
        setPrefilled(true);
      })
      .catch(() => {
        // Prefill is a convenience, never a blocker: fall back to whatever the
        // consultation page already passed in.
        setDiagnosis(prefill?.diagnosis ?? "");
        setChiefComplaint(prefill?.chiefComplaint ?? "");
        setInvestigations((prefill?.investigations ?? []).join("\n"));
      })
      .finally(() => setPrefilling(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, consultationId]);

  const filledRows = useMemo(() => rows.filter((row) => row.name.trim()), [rows]);

  // Re-run deterministic safety checks whenever the medicine list changes.
  useEffect(() => {
    if (!open) return;
    const payload = filledRows.map((row) => ({
      name: row.name,
      formulary_code: row.formulary_code ?? null,
      frequency_text: row.frequency_text ?? null,
      frequency_code: row.frequency_code ?? null,
    }));
    if (payload.length === 0) {
      setAlerts([]);
      return;
    }
    const timer = setTimeout(() => {
      staffApi
        .safetyCheck(patientId, payload)
        .then((result) => {
          setAlerts(result.alerts);
          setAllergies(result.known_allergies);
        })
        .catch(() => undefined);
    }, 300);
    return () => clearTimeout(timer);
  }, [filledRows, patientId, open]);

  const blocking = alerts.filter((alert) => alert.severity === "serious");
  const unacknowledged = blocking.filter((alert) => !acknowledged.has(alertKey(alert)));

  const applyDictation = useCallback(async () => {
    const transcript = dictation.transcript.trim();
    if (!transcript) return;
    setParsing(true);
    setError(null);
    try {
      const result = await staffApi.parseDictation(transcript, patientId);
      const parsed: MedicineRow[] = result.medicines.map((medicine) => ({
        key: newKey(),
        name: medicine.name,
        formulary_code: medicine.formulary_code,
        generic: medicine.generic,
        form: medicine.form,
        strength: medicine.strength,
        dosage: medicine.dosage,
        frequency_code: medicine.frequency_code,
        frequency_text: medicine.frequency_text,
        duration: medicine.duration,
        timing: medicine.timing,
        route: medicine.route,
        instructions: medicine.instructions,
        source: "dictated",
        confidence: medicine.confidence,
        unmatched: medicine.unmatched,
        substituted: medicine.substituted,
        warnings: medicine.warnings,
      }));
      setRows((current) => {
        const kept = current.filter((row) => row.name.trim());
        return [...kept, ...parsed, emptyRow()];
      });
      dictation.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that dictation.");
    } finally {
      setParsing(false);
    }
  }, [dictation, patientId]);

  async function suggestFromDiagnosis() {
    if (!diagnosis.trim()) {
      setError("Enter the clinical diagnosis before suggesting medicines.");
      return;
    }
    setAssisting(true);
    setError(null);
    try {
      const result: PrescriptionAssist = await staffApi.prescriptionAssist({
        consultation_id: consultationId,
        diagnosis: diagnosis.trim(),
        department,
      });
      if (result.medicines.length === 0) {
        setError("No matching medicine template found. Add medicines manually or search the formulary.");
        return;
      }
      const suggested: MedicineRow[] = result.medicines.map((medicine) => ({
        ...medicine,
        key: newKey(),
        source: "template",
      }));
      setRows((current) => [...current.filter((row) => row.name.trim()), ...suggested, emptyRow()]);
      setTemplateNames(result.templates);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not suggest medicines from this diagnosis.");
    } finally {
      setAssisting(false);
    }
  }

  async function submit() {
    if (filledRows.length === 0) {
      setError("Add at least one medicine.");
      return;
    }
    if (!diagnosis.trim()) {
      setError("Confirm the diagnosis before issuing.");
      return;
    }
    if (unacknowledged.length > 0) {
      setError("Acknowledge the serious safety warnings first.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const prescription = await staffApi.createPrescription({
        patient_id: patientId,
        consultation_id: consultationId ?? null,
        medicines: filledRows.map((row) => ({
          name: row.name,
          formulary_code: row.formulary_code ?? null,
          generic: row.generic ?? null,
          form: row.form ?? null,
          strength: row.strength ?? null,
          dosage: row.dosage ?? null,
          frequency_code: row.frequency_code ?? null,
          frequency_text: row.frequency_text ?? null,
          duration: row.duration ?? null,
          timing: row.timing ?? null,
          route: row.route ?? null,
          instructions: row.instructions ?? null,
          source: row.source,
        })),
        diagnosis: diagnosis.trim(),
        cause: cause.trim() || null,
        chief_complaint: chiefComplaint.trim() || null,
        clinical_findings: findings.trim() || null,
        investigations: investigations.split("\n").map((line) => line.trim()).filter(Boolean),
        general_instructions: instructions.trim() || null,
        follow_up_notes: followUp.trim() || null,
        dictation_transcript: dictation.transcript || null,
        acknowledged_alerts: blocking.map((alert) => ({
          kind: alert.kind,
          medicines: alert.medicines,
        })),
        issue: true,
      });
      onCreated(prescription);
      onOpenChange(false);
      // Reset for the next patient.
      setRows([emptyRow()]);
      setDiagnosis(""); setCause(""); setFindings(""); setInstructions(""); setFollowUp("");
      setAcknowledged(new Set());
      dictation.reset();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the prescription.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[92vh] max-h-[900px] w-[96vw] max-w-6xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <DialogTitle>Create prescription</DialogTitle>
          <DialogDescription>
            Dictate or type. Every line stays editable and is checked before issuing.
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          {/* Left: composition */}
          <div className="thin-scroll min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
            {/* Dictation */}
            <Card className={cn(dictation.listening && "border-clay/50 bg-clay/[0.03]")}>
              <CardContent className="p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    type="button"
                    variant={dictation.listening ? "destructive" : "default"}
                    onClick={() => (dictation.listening ? dictation.stop() : dictation.start())}
                  >
                    {dictation.listening ? <MicOff /> : <Mic />}
                    {dictation.listening ? "Stop dictation" : "Dictate medicines"}
                  </Button>

                  {dictation.listening && (
                    <span className="flex items-center gap-2 text-sm text-clay">
                      <span className="relative flex h-2 w-2">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-clay opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-clay" />
                      </span>
                      Listening — speak naturally
                    </span>
                  )}
                  {dictation.state === "connecting" && (
                    <span className="flex items-center gap-2 text-sm text-ink-muted">
                      <Loader2 className="h-4 w-4 animate-spin" /> Connecting…
                    </span>
                  )}

                  {dictation.transcript && !dictation.listening && (
                    <>
                      <Button type="button" variant="accent" onClick={applyDictation} disabled={parsing}>
                        {parsing ? <Loader2 className="animate-spin" /> : <Sparkles />}
                        Convert to medicines
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={dictation.reset}>
                        <Trash2 /> Clear
                      </Button>
                    </>
                  )}
                </div>

                {dictation.error && (
                  <p className="mt-2 text-xs text-clay">{dictation.error}</p>
                )}

                {dictation.transcript ? (
                  <div className="mt-3 rounded-lg bg-mint p-3">
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                      Heard
                    </p>
                    <p className="text-sm leading-relaxed text-ink">{dictation.transcript}</p>
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-ink-faint">
                    For example: &ldquo;Tablet Paracetamol 650 mg SOS. Tablet Pantoprazole 40 mg
                    before breakfast. Tablet Calcium once daily.&rdquo;
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Medicines */}
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h4 className="font-display text-sm font-semibold text-pine">
                  Medicines
                  <span className="tabular ml-2 rounded-full bg-pine px-2 py-0.5 text-xs text-mint">
                    {filledRows.length}
                  </span>
                </h4>
                <Button
                  type="button" size="sm" variant="outline"
                  onClick={() => setRows((current) => [...current, emptyRow()])}
                >
                  <Plus /> Add medicine
                </Button>
              </div>

              {formularyPending && (
                // Otherwise a doctor searching a near-empty formulary concludes
                // the system is broken. It is not: this speciality's medicine
                // list is drafted and withheld until a consultant of that
                // speciality has been through it.
                <p className="mb-2 rounded-lg border border-ochre/30 bg-ochre/5 px-3 py-2 text-xs text-ink-muted">
                  This department&apos;s medicine list and regimen templates are
                  awaiting a specialist&apos;s review, so they are not offered
                  here yet. Type any medicine by name to prescribe it as usual.
                </p>
              )}

              <div className="space-y-2">
                <AnimatePresence initial={false}>
                  {rows.map((row, index) => (
                    <motion.div
                      key={row.key}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.15 }}
                    >
                      <MedicineRowEditor
                        row={row}
                        index={index}
                        onChange={(updated) =>
                          setRows((current) =>
                            current.map((item) => (item.key === updated.key ? updated : item))
                          )
                        }
                        onRemove={() =>
                          setRows((current) => {
                            const next = current.filter((item) => item.key !== row.key);
                            return next.length ? next : [emptyRow()];
                          })
                        }
                      />
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
            </div>

            {/* Clinical detail */}
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h4 className="font-display text-sm font-semibold text-pine">Clinical detail</h4>
                {prefilling ? (
                  <span className="flex items-center gap-1.5 text-xs text-ink-muted">
                    <Loader2 className="h-3 w-3 animate-spin" /> Filling from the consultation…
                  </span>
                ) : prefilled ? (
                  <span className="flex items-center gap-1.5 text-xs text-marigold-deep">
                    <Sparkles className="h-3 w-3" />
                    Filled by AI from the intake — review and edit
                  </span>
                ) : null}
              </div>
              <div>
                <label className="field-label" htmlFor="diagnosis">
                  Clinical diagnosis <span className="text-clay">*</span>
                </label>
                <Input
                  id="diagnosis" value={diagnosis}
                  onChange={(event) => setDiagnosis(event.target.value)}
                  placeholder="e.g. comminuted fracture olecranon right elbow with tendon injury"
                />
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <Button type="button" size="sm" variant="accent" onClick={() => void suggestFromDiagnosis()} disabled={assisting}>
                    {assisting ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Suggest medicines from diagnosis
                  </Button>
                  {templateNames.map((name) => (
                    <Badge key={name} variant="ai" size="sm">Template: {name}</Badge>
                  ))}
                </div>
                <p className="mt-1 text-[11px] text-ink-faint">
                  Uses the diagnosis plus intake findings, allergies, current medicines and investigations. Review every row before issuing.
                </p>
              </div>
              <div>
                <label className="field-label" htmlFor="cause">Cause</label>
                <Input
                  id="cause" value={cause}
                  onChange={(event) => setCause(event.target.value)}
                  placeholder="What is driving it — mechanism, trigger or contributing factor"
                />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="field-label" htmlFor="complaint">Chief complaint</label>
                  <Input
                    id="complaint" value={chiefComplaint}
                    onChange={(event) => setChiefComplaint(event.target.value)}
                  />
                </div>
                <div>
                  <label className="field-label" htmlFor="followup">Follow-up</label>
                  <select
                    id="followup"
                    value={followUpDays ?? ""}
                    onChange={(event) =>
                      applyFollowUp(event.target.value ? Number(event.target.value) : null)
                    }
                    className="field-input"
                  >
                    <option value="">No follow-up set</option>
                    {FOLLOW_UP_OPTIONS.map((option) => (
                      <option key={option.days} value={option.days}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  {followUpDays !== null && (
                    <p className="mt-1 text-[11px] text-marigold-deep">
                      Medicines set to {durationForFollowUp(followUpDays)} — one day past
                      the review.
                    </p>
                  )}
                </div>
              </div>
              <div>
                <label className="field-label" htmlFor="findings">Clinical findings</label>
                <textarea
                  id="findings" value={findings} rows={2}
                  onChange={(event) => setFindings(event.target.value)}
                  className="field-input resize-none text-sm"
                  placeholder="Examination findings"
                />
              </div>
              <div>
                <label className="field-label" htmlFor="investigations">
                  Investigations advised (one per line)
                  {orderedCount > 0 && (
                    <span className="ml-2 font-normal normal-case tracking-normal text-marigold-deep">
                      {orderedCount} ordered on this visit, already added
                    </span>
                  )}
                </label>
                <textarea
                  id="investigations" value={investigations} rows={2}
                  onChange={(event) => setInvestigations(event.target.value)}
                  className="field-input resize-none text-sm"
                />
              </div>
              <div>
                <label className="field-label" htmlFor="advice">General instructions</label>
                <textarea
                  id="advice" value={instructions} rows={2}
                  onChange={(event) => setInstructions(event.target.value)}
                  className="field-input resize-none text-sm"
                  placeholder="Diet, activity, warning signs"
                />
              </div>
            </div>
          </div>

          {/* Right: safety */}
          <div className="flex w-full min-h-0 flex-col border-t border-border bg-mint/40 lg:w-[360px] lg:border-l lg:border-t-0">
            <div className="border-b border-border px-5 py-3">
              <p className="flex items-center gap-2 font-display text-sm font-semibold text-pine">
                <ShieldAlert className="h-4 w-4" /> Safety checks
              </p>
              <p className="mt-0.5 text-[11px] text-ink-muted">
                Rule-based and instant — not AI inference.
              </p>
            </div>

            <div className="thin-scroll min-h-0 flex-1 space-y-2 overflow-y-auto px-5 py-3">
              {allergies.length > 0 && (
                <div className="rounded-lg bg-clay/[0.07] px-3 py-2">
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-clay">
                    Known allergies
                  </p>
                  <p className="text-xs text-ink">{allergies.join(", ")}</p>
                </div>
              )}

              {alerts.length === 0 ? (
                <p className="py-8 text-center text-sm text-ink-faint">
                  {filledRows.length === 0
                    ? "Add medicines to run the checks."
                    : "No conflicts found in this list."}
                </p>
              ) : (
                alerts.map((alert) => {
                  const key = alertKey(alert);
                  const isAcknowledged = acknowledged.has(key);
                  return (
                    <div
                      key={key}
                      className={cn("rounded-lg border p-3", SEVERITY_STYLE[alert.severity])}
                    >
                      <div className="mb-1 flex flex-wrap items-center gap-1.5">
                        <Badge
                          variant={
                            alert.severity === "serious" ? "danger"
                            : alert.severity === "caution" ? "warning" : "outline"
                          }
                          size="sm"
                        >
                          {alert.kind}
                        </Badge>
                        {alert.detected_by === "rule" && (
                          <span className="text-[10px] uppercase tracking-wide text-ink-faint">
                            rule-based
                          </span>
                        )}
                      </div>
                      <p className="text-xs leading-relaxed text-ink">{alert.description}</p>
                      {alert.suggested_action && (
                        <p className="mt-1 text-xs font-medium text-pine">
                          {alert.suggested_action}
                        </p>
                      )}
                      {alert.severity === "serious" && (
                        <button
                          type="button"
                          onClick={() =>
                            setAcknowledged((current) => {
                              const next = new Set(current);
                              if (next.has(key)) next.delete(key);
                              else next.add(key);
                              return next;
                            })
                          }
                          className={cn(
                            "mt-2 inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-semibold transition",
                            isAcknowledged
                              ? "bg-pine text-mint"
                              : "border border-clay/40 text-clay hover:bg-clay hover:text-white"
                          )}
                        >
                          {isAcknowledged ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
                          {isAcknowledged ? "Acknowledged" : "Acknowledge to proceed"}
                        </button>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            <div className="space-y-2 border-t border-border px-5 py-4">
              {error && (
                <p role="alert" className="rounded-md bg-clay/10 px-3 py-2 text-xs text-clay">
                  {error}
                </p>
              )}
              {unacknowledged.length > 0 && (
                <p className="text-xs text-clay">
                  {unacknowledged.length} serious warning
                  {unacknowledged.length === 1 ? "" : "s"} need acknowledging.
                </p>
              )}
              <Button
                className="w-full" size="lg" onClick={submit}
                disabled={submitting || filledRows.length === 0 || unacknowledged.length > 0}
              >
                {submitting ? <Loader2 className="animate-spin" /> : <FileText />}
                Issue prescription &amp; generate PDF
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
