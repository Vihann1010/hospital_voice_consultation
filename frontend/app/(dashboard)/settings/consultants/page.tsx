"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { ConsultantsAdmin } from "@/components/settings/consultants-admin";

export default function ConsultantsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Consultants"
        subtitle="The doctors the hospital schedules and bills for: OPD hours, fees, follow-up rules and registration."
      />
      <ConsultantsAdmin />
    </div>
  );
}
