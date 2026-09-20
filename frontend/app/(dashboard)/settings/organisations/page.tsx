"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { Organisations } from "@/components/settings/organisations";
import { useAuth } from "@/components/dashboard/auth-provider";

export default function OrganisationsPage() {
  const { user } = useAuth();

  return (
    <ModuleGate module="insurance">
      <div className="space-y-6">
        <PageHeader
          title="Insurers, TPAs and employers"
          subtitle="The payers a claim or a corporate bill can name, and the rates agreed with each."
        />
        <Organisations canEdit={["admin", "manager"].includes(user?.role ?? "")} />
      </div>
    </ModuleGate>
  );
}
