"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  FileText,
  FlaskConical,
  History,
  Loader2,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ConsultationDetail } from "@/lib/types/core";
import {
  DEPARTMENT_LABEL,
  formatDateTime,
} from "@/lib/format";
import { PageHeader } from "@/components/dashboard/page-header";
import { StatusBadge, AiBadge } from "@/components/dashboard/badges";
import { TranscriptView } from "@/components/dashboard/transcript-view";
import { PrescriptionsTab } from "@/components/prescriptions/prescriptions-tab";
import { BroughtReports } from "@/components/investigations/brought-reports";
import { VisitPad } from "@/components/pad/visit-pad";
import { PatientForms } from "@/components/pad/patient-forms";
import { LabResultsPanel } from "@/components/lab/lab-results-panel";
import { RedFlagList, InfoRow } from "@/components/dashboard/clinical-blocks";
import { useModules } from "@/components/dashboard/modules-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";

/** The vitals typed at intake, shown exactly as they were entered. */
function intakeVitals(stored?: Record<string, unknown> | null): [string, string][] {
  if (!stored) return [];
  const read = (key: string) => String(stored[key] ?? "").trim();
  const rows: [string, string][] = [];
  if (read("bpSys") || read("bpDia")) rows.push(["Blood pressure", `${read("bpSys") || "—"} / ${read("bpDia") || "—"}`]);
  const named: [string, string][] = [
    ["pulse", "Pulse"], ["spo2", "SpO2"], ["temperature", "Temperature"], ["respiration", "Respiration"],
    ["weight", "Weight"], ["height", "Height"], ["sugar", "Blood sugar"], ["notes", "Notes"],
  ];
  for (const [key, label] of named) {
    if (read(key)) rows.push([label, read(key)]);
  }
  return rows;
}

export default function ConsultationDetailPage() {
  const hasLab = useModules().has("laboratory");
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<ConsultationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await staffApi.consultation(params.id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this consultation.");
    }
  }, [params.id]);

  useEffect(() => {
    void load();
  }, [load]);

  // Live consultations keep refreshing so the doctor sees the intake unfold.
  useEffect(() => {
    if (data?.status !== "in_progress") return;
    const timer = setInterval(() => void load(), 6000);
    return () => clearInterval(timer);
  }, [data?.status, load]);

  async function markReviewed() {
    setMarking(true);
    try {
      setData(await staffApi.markReviewed(params.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the record.");
    } finally {
      setMarking(false);
    }
  }

  if (error && !data) {
    return (
      <Card className="border-clay/30 bg-clay/5 p-6">
        <p className="text-sm text-clay">{error}</p>
        <Button variant="outline" className="mt-4" onClick={() => router.back()}>
          <ArrowLeft /> Go back
        </Button>
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  const dossier = data.medical_json;
  const record = dossier?.medical_json;
  const summary = dossier?.clinical_summary;
  const vitals = intakeVitals((dossier as { vitals?: Record<string, unknown> } | null | undefined)?.vitals);
  const reviewed = Boolean(dossier?.reviewed_at);
  const live = data.status === "in_progress";
  const intakePoints = [
    summary?.one_liner,
    summary?.history_of_present_illness,
    ...(summary?.pertinent_positives ?? []),
    record?.chief_complaint ? `Complaint: ${record.chief_complaint}` : null,
    record?.duration ? `Duration: ${record.duration}` : null,
    record?.pain?.location ? `Pain site: ${record.pain.location}` : null,
  ].filter((point): point is string => Boolean(point?.trim()));

  return (
    <>
      <div className="mb-5 flex items-center gap-3">
        <Button variant="ghost" size="sm" className="-ml-2" onClick={() => router.back()}>
          <ArrowLeft /> Back
        </Button>
        <StatusBadge status={data.status} reviewed={reviewed} />
        <p className="ml-auto hidden text-xs text-ink-muted sm:block">
          {formatDateTime(data.started_at)}
        </p>
      </div>

      <PageHeader
        title={data.patient.name}
        subtitle={`${data.patient.age} years · ${data.patient.gender} · ${data.patient.phone_number} · ${DEPARTMENT_LABEL[data.department]}`}
        actions={
          <>
            <Link href={`/patients/${data.patient.id}`}>
              <Button variant="outline" size="sm"><History /> Patient history</Button>
            </Link>
            {!reviewed && data.status === "completed" && (
              <Button size="sm" onClick={markReviewed} disabled={marking}>
                {marking ? <Loader2 className="animate-spin" /> : <CheckCircle2 />}
                Mark as seen
              </Button>
            )}
          </>
        }
      />

      <div className="min-w-0">
        {/* The clinical record is the single source of truth for this visit. */}
        <Tabs defaultValue={live ? "record" : "pad"}>
          <TabsList className="mb-4 w-fit justify-start overflow-x-auto">
              <TabsTrigger value="record">Record</TabsTrigger>
              <TabsTrigger value="pad">Visit Pad</TabsTrigger>
              <TabsTrigger value="forms">Certificates</TabsTrigger>
              <TabsTrigger value="prescriptions">Prescription</TabsTrigger>
              <TabsTrigger value="reports">
                <FlaskConical className="h-3.5 w-3.5" /> Reports brought
              </TabsTrigger>
              {/* An in-house bench this clinic may not have: the panel behind
                  this tab reads /lab, which is not served when the module is
                  off. Reports the patient brings in are a separate tab and
                  are always there. */}
              {hasLab && (
                <TabsTrigger value="lab">
                  <FlaskConical className="h-3.5 w-3.5" /> Lab results
                </TabsTrigger>
              )}
              <TabsTrigger value="transcript"><FileText className="h-3.5 w-3.5" /> Transcript</TabsTrigger>
          </TabsList>

            <TabsContent value="record" className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
              <Card>
                <CardHeader className="pb-3"><CardTitle>Presenting complaint</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                  {live && <p className="text-sm text-ink-muted">Intake is still in progress. The record will update as the conversation continues.</p>}
                  {!live && !record?.chief_complaint && <p className="text-sm text-ink-muted">No intake record — the patient did not complete the conversation.</p>}
                  <div className="divide-y divide-border rounded-xl border border-border px-3">
                    <InfoRow label="Chief complaint" value={record?.chief_complaint} />
                    <InfoRow label="Duration" value={record?.duration} />
                    <InfoRow label="Pain site" value={record?.pain?.location} />
                    <InfoRow label="Pain score" value={record?.pain?.score_out_of_10 != null ? `${record.pain.score_out_of_10} / 10` : undefined} />
                    <InfoRow label="Symptoms" value={record?.symptoms?.map((item) => item.name).join(", ")} />
                  </div>
                  <div className="rounded-xl border border-border px-3">
                    <p className="py-3 text-xs font-semibold uppercase tracking-wide text-ink-faint">Background</p>
                    <InfoRow label="Allergies" value={record?.allergies?.length ? record.allergies.join(", ") : "None reported"} />
                    <InfoRow label="Current medicines" value={record?.current_medicines?.length ? record.current_medicines.map((item) => item.name).join(", ") : "None reported"} />
                    <InfoRow label="Medical history" value={record?.medical_history?.length ? record.medical_history.join(", ") : "None reported"} />
                    <InfoRow label="Previous surgeries" value={record?.previous_surgeries?.length ? record.previous_surgeries.map((item) => item.name).join(", ") : "None reported"} />
                  </div>
                  {record?.red_flags && record.red_flags.length > 0 && (
                    <div className="rounded-xl border border-clay/30 bg-clay/[0.04] p-3">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-clay">Red flags</p>
                      <RedFlagList flags={record.red_flags} />
                    </div>
                  )}
                </CardContent>
              </Card>

              <div className="space-y-4">
                <Card>
                  <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                    <CardTitle>Key points from intake</CardTitle><AiBadge />
                  </CardHeader>
                  <CardContent>
                    {intakePoints.length > 0 ? (
                      <ul className="space-y-1.5 text-sm leading-snug text-ink">
                        {intakePoints.map((point) => (
                          <li key={point} className="flex min-w-0 items-start gap-2">
                            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-marigold-deep" />
                            <span className="min-w-0 whitespace-normal break-words">{point}</span>
                          </li>
                        ))}
                      </ul>
                    ) : <p className="text-sm text-ink-muted">No intake points recorded yet.</p>}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader className="pb-3"><CardTitle>Vitals</CardTitle></CardHeader>
                  <CardContent>
                    {vitals.length > 0 ? (
                      <div className="divide-y divide-border rounded-xl border border-border px-3">
                        {vitals.map(([label, value]) => <InfoRow key={label} label={label} value={value} />)}
                      </div>
                    ) : <p className="text-sm text-ink-muted">Not recorded yet.</p>}
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* The OCR analysis has existed for months with nowhere to
                appear. This is where the doctor finally sees it. */}
            <TabsContent value="pad">
              <VisitPad consultationId={data.id} />
            </TabsContent>

            <TabsContent value="forms">
              <PatientForms patientId={data.patient.id} consultationId={data.id} />
            </TabsContent>

            <TabsContent value="reports">
              <BroughtReports consultationId={data.id} />
            </TabsContent>

            {hasLab && (
              <TabsContent value="lab">
                <LabResultsPanel patientId={data.patient.id} />
              </TabsContent>
            )}

            <TabsContent value="transcript" className="h-[calc(100dvh-260px)] min-h-0 overflow-hidden">
              <TranscriptView turns={data.turns} className="h-full" />
            </TabsContent>


            <TabsContent value="prescriptions">
              <PrescriptionsTab
                patientId={data.patient.id}
                consultationId={data.id}
                department={data.department}
                prefill={{
                  diagnosis: dossier?.clinical_summary?.one_liner ?? record?.chief_complaint ?? null,
                  chiefComplaint: record?.chief_complaint ?? null,
                  investigations: (dossier?.investigations?.investigations ?? []).map(
                    (item) => item.test
                  ),
                }}
              />
            </TabsContent>
        </Tabs>
      </div>
    </>
  );
}
