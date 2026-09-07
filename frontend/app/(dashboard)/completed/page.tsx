"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { ConsultationList } from "@/components/dashboard/consultation-list";

export default function CompletedPage() {
  return (
    <>
      <PageHeader
        title="Completed consultations"
        subtitle="Visits you have already reviewed and signed off."
      />
      <ConsultationList
        filters={{ reviewed: true }}
        emptyTitle="No completed consultations yet"
        emptyDescription="Once you review a waiting patient and mark them as seen, the visit moves here."
      />
    </>
  );
}
