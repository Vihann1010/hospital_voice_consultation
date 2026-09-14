"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, CalendarDays } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PatientHistory } from "@/lib/types";
import { DEPARTMENT_LABEL, formatDateTime, initials, timeAgo } from "@/lib/format";
import { PageHeader } from "@/components/dashboard/page-header";
import { RiskBadge, StatusBadge } from "@/components/dashboard/badges";
import {
  AllergiesCard,
  ConditionsCard,
  MedicinesCard,
  SurgeriesCard,
} from "@/components/dashboard/clinical-blocks";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/dashboard/empty-state";
import { PatientForms } from "@/components/pad/patient-forms";
import { PatientFiles } from "@/components/patient/patient-files";
import { LabResultsPanel } from "@/components/lab/lab-results-panel";

export default function PatientDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<PatientHistory | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    staffApi
      .patientHistory(params.id)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Could not load patient."));
  }, [params.id]);

  if (error) {
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
        <Skeleton className="h-24 w-full rounded-xl" />
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      </div>
    );
  }

  const { patient, summary, visits } = data;

  return (
    <>
      <Button variant="ghost" size="sm" className="mb-3 -ml-2" onClick={() => router.back()}>
        <ArrowLeft /> Back
      </Button>

      <PageHeader
        title={patient.name}
        subtitle={`${patient.age} years · ${patient.gender} · ${patient.phone_number}`}
      />

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <Card className="mb-6 bg-pine p-5 text-mint">
          <div className="flex items-center gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white/10 font-display text-base font-semibold">
              {initials(patient.name)}
            </div>
            <div className="grid flex-1 grid-cols-2 gap-4 sm:grid-cols-4">
              <div>
                <p className="tabular font-display text-2xl font-semibold">{summary.total_visits}</p>
                <p className="text-xs text-mint/60">Total visits</p>
              </div>
              <div>
                <p className="tabular font-display text-2xl font-semibold">
                  {summary.current_medicines.length}
                </p>
                <p className="text-xs text-mint/60">Medicines</p>
              </div>
              <div>
                <p className="tabular font-display text-2xl font-semibold">{summary.allergies.length}</p>
                <p className="text-xs text-mint/60">Allergies</p>
              </div>
              <div>
                <p className="tabular font-display text-2xl font-semibold">{summary.conditions.length}</p>
                <p className="text-xs text-mint/60">Conditions</p>
              </div>
            </div>
          </div>
        </Card>
      </motion.div>

      <div className="grid gap-4 lg:grid-cols-2">
        <AllergiesCard allergies={summary.allergies} />
        <MedicinesCard medicines={summary.current_medicines} />
        <ConditionsCard conditions={summary.conditions} />
        <SurgeriesCard surgeries={summary.previous_surgeries} />
      </div>

      <div className="mt-6">
        <PatientForms patientId={params.id} />
      </div>

      <div className="mt-6">
        <PatientFiles patientId={params.id} />
      </div>

      <div className="mt-6">
        <LabResultsPanel patientId={params.id} />
      </div>

      <Card className="mt-6">
        <CardHeader className="flex-row items-center gap-2 space-y-0">
          <CalendarDays className="h-4 w-4 text-pine" />
          <CardTitle>Visit timeline</CardTitle>
        </CardHeader>
        <CardContent>
          {visits.length === 0 ? (
            <EmptyState icon={CalendarDays} title="No visits recorded" />
          ) : (
            <ol className="relative space-y-4 border-l border-border pl-6">
              {visits.map((visit, index) => (
                <motion.li
                  key={visit.consultation_id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.18, delay: Math.min(index * 0.04, 0.3) }}
                  className="relative"
                >
                  <span className="absolute -left-[27px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-pine" />
                  <Link href={`/consultations/${visit.consultation_id}`} className="group block">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-pine group-hover:underline">
                        {DEPARTMENT_LABEL[visit.department]}
                      </span>
                      <StatusBadge status={visit.status} reviewed={null} />
                      <RiskBadge risk={visit.overall_risk} />
                    </div>
                    <p className="mt-1 text-sm text-ink">
                      {visit.one_liner ?? visit.chief_complaint ?? "No summary recorded"}
                    </p>
                    <p className="tabular mt-0.5 text-xs text-ink-faint">
                      {formatDateTime(visit.started_at)} · {timeAgo(visit.started_at)}
                    </p>
                  </Link>
                </motion.li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </>
  );
}
