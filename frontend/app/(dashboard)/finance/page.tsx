"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { FinanceDashboard } from "@/components/finance/finance-dashboard";

export default function FinancePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Finance"
        subtitle="Collections, payment modes and cash reconciliation."
      />
      <FinanceDashboard />
    </div>
  );
}
