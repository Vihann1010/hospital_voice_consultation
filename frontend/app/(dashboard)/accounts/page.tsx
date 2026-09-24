"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { AccountsWorkspace } from "@/components/accounts/accounts-workspace";
import { FinanceGate } from "@/components/accounts/finance-gate";

export default function AccountsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Accounts"
        subtitle="Double-entry books kept from the counter's bills and receipts, and consultant payouts."
      />
      <FinanceGate>
        <AccountsWorkspace />
      </FinanceGate>
    </div>
  );
}
