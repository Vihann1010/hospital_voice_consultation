"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { TheatreMasters } from "@/components/theatre/theatre-masters";
import { useModules } from "@/components/dashboard/modules-provider";

export default function TheatreSettingsPage() {
  const { words } = useModules();
  return (
    <ModuleGate module="theatre">
      <div className="space-y-6">
        <PageHeader
          title={words.setup}
          subtitle={`${words.room}, what is done in them, their usual duration and the price code they are billed under.`}
        />
        <TheatreMasters />
      </div>
    </ModuleGate>
  );
}
