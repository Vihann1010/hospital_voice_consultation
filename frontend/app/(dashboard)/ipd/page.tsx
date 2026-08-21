"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { WardBoardView } from "@/components/ipd/ward-board";

export default function WardBoardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Ward board"
        subtitle="Every bed, who is in it, and who needs attention."
      />
      <WardBoardView />
    </div>
  );
}
