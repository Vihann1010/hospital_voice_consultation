"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { KitchenSheet } from "@/components/diet/kitchen-sheet";

export default function DietSheetPage() {
  return (
    <ModuleGate module="diet">
      <div className="space-y-6">
        <PageHeader title="Diet sheet" subtitle="What each inpatient is served at every meal of the day." />
        <KitchenSheet />
      </div>
    </ModuleGate>
  );
}
