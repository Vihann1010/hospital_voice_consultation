"use client";

import { PageHeader } from "@/components/dashboard/page-header";
import { LayoutEditor } from "@/components/pad/layout-editor";

export default function PadLayoutsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Pad layouts"
        subtitle="The sections of each clinical document: their order, names, fields, and what prints."
      />
      <LayoutEditor />
    </div>
  );
}
