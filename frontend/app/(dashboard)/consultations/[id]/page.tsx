"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardList,
  Clock,
  FileText,
  History,
  Loader2,
  FlaskConical,
  Pill,
  Ruler,
  User,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ConsultationDetail } from "@/lib/types";
import {
  DEPARTMENT_DOCTOR,
  DEPARTMENT_LABEL,
  duration,
  formatDateTime,
  initials,
  titleCase,
} from "@/lib/format";
import { PageHeader } from "@/components/dashboard/page-header";
import { RiskBadge, StatusBadge, TriageBadge, AiBadge } from "@/components/dashboard/badges";
import { CopilotPanel } from "@/components/dashboard/copilot-panel";
import { TranscriptView } from "@/components/dashboard/transcript-view";
import { VisitHistory } from "@/components/dashboard/visit-history";
import { InvestigationsTab } from "@/components/investigations/investigations-tab";
import { PrescriptionsTab } from "@/components/prescriptions/prescriptions-tab";
import {
  AllergiesCard,
  ConditionsCard,
  MedicinesCard,
  RedFlagList,
  SurgeriesCard,
  InfoRow,
} from "@/components/dashboard/clinical-blocks";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

export default function ConsultationDetailPage() {
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
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
          <Skeleton className="h-96 w-full rounded-xl" />
          <Skeleton className="h-96 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  const dossier = data.medical_json;
  const record = dossier?.medical_json;
  const risk = dossier?.risk_assessment;
  const summary = dossier?.clinical_summary;
  const reviewed = Boolean(dossier?.reviewed_at);
  const live = data.status === "in_progress";

  return (
    <>
      <Button variant="ghost" size="sm" className="mb-3 -ml-2" onClick={() => router.back()}>
        <ArrowLeft /> Back
      </Button>

      <PageHeader
        title={data.patient.name}
        subtitle={`${data.patient.age} years · ${data.patient.gender} · ${data.patient.phone_number}`}
        actions={
          <>
            <Link href={`/patients/${data.patient.id}`}>
              <Button variant="outline" size="sm">
                <History /> Patient history
              </Button>
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

      {/* Status strip */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="mb-6"
      >
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-mint font-display text-sm font-semibold text-pine">
                {initials(data.patient.name)}
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-faint">Department</p>
                <p className="text-sm font-semibold text-pine">
                  {DEPARTMENT_LABEL[data.department]}
                </p>
                <p className="text-xs text-ink-muted">{DEPARTMENT_DOCTOR[data.department]}</p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={data.status} reviewed={reviewed} />
              <RiskBadge risk={risk?.overall_risk} />
              <TriageBadge priority={risk?.triage_priority} />
              {risk?.emergency && (
                <Badge variant="danger" className="gap-1">
                  <AlertTriangle className="h-3 w-3" /> Emergency features
                </Badge>
              )}
            </div>

            <div className="ml-auto flex items-center gap-5 text-right">
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-faint">Started</p>
                <p className="tabular text-sm text-ink">{formatDateTime(data.started_at)}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-ink-faint">Duration</p>
                <p className="tabular text-sm text-ink">
                  {duration(data.started_at, data.ended_at)}
                </p>
              </div>
            </div>
          </div>

          {reviewed && dossier?.reviewed_by && (
            <p className="mt-3 border-t border-border pt-3 text-xs text-ink-muted">
              Reviewed by {dossier.reviewed_by.name} on {formatDateTime(dossier.reviewed_at)}
            </p>
          )}
          {live && (
            <p className="mt-3 flex items-center gap-2 border-t border-border pt-3 text-xs text-marigold-deep">
              <Activity className="h-3.5 w-3.5" />
              Intake is still in progress — this page refreshes automatically.
            </p>
          )}
        </Card>
      </motion.div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        {/* Left: the clinical record */}
        <div className="min-w-0">
          <Tabs defaultValue="summary">
            <TabsList className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="summary">
                <ClipboardList className="h-3.5 w-3.5" /> Summary
              </TabsTrigger>
              <TabsTrigger value="history">
                <User className="h-3.5 w-3.5" /> Medical history
              </TabsTrigger>
              <TabsTrigger value="transcript">
                <FileText className="h-3.5 w-3.5" /> Transcript
              </TabsTrigger>
              <TabsTrigger value="timeline">
                <Clock className="h-3.5 w-3.5" /> Visit history
              </TabsTrigger>
              <TabsTrigger value="investigations">
                <FlaskConical className="h-3.5 w-3.5" /> Investigations
              </TabsTrigger>
              <TabsTrigger value="prescriptions">
                <Pill className="h-3.5 w-3.5" /> Prescription
              </TabsTrigger>
            </TabsList>

            {/* --- AI summary --- */}
            <TabsContent value="summary" className="space-y-4">
              <Card>
                <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
                  <CardTitle>AI generated summary</CardTitle>
                  <AiBadge />
                </CardHeader>
                <CardContent className="space-y-4">
                  {summary?.one_liner && (
                    <p className="border-l-2 border-marigold pl-3 font-display text-[17px] font-semibold leading-snug text-pine">
                      {summary.one_liner}
                    </p>
                  )}
                  {summary?.history_of_present_illness && (
                    <div>
                      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">
                        History of present illness
                      </p>
                      <p className="text-sm leading-relaxed text-ink">
                        {summary.history_of_present_illness}
                      </p>
                    </div>
                  )}
                  <div className="grid gap-4 sm:grid-cols-2">
                    {summary?.pertinent_positives && summary.pertinent_positives.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-pine">
                          Pertinent positives
                        </p>
                        <ul className="space-y-1">
                          {summary.pertinent_positives.map((item) => (
                            <li key={item} className="flex gap-2 text-sm text-ink">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-pine/50" />
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {summary?.pertinent_negatives && summary.pertinent_negatives.length > 0 && (
                      <div>
                        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-muted">
                          Pertinent negatives
                        </p>
                        <ul className="space-y-1">
                          {summary.pertinent_negatives.map((item) => (
                            <li key={item} className="flex gap-2 text-sm text-ink-muted">
                              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-faint/50" />
                              {item}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                  {!summary?.one_liner && !summary?.history_of_present_illness && (
                    <p className="text-sm text-ink-faint">
                      {live
                        ? "The summary is generated once the intake conversation finishes."
                        : "No summary was generated for this visit."}
                    </p>
                  )}
                </CardContent>
              </Card>

              {record?.red_flags && record.red_flags.length > 0 && (
                <Card className="border-clay/35 bg-clay/[0.03]">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-clay">Red flags detected during intake</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <RedFlagList flags={record.red_flags} />
                  </CardContent>
                </Card>
              )}

              <Card>
                <CardHeader className="pb-3">
                  <CardTitle>Presenting complaint</CardTitle>
                </CardHeader>
                <CardContent className="divide-y divide-border">
                  <InfoRow label="Chief complaint" value={record?.chief_complaint} />
                  <InfoRow label="Duration" value={record?.duration} />
                  <InfoRow label="Pain site" value={record?.pain?.location} />
                  <InfoRow label="Pain character" value={record?.pain?.character} />
                  <InfoRow
                    label="Pain score"
                    value={
                      record?.pain?.score_out_of_10 !== undefined &&
                      record?.pain?.score_out_of_10 !== null
                        ? `${record.pain.score_out_of_10} / 10`
                        : undefined
                    }
                  />
                  <InfoRow label="Worse with" value={record?.pain?.aggravating_factors} />
                  <InfoRow label="Better with" value={record?.pain?.relieving_factors} />
                  {record?.symptoms && record.symptoms.length > 0 && (
                    <div className="py-2">
                      <p className="mb-2 text-xs uppercase tracking-wide text-ink-faint">Symptoms</p>
                      <div className="flex flex-wrap gap-1.5">
                        {record.symptoms.map((symptom, index) => (
                          <Badge key={`${symptom.name}-${index}`} variant="secondary">
                            {symptom.name}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* --- Medical history --- */}
            <TabsContent value="history" className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <AllergiesCard allergies={record?.allergies} />
                <MedicinesCard medicines={record?.current_medicines} />
                <ConditionsCard conditions={record?.medical_history} />
                <SurgeriesCard surgeries={record?.previous_surgeries} />
              </div>

              <Card>
                <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
                  <Ruler className="h-4 w-4 text-pine" />
                  <CardTitle>Measurements &amp; department findings</CardTitle>
                </CardHeader>
                <CardContent className="divide-y divide-border">
                  <InfoRow
                    label="Weight"
                    value={record?.weight_kg ? `${record.weight_kg} kg` : undefined}
                  />
                  <InfoRow
                    label="Height"
                    value={record?.height_cm ? `${record.height_cm} cm` : undefined}
                  />
                  {record?.department_specific &&
                    Object.entries(record.department_specific).map(([key, value]) =>
                      value === null || value === undefined || value === "" ? null : (
                        <InfoRow
                          key={key}
                          label={titleCase(key)}
                          value={typeof value === "object" ? JSON.stringify(value) : String(value)}
                        />
                      )
                    )}
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="transcript">
              <TranscriptView turns={data.turns} />
            </TabsContent>

            {/* --- Visit history --- */}
            <TabsContent value="timeline">
              <VisitHistory patientId={data.patient.id} currentConsultationId={data.id} />
            </TabsContent>

            <TabsContent value="investigations">
              <InvestigationsTab patientId={data.patient.id} consultationId={data.id} />
            </TabsContent>

            <TabsContent value="prescriptions">
              <PrescriptionsTab
                patientId={data.patient.id}
                consultationId={data.id}
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

        {/* Right: the copilot */}
        <div className="min-w-0">
          <div className="xl:sticky xl:top-6">
            <CopilotPanel consultationId={data.id} dossier={dossier} />
          </div>
        </div>
      </div>
    </>
  );
}
