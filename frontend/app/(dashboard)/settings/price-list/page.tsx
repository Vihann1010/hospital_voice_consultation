"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { PriceList } from "@/components/settings/price-list";
import { FinanceGate } from "@/components/accounts/finance-gate";
import { useAuth } from "@/components/dashboard/auth-provider";

export default function PriceListPage() {
  const { user } = useAuth();
  const canEdit = ["admin", "manager"].includes(user?.role ?? "");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Price list"
        subtitle="What each service costs at the counter. Bills already raised keep their old rate."
      />
      {canEdit ? (
        <FinanceGate>
          <PriceList canEdit />
        </FinanceGate>
      ) : (
        <PriceList canEdit={false} />
      )}
    </div>
  );
}
