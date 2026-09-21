"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { FinanceDashboard } from "@/components/finance/finance-dashboard";
import { FinanceGate } from "@/components/accounts/finance-gate";

export default function FinancePage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Finance"
        subtitle="Collections, payment modes and cash reconciliation."
      />
      {/* The shared gate: it asks again when the unlock expires. This page
          used to carry its own copy, which did not. */}
      <FinanceGate prompt="Enter the four-digit PIN to continue." action="Open finance">
        <FinanceDashboard />
      </FinanceGate>
    </div>
  );
}
