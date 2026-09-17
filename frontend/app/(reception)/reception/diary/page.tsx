"use client";

import { PatientDiaryView } from "@/components/reception/patient-diary";

export default function DiaryPage() {
  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold text-pine">Patient diary</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Everything one patient has been charged and has paid — OPD, inpatient and
          advances, with a running balance.
        </p>
      </div>
      <PatientDiaryView />
    </div>
  );
}
