"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { ConsultationList } from "@/components/dashboard/consultation-list";

export default function WaitingPage() {
  return (
    <>
      <PageHeader
        title="Waiting patients"
        subtitle="Intake finished — these patients are waiting to be seen. Open one to review the AI briefing before calling them in."
      />
      <ConsultationList
        filters={{ status: "completed", reviewed: false }}
        emptyTitle="Nobody is waiting"
        emptyDescription="When a patient finishes their voice intake, they will appear here with a full clinical briefing ready."
        refreshMs={15000}
      />
    </>
  );
}
