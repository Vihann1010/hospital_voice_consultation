"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { TheatreMasters } from "@/components/theatre/theatre-masters";

export default function TheatreSettingsPage() {
  return (
    <ModuleGate module="theatre">
      <div className="space-y-6">
        <PageHeader
          title="Operation list"
          subtitle="Theatres, operations, their usual duration and the price code they are billed under."
        />
        <TheatreMasters />
      </div>
    </ModuleGate>
  );
}
