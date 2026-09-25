"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Check, Clock, Loader2, Mic, Save } from "lucide-react";
import { useConsultation } from "@/lib/hooks/useConsultation";
import type { QueuedPatient } from "@/lib/types/emr";
import type { ConsultationDetail, MedicalRecord } from "@/lib/types/core";
import { DEPARTMENT_LABEL } from "@/lib/format";
import { staffApi } from "@/lib/staffApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { UploadQr } from "@/components/intake/upload-qr";

type Vitals = {
  bpSys: string;
  bpDia: string;
  pulse: string;
  spo2: string;
  temperature: string;
  respiration: string;
  height: string;
  weight: string;
  sugar: string;
  notes: string;
};

const EMPTY_VITALS: Vitals = {
  bpSys: "",
  bpDia: "",
  pulse: "",
  spo2: "",
  temperature: "",
  respiration: "",
  height: "",
  weight: "",
  sugar: "",
  notes: "",
};

function storedVitals(consultation?: ConsultationDetail | null): Vitals {
  const dossier = consultation?.medical_json as Record<string, unknown> | null | undefined;
  const value = dossier?.vitals;
  return value && typeof value === "object"
    ? { ...EMPTY_VITALS, ...(value as Partial<Vitals>) }
    : EMPTY_VITALS;
}

export function LiveIntakeWorkspace({
  patient,
  consultationId,
  token,
  consultation: initialConsultation,
  onBack,
  onRestartSession,
}: {
  patient: QueuedPatient;
  consultationId: string;
  token: string | null;
  consultation?: ConsultationDetail | null;
  onBack: () => void;
  onRestartSession?: (session: { consultation_id: string; session_token: string }) => void;
}) {
  const initialEntries = (initialConsultation?.turns ?? []).map((turn, index) => ({
    id: index + 1,
    role: turn.role,
    text: turn.content,
    interrupted: turn.interrupted,
  }));
  const { phase, entries, error, endConsultation, restartConsultation } = useConsultation(
    consultationId,
    token,
    initialEntries
  );
  const [consultation, setConsultation] = useState<ConsultationDetail | null>(initialConsultation ?? null);
  const [vitals, setVitals] = useState<Vitals>(() => storedVitals(initialConsultation));
  const [saved, setSaved] = useState(false);
  const [vitalsError, setVitalsError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);

  // Reload once whenever the intake ends. Not only when nothing was loaded:
  // a reopened or restarted intake starts with the earlier record, and kept
  // showing "Not captured yet" after the new conversation had filled it in.
  useEffect(() => {
    if (phase !== "ended") return;
    let cancelled = false;
    staffApi.consultation(consultationId).then((result) => {
      if (!cancelled) setConsultation(result);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [consultationId, phase]);

  useEffect(() => {
    const container = transcriptRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [entries]);

  function updateVital(key: keyof Vitals, value: string) {
    setVitals((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  async function saveVitals() {
    setSaved(false);
    setVitalsError(null);
    try {
      const result = await staffApi.updateConsultationVitals(consultationId, vitals);
      setConsultation(result);
      setSaved(true);
    } catch (err) {
      setVitalsError(err instanceof Error ? err.message : "Could not save vitals.");
      setSaved(false);
    }
  }

  async function finish() {
    setEnding(true);
    await endConsultation();
    setEnding(false);
  }

  async function restart() {
    setRestarting(true);
    const replacement = await restartConsultation();
    if (replacement) {
      sessionStorage.setItem(`consult:${replacement.consultation_id}`, replacement.session_token);
      onRestartSession?.(replacement);
    }
    setRestarting(false);
  }

  const phaseLabel = phase === "speaking" ? "Assistant speaking" : phase === "thinking" ? "Thinking" : phase === "ended" ? "Completed" : "Waiting";
  const record: MedicalRecord | undefined = consultation?.medical_json?.medical_json;
  const readOnly = !token;

  return (
    <div className="flex h-[calc(100dvh-113px)] min-h-[520px] flex-col gap-3">
      <div className="flex shrink-0 items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} disabled={phase !== "ended" && phase !== "error"}>
          <ArrowLeft /> Queue
        </Button>
        {/* One line: who the patient is, then straight into the conversation.
            Two stacked lines cost the photograph an inch of its height. */}
        <div className="flex min-w-0 items-baseline gap-2">
          <h1 className="truncate font-display text-base font-semibold text-pine">{patient.patient.name}</h1>
          <p className="truncate text-xs text-ink-muted">
            {patient.patient.age} yrs · {patient.patient.gender} ·{" "}
            {DEPARTMENT_LABEL[patient.department] ?? patient.department}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-full bg-marigold/20 px-3 py-1.5 text-xs font-semibold text-marigold-deep">
            <Clock className="h-3.5 w-3.5" /> {phaseLabel}
          </span>
          {!readOnly && phase !== "ended" && phase !== "error" && (
            <>
              <Button size="sm" variant="outline" onClick={() => void finish()} disabled={ending || restarting}>
                {ending ? <Loader2 className="animate-spin" /> : <Check />} End consultation
              </Button>
              <Button size="sm" onClick={() => void finish()} disabled={ending || restarting}>Done</Button>
              <Button size="sm" variant="ghost" onClick={() => void restart()} disabled={ending || restarting}>
                {restarting ? <Loader2 className="animate-spin" /> : <RefreshIcon />} Restart
              </Button>
            </>
          )}
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-3 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
        <div className="min-h-0 space-y-3 overflow-y-auto">
          <Card>
            <CardHeader className="pb-2"><CardTitle>Presenting complaint</CardTitle></CardHeader>
            <CardContent className="space-y-0 divide-y divide-border">
              <InfoRow label="Chief complaint" value={record?.chief_complaint ?? "Not captured yet"} />
              <InfoRow label="Duration" value={record?.duration ?? "Will update after intake"} />
              <InfoRow label="Pain site" value={record?.pain?.location ?? "Not captured yet"} />
              <InfoRow label="Pain score" value={record?.pain?.score_out_of_10 != null ? `${record.pain.score_out_of_10} / 10` : "Not captured yet"} />
              <InfoRow label="Patient" value={patient.patient.name} />
              <InfoRow label="UHID" value={patient.patient.uhid ?? "Not assigned"} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
              <div><CardTitle>Vitals</CardTitle><p className="mt-1 text-xs text-ink-muted">Record before or during intake</p></div>
              <Button size="sm" variant="outline" onClick={() => void saveVitals()} disabled={readOnly}><Save /> {saved ? "Saved" : "Save"}</Button>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2">
              {([
                ["bpSys", "BP sys mmHg"], ["bpDia", "BP dia mmHg"], ["pulse", "Pulse /min"],
                ["spo2", "SpO₂ %"], ["temperature", "Temp °F"], ["respiration", "Resp /min"],
                ["height", "Height cm"], ["weight", "Weight kg"], ["sugar", "Sugar mg/dL"],
              ] as [keyof Vitals, string][]).map(([key, label]) => (
                <label key={key} className="text-xs text-ink-muted">
                  {label}
                  <Input value={vitals[key]} onChange={(event) => updateVital(key, event.target.value)} className="mt-1 h-9" inputMode="decimal" />
                </label>
              ))}
              <label className="col-span-2 text-xs text-ink-muted">Notes
                <textarea value={vitals.notes} onChange={(event) => updateVital("notes", event.target.value)} className="field-input mt-1 h-14 resize-none text-sm" />
              </label>
              {vitalsError && <p className="col-span-2 text-xs text-clay">{vitalsError}</p>}
            </CardContent>
          </Card>

          {/* Beside the vitals because it belongs to the same moment: the
              nurse has the patient in front of them with a bag of papers,
              and this is the only point in the visit where photographing
              them costs nobody anything. */}
          <UploadQr consultationId={consultationId} />
        </div>

        <Card className="flex min-h-0 flex-col overflow-hidden">
          <CardHeader className="flex-row items-center justify-between space-y-0 border-b border-border py-2">
            <CardTitle className="flex items-center gap-2"><Mic className="h-4 w-4 text-pine" /> Conversation</CardTitle>
            <span className="text-xs text-ink-muted">{entries.length} turns · verbatim record</span>
          </CardHeader>
          {/* The assistant, at the head of the conversation and staying
              there: the tablet faces the patient, and a face to speak to
              carries a voice call that is otherwise a wall of text. It sits
              outside the scrolling area on purpose — only the conversation
              moves, as it always has. */}
          <div className="relative shrink-0 overflow-hidden border-b border-border">
            <Image
              src="/brand/intake-assistant.webp"
              alt=""
              width={1600}
              height={600}
              // The banner is the width of the conversation panel, a little
              // over two thirds of a tablet's screen; without this the
              // browser picks a 700px copy and upscales it.
              sizes="(max-width: 1024px) 100vw, 70vw"
              priority
              className="h-52 w-full object-cover object-[center_30%] sm:h-64"
            />
            {/* Said plainly, because the picture does not say it: the voice
                is an assistant preparing the visit, not a doctor. */}
            <span className="absolute bottom-2 left-3 rounded-full bg-pine-deep/80 px-2.5 py-1 text-[11px] font-medium text-mint">
              AI intake assistant — not a doctor
            </span>
          </div>
          <CardContent ref={transcriptRef} className="thin-scroll min-h-0 flex-1 space-y-4 overflow-y-auto p-4" role="log" aria-live="polite">
            {entries.length === 0 && <p className="py-12 text-center text-sm text-ink-faint">The conversation will appear here as the patient speaks.</p>}
            {entries.map((entry) => (
              <div key={entry.id} className={entry.role === "patient" ? "flex justify-end" : "flex justify-start"}>
                <div className="max-w-[82%]">
                  <p className={`mb-1 text-[11px] font-semibold uppercase tracking-wide ${entry.role === "patient" ? "text-pine text-right" : "text-marigold-deep"}`}>
                    {entry.role === "patient" ? "Patient" : "Assistant"}
                  </p>
                  <div className={`rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed ${entry.role === "patient" ? "rounded-tr-md bg-mint text-ink" : "rounded-tl-md bg-pine text-mint"}`}>
                    {entry.text}
                    {entry.interrupted && <span className="mt-1 block text-[11px] italic opacity-70">interrupted by the patient</span>}
                  </div>
                </div>
              </div>
            ))}
            {error && <p className="rounded-lg bg-clay/10 p-3 text-sm text-clay">{error}</p>}
          </CardContent>
          {phase === "ended" && <div className="flex items-center justify-between border-t border-border bg-mint/50 px-4 py-3"><p className="text-sm font-medium text-pine">Intake complete. Review the record before continuing.</p><Button size="sm" onClick={onBack}>Return to queue</Button></div>}
          {phase === "error" && <div className="flex items-center justify-between border-t border-border px-4 py-3"><p className="text-sm text-clay">The consultation connection was interrupted.</p><Button size="sm" variant="outline" onClick={() => void restart()} disabled={restarting}>{restarting ? <Loader2 className="animate-spin" /> : <RefreshIcon />} Restart</Button></div>}
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between gap-3 py-2"><span className="text-xs uppercase tracking-wide text-ink-faint">{label}</span><span className="truncate text-right text-sm font-medium text-ink">{value}</span></div>;
}

function RefreshIcon() {
  return <span aria-hidden="true">↻</span>;
}