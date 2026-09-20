"use client";

import { ModuleGate } from "@/components/dashboard/module-gate";
import { PageHeader } from "@/components/dashboard/page-header";
import { WardBoardView } from "@/components/ipd/ward-board";

export default function WardBoardPage() {
  return (
    <ModuleGate module="ipd">
      <div className="space-y-6">
        <PageHeader
          title="Ward board"
          subtitle="Every bed, who is in it, and who needs attention."
        />
        <WardBoardView />
      </div>
    </ModuleGate>
  );
}
