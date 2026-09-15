"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { ClaimsWorkspace } from "@/components/insurance/claims-workspace";

export default function InsurancePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Insurance claims"
        subtitle="TPA and insurance cases from pre-authorisation to the payer's settlement."
      />
      <ClaimsWorkspace />
    </div>
  );
}
