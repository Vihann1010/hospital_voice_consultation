"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { RadiologyWorklist } from "@/components/radiology/radiology-worklist";

export default function RadiologyPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Radiology"
        subtitle="Imaging studies ordered and waiting for a report. Signing a report marks the study reported."
      />
      <RadiologyWorklist />
    </div>
  );
}
