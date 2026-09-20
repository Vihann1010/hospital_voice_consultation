"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { WardsAndBeds } from "@/components/settings/wards-beds";
import { useAuth } from "@/components/dashboard/auth-provider";

export default function WardsPage() {
  const { user } = useAuth();

  return (
    <ModuleGate module="ipd">
      <div className="space-y-6">
        <PageHeader
          title="Wards and beds"
          subtitle="Wards, their nightly rates, and each bed — including taking a bed out of service."
        />
        <WardsAndBeds canEdit={["admin", "doctor"].includes(user?.role ?? "")} />
      </div>
    </ModuleGate>
  );
}
