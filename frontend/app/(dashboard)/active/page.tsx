"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { ConsultationList } from "@/components/dashboard/consultation-list";

export default function ActivePage() {
  return (
    <>
      <PageHeader
        title="Current consultations"
        subtitle="Voice intake happening right now. The transcript updates as the conversation continues."
      />
      <ConsultationList
        filters={{ status: "in_progress" }}
        emptyTitle="No consultations in progress"
        emptyDescription="Live voice intakes appear here the moment a patient taps Start consultation."
        refreshMs={8000}
      />
    </>
  );
}
